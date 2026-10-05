from __future__ import annotations
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.generalization_hardening_v51 import HardeningRequest,evaluate_hardening
from app.security import Principal,require_minimum_role
from app.validator_registry_v51 import VALIDATORS
router=APIRouter(prefix="/v5.1",tags=["v5.1-hardening"]); ADMIN=require_minimum_role("admin"); EVAL=require_minimum_role("evaluator")
class KeyRegistration(BaseModel):validator_id:str=Field(min_length=1,max_length=200);public_key_b64:str=Field(min_length=40,max_length=100)
class SignedEvaluation(BaseModel):validator_id:str;signature_b64:str;evaluation:HardeningRequest
@router.post("/validators")
def register(b:KeyRegistration,principal:Principal=Depends(ADMIN))->dict:
 try:k=VALIDATORS.register(b.validator_id,b.public_key_b64)
 except ValueError as e:raise HTTPException(422,str(e))
 return {"validator_id":k.validator_id,"key_fingerprint":k.key_fingerprint}
@router.post("/hardening/evaluate")
def evaluate(b:SignedEvaluation,principal:Principal=Depends(EVAL))->dict:
 payload=b.evaluation.model_dump(mode="json")
 try:fp=VALIDATORS.verify(b.validator_id,payload,b.signature_b64)
 except ValueError as e:raise HTTPException(401,str(e))
 try:r=evaluate_hardening(b.evaluation)
 except ValueError as e:raise HTTPException(422,str(e))
 return {**r,"validator_id":b.validator_id,"validator_key_fingerprint":fp,"validator_signature_verified":True,"independent_validation_claim":False}
@router.get("/readiness")
def readiness(principal:Principal=Depends(EVAL))->dict:
 return {"release":"5.1","ood_gate":True,"statistical_interval":True,"negative_transfer_gate":True,"catastrophic_forgetting_gate":True,"long_horizon_gate":True,"validator_ed25519_identity":True,"anti_leakage_protocol":True,"reproducibility_manifest":True,"agi_claim":False,"independent_validation_claim":False}
