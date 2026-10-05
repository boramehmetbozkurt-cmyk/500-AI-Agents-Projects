from fastapi import APIRouter,Depends,Request
from app.causal_intelligence_v11 import CausalRequest,CausalResult,evaluate
from app.security import Principal,require_minimum_role
from app.store import STORE
from app.stage_validation_ledger import record_stage
router=APIRouter(prefix="/v11/causal",tags=["v11-causal-intelligence"]);_OP=require_minimum_role("operator");_EV=require_minimum_role("evaluator")
@router.post("/evaluate",response_model=CausalResult)
def causal(body:CausalRequest,request:Request,principal:Principal=Depends(_OP)):
 r=evaluate(body,principal.workspace_id);record_stage(principal.workspace_id,"v11-causal-intelligence",r.status,{"graph_sha256":r.graph_sha256,"evidence_sha256":r.evidence_sha256});STORE.record_audit(request_id=getattr(request.state,"request_id",body.request_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="v11_causal_evaluation",status=r.status,metadata={"graph_sha256":r.graph_sha256,"evidence_sha256":r.evidence_sha256});return r
@router.get("/readiness")
def readiness(principal:Principal=Depends(_EV)):
 return {"release":"11.0","workspace_id":principal.workspace_id,"causal_dag_validation":True,"evidence_gated_edges":True,"confounder_gate":True,"intervention_hypothesis":True,"counterfactual_hypothesis":True,"signed_causal_receipt":True,"temporal_engine_available":True,"randomized_experiment_execution":False,"automatic_causal_discovery":False,"real_world_causality_claim":False}
