from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.crypto_core import canonical_json
from app.failure_memory_v15 import FAILURE_MEMORY_V15
from app.hierarchical_generalist_v17 import V17
from app.metacognition_v11h import MetaAssessment, assess as assess_metacognition
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v19/reflection", tags=["v19-metacognitive-reflection"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

ReflectionAction = Literal["CONTINUE", "REPLAN", "REVIEW", "BLOCK", "COMPLETE"]


def _hash(value: Any) -> str:
    import hashlib
    return hashlib.sha256(canonical_json(value)).hexdigest()


class ReflectionRequest(BaseModel):
    program_id: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    contradiction_rate: float = Field(ge=0.0, le=1.0)
    recent_failure_rate: float = Field(ge=0.0, le=1.0)
    distribution_shift: float = Field(ge=0.0, le=1.0)


class ReflectionDecision(BaseModel):
    program_id: str
    action: ReflectionAction
    next_goal_id: str | None
    reason_codes: list[str]
    metacognitive_status: str
    uncertainty: float
    release_blocked: bool
    reflection_sha256: str


def assess_program(workspace_id: str, body: ReflectionRequest) -> ReflectionDecision:
    try:
        state = V17.resume_state(workspace_id, body.program_id)
    except ValueError as exc:
        raise ValueError("reflection_program_not_found") from exc
    failure_gate = FAILURE_MEMORY_V15.release_gate(workspace_id)
    meta = assess_metacognition(MetaAssessment(
        confidence=body.confidence,
        evidence_coverage=body.evidence_coverage,
        contradiction_rate=body.contradiction_rate,
        recent_failure_rate=body.recent_failure_rate,
        distribution_shift=body.distribution_shift,
    ))
    reasons: list[str] = []
    if failure_gate.status == "BLOCK":
        action: ReflectionAction = "BLOCK"
        reasons.append("high_or_critical_failure_memory_block")
    elif state.program.status == "COMPLETE":
        action = "COMPLETE"
        reasons.append("program_complete")
    elif state.failed_goals or state.paused_goals or meta["status"] == "REPLAN":
        action = "REPLAN"
        if state.failed_goals:
            reasons.append("failed_goal_present")
        if state.paused_goals:
            reasons.append("paused_goal_present")
        if meta["status"] == "REPLAN":
            reasons.append("metacognitive_strategy_change_required")
    elif meta["status"] == "REVIEW":
        action = "REVIEW"
        reasons.append("metacognitive_uncertainty_requires_review")
    else:
        action = "CONTINUE"
        reasons.append("bounded_progress_can_continue")
    payload = {
        "program_id": body.program_id,
        "action": action,
        "next_goal_id": None if state.next_goal is None else state.next_goal.goal_id,
        "reason_codes": reasons,
        "metacognitive_status": meta["status"],
        "uncertainty": float(meta["uncertainty"]),
        "release_blocked": failure_gate.status == "BLOCK",
    }
    return ReflectionDecision(**payload, reflection_sha256=_hash(payload))


@router.post("/assess", response_model=ReflectionDecision)
def assess_endpoint(body: ReflectionRequest, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ReflectionDecision:
    try:
        result = assess_program(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.reflection_sha256),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="v19_reflection_assess",
        status=result.action,
        metadata={"program_id": body.program_id, "reflection_sha256": result.reflection_sha256},
    )
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v19",
        "structured_model_plan_synthesis": True,
        "strict_schema_and_risk_validation": True,
        "metadata_only_private_context": True,
        "separate_plan_proposal_and_tool_authority": True,
        "metacognitive_continue_replan_review_block": True,
        "automatic_tool_execution": False,
        "permission_self_escalation": False,
        "live_agi_claim": False,
        "boundary": (
            "V19 adds structured model-generated planning proposals and metacognitive control decisions. "
            "The planner cannot grant permissions or execute tools, private memory contents and world-fact values "
            "are excluded from provider prompts, and this is not proof of AGI."
        ),
    }
