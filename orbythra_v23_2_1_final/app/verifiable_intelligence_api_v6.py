from __future__ import annotations
import hashlib
from typing import Any
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,Field
from app.config import SETTINGS
from app.crypto_core import canonical_json,seal
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.stage_validation_ledger import record_stage
from app.verifiable_intelligence_v6 import EvidenceDocument,VerificationBundle,verify_claims

router=APIRouter(prefix="/v6/verifiable-intelligence",tags=["v6-verifiable-intelligence"])
_OP=require_minimum_role("operator");_EV=require_minimum_role("evaluator")

class VerifyRequest(BaseModel):
    request_id:str=Field(min_length=8,max_length=128)
    claims:list[str]=Field(min_length=1,max_length=200)
    evidence:list[EvidenceDocument]=Field(min_length=1,max_length=200)
    minimum_entailment:float=Field(default=.75,ge=.5,le=1)
    maximum_contradiction:float=Field(default=.25,ge=0,le=.5)
class VerifyResponse(BaseModel):
    request_id:str;release:str;verification:VerificationBundle;receipt:dict[str,Any];receipt_sha256:str
    factual_truth_claim:bool=False;independent_validation_claim:bool=False

@router.post("/verify",response_model=VerifyResponse)
def verify(body:VerifyRequest,request:Request,principal:Principal=Depends(_OP)):
    result=verify_claims(body.claims,body.evidence,body.minimum_entailment,body.maximum_contradiction)
    payload={"schema":"orbythra.verifiable-intelligence.v6","request_id":body.request_id,"workspace_id":principal.workspace_id,"release":"6.0","verification":result.model_dump(mode="json")}
    receipt=seal(payload=payload,intent={"action":"verify-ai-claims","asset":body.request_id},effect={"action":"verify-ai-claims","asset":body.request_id},approvals=[],min_approvals=0,workspace_id=principal.workspace_id,domain="v6-verification-receipt",ttl_seconds=0)
    receipt_sha=hashlib.sha256(canonical_json(receipt)).hexdigest()
    record_stage(principal.workspace_id,"v6-verifiable-intelligence",result.status,{"receipt_sha256":receipt_sha,"evidence_sha256":result.evidence_sha256})
    STORE.record_audit(request_id=getattr(request.state,"request_id",body.request_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="v6_verifiable_intelligence",status=result.status,metadata={"receipt_sha256":receipt_sha,"evidence_sha256":result.evidence_sha256,"claims":len(body.claims)})
    return VerifyResponse(request_id=body.request_id,release="6.0",verification=result,receipt=receipt,receipt_sha256=receipt_sha)

@router.get("/readiness")
def readiness(principal:Principal=Depends(_EV))->dict[str,Any]:
    return {"release":"6.0","workspace_id":principal.workspace_id,"claim_evidence_verification":True,"contradiction_fail_closed":True,"evidence_content_binding":True,"signed_verification_receipt":True,"web_source_retrieval_available":True,"deterministic_nli_baseline":True,"external_llm_nli_adapter":False,"factual_truth_claim":False,"independent_validation_claim":False,"release_sha":SETTINGS.release_sha}
