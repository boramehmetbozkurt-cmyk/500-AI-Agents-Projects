from __future__ import annotations
import hashlib
from typing import Any,Literal
from pydantic import BaseModel,Field,model_validator
from app.crypto_core import canonical_json,seal
from app.verifiable_intelligence_v6 import EvidenceDocument,verify_claims
from app.config import SETTINGS
class CausalEdge(BaseModel):
 cause:str=Field(min_length=1,max_length=500);effect:str=Field(min_length=1,max_length=500);mechanism:str=Field(min_length=1,max_length=2000);evidence_claims:list[str]=Field(min_length=1,max_length=50);confidence:float=Field(ge=0,le=1);confounders:list[str]=Field(default_factory=list,max_length=50);cause_observed_at:int|None=None;effect_observed_at:int|None=None;mediators:list[str]=Field(default_factory=list,max_length=50);colliders:list[str]=Field(default_factory=list,max_length=50)
class CausalRequest(BaseModel):
 request_id:str=Field(min_length=8,max_length=128);hypothesis:str=Field(min_length=1,max_length=2000);edges:list[CausalEdge]=Field(min_length=1,max_length=100);evidence:list[EvidenceDocument]=Field(min_length=1,max_length=200);intervention:str|None=Field(default=None,max_length=1000);counterfactual:str|None=Field(default=None,max_length=1000);minimum_edge_confidence:float=Field(default=.7,ge=0,le=1);require_confounder_analysis:bool=True
 @model_validator(mode="after")
 def graph(self):
  nodes={e.cause for e in self.edges}|{e.effect for e in self.edges};adj={n:[] for n in nodes}
  for e in self.edges:adj[e.cause].append(e.effect)
  seen=set();stack=set()
  def visit(n):
   if n in stack:raise ValueError("causal_graph_cycle")
   if n in seen:return
   stack.add(n)
   for m in adj[n]:visit(m)
   stack.remove(n);seen.add(n)
  for n in nodes:visit(n)
  return self
class CausalResult(BaseModel):
 status:Literal["PASS","REVIEW","FAIL"];edge_results:list[dict[str,Any]];evidence_sha256:str;graph_sha256:str;intervention_ready:bool;counterfactual_ready:bool;receipt:dict[str,Any]|None;boundary:str
def evaluate(x:CausalRequest,workspace_id:str)->CausalResult:
 results=[];all_supported=True;needs_review=False
 for e in x.edges:
  v=verify_claims(e.evidence_claims,x.evidence);conf_ok=e.confidence>=x.minimum_edge_confidence;confounder_ok=(not x.require_confounder_analysis) or bool(e.confounders)
  temporal_ok=e.cause_observed_at is None or e.effect_observed_at is None or e.cause_observed_at<=e.effect_observed_at
  structure_ok=not (set(e.confounders)&set(e.colliders)) and e.cause not in e.confounders and e.effect not in e.confounders
  ok=v.status=="PASS" and conf_ok and confounder_ok and temporal_ok and structure_ok
  if v.status!="PASS":all_supported=False
  if not conf_ok or not confounder_ok or not structure_ok:needs_review=True
  if not temporal_ok:all_supported=False
  results.append({"cause":e.cause,"effect":e.effect,"evidence_status":v.status,"confidence":e.confidence,"confounders":e.confounders,"mediators":e.mediators,"colliders":e.colliders,"temporal_precedence":temporal_ok,"structure_ok":structure_ok,"status":"PASS" if ok else ("FAIL" if v.status!="PASS" else "REVIEW")})
 status="PASS" if all_supported and not needs_review else ("FAIL" if not all_supported else "REVIEW")
 graph={"hypothesis":x.hypothesis,"edges":[e.model_dump(mode="json") for e in x.edges],"release_sha":SETTINGS.release_sha}
 gh=hashlib.sha256(canonical_json(graph)).hexdigest();eh=hashlib.sha256(canonical_json([e.model_dump(mode="json") for e in x.evidence])).hexdigest()
 receipt=None
 if status=="PASS":receipt=seal(payload={"schema":"orbythra.causal-intelligence.v11","request_id":x.request_id,"graph_sha256":gh,"evidence_sha256":eh,"status":status,"release_sha":SETTINGS.release_sha},intent={"action":"attest-causal-analysis","asset":x.request_id},effect={"action":"attest-causal-analysis","asset":x.request_id},approvals=[],min_approvals=0,workspace_id=workspace_id,domain="v11-causal-receipt",ttl_seconds=0)
 return CausalResult(status=status,edge_results=results,evidence_sha256=eh,graph_sha256=gh,intervention_ready=status=="PASS" and bool(x.intervention),counterfactual_ready=status=="PASS" and bool(x.counterfactual),receipt=receipt,boundary="Evidence-gated causal hypothesis analysis; observational support does not by itself establish real-world causation or intervention effect.")
