from __future__ import annotations
import json
from app.generalist_v5 import GeneralistEvaluationRequest,evaluate_generalist

def main():
 cases=[]
 domains=["engineering","finance","operations","security","research"]
 for i in range(500):
  success=(i%20)!=0
  cases.append({"case_id":f"frozen-{i:04d}","domain":domains[i%len(domains)],"unseen":True,"success":success,"evidence_coverage":0.95,"confidence":0.9 if success else 0.1,"transferred_skill":i>=400})
 body=GeneralistEvaluationRequest(evaluation_id="frozen-v5-ci",cases=cases,minimum_domains=5,minimum_success_rate=.90,minimum_unseen_success_rate=.90,minimum_evidence_coverage=.90,maximum_calibration_error=.15)
 result=evaluate_generalist(body)
 print(json.dumps(result,sort_keys=True))
 if not result["generalist_ready"]: raise SystemExit(1)
 if result["metrics"]["transfer_success_rate"] is None or result["metrics"]["transfer_success_rate"]<.90: raise SystemExit(1)
 if result["boundary"].lower().find("not proof of agi")<0: raise SystemExit(1)
if __name__=="__main__": main()
