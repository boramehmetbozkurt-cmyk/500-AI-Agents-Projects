from __future__ import annotations
import hashlib, json, re, time
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from app.config import SETTINGS
from app.crypto_core import KEYRING, canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.nli_verifier_v51 import NLI

router=APIRouter(prefix="/v5.1/model-output",tags=["model-output-assurance"])
_REQUIRE_OPERATOR=require_minimum_role("operator");_REQUIRE_EVALUATOR=require_minimum_role("evaluator")
_URL=re.compile(r"^https?://",re.I)

class EvidenceRef(BaseModel):
    source_id:str=Field(min_length=1,max_length=200)
    url:str|None=Field(default=None,max_length=2000)
    supports:list[str]=Field(default_factory=list,max_length=200)
    contradicts:list[str]=Field(default_factory=list,max_length=200)
    observed_at:int|None=None
    text:str|None=Field(default=None,max_length=100000)
class OutputAssuranceRequest(BaseModel):
    request_id:str=Field(min_length=8,max_length=128)
    nonce:str=Field(min_length=16,max_length=256)
    model_id:str=Field(min_length=1,max_length=200)
    prompt:str=Field(min_length=1,max_length=100000)
    output:str=Field(min_length=1,max_length=200000)
    confidence:float=Field(ge=0,le=1)
    risk_tier:Literal["low","moderate","high","critical"]="moderate"
    evidence:list[EvidenceRef]=Field(default_factory=list,max_length=200)
    required_claims:list[str]=Field(default_factory=list,max_length=200)
    human_approved:bool=False
    minimum_evidence_coverage:float=Field(default=.8,ge=0,le=1)
    minimum_confidence:float=Field(default=.5,ge=0,le=1)
    maximum_evidence_age_seconds:int=Field(default=2592000,ge=60,le=31536000)
    expected_release_sha:str=Field(min_length=40,max_length=80)
    configuration_sha256:str=Field(min_length=64,max_length=64)
    @model_validator(mode="after")
    def unique_claims(self):
        if len(set(self.required_claims))!=len(self.required_claims):raise ValueError("duplicate_required_claims")
        return self
class Gate(BaseModel):name:str;passed:bool;detail:str
class ClaimVerdict(BaseModel):
    claim:str;status:Literal["SUPPORTED","CONTRADICTED","UNSUPPORTED"];supporting_sources:list[str];contradicting_sources:list[str]
    nli_label:Literal["ENTAILMENT","CONTRADICTION","NEUTRAL"];nli_entailment:float;nli_contradiction:float;nli_verifier:str
class OutputAssuranceResponse(BaseModel):
    request_id:str;status:Literal["PASS","REVIEW","FAIL"];release_output:bool;output:str|None
    output_sha256:str;evidence_coverage:float;claim_verdicts:list[ClaimVerdict];gates:list[Gate]
    evidence_manifest_sha256:str;release_sha:str;configuration_sha256:str
    boundary:str="Platform gates validate supplied evidence bindings, freshness and contradictions; they do not independently fetch sources or prove factual truth; NLI is a verification signal, not an oracle."

def _sha(v:Any)->str:return hashlib.sha256(canonical_json(v)).hexdigest()
def _claims(body):
    out=[]
    for c in body.required_claims:
        sup=sorted({e.source_id for e in body.evidence if c in e.supports});con=sorted({e.source_id for e in body.evidence if c in e.contradicts})
        scored=[NLI.score(c,e.text) for e in body.evidence if e.text]
        best=max(scored,key=lambda x:max(x.entailment,x.contradiction)) if scored else NLI.score(c,"")
        if best.label=="CONTRADICTION": con=sorted(set(con)|{e.source_id for e in body.evidence if e.text and NLI.score(c,e.text).label=="CONTRADICTION"})
        nli_sup=[e.source_id for e in body.evidence if e.text and NLI.score(c,e.text).label=="ENTAILMENT"]
        sup=sorted(set(sup)|set(nli_sup))
        st="CONTRADICTED" if con else ("SUPPORTED" if sup and best.label!="NEUTRAL" else "UNSUPPORTED")
        out.append(ClaimVerdict(claim=c,status=st,supporting_sources=sup,contradicting_sources=con,nli_label=best.label,nli_entailment=best.entailment,nli_contradiction=best.contradiction,nli_verifier=best.verifier))
    return out

@router.post("/evaluate",response_model=OutputAssuranceResponse)
def evaluate(body:OutputAssuranceRequest,request:Request,principal:Principal=Depends(_REQUIRE_OPERATOR)):
    if not SETTINGS.release_sha or body.expected_release_sha!=SETTINGS.release_sha:raise HTTPException(409,"release_sha_mismatch")
    replay=_sha({"request_id":body.request_id,"nonce":body.nonce,"release":body.expected_release_sha})
    if not STORE.reserve_crypto_nonce(workspace_id=principal.workspace_id,nonce_fingerprint="model-output:"+replay,expires_at=int(time.time())+86400):raise HTTPException(409,"model_output_replay_detected")
    cv=_claims(body);supported=sum(x.status=="SUPPORTED" for x in cv);coverage=supported/len(cv) if cv else (1.0 if body.evidence else 0.0)
    now=int(time.time());fresh=all(e.observed_at is None or 0<=now-e.observed_at<=body.maximum_evidence_age_seconds for e in body.evidence)
    no_contradictions=all(x.status!="CONTRADICTED" for x in cv);all_claims=all(x.status=="SUPPORTED" for x in cv) if cv else bool(body.evidence)
    gates=[
      Gate(name="confidence",passed=body.confidence>=body.minimum_confidence,detail=f"{body.confidence:.3f} >= {body.minimum_confidence:.3f}"),
      Gate(name="evidence_present",passed=bool(body.evidence),detail=f"{len(body.evidence)} evidence references"),
      Gate(name="claim_support",passed=all_claims,detail=f"{supported}/{len(cv)} required claims supported"),
      Gate(name="evidence_coverage",passed=coverage>=body.minimum_evidence_coverage,detail=f"{coverage:.3f} >= {body.minimum_evidence_coverage:.3f}"),
      Gate(name="nli_verifier",passed=all(x.nli_label=="ENTAILMENT" for x in cv) if cv else False,detail="required claims must be entailed by supplied evidence text"),
      Gate(name="no_contradictions",passed=no_contradictions,detail="no supplied evidence contradicts required claims"),
      Gate(name="evidence_freshness",passed=fresh,detail=f"evidence age <= {body.maximum_evidence_age_seconds}s when timestamps supplied"),
      Gate(name="source_url_shape",passed=all(e.url is None or bool(_URL.match(e.url)) for e in body.evidence),detail="source URLs are HTTP(S) when present"),
      Gate(name="release_binding",passed=True,detail=body.expected_release_sha),
      Gate(name="high_risk_human_approval",passed=body.risk_tier not in {"high","critical"} or body.human_approved,detail="human approval required for high/critical risk")]
    failed=[g.name for g in gates if not g.passed];status="PASS" if not failed else ("REVIEW" if failed==["high_risk_human_approval"] else "FAIL")
    output_sha=hashlib.sha256(body.output.encode()).hexdigest()
    manifest={"request_id":body.request_id,"model_id":body.model_id,"output_sha256":output_sha,"release_sha":body.expected_release_sha,"configuration_sha256":body.configuration_sha256,"evidence":[e.model_dump(mode="json") for e in body.evidence],"claim_verdicts":[x.model_dump() for x in cv],"status":status}
    manifest_sha=_sha(manifest)
    STORE.record_audit(request_id=getattr(request.state,"request_id",body.request_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="model_output_assurance_v2",status=status,metadata={"manifest_sha256":manifest_sha,"output_sha256":output_sha,"failed_gates":failed,"release_sha":body.expected_release_sha,"configuration_sha256":body.configuration_sha256})
    return OutputAssuranceResponse(request_id=body.request_id,status=status,release_output=status=="PASS",output=body.output if status=="PASS" else None,output_sha256=output_sha,evidence_coverage=round(coverage,6),claim_verdicts=cv,gates=gates,evidence_manifest_sha256=manifest_sha,release_sha=body.expected_release_sha,configuration_sha256=body.configuration_sha256)

@router.get("/readiness")
def readiness(principal:Principal=Depends(_REQUIRE_EVALUATOR))->dict[str,Any]:
    return {"release":"5.1","workspace_id":principal.workspace_id,"model_output_assurance_v2":True,"fail_closed_output_release":True,"claim_level_verdicts":True,"deterministic_nli_baseline":True,"external_llm_nli_adapter":False,"nli_fail_closed":True,"contradiction_gate":True,"freshness_gate":True,"replay_protection":True,"exact_release_binding":True,"configuration_binding":True,"audit_manifest_hash":True,"external_source_fetching":False,"factual_truth_claim":False,"independent_validation_claim":False}
