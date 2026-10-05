from __future__ import annotations
import time
from typing import Any
from sqlalchemy import text
from app.store import STORE
from app.vault import VAULT
from app.validation_evidence_v45 import sha256

class GeneralistV5Store:
    def __init__(self) -> None:
        self.engine=STORE.engine
        with self.engine.begin() as c:
            c.execute(text("""CREATE TABLE IF NOT EXISTS generalist_evaluations_v5(
              workspace_id TEXT NOT NULL,evaluation_id TEXT NOT NULL,sequence BIGINT NOT NULL,
              payload_json TEXT NOT NULL,evaluation_sha256 TEXT NOT NULL,previous_sha256 TEXT,
              created_at BIGINT NOT NULL,PRIMARY KEY(workspace_id,evaluation_id),
              UNIQUE(workspace_id,sequence))"""))

    def append(self, workspace_id:str, result:dict[str,Any])->dict[str,Any]:
        with self.engine.connect() as c:
            prev=c.execute(text("SELECT sequence,evaluation_sha256 FROM generalist_evaluations_v5 WHERE workspace_id=:w ORDER BY sequence DESC LIMIT 1"),{"w":workspace_id}).mappings().first()
        seq=1 if prev is None else int(prev["sequence"])+1
        previous=None if prev is None else str(prev["evaluation_sha256"])
        created=int(time.time())
        payload={**result,"sequence":seq,"previous_sha256":previous}
        digest=sha256({k:v for k,v in payload.items() if k!="evaluation_sha256"})
        protected=VAULT.encrypt_json(payload,workspace_id=workspace_id,purpose="generalist-v5")
        with self.engine.begin() as c:
            c.execute(text("""INSERT INTO generalist_evaluations_v5
              (workspace_id,evaluation_id,sequence,payload_json,evaluation_sha256,previous_sha256,created_at)
              VALUES(:w,:id,:s,:p,:h,:prev,:t)"""),
              {"w":workspace_id,"id":payload["evaluation_id"],"s":seq,"p":protected,"h":digest,"prev":previous,"t":created})
        return {**payload,"evaluation_sha256":digest,"created_at":created}

    def get(self,workspace_id:str,evaluation_id:str)->dict[str,Any]|None:
        with self.engine.connect() as c:
            row=c.execute(text("SELECT payload_json,evaluation_sha256,created_at FROM generalist_evaluations_v5 WHERE workspace_id=:w AND evaluation_id=:id"),{"w":workspace_id,"id":evaluation_id}).mappings().first()
        if row is None:return None
        p=VAULT.decrypt_json(row["payload_json"],workspace_id=workspace_id,purpose="generalist-v5")
        return {**p,"evaluation_sha256":row["evaluation_sha256"],"created_at":int(row["created_at"])}

    def verify(self,workspace_id:str)->dict[str,Any]:
        with self.engine.connect() as c:
            rows=c.execute(text("SELECT evaluation_id,payload_json,evaluation_sha256 FROM generalist_evaluations_v5 WHERE workspace_id=:w ORDER BY sequence"),{"w":workspace_id}).mappings().all()
        previous=None; errors=[]
        for seq,row in enumerate(rows,1):
            p=VAULT.decrypt_json(row["payload_json"],workspace_id=workspace_id,purpose="generalist-v5")
            if p["sequence"]!=seq: errors.append("sequence:"+row["evaluation_id"])
            if p.get("previous_sha256")!=previous: errors.append("previous:"+row["evaluation_id"])
            expected=sha256({k:v for k,v in p.items() if k!="evaluation_sha256"})
            if row["evaluation_sha256"]!=expected: errors.append("digest:"+row["evaluation_id"])
            previous=row["evaluation_sha256"]
        return {"valid":bool(rows) and not errors,"entries":len(rows),"head_sha256":previous,"errors":errors}

GENERALIST_V5_STORE=GeneralistV5Store()
