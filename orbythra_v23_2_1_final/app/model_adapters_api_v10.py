from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from app.model_adapters_v10 import GovernedHttpModelAdapter,disagreement
from app.security import Principal,require_minimum_role
router=APIRouter(prefix="/v10/providers",tags=["v10-model-providers"]);_OP=require_minimum_role("operator");_EV=require_minimum_role("evaluator")
class InvokeRequest(BaseModel):model_ids:list[str]=Field(min_length=1,max_length=10);prompt:str=Field(min_length=1,max_length=100000)
@router.post("/invoke")
def invoke(body:InvokeRequest,principal:Principal=Depends(_OP)):
 adapter=GovernedHttpModelAdapter();results=[];errors=[]
 for m in body.model_ids:
  try:results.append(adapter.generate(model_id=m,prompt=body.prompt))
  except RuntimeError as e:errors.append({"model_id":m,"error":str(e)})
 status="PASS" if results and not errors else "FAIL"
 return {"status":status,"results":results,"errors":errors,"disagreement":disagreement(results)}
@router.get("/readiness")
def readiness(principal:Principal=Depends(_EV)):
 from app.providers import status
 s=status();return {"release":"10.0-hardening","workspace_id":principal.workspace_id,"governed_http_adapter":True,"llm_provider_configured":s.llm_provider_configured,"timeout_fail_closed":True,"schema_validation":True,"cross_model_disagreement_detection":True,"provider_independence_certified":False}
