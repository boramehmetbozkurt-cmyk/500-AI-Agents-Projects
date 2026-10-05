from __future__ import annotations

import hashlib
import ipaddress
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.agent_models import (
    AgentActionRequest,
    AgentActionResponse,
    AgentAuthorizationRequest,
    AgentOutcomeRequest,
    AgentOutcomeResponse,
    AgentProfile,
    AgentRunResponse,
    AgentRunStartRequest,
    AgentSupervisionResponse,
    ToolProfile,
)
from app.agent_policy import evaluate_agent_policy
from app.agent_store import AGENT_STORE
from app.config import SETTINGS
from app.crypto_core import CryptoConfigurationError, CryptoValidationError, canonical_json, commitment, seal, verify_approvals
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v2/agents", tags=["agents-v2"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object] | None = None) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "agents-v2"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **(metadata or {})},
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _intent(body: AgentActionRequest, workspace_id: str) -> dict[str, Any]:
    return {
        "kind": "agent-action",
        "workspace_id": workspace_id,
        "run_id": body.run_id,
        "agent_id": body.agent_id,
        "tool_id": body.tool_id,
        "operation": body.operation,
        "parameters": body.parameters,
        "intended_effect": body.intended_effect,
        "risk_tier": body.risk_tier,
        "data_categories": sorted(set(body.data_categories)),
        "idempotency_key": body.idempotency_key,
    }


def _intent_digest(body: AgentActionRequest, workspace_id: str) -> str:
    # EffectSeal verifies approval proofs against the standard intent domain.
    # The explicit kind field above provides agent-action domain separation.
    return commitment(_intent(body, workspace_id), domain="intent")["sha256"]


def _external_endpoint_allowed(tool: ToolProfile) -> bool:
    if tool.protocol == "internal" or tool.endpoint_url is None:
        return True
    if SETTINGS.environment == "production" and tool.endpoint_url.scheme != "https":
        return False
    host = tool.endpoint_url.host or ""
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified)


def _load_profiles(workspace_id: str, body: AgentActionRequest) -> tuple[AgentProfile, ToolProfile]:
    agent_item = AGENT_STORE.get_agent(workspace_id, body.agent_id)
    if agent_item is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    tool_item = AGENT_STORE.get_tool(workspace_id, body.tool_id)
    if tool_item is None:
        raise HTTPException(status_code=404, detail="tool_not_found")
    return AgentProfile(**agent_item), ToolProfile(**tool_item)


def _policy_snapshot(agent: AgentProfile, tool: ToolProfile, effective_risk: str, run: dict[str, Any] | None) -> str:
    return _hash({
        "agent": agent.model_dump(mode="json"),
        "tool": tool.model_dump(mode="json"),
        "effective_risk": effective_risk,
        "run": None if run is None else {
            "run_id": run["run_id"],
            "supervisor_agent_id": run["supervisor_agent_id"],
            "participant_agent_ids": run["participant_agent_ids"],
            "max_actions": run["max_actions"],
            "status": run["status"],
        },
    })


def _evaluate(workspace_id: str, body: AgentActionRequest, *, validate_proofs: bool = True) -> tuple[str, list[str], str, str, bool]:
    agent, tool = _load_profiles(workspace_id, body)
    run: dict[str, Any] | None = None
    run_lookup_failed = False
    agent_action_count = 0
    if body.run_id:
        run = AGENT_STORE.get_run(workspace_id, body.run_id)
        run_lookup_failed = run is None
        if run is not None:
            agent_action_count = sum(1 for item in AGENT_STORE.list_run_actions(workspace_id, body.run_id) if item["agent_id"] == body.agent_id)

    base = evaluate_agent_policy(
        agent,
        tool,
        body,
        run=run,
        run_lookup_failed=run_lookup_failed,
        agent_action_count=agent_action_count,
        external_endpoint_allowed=_external_endpoint_allowed(tool),
    )
    blocks = list(base.reasons) if base.decision == "BLOCK" else []
    reviews = list(base.reasons) if base.decision == "REVIEW" else []
    intent_digest = _intent_digest(body, workspace_id)

    if validate_proofs and body.approvals:
        try:
            verify_approvals([item.model_dump(mode="json") for item in body.approvals], intent_digest=intent_digest, min_approvals=0)
        except (CryptoConfigurationError, CryptoValidationError) as exc:
            blocks.append(str(exc))

    if base.signed_approval_required:
        signed = [item.model_dump(mode="json") for item in body.approvals if item.proof_type in {"signature", "hybrid_signature"}]
        if signed and validate_proofs:
            try:
                verify_approvals(signed, intent_digest=intent_digest, min_approvals=1)
            except (CryptoConfigurationError, CryptoValidationError) as exc:
                blocks.append(str(exc))

    snapshot = _policy_snapshot(agent, tool, base.effective_risk, run)
    if blocks:
        return "BLOCK", list(dict.fromkeys(blocks + reviews)), base.effective_risk, snapshot, base.signed_approval_required
    if reviews:
        return "REVIEW", list(dict.fromkeys(reviews)), base.effective_risk, snapshot, base.signed_approval_required
    return "ALLOW", ["agent_tool_policy_satisfied"], base.effective_risk, snapshot, base.signed_approval_required


def _authorization(workspace_id: str, body: AgentActionRequest, policy_snapshot_sha256: str, signed_required: bool) -> dict[str, Any]:
    return seal(
        payload={
            "kind": "agent-action-authorization",
            "policy_snapshot_sha256": policy_snapshot_sha256,
            "tool_id": body.tool_id,
            "operation": body.operation,
        },
        intent=_intent(body, workspace_id),
        effect=None,
        approvals=[item.model_dump(mode="json") for item in body.approvals],
        min_approvals=1 if signed_required else 0,
        workspace_id=workspace_id,
        domain="agent-action-authorization",
        ttl_seconds=body.authorization_ttl_seconds,
    )


def _to_action_response(item: dict[str, Any]) -> AgentActionResponse:
    return AgentActionResponse(
        action_id=item["action_id"],
        decision=item["decision"],
        status=item["status"],
        reasons=item["reasons"],
        intent_digest=item["intent_digest"],
        intended_effect_digest=item["intended_effect_digest"],
        policy_snapshot_sha256=item["policy_snapshot_sha256"],
        authorization_envelope=item.get("authorization_envelope"),
        created_at=item["created_at"],
        updated_at=item["updated_at"],
    )


@router.post("/registry", response_model=AgentProfile)
def register_agent(body: AgentProfile, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> AgentProfile:
    if body.supervisor_agent_id:
        supervisor = AGENT_STORE.get_agent(principal.workspace_id, body.supervisor_agent_id)
        if supervisor is None or not supervisor.get("enabled", True):
            raise HTTPException(status_code=400, detail="supervisor_agent_not_active")
    AGENT_STORE.upsert_agent(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "agent_registry_upsert", "OK", {"agent_id": body.agent_id})
    return body


@router.get("/registry", response_model=list[AgentProfile])
def list_agents(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[AgentProfile]:
    return [AgentProfile(**item) for item in AGENT_STORE.list_agents(principal.workspace_id)]


@router.post("/tools", response_model=ToolProfile)
def register_tool(body: ToolProfile, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> ToolProfile:
    if not _external_endpoint_allowed(body):
        raise HTTPException(status_code=400, detail="external_tool_endpoint_not_allowed")
    AGENT_STORE.upsert_tool(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "agent_tool_upsert", "OK", {"tool_id": body.tool_id, "protocol": body.protocol, "writes_state": body.writes_state})
    return body


@router.get("/tools", response_model=list[ToolProfile])
def list_tools(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[ToolProfile]:
    return [ToolProfile(**item) for item in AGENT_STORE.list_tools(principal.workspace_id)]


@router.post("/runs", response_model=AgentRunResponse)
def start_run(body: AgentRunStartRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentRunResponse:
    participant_ids = list(dict.fromkeys(body.participant_agent_ids))
    supervisor_item = AGENT_STORE.get_agent(principal.workspace_id, body.supervisor_agent_id)
    if supervisor_item is None or not supervisor_item.get("enabled", True):
        raise HTTPException(status_code=400, detail="supervisor_agent_not_active")
    participant_profiles: list[AgentProfile] = []
    for agent_id in participant_ids:
        item = AGENT_STORE.get_agent(principal.workspace_id, agent_id)
        if item is None or not item.get("enabled", True):
            raise HTTPException(status_code=400, detail=f"participant_agent_not_active:{agent_id}")
        profile = AgentProfile(**item)
        if profile.supervisor_agent_id and profile.supervisor_agent_id != body.supervisor_agent_id:
            raise HTTPException(status_code=400, detail=f"participant_supervisor_mismatch:{agent_id}")
        participant_profiles.append(profile)
    if body.max_actions > sum(item.max_actions_per_run for item in participant_profiles):
        raise HTTPException(status_code=400, detail="run_action_limit_exceeds_participant_limits")
    stored = AGENT_STORE.create_run(
        principal.workspace_id,
        objective=body.objective,
        supervisor_agent_id=body.supervisor_agent_id,
        participant_agent_ids=participant_ids,
        max_actions=body.max_actions,
    )
    _audit(request, principal, "agent_run_start", "ACTIVE", {"run_id": stored["run_id"], "supervisor_agent_id": body.supervisor_agent_id, "participant_count": len(participant_ids)})
    return AgentRunResponse(**stored)


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def get_run(run_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> AgentRunResponse:
    item = AGENT_STORE.get_run(principal.workspace_id, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    return AgentRunResponse(**item)


@router.post("/actions/propose", response_model=AgentActionResponse)
def propose_action(body: AgentActionRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentActionResponse:
    decision, reasons, _effective_risk, snapshot, signed_required = _evaluate(principal.workspace_id, body)
    intent_digest = _intent_digest(body, principal.workspace_id)
    effect_digest = commitment(body.intended_effect, domain="agent-effect")["sha256"]
    authorization = None
    status = "BLOCKED" if decision == "BLOCK" else "REVIEW" if decision == "REVIEW" else "AUTHORIZED"
    if decision == "ALLOW":
        try:
            authorization = _authorization(principal.workspace_id, body, snapshot, signed_required)
        except (CryptoConfigurationError, CryptoValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        stored = AGENT_STORE.create_action(
            principal.workspace_id,
            request_data=body.model_dump(mode="json"),
            decision=decision,
            status=status,
            reasons=reasons,
            intent_digest=intent_digest,
            intended_effect_digest=effect_digest,
            policy_snapshot_sha256=snapshot,
            authorization_envelope=authorization,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "agent_action_propose", status, {"action_id": stored["action_id"], "agent_id": body.agent_id, "tool_id": body.tool_id, "intent_digest": intent_digest, "policy_snapshot_sha256": snapshot})
    return AgentActionResponse(**stored)


@router.get("/actions/{action_id}", response_model=AgentActionResponse)
def get_action(action_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> AgentActionResponse:
    item = AGENT_STORE.get_action(principal.workspace_id, action_id)
    if item is None:
        raise HTTPException(status_code=404, detail="agent_action_not_found")
    return _to_action_response(item)


@router.post("/actions/{action_id}/authorize", response_model=AgentActionResponse)
def authorize_action(action_id: str, body: AgentAuthorizationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentActionResponse:
    current = AGENT_STORE.get_action(principal.workspace_id, action_id)
    if current is None:
        raise HTTPException(status_code=404, detail="agent_action_not_found")
    if current["status"] in {"OUTCOME_VERIFIED", "OUTCOME_MISMATCH"}:
        raise HTTPException(status_code=409, detail="agent_action_already_completed")
    request_data = dict(current["request"])
    request_data["human_approved"] = body.human_approved
    request_data["approvals"] = [item.model_dump(mode="json") for item in body.approvals]
    request_data["authorization_ttl_seconds"] = body.authorization_ttl_seconds
    action_body = AgentActionRequest(**request_data)
    if _intent_digest(action_body, principal.workspace_id) != current["intent_digest"]:
        raise HTTPException(status_code=409, detail="agent_action_intent_changed")
    decision, reasons, _effective_risk, snapshot, signed_required = _evaluate(principal.workspace_id, action_body)
    authorization = None
    status = "BLOCKED" if decision == "BLOCK" else "REVIEW" if decision == "REVIEW" else "AUTHORIZED"
    if decision == "ALLOW":
        try:
            authorization = _authorization(principal.workspace_id, action_body, snapshot, signed_required)
        except (CryptoConfigurationError, CryptoValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = AGENT_STORE.update_action_authorization(
        principal.workspace_id,
        action_id,
        request_data=action_body.model_dump(mode="json"),
        decision=decision,
        status=status,
        reasons=reasons,
        policy_snapshot_sha256=snapshot,
        authorization_envelope=authorization,
    )
    assert stored is not None
    _audit(request, principal, "agent_action_authorize", status, {"action_id": action_id, "policy_snapshot_sha256": snapshot})
    return _to_action_response(stored)


@router.post("/actions/{action_id}/revalidate", response_model=AgentActionResponse)
def revalidate_action(action_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentActionResponse:
    current = AGENT_STORE.get_action(principal.workspace_id, action_id)
    if current is None:
        raise HTTPException(status_code=404, detail="agent_action_not_found")
    if current["status"] in {"OUTCOME_VERIFIED", "OUTCOME_MISMATCH"}:
        raise HTTPException(status_code=409, detail="agent_action_already_completed")
    action_body = AgentActionRequest(**current["request"])
    decision, reasons, _effective_risk, snapshot, signed_required = _evaluate(principal.workspace_id, action_body)
    authorization = None
    if decision == "ALLOW":
        try:
            authorization = _authorization(principal.workspace_id, action_body, snapshot, signed_required)
        except (CryptoConfigurationError, CryptoValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        status = "AUTHORIZED"
    else:
        status = "POLICY_REVOKED" if current.get("authorization_envelope") is not None or current["status"] == "AUTHORIZED" else ("BLOCKED" if decision == "BLOCK" else "REVIEW")
    stored = AGENT_STORE.update_action_authorization(
        principal.workspace_id,
        action_id,
        request_data=None,
        decision=decision,
        status=status,
        reasons=reasons,
        policy_snapshot_sha256=snapshot,
        authorization_envelope=authorization,
    )
    assert stored is not None
    _audit(request, principal, "agent_action_revalidate", status, {"action_id": action_id, "policy_snapshot_sha256": snapshot, "previous_policy_snapshot_sha256": current["policy_snapshot_sha256"]})
    return _to_action_response(stored)


@router.post("/actions/{action_id}/outcome", response_model=AgentOutcomeResponse)
def record_outcome(action_id: str, body: AgentOutcomeRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentOutcomeResponse:
    current = AGENT_STORE.get_action(principal.workspace_id, action_id)
    if current is None:
        raise HTTPException(status_code=404, detail="agent_action_not_found")
    if current["status"] != "AUTHORIZED":
        raise HTTPException(status_code=409, detail="agent_action_not_authorized")
    action_body = AgentActionRequest(**current["request"])
    decision, reasons, _effective_risk, snapshot, _signed_required = _evaluate(principal.workspace_id, action_body)
    if decision != "ALLOW" or snapshot != current["policy_snapshot_sha256"]:
        AGENT_STORE.update_action_authorization(
            principal.workspace_id,
            action_id,
            request_data=None,
            decision=decision,
            status="POLICY_REVOKED",
            reasons=reasons + (["policy_snapshot_changed"] if snapshot != current["policy_snapshot_sha256"] else []),
            policy_snapshot_sha256=snapshot,
            authorization_envelope=None,
        )
        _audit(request, principal, "agent_action_outcome", "POLICY_REVOKED", {"action_id": action_id})
        raise HTTPException(status_code=409, detail="agent_authorization_no_longer_valid")
    actual_digest = commitment(body.actual_effect, domain="agent-effect")["sha256"]
    expected_digest = current["intended_effect_digest"]
    effect_match = actual_digest == expected_digest
    status = "OUTCOME_VERIFIED" if effect_match else "OUTCOME_MISMATCH"
    receipt = seal(
        payload={
            "kind": "agent-action-outcome",
            "action_id": action_id,
            "expected_effect_digest": expected_digest,
            "actual_effect_digest": actual_digest,
            "effect_match": effect_match,
            "actual_effect": body.actual_effect,
            "result": body.result,
            "policy_snapshot_sha256": snapshot,
        },
        intent=_intent(action_body, principal.workspace_id),
        effect=None,
        approvals=[],
        min_approvals=0,
        workspace_id=principal.workspace_id,
        domain="agent-action-outcome",
        ttl_seconds=0,
    )
    try:
        stored = AGENT_STORE.create_outcome(
            principal.workspace_id,
            action_id,
            status=status,
            expected_effect_digest=expected_digest,
            actual_effect_digest=actual_digest,
            outcome_data={"actual_effect": body.actual_effect, "result": body.result, "policy_snapshot_sha256": snapshot},
            signed_receipt=receipt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "agent_action_outcome", status, {"action_id": action_id, "effect_match": effect_match, "expected_effect_digest": expected_digest, "actual_effect_digest": actual_digest})
    return AgentOutcomeResponse(**stored)


@router.get("/runs/{run_id}/supervision", response_model=AgentSupervisionResponse)
def supervise_run(run_id: str, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> AgentSupervisionResponse:
    run = AGENT_STORE.get_run(principal.workspace_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    actions = AGENT_STORE.list_run_actions(principal.workspace_id, run_id)
    counts = Counter(item["status"] for item in actions)
    reasons: list[str] = []
    halt_statuses = {"BLOCKED", "POLICY_REVOKED", "OUTCOME_MISMATCH"}
    if any(counts.get(item, 0) for item in halt_statuses):
        decision = "HALT"
        reasons.append("material_agent_action_failure")
        AGENT_STORE.set_run_status(principal.workspace_id, run_id, "HALTED")
    elif counts.get("REVIEW", 0):
        decision = "REVIEW"
        reasons.append("agent_actions_require_review")
    else:
        decision = "PROCEED"
        reasons.append("no_material_agent_control_failure")
    snapshot = _hash({
        "run_id": run_id,
        "run_status": run["status"],
        "actions": [
            {"action_id": item["action_id"], "status": item["status"], "policy_snapshot_sha256": item["policy_snapshot_sha256"]}
            for item in actions
        ],
    })
    _audit(request, principal, "agent_run_supervision", decision, {"run_id": run_id, "action_count": len(actions), "status_counts": dict(counts)})
    return AgentSupervisionResponse(run_id=run_id, decision=decision, action_count=len(actions), status_counts=dict(counts), reasons=reasons, policy_snapshot_sha256=snapshot)


@router.post("/runs/{run_id}/complete", response_model=AgentRunResponse)
def complete_run(run_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentRunResponse:
    run = AGENT_STORE.get_run(principal.workspace_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    actions = AGENT_STORE.list_run_actions(principal.workspace_id, run_id)
    unresolved = [item for item in actions if item["status"] != "OUTCOME_VERIFIED"]
    if unresolved:
        raise HTTPException(status_code=409, detail="agent_run_has_unresolved_or_failed_actions")
    AGENT_STORE.set_run_status(principal.workspace_id, run_id, "COMPLETED")
    completed = AGENT_STORE.get_run(principal.workspace_id, run_id)
    assert completed is not None
    _audit(request, principal, "agent_run_complete", "COMPLETED", {"run_id": run_id, "action_count": len(actions)})
    return AgentRunResponse(**completed)


@router.get("/readiness")
def agent_readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    agents = AGENT_STORE.list_agents(principal.workspace_id)
    tools = AGENT_STORE.list_tools(principal.workspace_id)
    return {
        "product_version_target": "2.0.0",
        "internal_status": "AUTONOMOUS_ASSURANCE_BASELINE",
        "agent_count": len(agents),
        "tool_count": len(tools),
        "controls": [
            "workspace-scoped agent registry",
            "MCP/HTTP/internal tool registry",
            "tool-operation allowlisting",
            "risk-tier enforcement",
            "human and signed approval gates",
            "idempotency enforcement for state-changing tools",
            "short-lived cryptographic action authorization",
            "continuous authorization revalidation",
            "exact intended-effect vs actual-effect verification",
            "signed outcome receipts",
            "multi-agent run supervision",
            "fail-closed run halt on blocked/revoked/mismatched outcomes",
            "encrypted agent action/outcome records at rest",
        ],
        "external_gates": {
            "real_mcp_server_interoperability": "PENDING_INTEGRATION_TESTS",
            "live_tool_execution_history": "PENDING_PRODUCTION_OPERATION",
            "independent_agentic_security_validation": "PENDING_EXTERNAL_PARTY",
            "enterprise_customer_agent_workloads": "PENDING_COMMERCIAL_EXECUTION",
        },
        "claim": "Repository-controlled autonomous-agent assurance baseline only; no claim of independent validation or live autonomous production use.",
    }
