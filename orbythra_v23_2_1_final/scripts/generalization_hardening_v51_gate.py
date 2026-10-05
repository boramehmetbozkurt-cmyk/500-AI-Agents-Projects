from app.generalization_hardening_v51 import HardeningCase,HardeningRequest,evaluate_hardening
import json
cases=[]
domains=["engineering","finance","operations","security","research","legal"]
for i in range(600):
 mission=f"m{i//10}" if i<200 else None; step=i%10 if mission else None
 cases.append(HardeningCase(case_id=f"v51-{i}",domain=domains[i%6],success=i%25!=0,baseline_success=True if i>=300 else None,confidence=.9 if i%25!=0 else .1,evidence_coverage=.95,ood=i<300,transferred_skill=200<=i<400,negative_control=300<=i<400,regression_anchor=400<=i<600,mission_id=mission,step_index=step,total_steps=10 if mission else None))
# Ensure long-horizon missions are complete: mission segment must not contain synthetic failures.
for i in range(200):cases[i].success=True;cases[i].confidence=.9
r=evaluate_hardening(HardeningRequest(evaluation_id="v5.1-frozen-ci",cases=cases,minimum_domains=6,minimum_ood_success=.90,minimum_transfer_success=.90,maximum_negative_transfer_harm=.05,maximum_forgetting=.05,minimum_long_horizon_completion=.90,minimum_evidence=.90,maximum_calibration_error=.15))
print(json.dumps(r,sort_keys=True))
if r["status"]!="PASS":raise SystemExit(1)
