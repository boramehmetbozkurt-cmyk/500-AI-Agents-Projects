from __future__ import annotations
import json,urllib.request
from typing import Protocol
from app.config import SETTINGS
from app.nli_verifier_v51 import NLIVerdict,NLI
class SemanticVerifier(Protocol):
 def score(self,claim:str,evidence_text:str)->NLIVerdict:...
class GovernedSemanticVerifier:
 name="orbythra-semantic-provider-v1"
 def score(self,claim:str,evidence_text:str)->NLIVerdict:
  if not SETTINGS.llm_provider_url:return NLI.score(claim,evidence_text)
  body=json.dumps({"task":"nli","claim":claim,"evidence_text":evidence_text,"labels":["ENTAILMENT","CONTRADICTION","NEUTRAL"]}).encode()
  req=urllib.request.Request(SETTINGS.llm_provider_url+"/verify",data=body,headers={"Content-Type":"application/json"},method="POST")
  try:
   with urllib.request.urlopen(req,timeout=8) as r:data=json.loads(r.read().decode())
  except Exception as e:raise RuntimeError("semantic_verifier_provider_failed") from e
  try:
   scores=[float(data[k]) for k in ("entailment","contradiction","neutral")]
   if any(x<0 or x>1 for x in scores) or abs(sum(scores)-1)>0.03:raise ValueError()
   label=str(data["label"]).upper()
   if label not in {"ENTAILMENT","CONTRADICTION","NEUTRAL"}:raise ValueError()
  except Exception as e:raise RuntimeError("semantic_verifier_invalid_response") from e
  return NLIVerdict(label=label,entailment=scores[0],contradiction=scores[1],neutral=scores[2],verifier=self.name)
SEMANTIC_NLI=GovernedSemanticVerifier()
