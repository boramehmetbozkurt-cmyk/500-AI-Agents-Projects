from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from sqlalchemy import text

from app.store import STORE


class EnterpriseStore:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS enterprise_providers (workspace_id TEXT NOT NULL, provider_id TEXT NOT NULL, profile_json TEXT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, provider_id))""",
            """CREATE TABLE IF NOT EXISTS enterprise_policies (workspace_id TEXT NOT NULL, policy_id TEXT NOT NULL, policy_json TEXT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, policy_id))""",
            """CREATE TABLE IF NOT EXISTS enterprise_policy_revisions (workspace_id TEXT NOT NULL, policy_id TEXT NOT NULL, revision BIGINT NOT NULL, sha256 TEXT NOT NULL, policy_json TEXT NOT NULL, created_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, policy_id, revision))""",
            "CREATE INDEX IF NOT EXISTS idx_policy_revision_workspace ON enterprise_policy_revisions(workspace_id, policy_id, revision DESC)",
            """CREATE TABLE IF NOT EXISTS enterprise_identities (workspace_id TEXT NOT NULL, subject TEXT NOT NULL, active INTEGER NOT NULL, role_override TEXT, display_name TEXT, updated_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, subject))""",
            "CREATE INDEX IF NOT EXISTS idx_identity_workspace_active ON enterprise_identities(workspace_id, active)",
            """CREATE TABLE IF NOT EXISTS benchmark_runs (run_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, benchmark_name TEXT NOT NULL, model_label TEXT NOT NULL, result_json TEXT NOT NULL, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_benchmark_workspace_created ON benchmark_runs(workspace_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS usage_events (event_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, event_type TEXT NOT NULL, units BIGINT NOT NULL, request_reference TEXT, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_usage_workspace_created ON usage_events(workspace_id, created_at DESC)",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> str:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    def upsert_provider(self, workspace_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        payload = self._canonical(profile)
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM enterprise_providers WHERE workspace_id=:workspace_id AND provider_id=:provider_id"), {"workspace_id": workspace_id, "provider_id": profile["provider_id"]})
            conn.execute(text("INSERT INTO enterprise_providers(workspace_id, provider_id, profile_json, updated_at) VALUES (:workspace_id,:provider_id,:profile_json,:updated_at)"), {"workspace_id": workspace_id, "provider_id": profile["provider_id"], "profile_json": payload, "updated_at": now})
        return {**profile, "updated_at": now}

    def list_providers(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT profile_json, updated_at FROM enterprise_providers WHERE workspace_id=:workspace_id ORDER BY provider_id"), {"workspace_id": workspace_id}).mappings().all()
        return [{**json.loads(row["profile_json"]), "updated_at": row["updated_at"]} for row in rows]

    def get_provider(self, workspace_id: str, provider_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT profile_json, updated_at FROM enterprise_providers WHERE workspace_id=:workspace_id AND provider_id=:provider_id"), {"workspace_id": workspace_id, "provider_id": provider_id}).mappings().first()
        if row is None:
            return None
        return {**json.loads(row["profile_json"]), "updated_at": row["updated_at"]}

    def upsert_policy(self, workspace_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        payload = self._canonical(policy)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.engine.begin() as conn:
            current = conn.execute(text("SELECT COALESCE(MAX(revision),0) FROM enterprise_policy_revisions WHERE workspace_id=:workspace_id AND policy_id=:policy_id"), {"workspace_id": workspace_id, "policy_id": policy["policy_id"]}).scalar_one()
            revision = int(current) + 1
            conn.execute(text("INSERT INTO enterprise_policy_revisions(workspace_id, policy_id, revision, sha256, policy_json, created_at) VALUES (:workspace_id,:policy_id,:revision,:sha256,:policy_json,:created_at)"), {"workspace_id": workspace_id, "policy_id": policy["policy_id"], "revision": revision, "sha256": digest, "policy_json": payload, "created_at": now})
            conn.execute(text("DELETE FROM enterprise_policies WHERE workspace_id=:workspace_id AND policy_id=:policy_id"), {"workspace_id": workspace_id, "policy_id": policy["policy_id"]})
            conn.execute(text("INSERT INTO enterprise_policies(workspace_id, policy_id, policy_json, updated_at) VALUES (:workspace_id,:policy_id,:policy_json,:updated_at)"), {"workspace_id": workspace_id, "policy_id": policy["policy_id"], "policy_json": payload, "updated_at": now})
        return {**policy, "updated_at": now, "revision": revision, "sha256": digest}

    def get_policy(self, workspace_id: str, policy_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT policy_json, updated_at FROM enterprise_policies WHERE workspace_id=:workspace_id AND policy_id=:policy_id"), {"workspace_id": workspace_id, "policy_id": policy_id}).mappings().first()
        if row is None:
            return None
        return {**json.loads(row["policy_json"]), "updated_at": row["updated_at"]}

    def policy_history(self, workspace_id: str, policy_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT revision, sha256, policy_json, created_at FROM enterprise_policy_revisions WHERE workspace_id=:workspace_id AND policy_id=:policy_id ORDER BY revision DESC"), {"workspace_id": workspace_id, "policy_id": policy_id}).mappings().all()
        return [{"policy_id": policy_id, "revision": int(row["revision"]), "sha256": str(row["sha256"]), "policy": json.loads(row["policy_json"]), "created_at": int(row["created_at"])} for row in rows]

    def activate_policy_revision(self, workspace_id: str, policy_id: str, revision: int) -> dict[str, Any] | None:
        now = int(time.time())
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT policy_json FROM enterprise_policy_revisions WHERE workspace_id=:workspace_id AND policy_id=:policy_id AND revision=:revision"), {"workspace_id": workspace_id, "policy_id": policy_id, "revision": revision}).first()
            if row is None:
                return None
            payload = str(row[0])
            conn.execute(text("DELETE FROM enterprise_policies WHERE workspace_id=:workspace_id AND policy_id=:policy_id"), {"workspace_id": workspace_id, "policy_id": policy_id})
            conn.execute(text("INSERT INTO enterprise_policies(workspace_id, policy_id, policy_json, updated_at) VALUES (:workspace_id,:policy_id,:policy_json,:updated_at)"), {"workspace_id": workspace_id, "policy_id": policy_id, "policy_json": payload, "updated_at": now})
        return {**json.loads(payload), "updated_at": now}

    def upsert_identity(self, workspace_id: str, identity: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM enterprise_identities WHERE workspace_id=:workspace_id AND subject=:subject"), {"workspace_id": workspace_id, "subject": identity["subject"]})
            conn.execute(text("INSERT INTO enterprise_identities(workspace_id, subject, active, role_override, display_name, updated_at) VALUES (:workspace_id,:subject,:active,:role_override,:display_name,:updated_at)"), {"workspace_id": workspace_id, "subject": identity["subject"], "active": 1 if identity.get("active", True) else 0, "role_override": identity.get("role_override"), "display_name": identity.get("display_name"), "updated_at": now})
        return {**identity, "updated_at": now}

    def list_identities(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT subject, active, role_override, display_name, updated_at FROM enterprise_identities WHERE workspace_id=:workspace_id ORDER BY subject"), {"workspace_id": workspace_id}).mappings().all()
        return [{"subject": str(row["subject"]), "active": bool(row["active"]), "role_override": row["role_override"], "display_name": row["display_name"], "updated_at": int(row["updated_at"])} for row in rows]

    def get_identity(self, workspace_id: str, subject: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT subject, active, role_override, display_name, updated_at FROM enterprise_identities WHERE workspace_id=:workspace_id AND subject=:subject"), {"workspace_id": workspace_id, "subject": subject}).mappings().first()
        if row is None:
            return None
        return {"subject": str(row["subject"]), "active": bool(row["active"]), "role_override": row["role_override"], "display_name": row["display_name"], "updated_at": int(row["updated_at"])}

    def save_benchmark(self, workspace_id: str, result: dict[str, Any]) -> dict[str, Any]:
        run_id = result.get("run_id") or "bmk_" + uuid.uuid4().hex[:20]
        created_at = int(time.time())
        stored = {**result, "run_id": run_id, "created_at": created_at}
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO benchmark_runs(run_id, workspace_id, benchmark_name, model_label, result_json, created_at) VALUES (:run_id,:workspace_id,:benchmark_name,:model_label,:result_json,:created_at)"), {"run_id": run_id, "workspace_id": workspace_id, "benchmark_name": stored["benchmark_name"], "model_label": stored["model_label"], "result_json": self._canonical(stored), "created_at": created_at})
        return stored

    def get_benchmark(self, workspace_id: str, run_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT result_json FROM benchmark_runs WHERE workspace_id=:workspace_id AND run_id=:run_id"), {"workspace_id": workspace_id, "run_id": run_id}).first()
        return None if row is None else json.loads(row[0])

    def list_benchmarks(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT result_json FROM benchmark_runs WHERE workspace_id=:workspace_id ORDER BY created_at DESC LIMIT :limit"), {"workspace_id": workspace_id, "limit": max(1, min(1000, int(limit)))}).all()
        return [json.loads(row[0]) for row in rows]

    def record_usage(self, workspace_id: str, event_type: str, units: int, request_reference: str | None) -> str:
        event_id = "use_" + uuid.uuid4().hex[:20]
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO usage_events(event_id, workspace_id, event_type, units, request_reference, created_at) VALUES (:event_id,:workspace_id,:event_type,:units,:request_reference,:created_at)"), {"event_id": event_id, "workspace_id": workspace_id, "event_type": event_type, "units": units, "request_reference": request_reference, "created_at": int(time.time())})
        return event_id

    def usage_report(self, workspace_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT event_type, COUNT(*) AS event_count, COALESCE(SUM(units),0) AS units FROM usage_events WHERE workspace_id=:workspace_id GROUP BY event_type"), {"workspace_id": workspace_id}).mappings().all()
        by_type = {str(row["event_type"]): int(row["units"]) for row in rows}
        return {"workspace_id": workspace_id, "total_events": sum(int(row["event_count"]) for row in rows), "total_units": sum(int(row["units"]) for row in rows), "by_type": by_type, "generated_at": int(time.time())}


ENTERPRISE_STORE = EnterpriseStore()
