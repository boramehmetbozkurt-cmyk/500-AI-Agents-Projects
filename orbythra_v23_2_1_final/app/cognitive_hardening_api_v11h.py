from fastapi import APIRouter,Depends
from pydantic import BaseModel
from app.security import Principal,require_minimum_role
from app.general_cognitive_core_v11h import CognitiveTask,decide
from app.metacognition_v11h import MetaAssessment,assess
router=APIRouter(prefix="/v11h/cognitive",tags=["cognitive-hardening"]);_EV=require_minimum_role("evaluator")
class DecisionRequest(BaseModel):task:CognitiveTask;confidence:float;evidence_coverage:float
@router.post("/decide")
def decision(x:DecisionRequest,principal:Principal=Depends(_EV)):return decide(x.task,x.confidence,x.evidence_coverage)
@router.post("/metacognition")
def meta(x:MetaAssessment,principal:Principal=Depends(_EV)):return assess(x)
@router.get("/readiness")
def ready(principal:Principal=Depends(_EV)):return {"novel_task_detection":True,"bounded_skill_hypothesis":True,"uncertainty_estimation":True,"knowledge_gap_detection":True,"strategy_change_signal":True,"cross_domain_transfer_measurement":True,"forgetting_gate":True,"human_level_general_intelligence":False,"agi_claim":False}
