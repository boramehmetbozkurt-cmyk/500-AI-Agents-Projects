from __future__ import annotations
import base64,hashlib,json,time
from typing import Literal
from pydantic import BaseModel,Field
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519
def _b64d(v:str)->bytes:return base64.urlsafe_b64decode(v+"="*(-len(v)%4))
def _canon(v:dict)->bytes:return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
class Validator(BaseModel):
 validator_id:str=Field(min_length=1,max_length=128);public_key_b64:str;organization:str=Field(min_length=1,max_length=200);trust_weight:float=Field(default=1,gt=0,le=10);active:bool=True
class Attestation(BaseModel):
 validator_id:str;decision:Literal["PASS","FAIL"];payload_sha256:str=Field(pattern=r"^[0-9a-f]{64}$");nonce:str=Field(min_length=8,max_length=200);issued_at:int;signature_b64:str
class QuorumRequest(BaseModel):
 payload_sha256:str=Field(pattern=r"^[0-9a-f]{64}$");nonce:str=Field(min_length=8,max_length=200);attestations:list[Attestation]=Field(min_length=1,max_length=1000);minimum_validators:int=Field(default=3,ge=1);minimum_pass_fraction:float=Field(default=.67,gt=.5,le=1);maximum_age_seconds:int=Field(default=300,ge=1,le=86400);minimum_organizations:int=Field(default=1,ge=1,le=1000)
class TrustNetwork:
 def __init__(self):self.validators={}
 def _lookup(self,validator_id:str,workspace_id:str|None=None):
  from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
  return PERSISTENT_VALIDATORS_V9.get(validator_id,workspace_id=workspace_id)
 def register(self,v:Validator,workspace_id:str|None=None):
  raw=_b64d(v.public_key_b64)
  if len(raw)!=32:raise ValueError("invalid_ed25519_public_key")
  from app.persistent_validators_v9 import PERSISTENT_VALIDATORS_V9
  result=PERSISTENT_VALIDATORS_V9.register(v,workspace_id=workspace_id)
  if workspace_id is None:self.validators[v.validator_id]=v
  return result
 def message(self,a:Attestation)->bytes:return b"ORBYTHRA-V9-ATTESTATION\x00"+_canon({"validator_id":a.validator_id,"decision":a.decision,"payload_sha256":a.payload_sha256,"nonce":a.nonce,"issued_at":a.issued_at})
 def verify(self,a:Attestation,expected_hash:str,nonce:str,max_age:int,now:int|None=None,workspace_id:str|None=None)->Validator:
  v=self._lookup(a.validator_id,workspace_id=workspace_id)
  if not v or not v.active:raise ValueError("validator_unavailable")
  if a.payload_sha256!=expected_hash or a.nonce!=nonce:raise ValueError("attestation_binding_mismatch")
  n=int(time.time()) if now is None else now
  if abs(n-a.issued_at)>max_age:raise ValueError("stale_attestation")
  try:ed25519.Ed25519PublicKey.from_public_bytes(_b64d(v.public_key_b64)).verify(_b64d(a.signature_b64),self.message(a))
  except (InvalidSignature,ValueError) as e:raise ValueError("invalid_attestation_signature") from e
  return v
 def quorum(self,r:QuorumRequest,now:int|None=None,workspace_id:str|None=None)->dict:
  seen=set();valid=[];invalid=[]
  for a in r.attestations:
   if a.validator_id in seen:invalid.append({"validator_id":a.validator_id,"reason":"duplicate_validator"});continue
   seen.add(a.validator_id)
   try:valid.append((a,self.verify(a,r.payload_sha256,r.nonce,r.maximum_age_seconds,now,workspace_id=workspace_id)))
   except ValueError as e:invalid.append({"validator_id":a.validator_id,"reason":str(e)})
  pass_weight=sum(v.trust_weight for a,v in valid if a.decision=="PASS");total_weight=sum(v.trust_weight for _,v in valid);fraction=pass_weight/total_weight if total_weight else 0
  organizations=len({v.organization for _,v in valid})
  ok=len(valid)>=r.minimum_validators and organizations>=r.minimum_organizations and fraction>=r.minimum_pass_fraction
  result={"schema":"orbythra.distributed-verification.v9","status":"PASS" if ok else "FAIL","valid_validators":len(valid),"valid_organizations":organizations,"pass_weight_fraction":round(fraction,6),"invalid":invalid,"payload_sha256":r.payload_sha256,"nonce":r.nonce}
  return {**result,"quorum_sha256":hashlib.sha256(_canon(result)).hexdigest()}
TRUST_V9=TrustNetwork()
