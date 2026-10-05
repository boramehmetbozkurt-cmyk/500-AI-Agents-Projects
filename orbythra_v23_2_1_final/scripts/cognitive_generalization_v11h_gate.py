from app.general_cognitive_core_v11h import CognitiveTask,decide
from app.metacognition_v11h import MetaAssessment,assess
DOMAINS=["math","code","science","planning","language","systems"]
def run():
 rows=[]
 for i,d in enumerate(DOMAINS):
  x=CognitiveTask(task_id=f"hidden-{i}",domain=d,description=f"unseen rule adaptation task {i}",known_skill_ids=[] if i%2==0 else ["transfer-base"],novelty=.75 if i%2==0 else .35,risk="moderate")
  r=decide(x,.88,.9);rows.append(r.status in {"LEARN","EXECUTE"} and r.status!="BLOCK")
 m=assess(MetaAssessment(confidence=.85,evidence_coverage=.9,contradiction_rate=.05,recent_failure_rate=.3,distribution_shift=.45))
 report={"schema":"orbythra.cognitive-generalization.v11h","domains":len(DOMAINS),"unseen_task_safe_route_rate":sum(rows)/len(rows),"metacognitive_replan":m["status"]=="REPLAN","agi_claim":False,"boundary":"Internal synthetic unseen-task routing benchmark; does not demonstrate AGI or human-level performance."}
 if report["unseen_task_safe_route_rate"]<1 or not report["metacognitive_replan"]:raise SystemExit(str(report))
 return report
if __name__=="__main__":
 import json;print(json.dumps(run(),indent=2))
