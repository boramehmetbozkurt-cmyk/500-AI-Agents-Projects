from fastapi import APIRouter,Depends,Request
from app.ai_operating_layer_v10 import OperatingRequest,OperatingResult,orchestrate
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.stage_validation_ledger import record_stage
router=APIRouter(prefix="/v10/operate",tags=["v10-verifiable-ai-operating-layer"]);_OP=require_minimum_role("operator");_EV=require_minimum_role("evaluator")
@router.post("",response_model=OperatingResult)
def operate(body:OperatingRequest,request:Request,principal:Principal=Depends(_OP)):
 r=orchestrate(body,principal.workspace_id);record_stage(principal.workspace_id,"v10-ai-operating-layer",r.status,{"result_sha256":r.result_sha256,"selected_model_id":r.selected_model_id});STORE.record_audit(request_id=getattr(request.state,"request_id",body.request_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="v10_operate",status=r.status,metadata={"selected_model_id":r.selected_model_id,"result_sha256":r.result_sha256});return r
@router.get("/readiness")
def readiness(principal:Principal=Depends(_EV)):
 return {"release":"10.0","workspace_id":principal.workspace_id,"model_independent_candidate_selection":True,"evidence_verification":True,"governed_action_simulation":True,"effectseal_release_receipt":True,"temporal_reality_available":True,"distributed_verification_available":True,"direct_external_model_invocation":False,"universal_provider_certification":False,"production_cross_model_benchmark":False}
