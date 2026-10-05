from __future__ import annotations
import hashlib
from typing import Literal
from pydantic import BaseModel, Field
from app.crypto_core import canonical_json
from app.nli_verifier_v51 import NLI
from app.semantic_verifier_adapter import SEMANTIC_NLI

class EvidenceDocument(BaseModel):
    source_id:str=Field(min_length=1,max_length=200)
    text:str=Field(min_length=1,max_length=200000)
    url:str|None=Field(default=None,max_length=2000)
    observed_at:int|None=None
    authority:float=Field(default=.5,ge=0,le=1)

class ClaimCheck(BaseModel):
    claim:str
    verdict:Literal["SUPPORTED","CONTRADICTED","UNRESOLVED"]
    entailment:float;contradiction:float
    source_ids:list[str]
    verifier:str

class VerificationBundle(BaseModel):
    status:Literal["PASS","FAIL"]
    checks:list[ClaimCheck]
    evidence_sha256:str
    coverage:float
    contradiction_rate:float
    boundary:str="NLI verifies semantic support against supplied evidence text; source authenticity and factual truth require independent retrieval/attestation."

def verify_claims(claims:list[str],evidence:list[EvidenceDocument],minimum_entailment:float=.75,maximum_contradiction:float=.25,verifier=None)->VerificationBundle:
    verifier=verifier or SEMANTIC_NLI
    checks=[]
    for claim in claims:
        scored=[(d,verifier.score(claim,d.text)) for d in evidence]
        ent=[(d,v) for d,v in scored if v.entailment>=minimum_entailment]
        con=[(d,v) for d,v in scored if v.contradiction>maximum_contradiction]
        if con:
            d,v=max(con,key=lambda x:x[1].contradiction);verdict="CONTRADICTED";src=[x[0].source_id for x in con]
        elif ent:
            d,v=max(ent,key=lambda x:x[1].entailment);verdict="SUPPORTED";src=[x[0].source_id for x in ent]
        else:
            v=max((v for _,v in scored),key=lambda x:x.entailment,default=verifier.score(claim,""));verdict="UNRESOLVED";src=[]
        checks.append(ClaimCheck(claim=claim,verdict=verdict,entailment=v.entailment,contradiction=v.contradiction,source_ids=sorted(set(src)),verifier=v.verifier))
    supported=sum(c.verdict=="SUPPORTED" for c in checks);contradicted=sum(c.verdict=="CONTRADICTED" for c in checks)
    coverage=supported/max(1,len(checks));cr=contradicted/max(1,len(checks))
    digest=hashlib.sha256(canonical_json([d.model_dump(mode="json") for d in evidence])).hexdigest()
    return VerificationBundle(status="PASS" if checks and coverage==1.0 and contradicted==0 else "FAIL",checks=checks,evidence_sha256=digest,coverage=round(coverage,6),contradiction_rate=round(cr,6))
