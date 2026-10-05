from __future__ import annotations
import hashlib
from typing import Literal
from pydantic import BaseModel,Field
from app.crypto_core import canonical_json
class CognitiveTask(BaseModel):
 task_id:str=Field(min_length=1,max_length=120);domain:str=Field(min_length=1,max_length=120);description:str=Field(min_length=1,max_length=4000)
 known_skill_ids:list[str]=Field(default_factory=list,max_length=50);evidence_ids:list[str]=Field(default_factory=list,max_length=100)
 novelty:float=Field(ge=0,le=1);risk:Literal["low","moderate","high","critical"]="moderate"
class SkillHypothesis(BaseModel):
 skill_id:str;procedure:list[str]=Field(min_length=1,max_length=30);source_domains:list[str]=Field(default_factory=list);confidence:float=Field(ge=0,le=1)
class CognitiveDecision(BaseModel):
 status:Literal["EXECUTE","LEARN","REVIEW","BLOCK"];task_id:str;strategy:str;uncertainty:float;knowledge_gap:bool;skill_hypothesis:SkillHypothesis|None=None;reason_codes:list[str];decision_sha256:str
def decide(t:CognitiveTask,confidence:float,evidence_coverage:float)->CognitiveDecision:
 reasons=[];gap=not t.known_skill_ids or t.novelty>=.65
 if gap:reasons.append("knowledge_or_skill_gap")
 uncertainty=round(max(1-confidence,1-evidence_coverage,t.novelty*.5),6)
 if t.risk=="critical":status="BLOCK";reasons.append("critical_risk_requires_external_governance")
 elif uncertainty>.45:status="REVIEW";reasons.append("uncertainty_above_autonomy_ceiling")
 elif gap:
  status="LEARN";reasons.append("bounded_skill_acquisition_required")
 else:status="EXECUTE";reasons.append("known_skill_within_uncertainty_ceiling")
 h=None
 if status=="LEARN":
  sid="skill-"+hashlib.sha256(canonical_json({"domain":t.domain,"description":t.description})).hexdigest()[:16]
  h=SkillHypothesis(skill_id=sid,procedure=["decompose_task","retrieve_evidence","attempt_bounded_solution","verify_outcome","retain_only_if_regression_safe"],source_domains=sorted(set([t.domain])),confidence=round(max(0,min(confidence,evidence_coverage)),6))
 payload={"task_id":t.task_id,"status":status,"strategy":"bounded-general-cognitive-routing","uncertainty":uncertainty,"knowledge_gap":gap,"skill_hypothesis":h.model_dump(mode="json") if h else None,"reason_codes":reasons}
 return CognitiveDecision(**payload,decision_sha256=hashlib.sha256(canonical_json(payload)).hexdigest())
