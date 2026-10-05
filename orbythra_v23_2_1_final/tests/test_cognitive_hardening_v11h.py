from app.general_cognitive_core_v11h import CognitiveTask,decide
from app.metacognition_v11h import MetaAssessment,assess
def task(**k):return CognitiveTask(task_id=k.get("task_id","t"),domain=k.get("domain","novel"),description=k.get("description","solve unseen structured task"),known_skill_ids=k.get("known_skill_ids",[]),novelty=k.get("novelty",.8),risk=k.get("risk","moderate"))
def test_novel_task_does_not_blindly_execute():assert decide(task(),.9,.9).status=="LEARN"
def test_high_uncertainty_escalates():assert decide(task(known_skill_ids=["s"],novelty=.1),.4,.9).status=="REVIEW"
def test_critical_task_blocks():assert decide(task(risk="critical"),.99,.99).status=="BLOCK"
def test_skill_hypothesis_deterministic():
 a=decide(task(),.9,.9);b=decide(task(),.9,.9);assert a.skill_hypothesis.skill_id==b.skill_hypothesis.skill_id and a.decision_sha256==b.decision_sha256
def test_metacognition_knows_unknown():assert assess(MetaAssessment(confidence=.4,evidence_coverage=.9,contradiction_rate=0,recent_failure_rate=0,distribution_shift=0))["knows_unknown"]
def test_metacognition_replans_on_shift():assert assess(MetaAssessment(confidence=.9,evidence_coverage=.9,contradiction_rate=0,recent_failure_rate=0,distribution_shift=.5))["status"]=="REPLAN"
