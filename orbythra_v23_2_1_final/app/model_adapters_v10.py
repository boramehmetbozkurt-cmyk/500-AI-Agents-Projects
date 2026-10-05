from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
from typing import Any,Protocol
from app.providers import llm_provider
class ModelAdapter(Protocol):
 def generate(self,*,model_id:str,prompt:str)->dict[str,Any]:...
@dataclass
class GovernedHttpModelAdapter:
 timeout:float=20
 def generate(self,*,model_id:str,prompt:str)->dict[str,Any]:
  p=llm_provider()
  if p is None:raise RuntimeError("llm_provider_not_configured")
  try:r=p.post_json("/generate",{"model_id":model_id,"prompt":prompt},timeout=self.timeout)
  except Exception as e:raise RuntimeError("llm_provider_failed") from e
  output=r.get("output");confidence=r.get("confidence")
  if not isinstance(output,str) or not output.strip():raise RuntimeError("invalid_llm_provider_output")
  if not isinstance(confidence,(int,float)) or not 0<=float(confidence)<=1:raise RuntimeError("invalid_llm_provider_confidence")
  return {"model_id":model_id,"output":output,"confidence":float(confidence),"provider_response_sha256":hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()}
def disagreement(candidates:list[dict[str,Any]])->dict[str,Any]:
 if len(candidates)<2:return {"detected":False,"unique_outputs":len(candidates)}
 normalized={" ".join(str(x["output"]).lower().split()) for x in candidates}
 return {"detected":len(normalized)>1,"unique_outputs":len(normalized)}
