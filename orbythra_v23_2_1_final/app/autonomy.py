from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app import __version__
from app.agent_store import AGENT_STORE
from app.autonomy_models import (
    AutonomyReadinessResponse,
    CycleEvaluationRequest,
    CycleEvaluationResponse,
    DriftCheckResponse,
    MemoryCreateRequest,
    MemoryQuery,
    MemoryRecord,
    MissionCreateRequest,
    MissionPlan,
    MissionRecord,
    PlanStep,
    SkillDefinition,
)
from app.autonomy_store import AUTONOMY_STORE
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v3/autonomy", tags=["autonomy-v3"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")
_RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object] | None = None) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "autonomy-v3"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **(metadata or {})},
    )


def _agent(workspace_id: str, agent_id: str) -> dict[str, Any]:
    item = AGENT_STORE.get_agent(workspace_id, agent_id)
    if item is None or not item.get("enabled", True):
        raise HTTPException(status_code=400, detail="autonomy_agent_not_active")
    return item


def _viable_skills(workspace_id: str, agent: dict[str, Any], risk_budget: str) -> list[dict[str, Any]]:
    allowed_tools = set(agent.get("allowed_tool_ids", []))
    viable: list[dict[str, Any]] = []
    for skill in AUTONOMY_STORE.list_skills(workspace_id):
        if not skill.get("enabled", True):
            continue
        if _RISK.get(str(skill.get("risk_tier", "critical")), 3) > _RISK[risk_budget]:
            continue
        required_tools = set(skill.get("required_tool_ids", []))
        if not required_tools.issubset(allowed_tools):
            continue
        tools_ok = True
        for tool_id in required_tools:
            tool = AGENT_STORE.get_tool(workspace_id, tool_id)
            if tool is None or not tool.get("enabled", True):
                tools_ok = False
                break
        if tools_ok:
            viable.append(skill)
    return viable


def _select_skills(required_capabilities: list[str], viable: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for capability in list(dict.fromkeys(required_capabilities)):
        candidates = [s for s in viable if capability in set(s.get("capabilities", []))]
        if not candidates:
            missing.append(capability)
            continue
        chosen = sorted(candidates, key=lambda s: (_RISK.get(str(s.get("risk_tier", "critical")), 3), str(s["skill_id"])))[0]
        if chosen["skill_id"] not in {s["skill_id"] for s in selected}:
            selected.append(chosen)
    return selected, missing


def _context(workspace_id: str, mission: dict[str, Any], selected_skills: list[dict[str, Any]]) -> dict[str, Any]:
    agent = _agent(workspace_id, mission["agent_id"])
    tool_ids = sorted({tool_id for skill in selected_skills for tool_id in skill.get("required_tool_ids", [])})
    tools = [AGENT_STORE.get_tool(workspace_id, tool_id) for tool_id in tool_ids]
    return {
        "agent": agent,
        "skills": selected_skills,
        "tools": tools,
        "risk_budget": mission["risk_budget"],
        "required_capabilities": mission["required_capabilities"],
        "constraints": mission["constraints"],
    }


def _build_plan(workspace_id: str, mission: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    agent = _agent(workspace_id, mission["agent_id"])
    viable = _viable_skills(workspace_id, agent, mission["risk_budget"])
    selected, missing = _select_skills(mission["required_capabilities"], viable)
    memories = AUTONOMY_STORE.query_memories(workspace_id, agent_id=mission["agent_id"], kinds=[], tags=[], min_confidence=0.0, limit=20)
    steps: list[dict[str, Any]] = []
    sequence = 1
    steps.append(PlanStep(step_id=f"step-{sequence}", sequence=sequence, kind="RETRIEVE_MEMORY", instruction="Retrieve non-expired workspace-scoped memory relevant to the mission before proposing actions.").model_dump())
    sequence += 1
    for skill in selected:
        capability = next((c for c in mission["required_capabilities"] if c in skill.get("capabilities", [])), None)
        steps.append(PlanStep(step_id=f"step-{sequence}", sequence=sequence, kind="APPLY_SKILL", capability=capability, skill_id=skill["skill_id"], required_tool_ids=skill.get("required_tool_ids", []), instruction="Apply this registered skill. Any real tool action must be proposed and execution-checked through /v2/agents before execution.").model_dump())
        sequence += 1
    steps.append(PlanStep(step_id=f"step-{sequence}", sequence=sequence, kind="VERIFY_CRITERIA", instruction="Evaluate every declared success criterion from recorded observations and verified v2 action outcomes; do not infer completion from intent alone.").model_dump())
    sequence += 1
    steps.append(PlanStep(step_id=f"step-{sequence}", sequence=sequence, kind="LEARN", instruction="Persist bounded mission observations as memory only after evaluation; memory does not modify model weights.").model_dump())
    context = _context(workspace_id, mission, selected)
    context_sha = _sha(context)
    plan = {
        "steps": steps,
        "selected_skill_ids": [s["skill_id"] for s in selected],
        "missing_capabilities": missing,
        "memory_context_ids": [m["memory_id"] for m in memories],
    }
    return plan, context_sha, _sha(plan)


@router.post("/memory", response_model=MemoryRecord)
def add_memory(body: MemoryCreateRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> MemoryRecord:
    _agent(principal.workspace_id, body.agent_id)
    stored = AUTONOMY_STORE.add_memory(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "autonomy_memory_write", "OK", {"memory_id": stored["memory_id"], "agent_id": body.agent_id, "kind": body.kind, "content_sha256": stored["content_sha256"]})
    return MemoryRecord(**stored)


@router.post("/memory/query", response_model=list[MemoryRecord])
def query_memory(body: MemoryQuery, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[MemoryRecord]:
    _agent(principal.workspace_id, body.agent_id)
    items = AUTONOMY_STORE.query_memories(principal.workspace_id, agent_id=body.agent_id, kinds=list(body.kinds), tags=body.tags, min_confidence=body.min_confidence, limit=body.limit)
    return [MemoryRecord(**item) for item in items]


@router.post("/skills", response_model=SkillDefinition)
def register_skill(body: SkillDefinition, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> SkillDefinition:
    for tool_id in body.required_tool_ids:
        tool = AGENT_STORE.get_tool(principal.workspace_id, tool_id)
        if tool is None or not tool.get("enabled", True):
            raise HTTPException(status_code=400, detail=f"skill_tool_not_active:{tool_id}")
    AUTONOMY_STORE.upsert_skill(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "autonomy_skill_upsert", "OK", {"skill_id": body.skill_id, "version": body.version})
    return body


@router.get("/skills", response_model=list[SkillDefinition])
def list_skills(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[SkillDefinition]:
    return [SkillDefinition(**item) for item in AUTONOMY_STORE.list_skills(principal.workspace_id)]


@router.post("/missions", response_model=MissionRecord)
def create_mission(body: MissionCreateRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> MissionRecord:
    agent = _agent(principal.workspace_id, body.agent_id)
    if _RISK[body.risk_budget] > _RISK.get(str(agent.get("max_risk_tier", "high")), 2):
        raise HTTPException(status_code=400, detail="mission_risk_budget_exceeds_agent_ceiling")
    stored = AUTONOMY_STORE.create_mission(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "autonomy_mission_create", "ACTIVE", {"mission_id": stored["mission_id"], "agent_id": body.agent_id})
    return MissionRecord(**stored)


@router.get("/missions/{mission_id}", response_model=MissionRecord)
def get_mission(mission_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> MissionRecord:
    mission = AUTONOMY_STORE.get_mission(principal.workspace_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="autonomy_mission_not_found")
    return MissionRecord(**mission)


@router.post("/missions/{mission_id}/plan", response_model=MissionPlan)
def plan_mission(mission_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> MissionPlan:
    mission = AUTONOMY_STORE.get_mission(principal.workspace_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="autonomy_mission_not_found")
    if mission["status"] in {"COMPLETED", "FAILED"}:
        raise HTTPException(status_code=409, detail="autonomy_mission_terminal")
    plan, context_sha, plan_sha = _build_plan(principal.workspace_id, mission)
    stored = AUTONOMY_STORE.save_plan(principal.workspace_id, mission_id, plan, context_sha, plan_sha)
    status = "PAUSED" if stored["missing_capabilities"] else "ACTIVE"
    _audit(request, principal, "autonomy_plan_create", status, {"mission_id": mission_id, "revision": stored["revision"], "plan_sha256": plan_sha, "missing_capabilities": stored["missing_capabilities"]})
    return MissionPlan(**stored)


@router.get("/missions/{mission_id}/plan", response_model=MissionPlan)
def get_plan(mission_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> MissionPlan:
    plan = AUTONOMY_STORE.get_latest_plan(principal.workspace_id, mission_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="autonomy_plan_not_found")
    return MissionPlan(**plan)


@router.post("/missions/{mission_id}/drift", response_model=DriftCheckResponse)
def check_drift(mission_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> DriftCheckResponse:
    mission = AUTONOMY_STORE.get_mission(principal.workspace_id, mission_id)
    plan = AUTONOMY_STORE.get_latest_plan(principal.workspace_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="autonomy_mission_not_found")
    if plan is None:
        raise HTTPException(status_code=409, detail="autonomy_plan_required")
    skills_by_id = {s["skill_id"]: s for s in AUTONOMY_STORE.list_skills(principal.workspace_id)}
    selected = [skills_by_id[sid] for sid in plan["selected_skill_ids"] if sid in skills_by_id]
    current_sha = _sha(_context(principal.workspace_id, mission, selected))
    reasons: list[str] = []
    if len(selected) != len(plan["selected_skill_ids"]):
        reasons.append("selected_skill_missing")
    if current_sha != plan["context_sha256"]:
        reasons.append("autonomy_context_changed")
    drift = bool(reasons)
    if drift and mission["status"] not in {"COMPLETED", "FAILED"}:
        AUTONOMY_STORE.set_mission_state(principal.workspace_id, mission_id, status="PAUSED")
    status = "PAUSED" if drift and mission["status"] not in {"COMPLETED", "FAILED"} else mission["status"]
    _audit(request, principal, "autonomy_drift_check", "DRIFT" if drift else "STABLE", {"mission_id": mission_id, "current_context_sha256": current_sha})
    return DriftCheckResponse(mission_id=mission_id, drift_detected=drift, stored_context_sha256=plan["context_sha256"], current_context_sha256=current_sha, reasons=reasons or ["context_stable"], status=status)


@router.post("/missions/{mission_id}/evaluate", response_model=CycleEvaluationResponse)
def evaluate_cycle(mission_id: str, body: CycleEvaluationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> CycleEvaluationResponse:
    mission = AUTONOMY_STORE.get_mission(principal.workspace_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="autonomy_mission_not_found")
    plan = AUTONOMY_STORE.get_latest_plan(principal.workspace_id, mission_id)
    if plan is None:
        raise HTTPException(status_code=409, detail="autonomy_plan_required")
    if mission["status"] in {"COMPLETED", "FAILED"}:
        raise HTTPException(status_code=409, detail="autonomy_mission_terminal")
    criteria = mission["success_criteria"]
    satisfied = sum(1 for criterion in criteria if body.criterion_results.get(criterion) is True)
    action_statuses: list[str] = []
    reasons: list[str] = []
    for action_id in body.action_ids:
        action = AGENT_STORE.get_action(principal.workspace_id, action_id)
        if action is None:
            reasons.append(f"action_not_found:{action_id}")
            continue
        if action["agent_id"] != mission["agent_id"]:
            reasons.append(f"action_agent_mismatch:{action_id}")
        action_statuses.append(action["status"])
    counts = dict(Counter(action_statuses))
    unsafe = any(status in {"BLOCKED", "POLICY_REVOKED", "OUTCOME_MISMATCH"} for status in action_statuses) or any(r.startswith("action_") for r in reasons)
    cycle = mission["cycle_count"] + 1
    if unsafe:
        status = "PAUSED"
        reasons.append("verified_action_state_requires_review")
        next_step = "replan_or_review"
    elif satisfied == len(criteria):
        status = "COMPLETED"
        reasons.append("all_declared_success_criteria_satisfied")
        next_step = "mission_complete"
    elif cycle >= mission["max_cycles"]:
        status = "FAILED"
        reasons.append("maximum_cycle_budget_reached")
        next_step = "mission_failed"
    else:
        status = "ACTIVE"
        reasons.append("success_criteria_incomplete")
        next_step = "continue_plan"
    memory_id = None
    if body.write_memory and body.observations:
        mem = AUTONOMY_STORE.add_memory(principal.workspace_id, {
            "agent_id": mission["agent_id"], "kind": "episodic", "content": {"mission_id": mission_id, "cycle": cycle, "observations": body.observations, "criterion_results": body.criterion_results, "action_status_counts": counts},
            "tags": ["autonomy", "mission", mission_id], "confidence": 1.0, "source_refs": body.action_ids, "sensitivity": "confidential", "ttl_seconds": None,
        })
        memory_id = mem["memory_id"]
    payload = {"mission_id": mission_id, "cycle": cycle, "status": status, "criteria_satisfied": satisfied, "criteria_total": len(criteria), "action_status_counts": counts, "reasons": reasons, "next_step": next_step, "memory_id": memory_id}
    digest = AUTONOMY_STORE.add_evaluation(principal.workspace_id, mission_id, cycle, payload)
    AUTONOMY_STORE.set_mission_state(principal.workspace_id, mission_id, status=status, cycle_count=cycle)
    _audit(request, principal, "autonomy_cycle_evaluate", status, {"mission_id": mission_id, "cycle": cycle, "evaluation_sha256": digest})
    return CycleEvaluationResponse(**payload, completion_ratio=round(satisfied / len(criteria), 6), evaluation_sha256=digest)


@router.get("/readiness", response_model=AutonomyReadinessResponse)
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> AutonomyReadinessResponse:
    _ = principal
    return AutonomyReadinessResponse(
        version=__version__, persistent_memory=True, skill_registry=True, deterministic_planner=True,
        criteria_self_evaluation=True, continuous_drift_check=True, v2_execution_gate_required=True,
        live_general_intelligence_claim=False,
        boundary="v3 provides bounded autonomy orchestration, persistent encrypted memory, deterministic skill planning, self-evaluation and drift controls. It does not implement model-weight learning, claim AGI, or independently prove safe real-world autonomous execution.",
    )
