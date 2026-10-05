from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_models import AgentActionRequest, AgentProfile, ToolProfile
from app.crypto_core import canonical_json

_RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class AgentPolicyResult:
    decision: str
    reasons: tuple[str, ...]
    effective_risk: str
    human_approval_required: bool
    signed_approval_required: bool


def risk_at_or_above(actual: str, threshold: str) -> bool:
    return _RISK[actual] >= _RISK[threshold]


def max_risk(first: str, second: str) -> str:
    return first if _RISK[first] >= _RISK[second] else second


def evaluate_agent_policy(
    agent: AgentProfile,
    tool: ToolProfile,
    body: AgentActionRequest,
    *,
    run: dict[str, Any] | None = None,
    run_lookup_failed: bool = False,
    agent_action_count: int = 0,
    external_endpoint_allowed: bool = True,
) -> AgentPolicyResult:
    blocks: list[str] = []
    reviews: list[str] = []
    effective_risk = max_risk(body.risk_tier, tool.risk_tier)

    if not agent.enabled:
        blocks.append("agent_disabled")
    if not tool.enabled:
        blocks.append("tool_disabled")
    if agent.allowed_tool_ids and tool.tool_id not in agent.allowed_tool_ids:
        blocks.append("tool_not_allowed_for_agent")
    if body.operation not in tool.allowed_operations:
        blocks.append("operation_not_allowed")
    if _RISK[effective_risk] > _RISK[agent.max_risk_tier]:
        blocks.append("risk_exceeds_agent_limit")
    categories = set(body.data_categories) | set(tool.data_categories)
    prohibited = sorted(categories & set(agent.prohibited_data_categories))
    if prohibited:
        blocks.append("prohibited_data_categories:" + ",".join(prohibited))
    if tool.requires_idempotency_key and not body.idempotency_key:
        blocks.append("idempotency_key_required")
    if len(canonical_json(body.parameters)) > tool.max_input_bytes:
        blocks.append("tool_input_too_large")
    if not external_endpoint_allowed:
        blocks.append("external_tool_endpoint_not_allowed")

    if body.run_id:
        if run_lookup_failed or run is None:
            blocks.append("agent_run_not_found")
        else:
            if run.get("status") != "ACTIVE":
                blocks.append("agent_run_not_active")
            if body.agent_id not in set(run.get("participant_agent_ids") or []):
                blocks.append("agent_not_participant_in_run")
            if agent.supervisor_agent_id and agent.supervisor_agent_id != run.get("supervisor_agent_id"):
                blocks.append("agent_supervisor_mismatch")
            if agent_action_count >= agent.max_actions_per_run:
                blocks.append("agent_run_action_limit_reached")

    human_required = risk_at_or_above(effective_risk, agent.human_approval_from_risk)
    signed_required = risk_at_or_above(effective_risk, agent.signed_approval_from_risk)
    if human_required and not body.human_approved:
        reviews.append("human_approval_required")
    if signed_required and not any(item.proof_type in {"signature", "hybrid_signature"} for item in body.approvals):
        reviews.append("signed_approval_required")

    if blocks:
        return AgentPolicyResult("BLOCK", tuple(blocks + reviews), effective_risk, human_required, signed_required)
    if reviews:
        return AgentPolicyResult("REVIEW", tuple(reviews), effective_risk, human_required, signed_required)
    return AgentPolicyResult("ALLOW", ("agent_tool_policy_satisfied",), effective_risk, human_required, signed_required)
