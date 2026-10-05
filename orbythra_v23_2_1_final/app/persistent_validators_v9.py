from __future__ import annotations
import hashlib
from sqlalchemy import text
from app.distributed_verification_v9 import Validator,_b64d
from app.store import STORE
class PersistentValidatorRegistry:
 def __init__(self):
  with STORE.engine.begin() as c:c.execute(text("""CREATE TABLE IF NOT EXISTS validators_v9(validator_id TEXT PRIMARY KEY,public_key_b64 TEXT NOT NULL,organization TEXT NOT NULL,trust_weight REAL NOT NULL,active INTEGER NOT NULL,fingerprint TEXT NOT NULL)"""))
  with STORE.engine.begin() as c:c.execute(text("""CREATE TABLE IF NOT EXISTS workspace_validators_v9(workspace_id TEXT NOT NULL,validator_id TEXT NOT NULL,public_key_b64 TEXT NOT NULL,organization TEXT NOT NULL,trust_weight REAL NOT NULL,active INTEGER NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(workspace_id,validator_id))"""))
 def register(self,v:Validator,workspace_id:str|None=None):
  raw=_b64d(v.public_key_b64)
  if len(raw)!=32:raise ValueError("invalid_ed25519_public_key")
  fp=hashlib.sha256(raw).hexdigest()
  if workspace_id is not None:
   with STORE.engine.begin() as c:c.execute(text("""INSERT INTO workspace_validators_v9(workspace_id,validator_id,public_key_b64,organization,trust_weight,active,fingerprint) VALUES(:scope,:i,:p,:o,:w,:a,:f) ON CONFLICT(workspace_id,validator_id) DO UPDATE SET public_key_b64=:p,organization=:o,trust_weight=:w,active=:a,fingerprint=:f"""),{"scope":workspace_id,"i":v.validator_id,"p":v.public_key_b64,"o":v.organization,"w":v.trust_weight,"a":int(v.active),"f":fp})
   return {"validator_id":v.validator_id,"fingerprint":fp}
  with STORE.engine.begin() as c:c.execute(text("""INSERT INTO validators_v9(validator_id,public_key_b64,organization,trust_weight,active,fingerprint) VALUES(:i,:p,:o,:w,:a,:f) ON CONFLICT(validator_id) DO UPDATE SET public_key_b64=:p,organization=:o,trust_weight=:w,active=:a,fingerprint=:f"""),{"i":v.validator_id,"p":v.public_key_b64,"o":v.organization,"w":v.trust_weight,"a":1 if v.active else 0,"f":fp})
  return {"validator_id":v.validator_id,"fingerprint":fp}
 def set_active(self,i:str,active:bool):
  with STORE.engine.begin() as c:c.execute(text("UPDATE validators_v9 SET active=:a WHERE validator_id=:i"),{"a":1 if active else 0,"i":i})
 def rotate(self,i:str,public_key_b64:str):
  v=self.get(i)
  if not v:raise ValueError("validator_not_found")
  return self.register(v.model_copy(update={"public_key_b64":public_key_b64}))
 def organizations(self,ids:list[str])->set[str]:
  return {v.organization for i in ids if (v:=self.get(i))}
 def get(self,i:str,workspace_id:str|None=None):
  query="SELECT * FROM validators_v9 WHERE validator_id=:i" if workspace_id is None else "SELECT * FROM workspace_validators_v9 WHERE workspace_id=:scope AND validator_id=:i"
  with STORE.engine.connect() as c:r=c.execute(text(query),{"i":i,"scope":workspace_id}).mappings().first()
  return Validator(validator_id=r["validator_id"],public_key_b64=r["public_key_b64"],organization=r["organization"],trust_weight=r["trust_weight"],active=bool(r["active"])) if r else None
PERSISTENT_VALIDATORS_V9=PersistentValidatorRegistry()
