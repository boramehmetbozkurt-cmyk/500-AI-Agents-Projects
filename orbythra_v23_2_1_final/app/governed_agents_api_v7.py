from __future__ import annotations
from typing import Any
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,Field
from app.governed_agents_v7 import SimulationRequest,SimulationResult,recovery_plan,simulate
from app.security import Principal,require_minimum_role
from app.store import STORE
router=APIRouter(prefix="/v7/agents",tags=["v7-governed-agents"]);_OP=require_minimum_role("operator");_EV=require_minimum_role("evaluator")
class RecoveryRequest(BaseModel):
 action_id:str=Field(min_length=1,max_length=128);reason:str=Field(min_length=1,max_length=1000);rollback_plan:dict[str,Any]|None=None
@router.post("/simulate",response_model=SimulationResult)
def simulation(body:SimulationRequest,request:Request,principal:Principal=Depends(_OP)):
 r=simulate(body);STORE.record_audit(request_id=getattr(request.state,"request_id",body.action_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="v7_agent_simulation",status=r.decision,metadata={"simulation_sha256":r.simulation_sha256,"effective_risk":r.effective_risk});return r
@router.post("/recovery")
def recovery(body:RecoveryRequest,request:Request,principal:Principal=Depends(_OP))->dict[str,Any]:
 r=recovery_plan(action_id=body.action_id,reason=body.reason,rollback_plan=body.rollback_plan);STORE.record_audit(request_id=getattr(request.state,"request_id",body.action_id),principal_id=principal.principal_id,workspace_id=principal.workspace_id,action="v7_agent_recovery",status="CONTAINED",metadata={"recovery_sha256":r["recovery_sha256"]});return r
@router.get("/readiness")
def readiness(principal:Principal=Depends(_EV))->dict[str,Any]:
 return {"release":"7.0","workspace_id":principal.workspace_id,"pre_execution_simulation":True,"dynamic_blast_radius_risk":True,"rollback_recovery_planning":True,"existing_v2_policy_revalidation":True,"existing_effectseal_authorization":True,"existing_outcome_verification":True,"existing_multi_agent_supervision":True,"live_tool_sandbox_execution":False,"independent_agentic_security_validation":False,"claim":"Governed autonomous-agent control plane; no claim of unsupervised production autonomy."}
