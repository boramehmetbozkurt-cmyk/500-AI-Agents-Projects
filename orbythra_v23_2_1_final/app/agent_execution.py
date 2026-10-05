from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.agent_control_plane_v15 import CONTROL_PLANE_V15
from app.agent_models import AgentActionRequest, AgentExecutionCheckResponse
from app.agent_store import AGENT_STORE
from app.agents import _evaluate, _intent_digest
from app.crypto_core import CryptoConfigurationError, CryptoValidationError, open_envelope
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v2/agents", tags=["agents-v2"])
_REQUIRE_OPERATOR = require_minimum_role("operator")


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object] | None = None) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "agents-v2-execution"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **(metadata or {})},
    )


def _revoke(principal: Principal, action_id: str, current: dict, reasons: list[str], snapshot: str) -> None:
    AGENT_STORE.update_action_authorization(
        principal.workspace_id,
        action_id,
        request_data=None,
        decision="BLOCK",
        status="POLICY_REVOKED",
        reasons=reasons,
        policy_snapshot_sha256=snapshot,
        authorization_envelope=None,
    )


@router.post("/actions/{action_id}/execution-check", response_model=AgentExecutionCheckResponse)
def execution_check(action_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentExecutionCheckResponse:
    current = AGENT_STORE.get_action(principal.workspace_id, action_id)
    if current is None:
        raise HTTPException(status_code=404, detail="agent_action_not_found")
    if current["status"] != "AUTHORIZED":
        raise HTTPException(status_code=409, detail="agent_action_not_authorized")

    action_body = AgentActionRequest(**current["request"])

    # V15 is an execution-time control plane layered on top of the existing V2
    # cryptographic authorization. A kill/suspend/emergency decision is checked
    # immediately before execution, so an older authorization cannot bypass it.
    try:
        control = CONTROL_PLANE_V15.assert_execution_allowed(
            principal.workspace_id,
            action_body.agent_id,
            action_body.tool_id,
            action_body.operation,
            action_body.risk_tier,
        )
    except ValueError as exc:
        reason = "v15_control_plane:" + str(exc)
        _revoke(principal, action_id, current, [reason], current["policy_snapshot_sha256"])
        _audit(
            request,
            principal,
            "agent_execution_check",
            "POLICY_REVOKED",
            {"action_id": action_id, "agent_id": action_body.agent_id, "reason": reason},
        )
        raise HTTPException(status_code=409, detail=reason) from exc

    decision, reasons, _risk, snapshot, _signed_required = _evaluate(principal.workspace_id, action_body)
    if decision != "ALLOW" or snapshot != current["policy_snapshot_sha256"]:
        revocation_reasons = list(reasons)
        if snapshot != current["policy_snapshot_sha256"]:
            revocation_reasons.append("policy_snapshot_changed")
        _revoke(principal, action_id, current, list(dict.fromkeys(revocation_reasons)), snapshot)
        _audit(request, principal, "agent_execution_check", "POLICY_REVOKED", {"action_id": action_id})
        raise HTTPException(status_code=409, detail="agent_authorization_no_longer_valid")

    envelope = current.get("authorization_envelope")
    if not isinstance(envelope, dict):
        _revoke(principal, action_id, current, ["authorization_envelope_missing"], snapshot)
        raise HTTPException(status_code=409, detail="agent_authorization_missing")

    try:
        opened = open_envelope(
            envelope,
            expected_workspace_id=principal.workspace_id,
            expected_intent_digest=current["intent_digest"],
        )
    except (CryptoConfigurationError, CryptoValidationError) as exc:
        reason = str(exc)
        _revoke(principal, action_id, current, ["authorization_invalid:" + reason], snapshot)
        _audit(request, principal, "agent_execution_check", "POLICY_REVOKED", {"action_id": action_id, "reason": reason})
        raise HTTPException(status_code=409, detail="agent_authorization_invalid:" + reason) from exc

    payload = opened["content"].get("payload") or {}
    expected_payload = {
        "kind": "agent-action-authorization",
        "policy_snapshot_sha256": snapshot,
        "tool_id": action_body.tool_id,
        "operation": action_body.operation,
    }
    for key, expected in expected_payload.items():
        if payload.get(key) != expected:
            _revoke(principal, action_id, current, ["authorization_payload_mismatch:" + key], snapshot)
            _audit(request, principal, "agent_execution_check", "POLICY_REVOKED", {"action_id": action_id, "field": key})
            raise HTTPException(status_code=409, detail="agent_authorization_payload_mismatch:" + key)

    if _intent_digest(action_body, principal.workspace_id) != current["intent_digest"]:
        _revoke(principal, action_id, current, ["authorization_intent_mismatch"], snapshot)
        raise HTTPException(status_code=409, detail="agent_authorization_intent_mismatch")

    expires_at = int(opened["header"].get("expires_at") or 0)
    _audit(
        request,
        principal,
        "agent_execution_check",
        "EXECUTABLE",
        {
            "action_id": action_id,
            "expires_at": expires_at,
            "policy_snapshot_sha256": snapshot,
            "v15_control_plane_registered": bool(control["control_plane_registered"]),
            "v15_control_epoch": int(control["epoch"]),
            "v15_control_policy_sha256": control["policy_sha256"],
        },
    )
    return AgentExecutionCheckResponse(
        action_id=action_id,
        executable=True,
        intent_digest=current["intent_digest"],
        policy_snapshot_sha256=snapshot,
        authorization_expires_at=expires_at,
        authorization_signer_verified=bool(opened["signer_verified"]),
        tool_id=action_body.tool_id,
        operation=action_body.operation,
    )
