from __future__ import annotations
import os
from fastapi import APIRouter,Depends,HTTPException,Request
from app.generalist_v5 import GeneralistEvaluationRequest,evaluate_generalist
from app.generalist_store_v5 import GENERALIST_V5_STORE
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.validation_evidence_v45 import VALIDATION_EVIDENCE,sha256

router=APIRouter(prefix="/v5/generalist",tags=["generalist-v5"])
_EVAL=require_minimum_role("evaluator")
_OPER=require_minimum_role("operator")

def _audit(request,principal,action,status,metadata):
    STORE.record_audit(request_id=getattr(request.state,"request_id","generalist-v5"),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action=action,status=status,metadata={"role":principal.role,**metadata})

@router.post("/evaluate")
def evaluate(body:GeneralistEvaluationRequest,request:Request,principal:Principal=Depends(_OPER))->dict:
    if GENERALIST_V5_STORE.get(principal.workspace_id,body.evaluation_id):
        raise HTTPException(status_code=409,detail="generalist_evaluation_id_exists")
    result=evaluate_generalist(body)
    stored=GENERALIST_V5_STORE.append(principal.workspace_id,result)
    commit=os.getenv("ORBYTHRA_RELEASE_SHA","0"*40)
    if len(commit)!=40 or any(ch not in "0123456789abcdef" for ch in commit.lower()): commit="0"*40
    validation=VALIDATION_EVIDENCE.append(principal.workspace_id,{
      "suite":"v5-generalist:"+body.evaluation_id,
      "commit_sha":commit.lower(),
      "configuration_sha256":sha256({"minimum_domains":body.minimum_domains,"minimum_success_rate":body.minimum_success_rate,"minimum_unseen_success_rate":body.minimum_unseen_success_rate,"minimum_evidence_coverage":body.minimum_evidence_coverage,"maximum_calibration_error":body.maximum_calibration_error}),
      "result":stored["status"],"total":stored["metrics"]["cases"],
      "passed":round(stored["metrics"]["success_rate"]*stored["metrics"]["cases"]),
      "failed":stored["metrics"]["cases"]-round(stored["metrics"]["success_rate"]*stored["metrics"]["cases"]),
      "artifact_sha256":stored["evaluation_sha256"],"external_validator":None})
    _audit(request,principal,"generalist_v5_evaluate",stored["status"],{"evaluation_id":body.evaluation_id,"evaluation_sha256":stored["evaluation_sha256"],"validation_evidence_sha256":validation["evidence_sha256"]})
    return {**stored,"validation_evidence_id":validation["evidence_id"],"validation_evidence_sha256":validation["evidence_sha256"]}

@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id:str,principal:Principal=Depends(_EVAL))->dict:
    item=GENERALIST_V5_STORE.get(principal.workspace_id,evaluation_id)
    if item is None: raise HTTPException(status_code=404,detail="generalist_evaluation_not_found")
    return item

@router.get("/ledger/verify")
def verify_ledger(principal:Principal=Depends(_EVAL))->dict:
    result=GENERALIST_V5_STORE.verify(principal.workspace_id)
    if not result["valid"]: raise HTTPException(status_code=409,detail={"code":"generalist_v5_ledger_invalid",**result})
    return result

@router.get("/readiness")
def readiness(principal:Principal=Depends(_EVAL))->dict:
    ledger=GENERALIST_V5_STORE.verify(principal.workspace_id)
    return {"release":"5.0","governed_generalist_evaluation":True,"cross_domain_unseen_task_measurement":True,"confidence_calibration":True,"evidence_coverage_gate":True,"transfer_measurement":True,"hash_chained_evaluation_ledger":True,"v45_validation_evidence_binding":True,"ledger_valid":ledger["valid"],"agi_claim":False,"human_level_general_intelligence_claim":False,"model_weight_self_training":False,"boundary":"V5 measures governed bounded generalization. It does not claim AGI, human-level general intelligence, or autonomous foundation-model self-training."}
