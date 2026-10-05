from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from sqlalchemy import text

from app.store import STORE
from app.vault import VAULT


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class AutonomyStore:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS autonomy_memories (memory_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, agent_id TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL, tags_json TEXT NOT NULL, confidence TEXT NOT NULL, source_refs_json TEXT NOT NULL, sensitivity TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_at BIGINT NOT NULL, expires_at BIGINT)""",
            "CREATE INDEX IF NOT EXISTS idx_autonomy_memories_scope ON autonomy_memories(workspace_id, agent_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS autonomy_skills (workspace_id TEXT NOT NULL, skill_id TEXT NOT NULL, profile_json TEXT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id, skill_id))""",
            """CREATE TABLE IF NOT EXISTS autonomy_missions (mission_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, agent_id TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, cycle_count BIGINT NOT NULL, plan_revision BIGINT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_autonomy_missions_scope ON autonomy_missions(workspace_id, agent_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS autonomy_plans (mission_id TEXT NOT NULL, revision BIGINT NOT NULL, payload_json TEXT NOT NULL, context_sha256 TEXT NOT NULL, plan_sha256 TEXT NOT NULL, created_at BIGINT NOT NULL, PRIMARY KEY(mission_id, revision))""",
            """CREATE TABLE IF NOT EXISTS autonomy_evaluations (evaluation_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, workspace_id TEXT NOT NULL, cycle BIGINT NOT NULL, payload_json TEXT NOT NULL, evaluation_sha256 TEXT NOT NULL, created_at BIGINT NOT NULL)""",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def add_memory(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        memory_id = "mem_" + uuid.uuid4().hex[:24]
        expires_at = None if body.get("ttl_seconds") is None else now + int(body["ttl_seconds"])
        content_sha256 = _sha(body["content"])
        protected = VAULT.encrypt_json(body["content"], workspace_id=workspace_id, purpose="autonomy-memory")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO autonomy_memories(memory_id,workspace_id,agent_id,kind,payload_json,tags_json,confidence,source_refs_json,sensitivity,content_sha256,created_at,expires_at) VALUES (:memory_id,:workspace_id,:agent_id,:kind,:payload_json,:tags_json,:confidence,:source_refs_json,:sensitivity,:content_sha256,:created_at,:expires_at)"""), {
                "memory_id": memory_id, "workspace_id": workspace_id, "agent_id": body["agent_id"], "kind": body["kind"], "payload_json": protected,
                "tags_json": _canonical(sorted(set(body.get("tags", [])))), "confidence": str(float(body.get("confidence", 1.0))),
                "source_refs_json": _canonical(body.get("source_refs", [])), "sensitivity": body.get("sensitivity", "standard"),
                "content_sha256": content_sha256, "created_at": now, "expires_at": expires_at,
            })
        return {"memory_id": memory_id, **{k: body[k] for k in ["agent_id","kind","content"]}, "tags": sorted(set(body.get("tags", []))), "confidence": float(body.get("confidence",1.0)), "source_refs": body.get("source_refs", []), "sensitivity": body.get("sensitivity","standard"), "content_sha256": content_sha256, "created_at": now, "expires_at": expires_at}

    def query_memories(self, workspace_id: str, *, agent_id: str, kinds: list[str], tags: list[str], min_confidence: float, limit: int) -> list[dict[str, Any]]:
        now = int(time.time())
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM autonomy_memories WHERE workspace_id=:workspace_id AND agent_id=:agent_id AND (expires_at IS NULL OR expires_at>:now) ORDER BY created_at DESC LIMIT 500"), {"workspace_id": workspace_id, "agent_id": agent_id, "now": now}).mappings().all()
        out=[]
        wanted_tags=set(tags)
        for row in rows:
            if kinds and row["kind"] not in kinds: continue
            row_tags=set(json.loads(row["tags_json"]))
            if wanted_tags and not wanted_tags.issubset(row_tags): continue
            conf=float(row["confidence"])
            if conf < min_confidence: continue
            content=VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="autonomy-memory")
            out.append({"memory_id": row["memory_id"], "agent_id": row["agent_id"], "kind": row["kind"], "content": content, "tags": sorted(row_tags), "confidence": conf, "source_refs": json.loads(row["source_refs_json"]), "sensitivity": row["sensitivity"], "content_sha256": row["content_sha256"], "created_at": int(row["created_at"]), "expires_at": None if row["expires_at"] is None else int(row["expires_at"])})
            if len(out) >= limit: break
        return out

    def upsert_skill(self, workspace_id: str, skill: dict[str, Any]) -> dict[str, Any]:
        now=int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM autonomy_skills WHERE workspace_id=:workspace_id AND skill_id=:skill_id"), {"workspace_id":workspace_id,"skill_id":skill["skill_id"]})
            conn.execute(text("INSERT INTO autonomy_skills(workspace_id,skill_id,profile_json,updated_at) VALUES (:workspace_id,:skill_id,:profile_json,:updated_at)"), {"workspace_id":workspace_id,"skill_id":skill["skill_id"],"profile_json":_canonical(skill),"updated_at":now})
        return {**skill,"updated_at":now}

    def list_skills(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows=conn.execute(text("SELECT profile_json,updated_at FROM autonomy_skills WHERE workspace_id=:workspace_id ORDER BY skill_id"), {"workspace_id":workspace_id}).mappings().all()
        return [{**json.loads(r["profile_json"]),"updated_at":int(r["updated_at"])} for r in rows]

    def create_mission(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        now=int(time.time()); mission_id="mis_"+uuid.uuid4().hex[:24]
        protected=VAULT.encrypt_json(body, workspace_id=workspace_id, purpose="autonomy-mission")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO autonomy_missions(mission_id,workspace_id,agent_id,payload_json,status,cycle_count,plan_revision,created_at,updated_at) VALUES (:mission_id,:workspace_id,:agent_id,:payload_json,'ACTIVE',0,0,:created_at,:updated_at)"""), {"mission_id":mission_id,"workspace_id":workspace_id,"agent_id":body["agent_id"],"payload_json":protected,"created_at":now,"updated_at":now})
        return {"mission_id":mission_id,**body,"cycle_count":0,"status":"ACTIVE","plan_revision":0,"created_at":now,"updated_at":now}

    def get_mission(self, workspace_id: str, mission_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row=conn.execute(text("SELECT * FROM autonomy_missions WHERE workspace_id=:workspace_id AND mission_id=:mission_id"), {"workspace_id":workspace_id,"mission_id":mission_id}).mappings().first()
        if row is None: return None
        body=VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="autonomy-mission")
        return {"mission_id":row["mission_id"],**body,"cycle_count":int(row["cycle_count"]),"status":row["status"],"plan_revision":int(row["plan_revision"]),"created_at":int(row["created_at"]),"updated_at":int(row["updated_at"])}

    def set_mission_state(self, workspace_id: str, mission_id: str, *, status: str | None=None, cycle_count: int | None=None, plan_revision: int | None=None) -> None:
        current=self.get_mission(workspace_id, mission_id)
        if current is None: raise ValueError("mission_not_found")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE autonomy_missions SET status=:status,cycle_count=:cycle_count,plan_revision=:plan_revision,updated_at=:updated_at WHERE workspace_id=:workspace_id AND mission_id=:mission_id"), {"status":status or current["status"],"cycle_count":current["cycle_count"] if cycle_count is None else cycle_count,"plan_revision":current["plan_revision"] if plan_revision is None else plan_revision,"updated_at":int(time.time()),"workspace_id":workspace_id,"mission_id":mission_id})

    def save_plan(self, workspace_id: str, mission_id: str, plan: dict[str, Any], context_sha256: str, plan_sha256: str) -> dict[str, Any]:
        mission=self.get_mission(workspace_id, mission_id)
        if mission is None: raise ValueError("mission_not_found")
        revision=mission["plan_revision"]+1; now=int(time.time())
        payload={**plan,"mission_id":mission_id,"revision":revision,"context_sha256":context_sha256,"plan_sha256":plan_sha256,"created_at":now}
        protected=VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="autonomy-plan")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO autonomy_plans(mission_id,revision,payload_json,context_sha256,plan_sha256,created_at) VALUES (:mission_id,:revision,:payload_json,:context_sha256,:plan_sha256,:created_at)"), {"mission_id":mission_id,"revision":revision,"payload_json":protected,"context_sha256":context_sha256,"plan_sha256":plan_sha256,"created_at":now})
        self.set_mission_state(workspace_id, mission_id, plan_revision=revision, status="PAUSED" if plan.get("missing_capabilities") else "ACTIVE")
        return payload

    def get_latest_plan(self, workspace_id: str, mission_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row=conn.execute(text("SELECT payload_json FROM autonomy_plans WHERE mission_id=:mission_id ORDER BY revision DESC LIMIT 1"), {"mission_id":mission_id}).mappings().first()
        if row is None: return None
        return VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="autonomy-plan")

    def add_evaluation(self, workspace_id: str, mission_id: str, cycle: int, payload: dict[str, Any]) -> str:
        evaluation_id="eval_"+uuid.uuid4().hex[:24]; now=int(time.time()); digest=_sha(payload)
        protected=VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="autonomy-evaluation")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO autonomy_evaluations(evaluation_id,mission_id,workspace_id,cycle,payload_json,evaluation_sha256,created_at) VALUES (:evaluation_id,:mission_id,:workspace_id,:cycle,:payload_json,:evaluation_sha256,:created_at)"), {"evaluation_id":evaluation_id,"mission_id":mission_id,"workspace_id":workspace_id,"cycle":cycle,"payload_json":protected,"evaluation_sha256":digest,"created_at":now})
        return digest

AUTONOMY_STORE=AutonomyStore()
