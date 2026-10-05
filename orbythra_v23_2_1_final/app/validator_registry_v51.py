from __future__ import annotations
import base64,hashlib,json
from dataclasses import dataclass
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

def _b64d(v:str)->bytes:return base64.urlsafe_b64decode(v+"="*(-len(v)%4))
def canonical(v:dict)->bytes:return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
@dataclass(frozen=True)
class ValidatorKey: validator_id:str; public_key_b64:str; key_fingerprint:str
class ValidatorRegistry:
 def __init__(self):self._keys={}
 def register(self,validator_id:str,public_key_b64:str)->ValidatorKey:
  raw=_b64d(public_key_b64)
  if len(raw)!=32:raise ValueError("invalid_ed25519_public_key")
  fp=hashlib.sha256(raw).hexdigest(); item=ValidatorKey(validator_id,public_key_b64,fp); self._keys[validator_id]=item; return item
 def get(self,validator_id:str)->ValidatorKey|None:return self._keys.get(validator_id)
 def verify(self,validator_id:str,payload:dict,signature_b64:str)->str:
  k=self.get(validator_id)
  if not k:raise ValueError("validator_not_registered")
  try:ed25519.Ed25519PublicKey.from_public_bytes(_b64d(k.public_key_b64)).verify(_b64d(signature_b64),b"ORBYTHRA-VALIDATOR-V5.1\x00"+canonical(payload))
  except (InvalidSignature,ValueError) as e:raise ValueError("invalid_validator_signature") from e
  return k.key_fingerprint
VALIDATORS=ValidatorRegistry()
