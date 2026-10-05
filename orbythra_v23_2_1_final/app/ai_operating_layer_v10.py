from __future__ import annotations
import hashlib
from typing import Any,Literal
from pydantic import BaseModel,Field
from app.crypto_core import canonical_json,seal
from app.governed_agents_v7 import SimulationRequest,simulate
from app.verifiable_intelligence_v6 import EvidenceDocument,verify_claims
class ModelCandidate(BaseModel):
 model_id:str=Field(min_length=1,max_length=200);output:str=Field(min_length=1,max_length=100000);confidence:float=Field(ge=0,le=1)
class OperatingRequest(BaseModel):
 request_id:str=Field(min_length=8,max_length=128);prompt:str=Field(min_length=1,max_length=100000);claims:list[str]=Field(min_length=1,max_length=200);evidence:list[EvidenceDocument]=Field(min_length=1,max_length=200);candidates:list[ModelCandidate]=Field(min_length=1,max_length=20)
 action:SimulationRequest|None=None;minimum_confidence:float=Field(default=.7,ge=0,le=1)
class OperatingResult(BaseModel):
 status:Literal["PASS","REVIEW","FAIL"];selected_model_id:str|None;verification_status:str;action_decision:str|None;receipt:dict[str,Any]|None;result_sha256:str;boundary:str
def orchestrate(x:OperatingRequest,workspace_id:str)->OperatingResult:
 verification=verify_claims(x.claims,x.evidence)
 eligible=[c for c in x.candidates if c.confidence>=x.minimum_confidence]
 eligible.sort(key=lambda c:(-c.confidence,c.model_id))
 selected=eligible[0] if eligible else None
 action_result=simulate(x.action) if x.action else None
 if verification.status!="PASS" or not selected or (action_result and action_result.decision=="BLOCK"):status="FAIL"
 elif action_result and action_result.decision=="REVIEW":status="REVIEW"
 else:status="PASS"
 core={"schema":"orbythra.ai-operating-layer.v10","request_id":x.request_id,"selected_model_id":selected.model_id if selected else None,"verification_status":verification.status,"evidence_sha256":verification.evidence_sha256,"action_decision":action_result.decision if action_result else None,"status":status}
 digest=hashlib.sha256(canonical_json(core)).hexdigest()
 receipt=None
 if status=="PASS":
  receipt=seal(payload={**core,"result_sha256":digest},intent={"action":"release-ai-result","asset":x.request_id},effect={"action":"release-ai-result","asset":x.request_id},approvals=[],min_approvals=0,workspace_id=workspace_id,domain="v10-ai-operating-receipt",ttl_seconds=0)
 return OperatingResult(status=status,selected_model_id=core["selected_model_id"],verification_status=verification.status,action_decision=core["action_decision"],receipt=receipt,result_sha256=digest,boundary="Model-independent orchestration over supplied candidates; it does not itself invoke or certify external foundation models.")
