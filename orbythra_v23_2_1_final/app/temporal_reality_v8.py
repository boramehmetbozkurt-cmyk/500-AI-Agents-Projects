from __future__ import annotations
import hashlib,time,uuid
from typing import Any
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import text
from app.crypto_core import canonical_json
from app.store import STORE
from app.vault import VAULT

class TemporalFactIn(BaseModel):
 subject:str=Field(min_length=1,max_length=500);predicate:str=Field(min_length=1,max_length=200);object:Any
 valid_from:int;valid_to:int|None=None;source_id:str=Field(min_length=1,max_length=300);evidence_sha256:str=Field(pattern=r"^[0-9a-f]{64}$")
 confidence:float=Field(default=1,ge=0,le=1)
 @model_validator(mode="after")
 def interval(self):
  if self.valid_to is not None and self.valid_to<=self.valid_from:raise ValueError("valid_to_must_be_after_valid_from")
  return self

class TemporalStore:
 def __init__(self):
  with STORE.engine.begin() as c:
   c.execute(text("""CREATE TABLE IF NOT EXISTS temporal_facts_v8(fact_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,subject TEXT NOT NULL,predicate TEXT NOT NULL,object_json TEXT NOT NULL,valid_from BIGINT NOT NULL,valid_to BIGINT,recorded_at BIGINT NOT NULL,retired_at BIGINT,source_id TEXT NOT NULL,evidence_sha256 TEXT NOT NULL,confidence REAL NOT NULL,fact_sha256 TEXT NOT NULL)"""))
   c.execute(text("CREATE INDEX IF NOT EXISTS idx_temporal_v8_lookup ON temporal_facts_v8(workspace_id,subject,predicate,valid_from,valid_to,recorded_at)"))
 def add(self,workspace_id:str,x:TemporalFactIn)->dict[str,Any]:
  now=int(time.time());fid="tf8_"+uuid.uuid4().hex[:20]
  payload={"workspace_id":workspace_id,**x.model_dump(mode="json"),"recorded_at":now}
  digest=hashlib.sha256(canonical_json(payload)).hexdigest()
  obj=VAULT.encrypt_json(x.object,workspace_id=workspace_id,purpose="temporal-fact-v8")
  with STORE.engine.begin() as c:c.execute(text("""INSERT INTO temporal_facts_v8 VALUES(:id,:w,:s,:p,:o,:vf,:vt,:r,NULL,:src,:e,:conf,:h)"""),{"id":fid,"w":workspace_id,"s":x.subject,"p":x.predicate,"o":obj,"vf":x.valid_from,"vt":x.valid_to,"r":now,"src":x.source_id,"e":x.evidence_sha256,"conf":x.confidence,"h":digest})
  return {"fact_id":fid,"recorded_at":now,"fact_sha256":digest}
 def snapshot(self,workspace_id:str,valid_at:int,known_at:int|None=None)->list[dict[str,Any]]:
  known=int(time.time()) if known_at is None else known_at
  q="""SELECT * FROM temporal_facts_v8 WHERE workspace_id=:w AND valid_from<=:v AND (valid_to IS NULL OR valid_to>:v) AND recorded_at<=:k AND (retired_at IS NULL OR retired_at>:k) ORDER BY subject,predicate,recorded_at,fact_id"""
  with STORE.engine.connect() as c:rows=c.execute(text(q),{"w":workspace_id,"v":valid_at,"k":known}).mappings().all()
  out=[]
  for row in rows:
   d=dict(row);d["object"]=VAULT.decrypt_json(d.pop("object_json"),workspace_id=workspace_id,purpose="temporal-fact-v8");out.append(d)
  return out
 def conflicts(self,workspace_id:str,valid_at:int,known_at:int|None=None)->list[dict[str,Any]]:
  rows=self.snapshot(workspace_id,valid_at,known_at);groups={}
  for r in rows:groups.setdefault((r["subject"],r["predicate"]),[]).append(r)
  return [{"subject":k[0],"predicate":k[1],"fact_ids":[x["fact_id"] for x in v]} for k,v in groups.items() if len({canonical_json(x["object"]) for x in v})>1]
 def stale(self,workspace_id:str,max_age_seconds:int,now:int|None=None)->list[str]:
  n=int(time.time()) if now is None else now
  with STORE.engine.connect() as c:rows=c.execute(text("SELECT fact_id,recorded_at FROM temporal_facts_v8 WHERE workspace_id=:w AND retired_at IS NULL"),{"w":workspace_id}).mappings().all()
  return [r["fact_id"] for r in rows if n-r["recorded_at"]>max_age_seconds]
TEMPORAL_V8=TemporalStore()
