from __future__ import annotations
import os
from fastapi import APIRouter,Depends,HTTPException,Request
from app.blind_challenge_v5 import BlindChallengeRequest,execute_blind_challenge
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.validation_evidence_v45 import VALIDATION_EVIDENCE,sha256

router=APIRouter(prefix="/v5/validation",tags=["validation-v5"])
_OPER=require_minimum_role("operator")
_EVAL=require_minimum_role("evaluator")

@router.post("/blind-challenges/execute")
def execute(body:BlindChallengeRequest,request:Request,principal:Principal=Depends(_OPER))->dict:
 current=os.getenv("ORBYTHRA_RELEASE_SHA","").strip().lower()
 if len(current)!=40 or any(c not in "0123456789abcdef" for c in current):
  raise HTTPException(status_code=503,detail="release_sha_not_configured")
 result=execute_blind_challenge(body,current)
 if result["status"]=="REJECTED":
  raise HTTPException(status_code=409,detail=result)
 metrics=result["result"]["metrics"]; total=metrics["cases"]; passed=round(metrics["success_rate"]*total); failed=total-passed
 ev=VALIDATION_EVIDENCE.append(principal.workspace_id,{"suite":"blind-challenge:"+body.challenge_id,"commit_sha":current,"configuration_sha256":sha256({"minimum_domains":body.minimum_domains}),"result":result["status"],"total":total,"passed":passed,"failed":failed,"artifact_sha256":result["manifest_sha256"],"external_validator":body.validator_id})
 STORE.record_audit(request_id=getattr(request.state,"request_id","blind-v5"),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="blind_challenge_v5_execute",status=result["status"],metadata={"validator_id":body.validator_id,"manifest_sha256":result["manifest_sha256"],"evidence_sha256":ev["evidence_sha256"]})
 return {**result,"validation_evidence_id":ev["evidence_id"],"validation_evidence_sha256":ev["evidence_sha256"]}

@router.get("/release-readiness")
def release_readiness(principal:Principal=Depends(_EVAL))->dict:
 current=os.getenv("ORBYTHRA_RELEASE_SHA","").strip().lower()
 entries=VALIDATION_EVIDENCE.list(principal.workspace_id)
 matching=[e for e in entries if e["commit_sha"]==current and e["result"]=="PASS"]
 blind=[e for e in matching if str(e["suite"]).startswith("blind-challenge:") and e.get("external_validator")]
 return {"commit_sha":current,"ledger":VALIDATION_EVIDENCE.verify(principal.workspace_id),"current_release_pass_evidence":len(matching),"current_release_blind_evidence":len(blind),"release_validated":bool(blind),"independent_validation_claim":False,"boundary":"A passing blind-challenge record is protocol evidence only. Independence must be established by the external validator's identity, custody and procedure."}
