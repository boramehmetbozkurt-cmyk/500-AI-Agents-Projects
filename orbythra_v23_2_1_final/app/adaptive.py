from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app import __version__
from app.adaptive_core import RISK, learning_gate, select_strategy
from app.adaptive_models import (
    AdaptiveReadinessResponse,
    LearningActivationRequest,
    LearningCandidateRequest,
    LearningRecord,
    MetaRouteRequest,
    MetaRouteResponse,
    StrategyDefinition,
    TransferProposalRequest,
    TransferProposalResponse,
    WorldStateRecord,
    WorldStateUpdateRequest,
)
from app.adaptive_store import ADAPTIVE_STORE
from app.agent_store import AGENT_STORE
from app.autonomy_store import AUTONOMY_STORE
from app.enterprise_store import ENTERPRISE_STORE
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v4/adaptive", tags=["adaptive-v4"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object] | None = None) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "adaptive-v4"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **(metadata or {})},
    )


def _agent(workspace_id: str, agent_id: str) -> dict[str, Any]:
    item = AGENT_STORE.get_agent(workspace_id, agent_id)
    if item is None or not item.get("enabled", True):
        raise HTTPException(status_code=400, detail="adaptive_agent_not_active")
    return item


def _validate_tools(workspace_id: str, agent: dict[str, Any], tool_ids: list[str]) -> None:
    allowed = set(agent.get("allowed_tool_ids", []))
    for tool_id in tool_ids:
        tool = AGENT_STORE.get_tool(workspace_id, tool_id)
        if tool is None or not tool.get("enabled", True):
            raise HTTPException(status_code=400, detail=f"adaptive_tool_not_active:{tool_id}")
        if tool_id not in allowed:
            raise HTTPException(status_code=400, detail=f"adaptive_tool_not_allowed_for_agent:{tool_id}")


@router.post("/world-state", response_model=WorldStateRecord)
def update_world_state(body: WorldStateUpdateRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> WorldStateRecord:
    _agent(principal.workspace_id, body.agent_id)
    stored = ADAPTIVE_STORE.update_world_state(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "adaptive_world_state_update", "OK", {"agent_id": body.agent_id, "domain": body.domain, "revision": stored["revision"], "state_sha256": stored["state_sha256"]})
    return WorldStateRecord(**stored)


@router.get("/world-state/{agent_id}/{domain}", response_model=WorldStateRecord)
def get_world_state(agent_id: str, domain: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> WorldStateRecord:
    item = ADAPTIVE_STORE.latest_world_state(principal.workspace_id, agent_id, domain)
    if item is None:
        raise HTTPException(status_code=404, detail="adaptive_world_state_not_found")
    return WorldStateRecord(**item)


@router.post("/learning/candidates", response_model=LearningRecord)
def create_learning_candidate(body: LearningCandidateRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> LearningRecord:
    agent = _agent(principal.workspace_id, body.agent_id)
    if RISK[body.risk_tier] > RISK.get(str(agent.get("max_risk_tier", "high")), 2):
        raise HTTPException(status_code=400, detail="learning_risk_exceeds_agent_ceiling")
    _validate_tools(principal.workspace_id, agent, body.required_tool_ids)
    stored = ADAPTIVE_STORE.create_learning(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "adaptive_learning_candidate", "CANDIDATE", {"learning_id": stored["learning_id"], "learning_sha256": stored["learning_sha256"], "improvement": stored["improvement"]})
    return LearningRecord(**stored)


@router.get("/learning/{learning_id}/history", response_model=list[LearningRecord])
def learning_history(learning_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[LearningRecord]:
    items = ADAPTIVE_STORE.learning_history(principal.workspace_id, learning_id)
    if not items:
        raise HTTPException(status_code=404, detail="adaptive_learning_not_found")
    return [LearningRecord(**item) for item in items]


@router.post("/learning/{learning_id}/activate", response_model=LearningRecord)
def activate_learning(learning_id: str, body: LearningActivationRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> LearningRecord:
    current = ADAPTIVE_STORE.get_learning(principal.workspace_id, learning_id)
    if current is None:
        raise HTTPException(status_code=404, detail="adaptive_learning_not_found")
    if current["status"] != "CANDIDATE":
        raise HTTPException(status_code=409, detail="adaptive_learning_not_candidate")
    gate, _improvement = learning_gate(baseline_score=current["baseline_score"], candidate_score=current["candidate_score"], minimum_improvement=current["minimum_improvement"])
    if gate != "ACCEPT":
        rejected = ADAPTIVE_STORE.transition_learning(principal.workspace_id, learning_id, "REJECTED")
        assert rejected is not None
        _audit(request, principal, "adaptive_learning_activate", "REJECTED", {"learning_id": learning_id, "reason": "minimum_improvement_not_met"})
        raise HTTPException(status_code=409, detail="adaptive_learning_minimum_improvement_not_met")
    if RISK[current["risk_tier"]] >= RISK["high"] and not body.human_approved:
        raise HTTPException(status_code=409, detail="adaptive_learning_human_approval_required")
    agent = _agent(principal.workspace_id, current["agent_id"])
    _validate_tools(principal.workspace_id, agent, current["required_tool_ids"])
    skill = {
        "skill_id": current["derived_skill_id"],
        "display_name": f"Adaptive learned skill: {current['capability']}",
        "version": f"{current['revision']}.0.0",
        "description": "Evidence-gated application-level learned procedure. Provenance is the associated adaptive learning record; this does not modify model weights.",
        "capabilities": [current["capability"]],
        "required_tool_ids": current["required_tool_ids"],
        "risk_tier": current["risk_tier"],
        "enabled": True,
    }
    AUTONOMY_STORE.upsert_skill(principal.workspace_id, skill)
    activated = ADAPTIVE_STORE.transition_learning(principal.workspace_id, learning_id, "ACTIVE")
    assert activated is not None
    _audit(request, principal, "adaptive_learning_activate", "ACTIVE", {"learning_id": learning_id, "derived_skill_id": current["derived_skill_id"], "learning_sha256": activated["learning_sha256"]})
    return LearningRecord(**activated)


@router.post("/learning/{learning_id}/rollback", response_model=LearningRecord)
def rollback_learning(learning_id: str, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> LearningRecord:
    current = ADAPTIVE_STORE.get_learning(principal.workspace_id, learning_id)
    if current is None:
        raise HTTPException(status_code=404, detail="adaptive_learning_not_found")
    if current["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="adaptive_learning_not_active")
    skills = {item["skill_id"]: item for item in AUTONOMY_STORE.list_skills(principal.workspace_id)}
    skill = skills.get(current["derived_skill_id"])
    if skill is not None:
        skill = {k: skill[k] for k in ["skill_id","display_name","version","description","capabilities","required_tool_ids","risk_tier","enabled"] if k in skill}
        skill["enabled"] = False
        AUTONOMY_STORE.upsert_skill(principal.workspace_id, skill)
    rolled = ADAPTIVE_STORE.transition_learning(principal.workspace_id, learning_id, "ROLLED_BACK")
    assert rolled is not None
    _audit(request, principal, "adaptive_learning_rollback", "ROLLED_BACK", {"learning_id": learning_id, "derived_skill_id": current["derived_skill_id"]})
    return LearningRecord(**rolled)


@router.post("/transfer/propose", response_model=TransferProposalResponse)
def propose_transfer(body: TransferProposalRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> TransferProposalResponse:
    learning = ADAPTIVE_STORE.get_learning(principal.workspace_id, body.learning_id)
    if learning is None:
        raise HTTPException(status_code=404, detail="adaptive_learning_not_found")
    if learning["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="adaptive_transfer_requires_active_learning")
    payload = {
        "learning_id": body.learning_id,
        "source_domain": learning["source_domain"],
        "target_domain": body.target_domain,
        "source_capability": learning["capability"],
        "target_capability": body.target_capability,
        "evidence_refs": body.evidence_refs,
    }
    stored = ADAPTIVE_STORE.create_transfer(principal.workspace_id, payload)
    _audit(request, principal, "adaptive_transfer_propose", "PROPOSED", {"transfer_id": stored["transfer_id"], "learning_id": body.learning_id, "transfer_sha256": stored["transfer_sha256"]})
    return TransferProposalResponse(**stored, boundary="Transfer is a provenance-bound proposal only. It grants no tool authority and creates no active skill until separately evidenced and approved.")


@router.post("/strategies", response_model=StrategyDefinition)
def register_strategy(body: StrategyDefinition, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> StrategyDefinition:
    if body.provider_id:
        providers = {item.get("provider_id") for item in ENTERPRISE_STORE.list_providers(principal.workspace_id)}
        if body.provider_id not in providers:
            raise HTTPException(status_code=400, detail="adaptive_strategy_provider_not_registered")
    ADAPTIVE_STORE.upsert_strategy(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "adaptive_strategy_upsert", "OK", {"strategy_id": body.strategy_id, "provider_id": body.provider_id})
    return body


@router.get("/strategies", response_model=list[StrategyDefinition])
def list_strategies(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[StrategyDefinition]:
    return [StrategyDefinition(**item) for item in ADAPTIVE_STORE.list_strategies(principal.workspace_id)]


@router.post("/route", response_model=MetaRouteResponse)
def route_strategy(body: MetaRouteRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> MetaRouteResponse:
    selected, utility = select_strategy(ADAPTIVE_STORE.list_strategies(principal.workspace_id), domain=body.domain, required_capabilities=body.required_capabilities, max_risk_tier=body.max_risk_tier)
    if selected is None or utility is None:
        raise HTTPException(status_code=409, detail="adaptive_no_strategy_satisfies_constraints")
    routing = {"domain": body.domain, "required_capabilities": sorted(set(body.required_capabilities)), "max_risk_tier": body.max_risk_tier, "strategy_id": selected["strategy_id"], "provider_id": selected.get("provider_id"), "utility_score": utility}
    digest = _sha(routing)
    _audit(request, principal, "adaptive_meta_route", "SELECTED", {"strategy_id": selected["strategy_id"], "routing_sha256": digest})
    return MetaRouteResponse(strategy_id=selected["strategy_id"], provider_id=selected.get("provider_id"), utility_score=utility, reasons=["capabilities_satisfied", "domain_satisfied", "risk_budget_satisfied", "highest_deterministic_utility"], routing_sha256=digest)


@router.get("/readiness", response_model=AdaptiveReadinessResponse)
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> AdaptiveReadinessResponse:
    return AdaptiveReadinessResponse(
        version=__version__,
        world_state_revisioning=True,
        gated_continual_learning=True,
        rollbackable_learning=True,
        cross_domain_transfer_proposals=True,
        derived_skill_acquisition=True,
        deterministic_meta_routing=True,
        v3_memory_and_missions_preserved=True,
        v2_execution_gate_required=True,
        model_weight_self_training=False,
        agi_claim=False,
        boundary="v4 is an application-level adaptive generalist baseline. Learning is evidence-gated, provenance-bound and rollbackable; it does not self-train foundation-model weights and is not an AGI claim.",
    )
