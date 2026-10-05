from __future__ import annotations
import hashlib
from typing import Any,Literal
from pydantic import BaseModel,Field
from app.crypto_core import canonical_json

RISK={"low":0,"moderate":1,"high":2,"critical":3}
class SimulationRequest(BaseModel):
    action_id:str=Field(min_length=1,max_length=128);operation:str=Field(min_length=1,max_length=200)
    intended_effect:dict[str,Any];predicted_effect:dict[str,Any]
    risk_tier:Literal["low","moderate","high","critical"]="moderate"
    reversible:bool=True;rollback_plan:dict[str,Any]|None=None
    blast_radius:int=Field(default=1,ge=1,le=10000)
class SimulationResult(BaseModel):
    decision:Literal["ALLOW","REVIEW","BLOCK"];effective_risk:str;effect_match:bool;rollback_ready:bool
    reasons:list[str];simulation_sha256:str

def simulate(x:SimulationRequest)->SimulationResult:
    match=canonical_json(x.intended_effect)==canonical_json(x.predicted_effect)
    rollback_ready=x.reversible and bool(x.rollback_plan)
    risk=RISK[x.risk_tier]
    if x.blast_radius>100:risk=max(risk,2)
    if x.blast_radius>1000:risk=3
    effective=next(k for k,v in RISK.items() if v==risk)
    reasons=[]
    if not match:reasons.append("predicted_effect_mismatch")
    if x.reversible and not rollback_ready:reasons.append("rollback_plan_required")
    if risk>=3:reasons.append("critical_risk_requires_human_escalation")
    decision="BLOCK" if not match else ("REVIEW" if reasons else "ALLOW")
    digest=hashlib.sha256(canonical_json({"request":x.model_dump(mode="json"),"decision":decision,"effective_risk":effective,"reasons":reasons})).hexdigest()
    return SimulationResult(decision=decision,effective_risk=effective,effect_match=match,rollback_ready=rollback_ready,reasons=reasons or ["simulation_policy_satisfied"],simulation_sha256=digest)

def recovery_plan(*,action_id:str,reason:str,rollback_plan:dict[str,Any]|None)->dict[str,Any]:
    plan={"action_id":action_id,"state":"CONTAINED","reason":reason,"rollback":rollback_plan,"steps":["contain","rollback" if rollback_plan else "manual_review","revalidate","resume_only_after_pass"]}
    return {**plan,"recovery_sha256":hashlib.sha256(canonical_json(plan)).hexdigest()}
