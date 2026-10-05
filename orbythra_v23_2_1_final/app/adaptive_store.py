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


class AdaptiveStore:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS adaptive_world_state (workspace_id TEXT NOT NULL, agent_id TEXT NOT NULL, domain TEXT NOT NULL, revision BIGINT NOT NULL, payload_json TEXT NOT NULL, state_sha256 TEXT NOT NULL, previous_sha256 TEXT, created_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,agent_id,domain,revision))""",
            """CREATE TABLE IF NOT EXISTS adaptive_learning (learning_id TEXT NOT NULL, workspace_id TEXT NOT NULL, revision BIGINT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, learning_sha256 TEXT NOT NULL, previous_sha256 TEXT, created_at BIGINT NOT NULL, PRIMARY KEY(learning_id,revision))""",
            "CREATE INDEX IF NOT EXISTS idx_adaptive_learning_scope ON adaptive_learning(workspace_id,learning_id,revision DESC)",
            """CREATE TABLE IF NOT EXISTS adaptive_strategies (workspace_id TEXT NOT NULL, strategy_id TEXT NOT NULL, profile_json TEXT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,strategy_id))""",
            """CREATE TABLE IF NOT EXISTS adaptive_transfers (transfer_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, payload_json TEXT NOT NULL, transfer_sha256 TEXT NOT NULL, created_at BIGINT NOT NULL)""",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def update_world_state(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT revision,state_sha256 FROM adaptive_world_state WHERE workspace_id=:w AND agent_id=:a AND domain=:d ORDER BY revision DESC LIMIT 1"), {"w": workspace_id, "a": body["agent_id"], "d": body["domain"]}).mappings().first()
        revision = 1 if row is None else int(row["revision"]) + 1
        previous = None if row is None else str(row["state_sha256"])
        payload = {"agent_id": body["agent_id"], "domain": body["domain"], "revision": revision, "state": body["state"], "evidence_refs": body.get("evidence_refs", []), "confidence": float(body.get("confidence", 1.0)), "previous_sha256": previous, "created_at": now}
        digest = _sha({k: v for k, v in payload.items() if k != "created_at"})
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="adaptive-world-state")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO adaptive_world_state(workspace_id,agent_id,domain,revision,payload_json,state_sha256,previous_sha256,created_at) VALUES (:w,:a,:d,:r,:p,:s,:prev,:t)"), {"w": workspace_id, "a": body["agent_id"], "d": body["domain"], "r": revision, "p": protected, "s": digest, "prev": previous, "t": now})
        return {**payload, "state_sha256": digest}

    def latest_world_state(self, workspace_id: str, agent_id: str, domain: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT payload_json,state_sha256 FROM adaptive_world_state WHERE workspace_id=:w AND agent_id=:a AND domain=:d ORDER BY revision DESC LIMIT 1"), {"w": workspace_id, "a": agent_id, "d": domain}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="adaptive-world-state")
        return {**payload, "state_sha256": row["state_sha256"]}

    def create_learning(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        learning_id = "learn_" + uuid.uuid4().hex[:20]
        return self._append_learning(workspace_id, learning_id, "CANDIDATE", body, None)

    def _append_learning(self, workspace_id: str, learning_id: str, status: str, body: dict[str, Any], previous_sha: str | None) -> dict[str, Any]:
        now = int(time.time())
        history = self.learning_history(workspace_id, learning_id)
        revision = 1 if not history else int(history[-1]["revision"]) + 1
        improvement = round(float(body["candidate_score"]) - float(body["baseline_score"]), 10)
        derived_skill_id = f"adaptive.{learning_id}"
        payload = {**body, "learning_id": learning_id, "revision": revision, "status": status, "improvement": improvement, "derived_skill_id": derived_skill_id, "previous_sha256": previous_sha, "created_at": now}
        digest = _sha({k: v for k, v in payload.items() if k != "created_at"})
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="adaptive-learning")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO adaptive_learning(learning_id,workspace_id,revision,status,payload_json,learning_sha256,previous_sha256,created_at) VALUES (:id,:w,:r,:st,:p,:s,:prev,:t)"), {"id": learning_id, "w": workspace_id, "r": revision, "st": status, "p": protected, "s": digest, "prev": previous_sha, "t": now})
        return {**payload, "learning_sha256": digest}

    def get_learning(self, workspace_id: str, learning_id: str) -> dict[str, Any] | None:
        history = self.learning_history(workspace_id, learning_id)
        return history[-1] if history else None

    def learning_history(self, workspace_id: str, learning_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT payload_json,learning_sha256 FROM adaptive_learning WHERE workspace_id=:w AND learning_id=:id ORDER BY revision"), {"w": workspace_id, "id": learning_id}).mappings().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="adaptive-learning")
            out.append({**payload, "learning_sha256": row["learning_sha256"]})
        return out

    def transition_learning(self, workspace_id: str, learning_id: str, status: str) -> dict[str, Any] | None:
        current = self.get_learning(workspace_id, learning_id)
        if current is None:
            return None
        base = {k: current[k] for k in ["agent_id","source_domain","capability","procedure","evidence_refs","required_tool_ids","risk_tier","baseline_score","candidate_score","minimum_improvement"]}
        return self._append_learning(workspace_id, learning_id, status, base, current["learning_sha256"])

    def upsert_strategy(self, workspace_id: str, strategy: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM adaptive_strategies WHERE workspace_id=:w AND strategy_id=:id"), {"w": workspace_id, "id": strategy["strategy_id"]})
            conn.execute(text("INSERT INTO adaptive_strategies(workspace_id,strategy_id,profile_json,updated_at) VALUES (:w,:id,:p,:t)"), {"w": workspace_id, "id": strategy["strategy_id"], "p": _canonical(strategy), "t": now})
        return {**strategy, "updated_at": now}

    def list_strategies(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT profile_json,updated_at FROM adaptive_strategies WHERE workspace_id=:w ORDER BY strategy_id"), {"w": workspace_id}).mappings().all()
        return [{**json.loads(row["profile_json"]), "updated_at": int(row["updated_at"])} for row in rows]

    def create_transfer(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        transfer_id = "xfer_" + uuid.uuid4().hex[:20]
        now = int(time.time())
        body = {"transfer_id": transfer_id, **payload, "status": "PROPOSED"}
        digest = _sha(body)
        protected = VAULT.encrypt_json(body, workspace_id=workspace_id, purpose="adaptive-transfer")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO adaptive_transfers(transfer_id,workspace_id,payload_json,transfer_sha256,created_at) VALUES (:id,:w,:p,:s,:t)"), {"id": transfer_id, "w": workspace_id, "p": protected, "s": digest, "t": now})
        return {**body, "transfer_sha256": digest}


ADAPTIVE_STORE = AdaptiveStore()
