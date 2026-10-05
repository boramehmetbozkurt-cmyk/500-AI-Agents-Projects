from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.autonomy_store import AUTONOMY_STORE
from app.continual_generalist_v16 import CONTINUAL_V16, WorldFactQuery
from app.crypto_core import canonical_json
from app.hierarchical_generalist_v17 import GoalExpansionRequest, GoalRecord, GoalReplanRequest, GoalSpec, V17
from app.model_adapters_v10 import GovernedHttpModelAdapter
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v19/planner", tags=["v19-structured-planner"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")

ProposalMode = Literal["EXPAND", "REPLAN"]
_RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _strip_fence(value: str) -> str:
    text_value = value.strip()
    fence = chr(96) * 3
    if text_value.startswith(fence):
        lines = text_value.splitlines()[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        text_value = "\n".join(lines).strip()
    return text_value


class PlannerSynthesisRequest(BaseModel):
    program_id: str = Field(min_length=1, max_length=120)
    goal_id: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    mode: ProposalMode = "EXPAND"
    maximum_subgoals: int = Field(default=6, ge=1, le=20)
    memory_limit: int = Field(default=20, ge=0, le=100)
    world_fact_limit: int = Field(default=20, ge=0, le=100)


class PlannerProposal(BaseModel):
    proposal_id: str
    program_id: str
    goal_id: str
    model_id: str
    mode: ProposalMode
    subgoals: list[GoalSpec]
    rationale: str
    provider_response_sha256: str
    proposal_sha256: str
    applied: bool
    created_at: int


class StructuredPlannerV19:
    def __init__(self) -> None:
        self.engine = STORE.engine
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS planner_proposals_v19(
                workspace_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                program_id TEXT NOT NULL,
                goal_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                provider_response_sha256 TEXT NOT NULL,
                proposal_sha256 TEXT NOT NULL,
                applied INTEGER NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,proposal_id)
                )"""
            ))

    def _context(self, workspace_id: str, body: PlannerSynthesisRequest) -> tuple[dict[str, Any], Any, Any]:
        program = V17.get_program(workspace_id, body.program_id)
        goal = V17.get_goal(workspace_id, body.goal_id)
        if program is None:
            raise ValueError("planner_program_not_found")
        if goal is None or goal.program_id != program.program_id:
            raise ValueError("planner_goal_not_found")
        memories = AUTONOMY_STORE.query_memories(
            workspace_id,
            agent_id=program.agent_id,
            kinds=[],
            tags=[],
            min_confidence=0.0,
            limit=body.memory_limit,
        ) if body.memory_limit else []
        world = CONTINUAL_V16.query_facts(
            workspace_id,
            WorldFactQuery(limit=body.world_fact_limit, minimum_confidence=0.0),
        ) if body.world_fact_limit else None
        context = {
            "program": {
                "objective": program.objective,
                "success_criteria": program.success_criteria,
                "constraints": program.constraints,
                "risk_budget": program.risk_budget,
                "maximum_depth": program.maximum_depth,
                "maximum_nodes": program.maximum_nodes,
            },
            "goal": {
                "objective": goal.objective,
                "success_criteria": goal.success_criteria,
                "required_capabilities": goal.required_capabilities,
                "constraints": goal.constraints,
                "risk_tier": goal.risk_tier,
                "depth": goal.depth,
            },
            "memory_metadata": [
                {
                    "memory_id": item["memory_id"],
                    "kind": item["kind"],
                    "tags": item["tags"],
                    "confidence": item["confidence"],
                }
                for item in memories
            ],
            "world_fact_metadata": [] if world is None else [
                {
                    "fact_id": fact.fact_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "domain": fact.domain,
                    "confidence": fact.confidence,
                }
                for fact in world.facts
            ],
            "world_contradiction_detected": False if world is None else world.contradiction_detected,
        }
        return context, program, goal

    @staticmethod
    def _prompt(context: dict[str, Any], body: PlannerSynthesisRequest) -> str:
        schema = {
            "rationale": "short explanation",
            "subgoals": [{
                "objective": "bounded subgoal",
                "success_criteria": ["observable criterion"],
                "required_capabilities": ["capability"],
                "constraints": ["constraint"],
                "risk_tier": "moderate",
                "priority": 0.8,
                "maximum_attempts": 5,
            }],
        }
        return (
            "You are a bounded ORBYTHRA planning component. Return strict JSON only. "
            "Do not execute tools, grant permissions, alter policy, or claim completion. "
            "Success criteria must be observable. Avoid duplicate or circular goals. "
            f"Mode={body.mode}; maximum_subgoals={body.maximum_subgoals}. "
            "Schema=" + json.dumps(schema, ensure_ascii=False, separators=(",", ":")) +
            " Context(metadata-only)=" + json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
        )

    def synthesize(self, workspace_id: str, body: PlannerSynthesisRequest) -> PlannerProposal:
        context, program, goal = self._context(workspace_id, body)
        generated = GovernedHttpModelAdapter().generate(model_id=body.model_id, prompt=self._prompt(context, body))
        raw = str(generated["output"])
        try:
            parsed = json.loads(_strip_fence(raw))
        except json.JSONDecodeError as exc:
            raise ValueError("planner_invalid_json") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("subgoals"), list):
            raise ValueError("planner_invalid_schema")
        if not 1 <= len(parsed["subgoals"]) <= body.maximum_subgoals:
            raise ValueError("planner_subgoal_count_invalid")
        try:
            subgoals = [GoalSpec.model_validate(item) for item in parsed["subgoals"]]
        except Exception as exc:
            raise ValueError("planner_invalid_subgoal_schema") from exc
        normalized = [item.objective.strip().casefold() for item in subgoals]
        if len(set(normalized)) != len(normalized):
            raise ValueError("planner_duplicate_subgoal_objective")
        if goal.objective.strip().casefold() in set(normalized):
            raise ValueError("planner_parent_goal_restatement")
        for item in subgoals:
            if _RISK[item.risk_tier] > _RISK[program.risk_budget] or _RISK[item.risk_tier] > _RISK[goal.risk_tier]:
                raise ValueError("planner_subgoal_risk_exceeds_budget")
        rationale = parsed.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("planner_rationale_required")
        provider_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        payload = {
            "program_id": body.program_id,
            "goal_id": body.goal_id,
            "model_id": body.model_id,
            "mode": body.mode,
            "subgoals": [item.model_dump(mode="json") for item in subgoals],
            "rationale": rationale.strip(),
            "provider_response_sha256": provider_sha,
        }
        proposal_sha = _hash(payload)
        proposal_id = "pp19_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO planner_proposals_v19(
                workspace_id,proposal_id,program_id,goal_id,model_id,mode,payload_json,
                provider_response_sha256,proposal_sha256,applied,created_at
                ) VALUES(:w,:proposal,:program,:goal,:model,:mode,:payload,:provider,:sha,0,:created)"""
            ), {
                "w": workspace_id,
                "proposal": proposal_id,
                "program": body.program_id,
                "goal": body.goal_id,
                "model": body.model_id,
                "mode": body.mode,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="planner-proposal-v19"),
                "provider": provider_sha,
                "sha": proposal_sha,
                "created": now,
            })
        return PlannerProposal(
            proposal_id=proposal_id,
            program_id=body.program_id,
            goal_id=body.goal_id,
            model_id=body.model_id,
            mode=body.mode,
            subgoals=subgoals,
            rationale=rationale.strip(),
            provider_response_sha256=provider_sha,
            proposal_sha256=proposal_sha,
            applied=False,
            created_at=now,
        )

    def get(self, workspace_id: str, proposal_id: str) -> PlannerProposal | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM planner_proposals_v19 WHERE workspace_id=:w AND proposal_id=:proposal"
            ), {"w": workspace_id, "proposal": proposal_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="planner-proposal-v19")
        expected_sha = _hash(payload)
        if expected_sha != row["proposal_sha256"]:
            raise RuntimeError("planner_proposal_integrity_failed")
        return PlannerProposal(
            proposal_id=row["proposal_id"],
            program_id=row["program_id"],
            goal_id=row["goal_id"],
            model_id=row["model_id"],
            mode=row["mode"],
            subgoals=[GoalSpec.model_validate(item) for item in payload["subgoals"]],
            rationale=payload["rationale"],
            provider_response_sha256=row["provider_response_sha256"],
            proposal_sha256=row["proposal_sha256"],
            applied=bool(row["applied"]),
            created_at=int(row["created_at"]),
        )

    def apply(self, workspace_id: str, proposal_id: str) -> list[GoalRecord]:
        proposal = self.get(workspace_id, proposal_id)
        if proposal is None:
            raise ValueError("planner_proposal_not_found")
        if proposal.applied:
            raise ValueError("planner_proposal_already_applied")
        if proposal.mode == "REPLAN":
            goals = V17.replan_goal(
                workspace_id,
                proposal.goal_id,
                GoalReplanRequest(reason="V19 proposal " + proposal.proposal_sha256, replacement_subgoals=proposal.subgoals),
            )
        else:
            goals = V17.expand_goal(workspace_id, proposal.goal_id, GoalExpansionRequest(subgoals=proposal.subgoals))
        with self.engine.begin() as connection:
            connection.execute(text(
                "UPDATE planner_proposals_v19 SET applied=1 WHERE workspace_id=:w AND proposal_id=:proposal"
            ), {"w": workspace_id, "proposal": proposal_id})
        return goals


PLANNER_V19 = StructuredPlannerV19()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", action),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **metadata},
    )


@router.post("/synthesize", response_model=PlannerProposal)
def synthesize(body: PlannerSynthesisRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PlannerProposal:
    try:
        result = PLANNER_V19.synthesize(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v19_planner_synthesize", "PROPOSED", {"proposal_id": result.proposal_id})
    return result


@router.get("/proposals/{proposal_id}", response_model=PlannerProposal)
def get_proposal(proposal_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> PlannerProposal:
    result = PLANNER_V19.get(principal.workspace_id, proposal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="planner_proposal_not_found")
    return result


@router.post("/proposals/{proposal_id}/apply", response_model=list[GoalRecord])
def apply_proposal(proposal_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> list[GoalRecord]:
    try:
        result = PLANNER_V19.apply(principal.workspace_id, proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v19_planner_apply", "APPLIED", {"proposal_id": proposal_id, "goal_count": len(result)})
    return result
