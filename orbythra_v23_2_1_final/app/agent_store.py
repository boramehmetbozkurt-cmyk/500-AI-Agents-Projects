from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import text

from app.store import STORE
from app.vault import VAULT


class AgentStore:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS agent_profiles (workspace_id TEXT NOT NULL, agent_id TEXT NOT NULL, profile_json TEXT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, agent_id))""",
            """CREATE TABLE IF NOT EXISTS agent_tools (workspace_id TEXT NOT NULL, tool_id TEXT NOT NULL, profile_json TEXT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, tool_id))""",
            """CREATE TABLE IF NOT EXISTS agent_runs (run_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, objective_json TEXT NOT NULL, supervisor_agent_id TEXT NOT NULL, participant_agent_ids_json TEXT NOT NULL, max_actions BIGINT NOT NULL, action_count BIGINT NOT NULL, status TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_workspace ON agent_runs(workspace_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS agent_actions (action_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, run_id TEXT, agent_id TEXT NOT NULL, tool_id TEXT NOT NULL, intent_digest TEXT NOT NULL, intended_effect_digest TEXT NOT NULL, policy_snapshot_sha256 TEXT NOT NULL, request_json TEXT NOT NULL, authorization_json TEXT, decision TEXT NOT NULL, status TEXT NOT NULL, reasons_json TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_agent_actions_workspace_run ON agent_actions(workspace_id, run_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_agent_actions_workspace_agent ON agent_actions(workspace_id, agent_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS agent_outcomes (outcome_id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE, workspace_id TEXT NOT NULL, status TEXT NOT NULL, expected_effect_digest TEXT NOT NULL, actual_effect_digest TEXT NOT NULL, outcome_json TEXT NOT NULL, receipt_json TEXT NOT NULL, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_agent_outcomes_workspace ON agent_outcomes(workspace_id, created_at DESC)",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)

    def upsert_agent(self, workspace_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM agent_profiles WHERE workspace_id=:workspace_id AND agent_id=:agent_id"), {"workspace_id": workspace_id, "agent_id": profile["agent_id"]})
            conn.execute(text("INSERT INTO agent_profiles(workspace_id,agent_id,profile_json,updated_at) VALUES (:workspace_id,:agent_id,:profile_json,:updated_at)"), {"workspace_id": workspace_id, "agent_id": profile["agent_id"], "profile_json": self._canonical(profile), "updated_at": now})
        return {**profile, "updated_at": now}

    def get_agent(self, workspace_id: str, agent_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT profile_json,updated_at FROM agent_profiles WHERE workspace_id=:workspace_id AND agent_id=:agent_id"), {"workspace_id": workspace_id, "agent_id": agent_id}).mappings().first()
        if row is None:
            return None
        return {**json.loads(row["profile_json"]), "updated_at": int(row["updated_at"])}

    def list_agents(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT profile_json,updated_at FROM agent_profiles WHERE workspace_id=:workspace_id ORDER BY agent_id"), {"workspace_id": workspace_id}).mappings().all()
        return [{**json.loads(row["profile_json"]), "updated_at": int(row["updated_at"])} for row in rows]

    def upsert_tool(self, workspace_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM agent_tools WHERE workspace_id=:workspace_id AND tool_id=:tool_id"), {"workspace_id": workspace_id, "tool_id": profile["tool_id"]})
            conn.execute(text("INSERT INTO agent_tools(workspace_id,tool_id,profile_json,updated_at) VALUES (:workspace_id,:tool_id,:profile_json,:updated_at)"), {"workspace_id": workspace_id, "tool_id": profile["tool_id"], "profile_json": self._canonical(profile), "updated_at": now})
        return {**profile, "updated_at": now}

    def get_tool(self, workspace_id: str, tool_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT profile_json,updated_at FROM agent_tools WHERE workspace_id=:workspace_id AND tool_id=:tool_id"), {"workspace_id": workspace_id, "tool_id": tool_id}).mappings().first()
        if row is None:
            return None
        return {**json.loads(row["profile_json"]), "updated_at": int(row["updated_at"])}

    def list_tools(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT profile_json,updated_at FROM agent_tools WHERE workspace_id=:workspace_id ORDER BY tool_id"), {"workspace_id": workspace_id}).mappings().all()
        return [{**json.loads(row["profile_json"]), "updated_at": int(row["updated_at"])} for row in rows]

    def create_run(self, workspace_id: str, *, objective: str, supervisor_agent_id: str, participant_agent_ids: list[str], max_actions: int) -> dict[str, Any]:
        run_id = "run_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        protected_objective = VAULT.encrypt_json({"objective": objective}, workspace_id=workspace_id, purpose="agent-run-objective")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO agent_runs(run_id,workspace_id,objective_json,supervisor_agent_id,participant_agent_ids_json,max_actions,action_count,status,created_at,updated_at) VALUES (:run_id,:workspace_id,:objective_json,:supervisor_agent_id,:participants,:max_actions,0,'ACTIVE',:created_at,:updated_at)"""), {"run_id": run_id, "workspace_id": workspace_id, "objective_json": protected_objective, "supervisor_agent_id": supervisor_agent_id, "participants": self._canonical(participant_agent_ids), "max_actions": max_actions, "created_at": now, "updated_at": now})
        return {"run_id": run_id, "objective": objective, "supervisor_agent_id": supervisor_agent_id, "participant_agent_ids": participant_agent_ids, "max_actions": max_actions, "action_count": 0, "status": "ACTIVE", "created_at": now, "updated_at": now}

    def get_run(self, workspace_id: str, run_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM agent_runs WHERE workspace_id=:workspace_id AND run_id=:run_id"), {"workspace_id": workspace_id, "run_id": run_id}).mappings().first()
        if row is None:
            return None
        objective = VAULT.decrypt_json(row["objective_json"], workspace_id=workspace_id, purpose="agent-run-objective")
        return {"run_id": row["run_id"], "objective": objective.get("objective", ""), "supervisor_agent_id": row["supervisor_agent_id"], "participant_agent_ids": json.loads(row["participant_agent_ids_json"]), "max_actions": int(row["max_actions"]), "action_count": int(row["action_count"]), "status": row["status"], "created_at": int(row["created_at"]), "updated_at": int(row["updated_at"])}

    def set_run_status(self, workspace_id: str, run_id: str, status: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(text("UPDATE agent_runs SET status=:status,updated_at=:updated_at WHERE workspace_id=:workspace_id AND run_id=:run_id"), {"status": status, "updated_at": int(time.time()), "workspace_id": workspace_id, "run_id": run_id})
        return bool(result.rowcount)

    def create_action(self, workspace_id: str, *, request_data: dict[str, Any], decision: str, status: str, reasons: list[str], intent_digest: str, intended_effect_digest: str, policy_snapshot_sha256: str, authorization_envelope: dict[str, Any] | None) -> dict[str, Any]:
        action_id = "act_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        run_id = request_data.get("run_id")
        protected_request = VAULT.encrypt_json(request_data, workspace_id=workspace_id, purpose="agent-action")
        protected_authorization = None if authorization_envelope is None else VAULT.encrypt_json(authorization_envelope, workspace_id=workspace_id, purpose="agent-authorization")
        with self.engine.begin() as conn:
            if run_id:
                row = conn.execute(text("SELECT max_actions,action_count,status FROM agent_runs WHERE workspace_id=:workspace_id AND run_id=:run_id"), {"workspace_id": workspace_id, "run_id": run_id}).mappings().first()
                if row is None:
                    raise ValueError("agent_run_not_found")
                if row["status"] != "ACTIVE":
                    raise ValueError("agent_run_not_active")
                if int(row["action_count"]) >= int(row["max_actions"]):
                    raise ValueError("agent_run_action_limit_reached")
                conn.execute(text("UPDATE agent_runs SET action_count=action_count+1,updated_at=:updated_at WHERE workspace_id=:workspace_id AND run_id=:run_id"), {"updated_at": now, "workspace_id": workspace_id, "run_id": run_id})
            conn.execute(text("""INSERT INTO agent_actions(action_id,workspace_id,run_id,agent_id,tool_id,intent_digest,intended_effect_digest,policy_snapshot_sha256,request_json,authorization_json,decision,status,reasons_json,created_at,updated_at) VALUES (:action_id,:workspace_id,:run_id,:agent_id,:tool_id,:intent_digest,:effect_digest,:policy_snapshot,:request_json,:authorization_json,:decision,:status,:reasons_json,:created_at,:updated_at)"""), {"action_id": action_id, "workspace_id": workspace_id, "run_id": run_id, "agent_id": request_data["agent_id"], "tool_id": request_data["tool_id"], "intent_digest": intent_digest, "effect_digest": intended_effect_digest, "policy_snapshot": policy_snapshot_sha256, "request_json": protected_request, "authorization_json": protected_authorization, "decision": decision, "status": status, "reasons_json": self._canonical(reasons), "created_at": now, "updated_at": now})
        return {"action_id": action_id, "decision": decision, "status": status, "reasons": reasons, "intent_digest": intent_digest, "intended_effect_digest": intended_effect_digest, "policy_snapshot_sha256": policy_snapshot_sha256, "authorization_envelope": authorization_envelope, "created_at": now, "updated_at": now}

    def get_action(self, workspace_id: str, action_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM agent_actions WHERE workspace_id=:workspace_id AND action_id=:action_id"), {"workspace_id": workspace_id, "action_id": action_id}).mappings().first()
        if row is None:
            return None
        request_data = VAULT.decrypt_json(row["request_json"], workspace_id=workspace_id, purpose="agent-action")
        authorization = None if row["authorization_json"] is None else VAULT.decrypt_json(row["authorization_json"], workspace_id=workspace_id, purpose="agent-authorization")
        return {"action_id": row["action_id"], "run_id": row["run_id"], "agent_id": row["agent_id"], "tool_id": row["tool_id"], "intent_digest": row["intent_digest"], "intended_effect_digest": row["intended_effect_digest"], "policy_snapshot_sha256": row["policy_snapshot_sha256"], "request": request_data, "authorization_envelope": authorization, "decision": row["decision"], "status": row["status"], "reasons": json.loads(row["reasons_json"]), "created_at": int(row["created_at"]), "updated_at": int(row["updated_at"])}

    def update_action_authorization(self, workspace_id: str, action_id: str, *, request_data: dict[str, Any] | None, decision: str, status: str, reasons: list[str], policy_snapshot_sha256: str, authorization_envelope: dict[str, Any] | None) -> dict[str, Any] | None:
        now = int(time.time())
        protected_authorization = None if authorization_envelope is None else VAULT.encrypt_json(authorization_envelope, workspace_id=workspace_id, purpose="agent-authorization")
        protected_request = None if request_data is None else VAULT.encrypt_json(request_data, workspace_id=workspace_id, purpose="agent-action")
        with self.engine.begin() as conn:
            if protected_request is None:
                result = conn.execute(text("UPDATE agent_actions SET decision=:decision,status=:status,reasons_json=:reasons_json,policy_snapshot_sha256=:policy_snapshot,authorization_json=:authorization_json,updated_at=:updated_at WHERE workspace_id=:workspace_id AND action_id=:action_id"), {"decision": decision, "status": status, "reasons_json": self._canonical(reasons), "policy_snapshot": policy_snapshot_sha256, "authorization_json": protected_authorization, "updated_at": now, "workspace_id": workspace_id, "action_id": action_id})
            else:
                result = conn.execute(text("UPDATE agent_actions SET request_json=:request_json,decision=:decision,status=:status,reasons_json=:reasons_json,policy_snapshot_sha256=:policy_snapshot,authorization_json=:authorization_json,updated_at=:updated_at WHERE workspace_id=:workspace_id AND action_id=:action_id"), {"request_json": protected_request, "decision": decision, "status": status, "reasons_json": self._canonical(reasons), "policy_snapshot": policy_snapshot_sha256, "authorization_json": protected_authorization, "updated_at": now, "workspace_id": workspace_id, "action_id": action_id})
        return None if not result.rowcount else self.get_action(workspace_id, action_id)

    def create_outcome(self, workspace_id: str, action_id: str, *, status: str, expected_effect_digest: str, actual_effect_digest: str, outcome_data: dict[str, Any], signed_receipt: dict[str, Any]) -> dict[str, Any]:
        outcome_id = "out_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        protected_outcome = VAULT.encrypt_json(outcome_data, workspace_id=workspace_id, purpose="agent-outcome")
        protected_receipt = VAULT.encrypt_json(signed_receipt, workspace_id=workspace_id, purpose="agent-outcome-receipt")
        with self.engine.begin() as conn:
            existing = conn.execute(text("SELECT outcome_id FROM agent_outcomes WHERE workspace_id=:workspace_id AND action_id=:action_id"), {"workspace_id": workspace_id, "action_id": action_id}).first()
            if existing is not None:
                raise ValueError("agent_outcome_already_recorded")
            conn.execute(text("""INSERT INTO agent_outcomes(outcome_id,action_id,workspace_id,status,expected_effect_digest,actual_effect_digest,outcome_json,receipt_json,created_at) VALUES (:outcome_id,:action_id,:workspace_id,:status,:expected_effect_digest,:actual_effect_digest,:outcome_json,:receipt_json,:created_at)"""), {"outcome_id": outcome_id, "action_id": action_id, "workspace_id": workspace_id, "status": status, "expected_effect_digest": expected_effect_digest, "actual_effect_digest": actual_effect_digest, "outcome_json": protected_outcome, "receipt_json": protected_receipt, "created_at": now})
            conn.execute(text("UPDATE agent_actions SET status=:status,updated_at=:updated_at WHERE workspace_id=:workspace_id AND action_id=:action_id"), {"status": status, "updated_at": now, "workspace_id": workspace_id, "action_id": action_id})
        return {"outcome_id": outcome_id, "action_id": action_id, "status": status, "expected_effect_digest": expected_effect_digest, "actual_effect_digest": actual_effect_digest, "effect_match": expected_effect_digest == actual_effect_digest, "signed_receipt": signed_receipt, "created_at": now}

    def list_run_actions(self, workspace_id: str, run_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT action_id,agent_id,tool_id,status,decision,policy_snapshot_sha256,created_at,updated_at FROM agent_actions WHERE workspace_id=:workspace_id AND run_id=:run_id ORDER BY created_at,action_id"), {"workspace_id": workspace_id, "run_id": run_id}).mappings().all()
        return [{"action_id": row["action_id"], "agent_id": row["agent_id"], "tool_id": row["tool_id"], "status": row["status"], "decision": row["decision"], "policy_snapshot_sha256": row["policy_snapshot_sha256"], "created_at": int(row["created_at"]), "updated_at": int(row["updated_at"])} for row in rows]


AGENT_STORE = AgentStore()
