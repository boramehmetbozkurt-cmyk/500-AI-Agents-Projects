from __future__ import annotations
import hashlib,json,math
from collections import defaultdict
from typing import Any
from pydantic import BaseModel,Field

def _sha(v:Any)->str:
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def wilson(successes:int,n:int,z:float=1.96)->tuple[float,float]:
 if n<=0:return (0.0,0.0)
 p=successes/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; m=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/d
 return (max(0,c-m),min(1,c+m))

class HardeningCase(BaseModel):
 case_id:str=Field(min_length=1,max_length=120); domain:str=Field(min_length=1,max_length=120)
 success:bool; baseline_success:bool|None=None; confidence:float=Field(ge=0,le=1); evidence_coverage:float=Field(ge=0,le=1)
 ood:bool=False; transferred_skill:bool=False; negative_control:bool=False; regression_anchor:bool=False
 mission_id:str|None=None; step_index:int|None=Field(default=None,ge=0); total_steps:int|None=Field(default=None,ge=1)

class HardeningRequest(BaseModel):
 evaluation_id:str=Field(pattern=r"^[A-Za-z0-9._-]+$",min_length=1,max_length=120); cases:list[HardeningCase]=Field(min_length=50,max_length=20000)
 minimum_domains:int=Field(default=5,ge=3); minimum_ood_success:float=Field(default=.75,ge=0,le=1)
 minimum_transfer_success:float=Field(default=.75,ge=0,le=1); maximum_negative_transfer_harm:float=Field(default=.05,ge=0,le=1)
 maximum_forgetting:float=Field(default=.03,ge=0,le=1); minimum_long_horizon_completion:float=Field(default=.70,ge=0,le=1)
 minimum_evidence:float=Field(default=.85,ge=0,le=1); maximum_calibration_error:float=Field(default=.15,ge=0,le=1)

def evaluate_hardening(b:HardeningRequest)->dict[str,Any]:
 cs=b.cases
 if len({c.case_id for c in cs})!=len(cs): raise ValueError("duplicate_case_id")
 domains={c.domain for c in cs}; ood=[c for c in cs if c.ood]; tr=[c for c in cs if c.transferred_skill and not c.negative_control]; neg=[c for c in cs if c.negative_control]; reg=[c for c in cs if c.regression_anchor and c.baseline_success is not None]
 rate=lambda xs:sum(c.success for c in xs)/len(xs) if xs else 0.0
 harm=sum(bool(c.baseline_success) and not c.success for c in neg)/len(neg) if neg else 1.0
 forgetting=sum(bool(c.baseline_success) and not c.success for c in reg)/len(reg) if reg else 1.0
 missions=defaultdict(list)
 for c in cs:
  if c.mission_id: missions[c.mission_id].append(c)
 complete=0
 for xs in missions.values():
  expected=max((x.total_steps or 0) for x in xs); indices={x.step_index for x in xs}
  if expected and len(indices)==expected and all(x.success for x in xs): complete+=1
 long=complete/len(missions) if missions else 0.0
 ev=sum(c.evidence_coverage for c in cs)/len(cs); cal=sum(abs(c.confidence-float(c.success)) for c in cs)/len(cs)
 ood_s=sum(c.success for c in ood); ci=wilson(ood_s,len(ood))
 gates={"domain_diversity":len(domains)>=b.minimum_domains,"ood_present":bool(ood),"ood_success":bool(ood) and rate(ood)>=b.minimum_ood_success,"ood_ci_nonzero":ci[0]>0,"transfer_present":bool(tr),"transfer_success":bool(tr) and rate(tr)>=b.minimum_transfer_success,"negative_controls_present":bool(neg),"negative_transfer_harm":bool(neg) and harm<=b.maximum_negative_transfer_harm,"regression_anchors_present":bool(reg),"catastrophic_forgetting":bool(reg) and forgetting<=b.maximum_forgetting,"long_horizon_present":bool(missions),"long_horizon_completion":bool(missions) and long>=b.minimum_long_horizon_completion,"evidence":ev>=b.minimum_evidence,"calibration":cal<=b.maximum_calibration_error}
 metrics={"cases":len(cs),"domains":len(domains),"ood_cases":len(ood),"ood_success_rate":round(rate(ood),6),"ood_success_wilson95":[round(ci[0],6),round(ci[1],6)],"transfer_cases":len(tr),"transfer_success_rate":round(rate(tr),6),"negative_controls":len(neg),"negative_transfer_harm_rate":round(harm,6),"regression_anchors":len(reg),"forgetting_rate":round(forgetting,6),"missions":len(missions),"long_horizon_completion_rate":round(long,6),"evidence_coverage":round(ev,6),"calibration_error":round(cal,6)}
 result={"schema":"orbythra.generalization-hardening.v5.1","evaluation_id":b.evaluation_id,"status":"PASS" if all(gates.values()) else "FAIL","gates":gates,"metrics":metrics,"boundary":"Internal hardening evidence is not independent validation and is not proof of AGI or human-level general intelligence."}
 return {**result,"evaluation_sha256":_sha(result)}
