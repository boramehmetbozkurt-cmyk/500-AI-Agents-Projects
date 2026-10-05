from __future__ import annotations
from pydantic import BaseModel,Field
class MetaAssessment(BaseModel):
 confidence:float=Field(ge=0,le=1);evidence_coverage:float=Field(ge=0,le=1);contradiction_rate:float=Field(ge=0,le=1);recent_failure_rate:float=Field(ge=0,le=1);distribution_shift:float=Field(ge=0,le=1)
def assess(x:MetaAssessment)->dict:
 uncertainty=max(1-x.confidence,1-x.evidence_coverage,x.contradiction_rate,x.recent_failure_rate,x.distribution_shift)
 knows_unknown=uncertainty>=.35
 change_strategy=x.recent_failure_rate>=.25 or x.distribution_shift>=.4 or x.contradiction_rate>=.2
 abstain=uncertainty>=.6
 return {"uncertainty":round(uncertainty,6),"knows_unknown":knows_unknown,"change_strategy":change_strategy,"abstain":abstain,"status":"REVIEW" if abstain else ("REPLAN" if change_strategy else "CONTINUE"),"boundary":"Deterministic metacognitive control signals; not consciousness or human self-awareness."}
