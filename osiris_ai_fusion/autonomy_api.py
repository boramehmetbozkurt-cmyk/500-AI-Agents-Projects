from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from autonomy import AutonomyStore
from graph import investigate
from saas import AuthContext, require_identity
from store import FusionStore

router = APIRouter(prefix="/operator", tags=["orbythra-persistent-operator"])
Identity = Annotated[AuthContext, Depends(require_identity)]
autonomy_store = AutonomyStore()
fusion_store = FusionStore()


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=3, max_length=4000)
    success_criteria: list[str] = Field(default_factory=list, max_length=12)
    cadence_seconds: int = Field(default=86_400, ge=3600, le=2_592_000)
    max_iterations: int = Field(default=12, ge=1, le=100)
    enabled: bool = True


class GoalStatusUpdate(BaseModel):
    status: Literal["active", "paused", "review", "completed", "cancelled"]


class ActionProposal(BaseModel):
    action_type: Literal[
        "followup_research",
        "create_watchlist",
        "create_case",
        "external_connector",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    goal_id: str | None = Field(default=None, max_length=100)
    risk_level: Literal["low", "medium", "high"] = "low"


def _scope(auth: AuthContext, *, goal_id: str | None = None) -> dict[str, Any]:
    policy = autonomy_store.get_learning_policy(auth.tenant_id)
    scope: dict[str, Any] = {
        "workspace_id": auth.tenant_id,
        "memory_write_enabled": True,
        "adaptive_policy": {
            "observations": policy.get("observations", 0),
            "planner_hints": list(policy.get("planner_hints") or [])[:5],
        },
    }
    if goal_id:
        try:
            scope["goal_id"] = goal_id
            scope["goal_context"] = autonomy_store.goal_context(goal_id, auth.tenant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Goal not found") from exc
    return scope


def _learning_snapshot(auth: AuthContext, result: dict[str, Any]) -> dict[str, Any]:
    evaluation = result.get("self_evaluation") or {}
    autonomy_store.record_telemetry(
        auth.tenant_id,
        "investigation",
        float(evaluation.get("score", 0.0)),
        {
            "evidence_count": len(result.get("evidence_index") or []),
            "refined": bool((result.get("adaptation") or {}).get("performed")),
        },
    )
    return autonomy_store.get_learning_policy(auth.tenant_id)


@router.get("")
async def operator_info(auth: Identity) -> dict[str, Any]:
    return {
        "name": "ORBYTHRA Persistent Autonomous Research Operator",
        "workspace_id": auth.tenant_id,
        "capabilities": [
            "persistent_goals",
            "goal_step_tracking",
            "tenant_long_term_memory",
            "evaluation_learning_policy",
            "bounded_read_only_goal_runs",
            "approval_gated_actions",
            "persistent_cognitive_telemetry",
        ],
        "safety_contract": {
            "autonomous_external_effects": False,
            "read_only_research_can_run": True,
            "external_connector_actions_require_approval": True,
            "unsupported_connectors_are_never_faked": True,
        },
    }


@router.post("/goals")
async def create_goal(body: GoalCreate, auth: Identity) -> dict[str, Any]:
    return autonomy_store.create_goal(
        workspace_id=auth.tenant_id,
        title=body.title,
        objective=body.objective,
        success_criteria=body.success_criteria or None,
        cadence_seconds=body.cadence_seconds,
        max_iterations=body.max_iterations,
        enabled=body.enabled,
    )


@router.get("/goals")
async def list_goals(
    auth: Identity,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    return autonomy_store.list_goals(auth.tenant_id, limit=limit)


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str, auth: Identity) -> dict[str, Any]:
    try:
        return autonomy_store.get_goal(goal_id, auth.tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Goal not found") from exc


@router.patch("/goals/{goal_id}/status")
async def update_goal_status(
    goal_id: str,
    body: GoalStatusUpdate,
    auth: Identity,
) -> dict[str, Any]:
    try:
        return autonomy_store.set_goal_status(goal_id, auth.tenant_id, body.status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Goal not found") from exc


@router.post("/goals/{goal_id}/run")
async def run_goal(goal_id: str, auth: Identity) -> dict[str, Any]:
    try:
        goal = autonomy_store.get_goal(goal_id, auth.tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Goal not found") from exc
    if goal["status"] not in {"active", "review"}:
        raise HTTPException(status_code=409, detail="Goal is not runnable in its current state")
    result = await investigate(goal["objective"], scope=_scope(auth, goal_id=goal_id))
    policy = _learning_snapshot(auth, result)
    updated_goal = autonomy_store.record_goal_run(goal_id, auth.tenant_id, result)
    return {
        "goal": updated_goal,
        "learning_policy": policy,
        "result": result,
    }


@router.get("/learning-policy")
async def learning_policy(auth: Identity) -> dict[str, Any]:
    return autonomy_store.get_learning_policy(auth.tenant_id)


@router.get("/telemetry")
async def cognitive_telemetry(
    auth: Identity,
    hours: int = Query(default=168, ge=1, le=2160),
) -> dict[str, Any]:
    return autonomy_store.telemetry_summary(auth.tenant_id, hours=hours)


@router.post("/actions")
async def propose_action(body: ActionProposal, auth: Identity) -> dict[str, Any]:
    try:
        return autonomy_store.propose_action(
            workspace_id=auth.tenant_id,
            action_type=body.action_type,
            payload=body.payload,
            goal_id=body.goal_id,
            risk_level=body.risk_level,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Goal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/actions")
async def list_actions(
    auth: Identity,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, Any]]:
    return autonomy_store.list_actions(auth.tenant_id, limit=limit)


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, auth: Identity) -> dict[str, Any]:
    try:
        return autonomy_store.approve_action(action_id, auth.tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Action not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/actions/{action_id}/execute")
async def execute_action(action_id: str, auth: Identity) -> dict[str, Any]:
    try:
        action = autonomy_store.get_action(action_id, auth.tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Action not found") from exc
    if action["status"] != "approved":
        raise HTTPException(status_code=409, detail="Action requires explicit approval first")

    payload = action.get("payload") or {}
    action_type = action["action_type"]
    if action_type == "followup_research":
        query = str(payload.get("query") or "").strip()
        if len(query) < 3:
            raise HTTPException(status_code=400, detail="followup_research requires payload.query")
        result = await investigate(
            query,
            scope=_scope(auth, goal_id=action.get("goal_id")),
        )
        policy = _learning_snapshot(auth, result)
        return autonomy_store.finish_action(
            action_id,
            auth.tenant_id,
            {"result": result, "learning_policy": policy},
        )

    if action_type == "create_case":
        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="create_case requires payload.title")
        created = fusion_store.create_case(title[:240], auth.tenant_id)
        return autonomy_store.finish_action(
            action_id,
            auth.tenant_id,
            {"case": created},
        )

    if action_type == "create_watchlist":
        name = str(payload.get("name") or "").strip()
        query = str(payload.get("query") or "").strip()
        if not name or len(query) < 3:
            raise HTTPException(
                status_code=400,
                detail="create_watchlist requires payload.name and payload.query",
            )
        cadence = max(60, min(int(payload.get("cadence_seconds", 3600)), 604800))
        created = fusion_store.create_watchlist(
            {
                "workspace_id": auth.tenant_id,
                "name": name[:240],
                "query": query[:4000],
                "scope": {"workspace_id": auth.tenant_id},
                "allowed_tools": payload.get("allowed_tools"),
                "cadence_seconds": cadence,
                "min_confidence": max(
                    0.0,
                    min(1.0, float(payload.get("min_confidence", 0.6))),
                ),
                "enabled": bool(payload.get("enabled", True)),
            }
        )
        return autonomy_store.finish_action(
            action_id,
            auth.tenant_id,
            {"watchlist": created},
        )

    return autonomy_store.finish_action(
        action_id,
        auth.tenant_id,
        {
            "reason": (
                "No server-side external connector adapter is bound to this action. "
                "The approved request remains auditable and waits for an explicit connector binding."
            )
        },
        status="waiting_connector",
    )
