from __future__ import annotations

import hashlib
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/agent-control", tags=["v15-agent-control"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

AgentControlState = Literal["ACTIVE", "SUSPENDED", "KILLED"]
_RISK_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class AgentControlPolicy(BaseModel):
    state: AgentControlState = "ACTIVE"
    allowed_tool_ids: list[str] = Field(default_factory=list, max_length=500)
    allowed_operations: list[str] = Field(default_factory=list, max_length=500)
    maximum_risk_tier: Literal["low", "moderate", "high", "critical"] = "critical"
    expires_at: int | None = None
    reason: str = Field(default="", max_length=1000)


class AgentControlRecord(BaseModel):
    workspace_id: str
    agent_id: str
    state: AgentControlState
    allowed_tool_ids: list[str]
    allowed_operations: list[str]
    maximum_risk_tier: str
    expires_at: int | None
    reason: str
    epoch: int
    updated_at: int
    policy_sha256: str


class AgentStateRequest(BaseModel):
    state: AgentControlState
    reason: str = Field(min_length=1, max_length=1000)


class WorkspaceEmergencyRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=1000)


class AgentControlPlaneV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS agent_control_v15(
                    workspace_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    allowed_tool_ids_json TEXT NOT NULL,
                    allowed_operations_json TEXT NOT NULL,
                    maximum_risk_tier TEXT NOT NULL,
                    expires_at BIGINT,
                    reason TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    updated_at BIGINT NOT NULL,
                    policy_sha256 TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,agent_id)
                    )"""
                )
            )

    @staticmethod
    def _normalize(values: list[str]) -> list[str]:
        return sorted({item.strip() for item in values if item.strip()})

    def _policy_hash(
        self,
        workspace_id: str,
        agent_id: str,
        state: str,
        tools: list[str],
        operations: list[str],
        maximum_risk_tier: str,
        expires_at: int | None,
        epoch: int,
    ) -> str:
        return _hash(
            {
                "domain": "ORBYTHRA-V15-AGENT-CONTROL",
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "state": state,
                "allowed_tool_ids": tools,
                "allowed_operations": operations,
                "maximum_risk_tier": maximum_risk_tier,
                "expires_at": expires_at,
                "epoch": epoch,
            }
        )

    def put(self, workspace_id: str, agent_id: str, policy: AgentControlPolicy, *, now: int | None = None) -> AgentControlRecord:
        updated_at = int(time.time()) if now is None else int(now)
        tools = self._normalize(policy.allowed_tool_ids)
        operations = self._normalize(policy.allowed_operations)
        if policy.expires_at is not None and policy.expires_at <= updated_at:
            raise ValueError("agent_control_expiry_must_be_future")
        with STORE.engine.begin() as connection:
            existing = connection.execute(
                text("SELECT epoch FROM agent_control_v15 WHERE workspace_id=:w AND agent_id=:a"),
                {"w": workspace_id, "a": agent_id},
            ).first()
            epoch = (int(existing[0]) + 1) if existing else 1
            policy_sha = self._policy_hash(
                workspace_id,
                agent_id,
                policy.state,
                tools,
                operations,
                policy.maximum_risk_tier,
                policy.expires_at,
                epoch,
            )
            params = {
                "w": workspace_id,
                "a": agent_id,
                "state": policy.state,
                "tools": json.dumps(tools, separators=(",", ":")),
                "ops": json.dumps(operations, separators=(",", ":")),
                "risk": policy.maximum_risk_tier,
                "exp": policy.expires_at,
                "reason": policy.reason,
                "epoch": epoch,
                "updated": updated_at,
                "sha": policy_sha,
            }
            if existing:
                connection.execute(
                    text(
                        """UPDATE agent_control_v15 SET state=:state,allowed_tool_ids_json=:tools,
                        allowed_operations_json=:ops,maximum_risk_tier=:risk,expires_at=:exp,reason=:reason,
                        epoch=:epoch,updated_at=:updated,policy_sha256=:sha
                        WHERE workspace_id=:w AND agent_id=:a"""
                    ),
                    params,
                )
            else:
                connection.execute(
                    text(
                        """INSERT INTO agent_control_v15(
                        workspace_id,agent_id,state,allowed_tool_ids_json,allowed_operations_json,
                        maximum_risk_tier,expires_at,reason,epoch,updated_at,policy_sha256
                        ) VALUES(:w,:a,:state,:tools,:ops,:risk,:exp,:reason,:epoch,:updated,:sha)"""
                    ),
                    params,
                )
        record = self.get(workspace_id, agent_id)
        if record is None:
            raise RuntimeError("agent_control_not_persisted")
        return record

    def get(self, workspace_id: str, agent_id: str) -> AgentControlRecord | None:
        with STORE.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM agent_control_v15 WHERE workspace_id=:w AND agent_id=:a"),
                {"w": workspace_id, "a": agent_id},
            ).mappings().first()
        if row is None:
            return None
        return AgentControlRecord(
            workspace_id=row["workspace_id"],
            agent_id=row["agent_id"],
            state=row["state"],
            allowed_tool_ids=json.loads(row["allowed_tool_ids_json"]),
            allowed_operations=json.loads(row["allowed_operations_json"]),
            maximum_risk_tier=row["maximum_risk_tier"],
            expires_at=None if row["expires_at"] is None else int(row["expires_at"]),
            reason=row["reason"],
            epoch=int(row["epoch"]),
            updated_at=int(row["updated_at"]),
            policy_sha256=row["policy_sha256"],
        )

    def set_state(self, workspace_id: str, agent_id: str, state: AgentControlState, reason: str, *, now: int | None = None) -> AgentControlRecord:
        current = self.get(workspace_id, agent_id)
        policy = AgentControlPolicy(
            state=state,
            allowed_tool_ids=[] if current is None else current.allowed_tool_ids,
            allowed_operations=[] if current is None else current.allowed_operations,
            maximum_risk_tier="critical" if current is None else current.maximum_risk_tier,
            expires_at=None if current is None else current.expires_at,
            reason=reason,
        )
        return self.put(workspace_id, agent_id, policy, now=now)

    def set_workspace_emergency(self, workspace_id: str, enabled: bool, reason: str, *, now: int | None = None) -> AgentControlRecord:
        return self.set_state(workspace_id, "*", "KILLED" if enabled else "ACTIVE", reason, now=now)

    @staticmethod
    def _allowed(value: str, allowlist: list[str]) -> bool:
        return not allowlist or "*" in allowlist or value in allowlist

    def assert_execution_allowed(
        self,
        workspace_id: str,
        agent_id: str,
        tool_id: str,
        operation: str,
        risk_tier: str,
        *,
        now: int | None = None,
    ) -> dict[str, object]:
        current_time = int(time.time()) if now is None else int(now)
        workspace_control = self.get(workspace_id, "*")
        if workspace_control is not None and workspace_control.state != "ACTIVE":
            raise ValueError("workspace_agent_emergency_stop")
        record = self.get(workspace_id, agent_id)
        if record is None:
            return {"allowed": True, "control_plane_registered": False, "epoch": 0, "policy_sha256": None}
        if record.state == "KILLED":
            raise ValueError("agent_killed")
        if record.state == "SUSPENDED":
            raise ValueError("agent_suspended")
        if record.expires_at is not None and record.expires_at <= current_time:
            raise ValueError("agent_control_policy_expired")
        if not self._allowed(tool_id, record.allowed_tool_ids):
            raise ValueError("agent_tool_not_allowed_by_v15_control_plane")
        if not self._allowed(operation, record.allowed_operations):
            raise ValueError("agent_operation_not_allowed_by_v15_control_plane")
        if _RISK_ORDER.get(risk_tier, 99) > _RISK_ORDER.get(record.maximum_risk_tier, -1):
            raise ValueError("agent_risk_exceeds_v15_control_plane")
        return {
            "allowed": True,
            "control_plane_registered": True,
            "epoch": record.epoch,
            "policy_sha256": record.policy_sha256,
        }


CONTROL_PLANE_V15 = AgentControlPlaneV15()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "agent-control-v15"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata=metadata,
    )


@router.put("/agents/{agent_id}", response_model=AgentControlRecord)
def put_agent_control(agent_id: str, body: AgentControlPolicy, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> AgentControlRecord:
    if agent_id == "*":
        raise HTTPException(status_code=400, detail="reserved_agent_id")
    try:
        result = CONTROL_PLANE_V15.put(principal.workspace_id, agent_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, principal, "agent_control_v15_policy", result.state, {"agent_id": agent_id, "epoch": result.epoch, "policy_sha256": result.policy_sha256})
    return result


@router.post("/agents/{agent_id}/state", response_model=AgentControlRecord)
def set_agent_state(agent_id: str, body: AgentStateRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentControlRecord:
    if agent_id == "*":
        raise HTTPException(status_code=400, detail="reserved_agent_id")
    result = CONTROL_PLANE_V15.set_state(principal.workspace_id, agent_id, body.state, body.reason)
    _audit(request, principal, "agent_control_v15_state", result.state, {"agent_id": agent_id, "epoch": result.epoch, "reason": body.reason})
    return result


@router.post("/workspace-emergency", response_model=AgentControlRecord)
def workspace_emergency(body: WorkspaceEmergencyRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> AgentControlRecord:
    result = CONTROL_PLANE_V15.set_workspace_emergency(principal.workspace_id, body.enabled, body.reason)
    _audit(request, principal, "agent_control_v15_workspace_emergency", result.state, {"enabled": body.enabled, "epoch": result.epoch, "reason": body.reason})
    return result


@router.get("/agents/{agent_id}", response_model=AgentControlRecord)
def get_agent_control(agent_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> AgentControlRecord:
    record = CONTROL_PLANE_V15.get(principal.workspace_id, agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="agent_control_not_found")
    return record


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "per_agent_kill_switch": True,
        "workspace_emergency_stop": True,
        "policy_epoch_revocation": True,
        "tool_capability_allowlist": True,
        "operation_capability_allowlist": True,
        "risk_ceiling": True,
        "policy_expiry": True,
        "execution_time_enforcement_hook": True,
        "workspace_isolation": True,
        "legacy_unregistered_agent_behavior": "existing V2 policy remains authoritative until a V15 control record is created",
    }
