from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agent_store import AGENT_STORE
from app.autonomy_models import SkillDefinition
from app.autonomy_store import AUTONOMY_STORE
from app.causal_intelligence_v11 import CausalRequest, evaluate as evaluate_causal
from app.continual_generalist_v16 import CONTINUAL_V16, SkillExperience, SkillPromotionPolicy
from app.crypto_core import canonical_json
from app.failure_memory_v15 import FAILURE_MEMORY_V15
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v17/generalist", tags=["v17-hierarchical-generalist"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")

RiskTier = Literal["low", "moderate", "high", "critical"]
GoalStatus = Literal["PENDING", "ACTIVE", "PAUSED", "COMPLETE", "FAILED", "SUPERSEDED"]
ProgramStatus = Literal["ACTIVE", "PAUSED", "COMPLETE", "FAILED"]
CandidateStatus = Literal["CANDIDATE", "TRIAL", "PROMOTABLE", "PROMOTED", "REJECTED"]
_RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class ProgramCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    objective: str = Field(min_length=1, max_length=20_000)
    success_criteria: list[str] = Field(min_length=1, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=200)
    risk_budget: RiskTier = "high"
    maximum_depth: int = Field(default=6, ge=1, le=12)
    maximum_nodes: int = Field(default=128, ge=2, le=5000)
    maximum_actions: int = Field(default=1000, ge=1, le=100_000)
    maximum_replans: int = Field(default=32, ge=0, le=10_000)


class ProgramRecord(BaseModel):
    program_id: str
    root_goal_id: str
    agent_id: str
    objective: str
    success_criteria: list[str]
    constraints: list[str]
    risk_budget: RiskTier
    maximum_depth: int
    maximum_nodes: int
    maximum_actions: int
    maximum_replans: int
    actions_used: int
    replans_used: int
    status: ProgramStatus
    created_at: int
    updated_at: int


class GoalSpec(BaseModel):
    objective: str = Field(min_length=1, max_length=10_000)
    success_criteria: list[str] = Field(min_length=1, max_length=50)
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=100)
    risk_tier: RiskTier = "moderate"
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    maximum_attempts: int = Field(default=5, ge=1, le=1000)


class GoalRecord(BaseModel):
    goal_id: str
    program_id: str
    parent_goal_id: str | None
    depth: int
    objective: str
    success_criteria: list[str]
    required_capabilities: list[str]
    constraints: list[str]
    risk_tier: RiskTier
    priority: float
    maximum_attempts: int
    attempts: int
    status: GoalStatus
    created_at: int
    updated_at: int


class GoalExpansionRequest(BaseModel):
    subgoals: list[GoalSpec] = Field(min_length=1, max_length=100)


class GoalCheckpointRequest(BaseModel):
    observations: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    criterion_results: dict[str, bool] = Field(default_factory=dict)
    action_ids: list[str] = Field(default_factory=list, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list, max_length=500)
    notes: str = Field(default="", max_length=20_000)


class GoalCheckpoint(BaseModel):
    checkpoint_id: str
    program_id: str
    goal_id: str
    attempt: int
    criterion_results: dict[str, bool]
    action_ids: list[str]
    evidence_refs: list[str]
    observations_sha256: str
    status: GoalStatus
    created_at: int


class GoalEvaluation(BaseModel):
    program_id: str
    goal_id: str
    status: GoalStatus
    criteria_satisfied: int
    criteria_total: int
    incomplete_child_goals: list[str]
    unsafe_action_ids: list[str]
    reason_codes: list[str]
    evaluation_sha256: str


class GoalReplanRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)
    replacement_subgoals: list[GoalSpec] = Field(min_length=1, max_length=100)


class ResumeState(BaseModel):
    program: ProgramRecord
    next_goal: GoalRecord | None
    active_goals: list[GoalRecord]
    paused_goals: list[GoalRecord]
    failed_goals: list[GoalRecord]
    completion_ratio: float
    release_blocked_by_failures: bool
    blocking_failure_ids: list[str]


class SkillTraceSynthesisRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    source_task_ids: list[str] = Field(min_length=2, max_length=1000)
    domains: list[str] = Field(min_length=1, max_length=100)
    procedure_steps: list[str] = Field(min_length=2, max_length=100)
    capabilities: list[str] = Field(min_length=1, max_length=100)
    required_tool_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_tier: RiskTier = "moderate"
    evidence_refs: list[str] = Field(min_length=1, max_length=500)


class SkillCandidate(BaseModel):
    candidate_id: str
    skill_id: str
    display_name: str
    description: str
    source_task_ids: list[str]
    domains: list[str]
    procedure_steps: list[str]
    capabilities: list[str]
    required_tool_ids: list[str]
    risk_tier: RiskTier
    evidence_refs: list[str]
    evidence_sha256: str
    status: CandidateStatus
    created_at: int


class SkillTrialRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    domain: str = Field(min_length=1, max_length=120)
    success: bool
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    regression_safe: bool
    novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class SkillCandidateDecision(BaseModel):
    candidate_id: str
    skill_id: str
    status: CandidateStatus
    trial_count: int
    v16_eligible: bool
    v16_decision_sha256: str
    reasons: list[str]
    decision_sha256: str


class SkillCandidatePromotionRequest(BaseModel):
    version: str = Field(default="1.0.0", min_length=1, max_length=40)
    policy: SkillPromotionPolicy = Field(default_factory=SkillPromotionPolicy)


class VerifiedCausalModelRequest(BaseModel):
    causal_request: CausalRequest


class VerifiedCausalModel(BaseModel):
    model_id: str
    request_id: str
    graph_sha256: str
    evidence_sha256: str
    nodes: list[str]
    edges: list[dict[str, str]]
    created_at: int


class CounterfactualImpactRequest(BaseModel):
    intervention_node: str = Field(min_length=1, max_length=500)
    maximum_hops: int = Field(default=8, ge=1, le=50)


class CounterfactualImpactResult(BaseModel):
    model_id: str
    intervention_node: str
    impacted_nodes: list[str]
    paths: list[list[str]]
    maximum_hops: int
    result_sha256: str
    boundary: str


class HierarchicalGeneralistV17:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS hierarchical_programs_v17(
            workspace_id TEXT NOT NULL, program_id TEXT NOT NULL, agent_id TEXT NOT NULL, root_goal_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, status TEXT NOT NULL, actions_used BIGINT NOT NULL, replans_used BIGINT NOT NULL,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,program_id))""",
            """CREATE TABLE IF NOT EXISTS hierarchical_goals_v17(
            workspace_id TEXT NOT NULL, program_id TEXT NOT NULL, goal_id TEXT NOT NULL, parent_goal_id TEXT,
            depth BIGINT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, attempts BIGINT NOT NULL,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,goal_id))""",
            "CREATE INDEX IF NOT EXISTS idx_v17_goal_program ON hierarchical_goals_v17(workspace_id,program_id,status,depth)",
            """CREATE TABLE IF NOT EXISTS hierarchical_checkpoints_v17(
            workspace_id TEXT NOT NULL, checkpoint_id TEXT NOT NULL, program_id TEXT NOT NULL, goal_id TEXT NOT NULL,
            attempt BIGINT NOT NULL, payload_json TEXT NOT NULL, created_at BIGINT NOT NULL,
            PRIMARY KEY(workspace_id,checkpoint_id))""",
            """CREATE TABLE IF NOT EXISTS hierarchical_actions_v17(
            workspace_id TEXT NOT NULL, program_id TEXT NOT NULL, action_id TEXT NOT NULL, goal_id TEXT NOT NULL,
            first_checkpoint_id TEXT NOT NULL, created_at BIGINT NOT NULL,
            PRIMARY KEY(workspace_id,program_id,action_id))""",
            """CREATE TABLE IF NOT EXISTS skill_candidates_v17(
            workspace_id TEXT NOT NULL, candidate_id TEXT NOT NULL, skill_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, status TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,candidate_id), UNIQUE(workspace_id,skill_id))""",
            """CREATE TABLE IF NOT EXISTS skill_trials_v17(
            workspace_id TEXT NOT NULL, trial_id TEXT NOT NULL, candidate_id TEXT NOT NULL, payload_json TEXT NOT NULL,
            created_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,trial_id))""",
            """CREATE TABLE IF NOT EXISTS causal_models_v17(
            workspace_id TEXT NOT NULL, model_id TEXT NOT NULL, request_id TEXT NOT NULL, graph_sha256 TEXT NOT NULL,
            evidence_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, created_at BIGINT NOT NULL,
            PRIMARY KEY(workspace_id,model_id))""",
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def create_program(self, workspace_id: str, body: ProgramCreate) -> ProgramRecord:
        agent = AGENT_STORE.get_agent(workspace_id, body.agent_id)
        if agent is None or not agent.get("enabled", True):
            raise ValueError("agent_not_active")
        agent_ceiling = str(agent.get("max_risk_tier", "high"))
        if _RISK[body.risk_budget] > _RISK.get(agent_ceiling, 2):
            raise ValueError("program_risk_budget_exceeds_agent_ceiling")
        now = int(time.time())
        program_id = "pg17_" + uuid.uuid4().hex[:24]
        root_goal_id = "goal17_" + uuid.uuid4().hex[:24]
        program_payload = body.model_dump(mode="json")
        root = GoalSpec(
            objective=body.objective,
            success_criteria=body.success_criteria,
            required_capabilities=[],
            constraints=body.constraints,
            risk_tier=body.risk_budget,
            priority=1.0,
            maximum_attempts=max(5, min(1000, body.maximum_replans + 1)),
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO hierarchical_programs_v17(
                workspace_id,program_id,agent_id,root_goal_id,payload_json,status,actions_used,replans_used,created_at,updated_at
                ) VALUES(:w,:program,:agent,:root,:payload,'ACTIVE',0,0,:created,:updated)"""
            ), {
                "w": workspace_id, "program": program_id, "agent": body.agent_id, "root": root_goal_id,
                "payload": VAULT.encrypt_json(program_payload, workspace_id=workspace_id, purpose="program-v17"),
                "created": now, "updated": now,
            })
            connection.execute(text(
                """INSERT INTO hierarchical_goals_v17(
                workspace_id,program_id,goal_id,parent_goal_id,depth,payload_json,status,attempts,created_at,updated_at
                ) VALUES(:w,:program,:goal,NULL,0,:payload,'ACTIVE',0,:created,:updated)"""
            ), {
                "w": workspace_id, "program": program_id, "goal": root_goal_id,
                "payload": VAULT.encrypt_json(root.model_dump(mode="json"), workspace_id=workspace_id, purpose="goal-v17"),
                "created": now, "updated": now,
            })
        result = self.get_program(workspace_id, program_id)
        if result is None:
            raise RuntimeError("program_not_persisted")
        return result

    def get_program(self, workspace_id: str, program_id: str) -> ProgramRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM hierarchical_programs_v17 WHERE workspace_id=:w AND program_id=:program"
            ), {"w": workspace_id, "program": program_id}).mappings().first()
        if row is None:
            return None
        body = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="program-v17")
        body = {key: value for key, value in body.items() if key != "agent_id"}
        return ProgramRecord(
            program_id=row["program_id"], root_goal_id=row["root_goal_id"], agent_id=row["agent_id"],
            **body, actions_used=int(row["actions_used"]), replans_used=int(row["replans_used"]),
            status=row["status"], created_at=int(row["created_at"]), updated_at=int(row["updated_at"]),
        )

    def get_goal(self, workspace_id: str, goal_id: str) -> GoalRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM hierarchical_goals_v17 WHERE workspace_id=:w AND goal_id=:goal"
            ), {"w": workspace_id, "goal": goal_id}).mappings().first()
        if row is None:
            return None
        body = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="goal-v17")
        return GoalRecord(
            goal_id=row["goal_id"], program_id=row["program_id"], parent_goal_id=row["parent_goal_id"],
            depth=int(row["depth"]), **body, attempts=int(row["attempts"]), status=row["status"],
            created_at=int(row["created_at"]), updated_at=int(row["updated_at"]),
        )

    def list_goals(self, workspace_id: str, program_id: str) -> list[GoalRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT goal_id FROM hierarchical_goals_v17 WHERE workspace_id=:w AND program_id=:program ORDER BY depth,created_at,goal_id"
            ), {"w": workspace_id, "program": program_id}).mappings().all()
        return [goal for row in rows if (goal := self.get_goal(workspace_id, row["goal_id"])) is not None]

    def expand_goal(self, workspace_id: str, goal_id: str, body: GoalExpansionRequest) -> list[GoalRecord]:
        parent = self.get_goal(workspace_id, goal_id)
        if parent is None:
            raise ValueError("goal_not_found")
        if parent.status in {"COMPLETE", "FAILED", "SUPERSEDED"}:
            raise ValueError("goal_terminal")
        program = self.get_program(workspace_id, parent.program_id)
        if program is None:
            raise RuntimeError("program_missing")
        if parent.depth + 1 > program.maximum_depth:
            raise ValueError("program_maximum_depth_exceeded")
        current = self.list_goals(workspace_id, program.program_id)
        if len(current) + len(body.subgoals) > program.maximum_nodes:
            raise ValueError("program_maximum_nodes_exceeded")
        normalized = [item.objective.strip().casefold() for item in body.subgoals]
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate_subgoal_objective")
        for spec in body.subgoals:
            if _RISK[spec.risk_tier] > _RISK[program.risk_budget]:
                raise ValueError("subgoal_risk_exceeds_program_budget")
        now = int(time.time())
        created: list[str] = []
        with self.engine.begin() as connection:
            for spec in body.subgoals:
                child_id = "goal17_" + uuid.uuid4().hex[:24]
                connection.execute(text(
                    """INSERT INTO hierarchical_goals_v17(
                    workspace_id,program_id,goal_id,parent_goal_id,depth,payload_json,status,attempts,created_at,updated_at
                    ) VALUES(:w,:program,:goal,:parent,:depth,:payload,'PENDING',0,:created,:updated)"""
                ), {
                    "w": workspace_id, "program": parent.program_id, "goal": child_id, "parent": goal_id,
                    "depth": parent.depth + 1,
                    "payload": VAULT.encrypt_json(spec.model_dump(mode="json"), workspace_id=workspace_id, purpose="goal-v17"),
                    "created": now, "updated": now,
                })
                created.append(child_id)
        return [goal for child_id in created if (goal := self.get_goal(workspace_id, child_id)) is not None]

    def checkpoint(self, workspace_id: str, goal_id: str, body: GoalCheckpointRequest) -> GoalCheckpoint:
        goal = self.get_goal(workspace_id, goal_id)
        if goal is None:
            raise ValueError("goal_not_found")
        if goal.status in {"COMPLETE", "FAILED", "SUPERSEDED"}:
            raise ValueError("goal_terminal")
        program = self.get_program(workspace_id, goal.program_id)
        if program is None:
            raise RuntimeError("program_missing")
        unique_actions = list(dict.fromkeys(body.action_ids))
        with self.engine.connect() as connection:
            existing_action_ids = {
                row["action_id"]
                for row in connection.execute(text(
                    "SELECT action_id FROM hierarchical_actions_v17 WHERE workspace_id=:w AND program_id=:program"
                ), {"w": workspace_id, "program": program.program_id}).mappings().all()
            }
        new_actions = [action_id for action_id in unique_actions if action_id not in existing_action_ids]
        if program.actions_used + len(new_actions) > program.maximum_actions:
            raise ValueError("program_action_budget_exceeded")
        unsafe: list[str] = []
        for action_id in unique_actions:
            action = AGENT_STORE.get_action(workspace_id, action_id)
            if action is None:
                raise ValueError("action_not_found:" + action_id)
            if action["agent_id"] != program.agent_id:
                raise ValueError("action_agent_mismatch:" + action_id)
            if action["status"] in {"BLOCKED", "POLICY_REVOKED", "OUTCOME_MISMATCH"}:
                unsafe.append(action_id)
        attempt = goal.attempts + 1
        status: GoalStatus = "PAUSED" if unsafe else "ACTIVE"
        checkpoint_id = "ck17_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        payload = body.model_dump(mode="json")
        payload["unsafe_action_ids"] = unsafe
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO hierarchical_checkpoints_v17(
                workspace_id,checkpoint_id,program_id,goal_id,attempt,payload_json,created_at
                ) VALUES(:w,:checkpoint,:program,:goal,:attempt,:payload,:created)"""
            ), {
                "w": workspace_id, "checkpoint": checkpoint_id, "program": goal.program_id, "goal": goal_id,
                "attempt": attempt,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="checkpoint-v17"),
                "created": now,
            })
            connection.execute(text(
                "UPDATE hierarchical_goals_v17 SET attempts=:attempts,status=:status,updated_at=:updated WHERE workspace_id=:w AND goal_id=:goal"
            ), {"attempts": attempt, "status": status, "updated": now, "w": workspace_id, "goal": goal_id})
            for action_id in new_actions:
                connection.execute(text(
                    """INSERT INTO hierarchical_actions_v17(
                    workspace_id,program_id,action_id,goal_id,first_checkpoint_id,created_at
                    ) VALUES(:w,:program,:action,:goal,:checkpoint,:created)"""
                ), {
                    "w": workspace_id, "program": goal.program_id, "action": action_id,
                    "goal": goal_id, "checkpoint": checkpoint_id, "created": now,
                })
            connection.execute(text(
                "UPDATE hierarchical_programs_v17 SET actions_used=actions_used+:inc,updated_at=:updated WHERE workspace_id=:w AND program_id=:program"
            ), {"inc": len(new_actions), "updated": now, "w": workspace_id, "program": goal.program_id})
        return GoalCheckpoint(
            checkpoint_id=checkpoint_id, program_id=goal.program_id, goal_id=goal_id, attempt=attempt,
            criterion_results=body.criterion_results, action_ids=unique_actions, evidence_refs=body.evidence_refs,
            observations_sha256=_hash(body.observations), status=status, created_at=now,
        )

    def _latest_checkpoint(self, workspace_id: str, goal_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM hierarchical_checkpoints_v17 WHERE workspace_id=:w AND goal_id=:goal ORDER BY attempt DESC,created_at DESC LIMIT 1"
            ), {"w": workspace_id, "goal": goal_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="checkpoint-v17")
        return {**payload, "checkpoint_id": row["checkpoint_id"], "attempt": int(row["attempt"]), "created_at": int(row["created_at"])}

    def evaluate_goal(self, workspace_id: str, goal_id: str) -> GoalEvaluation:
        goal = self.get_goal(workspace_id, goal_id)
        if goal is None:
            raise ValueError("goal_not_found")
        checkpoint = self._latest_checkpoint(workspace_id, goal_id)
        children = [g for g in self.list_goals(workspace_id, goal.program_id) if g.parent_goal_id == goal_id and g.status != "SUPERSEDED"]
        incomplete_children = sorted(g.goal_id for g in children if g.status != "COMPLETE")
        criterion_results = {} if checkpoint is None else dict(checkpoint.get("criterion_results") or {})
        satisfied = sum(criterion_results.get(c) is True for c in goal.success_criteria)
        unsafe = [] if checkpoint is None else list(checkpoint.get("unsafe_action_ids") or [])
        reasons: list[str] = []
        if unsafe:
            status: GoalStatus = "PAUSED"
            reasons.append("unsafe_or_revoked_action_requires_review")
        elif incomplete_children:
            status = "ACTIVE"
            reasons.append("child_goals_incomplete")
        elif satisfied == len(goal.success_criteria):
            status = "COMPLETE"
            reasons.append("all_success_criteria_verified")
        elif goal.attempts >= goal.maximum_attempts:
            status = "FAILED"
            reasons.append("maximum_attempts_reached")
        else:
            status = "ACTIVE"
            reasons.append("success_criteria_incomplete")
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                "UPDATE hierarchical_goals_v17 SET status=:status,updated_at=:updated WHERE workspace_id=:w AND goal_id=:goal"
            ), {"status": status, "updated": now, "w": workspace_id, "goal": goal_id})
        payload = {
            "program_id": goal.program_id, "goal_id": goal_id, "status": status,
            "criteria_satisfied": satisfied, "criteria_total": len(goal.success_criteria),
            "incomplete_child_goals": incomplete_children, "unsafe_action_ids": unsafe,
            "reason_codes": reasons,
        }
        self._refresh_program_status(workspace_id, goal.program_id)
        return GoalEvaluation(**payload, evaluation_sha256=_hash(payload))

    def replan_goal(self, workspace_id: str, goal_id: str, body: GoalReplanRequest) -> list[GoalRecord]:
        goal = self.get_goal(workspace_id, goal_id)
        if goal is None:
            raise ValueError("goal_not_found")
        program = self.get_program(workspace_id, goal.program_id)
        if program is None:
            raise RuntimeError("program_missing")
        if program.replans_used >= program.maximum_replans:
            raise ValueError("program_replan_budget_exceeded")
        existing_children = [g for g in self.list_goals(workspace_id, program.program_id) if g.parent_goal_id == goal_id and g.status != "SUPERSEDED"]
        now = int(time.time())
        with self.engine.begin() as connection:
            for child in existing_children:
                if child.status != "COMPLETE":
                    connection.execute(text(
                        "UPDATE hierarchical_goals_v17 SET status='SUPERSEDED',updated_at=:updated WHERE workspace_id=:w AND goal_id=:goal"
                    ), {"updated": now, "w": workspace_id, "goal": child.goal_id})
            connection.execute(text(
                "UPDATE hierarchical_programs_v17 SET replans_used=replans_used+1,updated_at=:updated WHERE workspace_id=:w AND program_id=:program"
            ), {"updated": now, "w": workspace_id, "program": program.program_id})
            connection.execute(text(
                "UPDATE hierarchical_goals_v17 SET status='ACTIVE',updated_at=:updated WHERE workspace_id=:w AND goal_id=:goal"
            ), {"updated": now, "w": workspace_id, "goal": goal_id})
        return self.expand_goal(workspace_id, goal_id, GoalExpansionRequest(subgoals=body.replacement_subgoals))

    def _refresh_program_status(self, workspace_id: str, program_id: str) -> None:
        program = self.get_program(workspace_id, program_id)
        if program is None:
            return
        root = self.get_goal(workspace_id, program.root_goal_id)
        if root is None:
            return
        status: ProgramStatus
        if root.status == "COMPLETE":
            status = "COMPLETE"
        elif root.status == "FAILED":
            status = "FAILED"
        elif root.status == "PAUSED":
            status = "PAUSED"
        else:
            status = "ACTIVE"
        with self.engine.begin() as connection:
            connection.execute(text(
                "UPDATE hierarchical_programs_v17 SET status=:status,updated_at=:updated WHERE workspace_id=:w AND program_id=:program"
            ), {"status": status, "updated": int(time.time()), "w": workspace_id, "program": program_id})

    def resume_state(self, workspace_id: str, program_id: str) -> ResumeState:
        program = self.get_program(workspace_id, program_id)
        if program is None:
            raise ValueError("program_not_found")
        goals = self.list_goals(workspace_id, program_id)
        live = [g for g in goals if g.status in {"PENDING", "ACTIVE"}]
        incomplete_parent_ids = {
            g.parent_goal_id
            for g in goals
            if g.parent_goal_id is not None and g.status not in {"COMPLETE", "SUPERSEDED"}
        }
        actionable_leaves = [g for g in live if g.goal_id not in incomplete_parent_ids]
        actionable_leaves.sort(key=lambda g: (-g.priority, -g.depth, g.created_at, g.goal_id))
        next_goal = actionable_leaves[0] if actionable_leaves else None
        active = live
        paused = [g for g in goals if g.status == "PAUSED"]
        failed = [g for g in goals if g.status == "FAILED"]
        non_superseded = [g for g in goals if g.status != "SUPERSEDED"]
        completed = sum(g.status == "COMPLETE" for g in non_superseded)
        ratio = completed / len(non_superseded) if non_superseded else 0.0
        failure_gate = FAILURE_MEMORY_V15.release_gate(workspace_id)
        return ResumeState(
            program=program, next_goal=next_goal, active_goals=active, paused_goals=paused, failed_goals=failed,
            completion_ratio=round(ratio, 6), release_blocked_by_failures=failure_gate.status == "BLOCK",
            blocking_failure_ids=failure_gate.blocking_failure_ids,
        )

    def synthesize_candidate(self, workspace_id: str, body: SkillTraceSynthesisRequest) -> SkillCandidate:
        for tool_id in body.required_tool_ids:
            tool = AGENT_STORE.get_tool(workspace_id, tool_id)
            if tool is None or not tool.get("enabled", True):
                raise ValueError("skill_tool_not_active:" + tool_id)
        now = int(time.time())
        candidate_id = "skc17_" + uuid.uuid4().hex[:24]
        evidence_sha = _hash({
            "source_task_ids": sorted(set(body.source_task_ids)),
            "evidence_refs": sorted(set(body.evidence_refs)),
            "procedure_steps": body.procedure_steps,
        })
        payload = body.model_dump(mode="json")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO skill_candidates_v17(
                workspace_id,candidate_id,skill_id,payload_json,status,evidence_sha256,created_at,updated_at
                ) VALUES(:w,:candidate,:skill,:payload,'CANDIDATE',:evidence,:created,:updated)"""
            ), {
                "w": workspace_id, "candidate": candidate_id, "skill": body.skill_id,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="skill-candidate-v17"),
                "evidence": evidence_sha, "created": now, "updated": now,
            })
        return SkillCandidate(
            candidate_id=candidate_id, **payload, evidence_sha256=evidence_sha, status="CANDIDATE", created_at=now
        )

    def get_candidate(self, workspace_id: str, candidate_id: str) -> SkillCandidate | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM skill_candidates_v17 WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"w": workspace_id, "candidate": candidate_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="skill-candidate-v17")
        return SkillCandidate(
            candidate_id=row["candidate_id"], **payload, evidence_sha256=row["evidence_sha256"],
            status=row["status"], created_at=int(row["created_at"])
        )

    def record_trial(self, workspace_id: str, candidate_id: str, body: SkillTrialRequest) -> SkillCandidateDecision:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("skill_candidate_not_found")
        if candidate.status in {"PROMOTED", "REJECTED"}:
            raise ValueError("skill_candidate_terminal")
        now = int(time.time())
        trial_id = "skt17_" + uuid.uuid4().hex[:24]
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO skill_trials_v17(workspace_id,trial_id,candidate_id,payload_json,created_at)
                VALUES(:w,:trial,:candidate,:payload,:created)"""
            ), {
                "w": workspace_id, "trial": trial_id, "candidate": candidate_id,
                "payload": VAULT.encrypt_json(body.model_dump(mode="json"), workspace_id=workspace_id, purpose="skill-trial-v17"),
                "created": now,
            })
            connection.execute(text(
                "UPDATE skill_candidates_v17 SET status='TRIAL',updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"updated": now, "w": workspace_id, "candidate": candidate_id})
        CONTINUAL_V16.record_experience(workspace_id, SkillExperience(
            task_id=body.task_id, skill_id=candidate.skill_id, domain=body.domain, success=body.success,
            evidence_coverage=body.evidence_coverage, confidence=body.confidence,
            regression_safe=body.regression_safe, novelty=body.novelty, source_refs=body.evidence_refs,
        ))
        return self.candidate_decision(workspace_id, candidate_id, SkillPromotionPolicy())

    def candidate_decision(self, workspace_id: str, candidate_id: str, policy: SkillPromotionPolicy) -> SkillCandidateDecision:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("skill_candidate_not_found")
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT payload_json FROM skill_trials_v17 WHERE workspace_id=:w AND candidate_id=:candidate ORDER BY created_at,trial_id"
            ), {"w": workspace_id, "candidate": candidate_id}).mappings().all()
        trials = [
            VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="skill-trial-v17")
            for row in rows
        ]
        count = len(trials)
        domains = {str(row["domain"]) for row in trials}
        success_rate = sum(bool(row["success"]) for row in trials) / count if count else 0.0
        evidence_rate = sum(float(row["evidence_coverage"]) for row in trials) / count if count else 0.0
        safe_rate = sum(bool(row["regression_safe"]) for row in trials) / count if count else 0.0
        high_novelty_successes = sum(
            bool(row["success"]) and float(row["novelty"]) >= policy.high_novelty_threshold
            for row in trials
        )
        candidate_reasons: list[str] = []
        if count < policy.minimum_observations:
            candidate_reasons.append("candidate_insufficient_trials")
        if len(domains) < policy.minimum_domains:
            candidate_reasons.append("candidate_insufficient_domain_transfer")
        if success_rate < policy.minimum_success_rate:
            candidate_reasons.append("candidate_success_rate_below_threshold")
        if evidence_rate < policy.minimum_evidence_coverage:
            candidate_reasons.append("candidate_evidence_coverage_below_threshold")
        if safe_rate < policy.minimum_regression_safe_rate:
            candidate_reasons.append("candidate_regression_safety_below_threshold")
        if high_novelty_successes < policy.minimum_high_novelty_successes:
            candidate_reasons.append("candidate_insufficient_high_novelty_success")

        decision = CONTINUAL_V16.evaluate_promotion(workspace_id, candidate.skill_id, policy)
        eligible = decision.eligible and not candidate_reasons
        status: CandidateStatus = "PROMOTABLE" if eligible else ("TRIAL" if count else "CANDIDATE")
        if candidate.status in {"PROMOTED", "REJECTED"}:
            status = candidate.status
        reasons = list(dict.fromkeys([*candidate_reasons, *([] if decision.eligible else decision.reasons)]))
        if eligible:
            reasons = ["candidate_and_v16_promotion_thresholds_satisfied"]
        payload = {
            "candidate_id": candidate_id, "skill_id": candidate.skill_id, "status": status,
            "trial_count": count, "v16_eligible": eligible,
            "v16_decision_sha256": decision.decision_sha256, "reasons": reasons,
        }
        if status == "PROMOTABLE" and candidate.status != "PROMOTABLE":
            with self.engine.begin() as connection:
                connection.execute(text(
                    "UPDATE skill_candidates_v17 SET status='PROMOTABLE',updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
                ), {"updated": int(time.time()), "w": workspace_id, "candidate": candidate_id})
        return SkillCandidateDecision(**payload, decision_sha256=_hash(payload))

    def promote_candidate(self, workspace_id: str, candidate_id: str, body: SkillCandidatePromotionRequest) -> SkillDefinition:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("skill_candidate_not_found")
        decision = self.candidate_decision(workspace_id, candidate_id, body.policy)
        if not decision.v16_eligible:
            raise ValueError("skill_candidate_not_promotable")
        skill = SkillDefinition(
            skill_id=candidate.skill_id, display_name=candidate.display_name, version=body.version,
            description=candidate.description + "\nProcedure: " + " -> ".join(candidate.procedure_steps),
            capabilities=candidate.capabilities, required_tool_ids=candidate.required_tool_ids,
            risk_tier=candidate.risk_tier, enabled=True,
        )
        AUTONOMY_STORE.upsert_skill(workspace_id, skill.model_dump(mode="json"))
        with self.engine.begin() as connection:
            connection.execute(text(
                "UPDATE skill_candidates_v17 SET status='PROMOTED',updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"updated": int(time.time()), "w": workspace_id, "candidate": candidate_id})
        return skill

    def register_causal_model(self, workspace_id: str, body: VerifiedCausalModelRequest) -> VerifiedCausalModel:
        result = evaluate_causal(body.causal_request, workspace_id)
        if result.status != "PASS":
            raise ValueError("causal_model_not_verified")
        now = int(time.time())
        model_id = "cm17_" + uuid.uuid4().hex[:24]
        edges = [{"cause": edge.cause, "effect": edge.effect} for edge in body.causal_request.edges]
        nodes = sorted({edge["cause"] for edge in edges} | {edge["effect"] for edge in edges})
        payload = {"request_id": body.causal_request.request_id, "nodes": nodes, "edges": edges}
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO causal_models_v17(
                workspace_id,model_id,request_id,graph_sha256,evidence_sha256,payload_json,created_at
                ) VALUES(:w,:model,:request,:graph,:evidence,:payload,:created)"""
            ), {
                "w": workspace_id, "model": model_id, "request": body.causal_request.request_id,
                "graph": result.graph_sha256, "evidence": result.evidence_sha256,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="causal-model-v17"),
                "created": now,
            })
        return VerifiedCausalModel(
            model_id=model_id, request_id=body.causal_request.request_id, graph_sha256=result.graph_sha256,
            evidence_sha256=result.evidence_sha256, nodes=nodes, edges=edges, created_at=now,
        )

    def counterfactual_impact(self, workspace_id: str, model_id: str, body: CounterfactualImpactRequest) -> CounterfactualImpactResult:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT payload_json FROM causal_models_v17 WHERE workspace_id=:w AND model_id=:model"
            ), {"w": workspace_id, "model": model_id}).mappings().first()
        if row is None:
            raise ValueError("causal_model_not_found")
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="causal-model-v17")
        if body.intervention_node not in payload["nodes"]:
            raise ValueError("intervention_node_not_in_model")
        adjacency: dict[str, list[str]] = {node: [] for node in payload["nodes"]}
        for edge in payload["edges"]:
            adjacency[edge["cause"]].append(edge["effect"])
        paths: list[list[str]] = []
        queue: list[list[str]] = [[body.intervention_node]]
        while queue:
            path = queue.pop(0)
            if len(path) - 1 >= body.maximum_hops:
                continue
            for nxt in sorted(adjacency.get(path[-1], [])):
                if nxt in path:
                    continue
                new_path = [*path, nxt]
                paths.append(new_path)
                queue.append(new_path)
        impacted = sorted({node for path in paths for node in path[1:]})
        result_payload = {
            "model_id": model_id, "intervention_node": body.intervention_node,
            "impacted_nodes": impacted, "paths": paths, "maximum_hops": body.maximum_hops,
        }
        return CounterfactualImpactResult(
            **result_payload, result_sha256=_hash(result_payload),
            boundary=(
                "Structural reachability over an evidence-gated causal hypothesis graph. "
                "This identifies downstream variables that may be affected; it does not estimate intervention magnitude, "
                "guarantee real-world causation, or replace experimental validation."
            ),
        )


V17 = HierarchicalGeneralistV17()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", action),
        principal_id=principal.principal_id, workspace_id=principal.workspace_id,
        action=action, status=status, metadata={"role": principal.role, **metadata},
    )


@router.post("/programs", response_model=ProgramRecord)
def create_program(body: ProgramCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> ProgramRecord:
    try:
        result = V17.create_program(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, principal, "v17_program_create", "ACTIVE", {"program_id": result.program_id})
    return result


@router.get("/programs/{program_id}", response_model=ProgramRecord)
def get_program(program_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ProgramRecord:
    result = V17.get_program(principal.workspace_id, program_id)
    if result is None:
        raise HTTPException(status_code=404, detail="program_not_found")
    return result


@router.post("/goals/{goal_id}/expand", response_model=list[GoalRecord])
def expand_goal(goal_id: str, body: GoalExpansionRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> list[GoalRecord]:
    try:
        result = V17.expand_goal(principal.workspace_id, goal_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v17_goal_expand", "CREATED", {"goal_id": goal_id, "children": len(result)})
    return result


@router.post("/goals/{goal_id}/checkpoint", response_model=GoalCheckpoint)
def checkpoint(goal_id: str, body: GoalCheckpointRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> GoalCheckpoint:
    try:
        result = V17.checkpoint(principal.workspace_id, goal_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v17_goal_checkpoint", result.status, {"goal_id": goal_id, "attempt": result.attempt})
    return result


@router.post("/goals/{goal_id}/evaluate", response_model=GoalEvaluation)
def evaluate_goal(goal_id: str, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> GoalEvaluation:
    try:
        result = V17.evaluate_goal(principal.workspace_id, goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(request, principal, "v17_goal_evaluate", result.status, {"goal_id": goal_id, "evaluation_sha256": result.evaluation_sha256})
    return result


@router.post("/goals/{goal_id}/replan", response_model=list[GoalRecord])
def replan_goal(goal_id: str, body: GoalReplanRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> list[GoalRecord]:
    try:
        result = V17.replan_goal(principal.workspace_id, goal_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v17_goal_replan", "REPLANNED", {"goal_id": goal_id, "replacement_count": len(result)})
    return result


@router.get("/programs/{program_id}/resume", response_model=ResumeState)
def resume(program_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ResumeState:
    try:
        return V17.resume_state(principal.workspace_id, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/skills/synthesize", response_model=SkillCandidate)
def synthesize_skill(body: SkillTraceSynthesisRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> SkillCandidate:
    try:
        result = V17.synthesize_candidate(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, principal, "v17_skill_synthesize", "CANDIDATE", {"candidate_id": result.candidate_id, "skill_id": result.skill_id})
    return result


@router.post("/skills/{candidate_id}/trials", response_model=SkillCandidateDecision)
def record_skill_trial(candidate_id: str, body: SkillTrialRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> SkillCandidateDecision:
    try:
        result = V17.record_trial(principal.workspace_id, candidate_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v17_skill_trial", result.status, {"candidate_id": candidate_id, "trial_count": result.trial_count})
    return result


@router.post("/skills/{candidate_id}/decision", response_model=SkillCandidateDecision)
def skill_candidate_decision(candidate_id: str, policy: SkillPromotionPolicy, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> SkillCandidateDecision:
    try:
        return V17.candidate_decision(principal.workspace_id, candidate_id, policy)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/skills/{candidate_id}/promote", response_model=SkillDefinition)
def promote_skill_candidate(candidate_id: str, body: SkillCandidatePromotionRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> SkillDefinition:
    try:
        result = V17.promote_candidate(principal.workspace_id, candidate_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v17_skill_promote", "PROMOTED", {"candidate_id": candidate_id, "skill_id": result.skill_id})
    return result


@router.post("/causal/models", response_model=VerifiedCausalModel)
def register_causal_model(body: VerifiedCausalModelRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> VerifiedCausalModel:
    try:
        result = V17.register_causal_model(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v17_causal_model", "VERIFIED", {"model_id": result.model_id, "graph_sha256": result.graph_sha256})
    return result


@router.post("/causal/models/{model_id}/counterfactual-impact", response_model=CounterfactualImpactResult)
def counterfactual_impact(model_id: str, body: CounterfactualImpactRequest, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> CounterfactualImpactResult:
    try:
        return V17.counterfactual_impact(principal.workspace_id, model_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v17",
        "persistent_hierarchical_programs": True,
        "bounded_long_horizon_resume": True,
        "checkpoint_and_replan": True,
        "execution_action_binding": True,
        "failure_memory_release_gate_binding": True,
        "trace_based_skill_synthesis": True,
        "cross_domain_trial_promotion": True,
        "evidence_gated_causal_model": True,
        "bounded_counterfactual_reachability": True,
        "unrestricted_self_modification": False,
        "model_weight_learning": False,
        "live_agi_claim": False,
        "boundary": (
            "V17 adds bounded long-horizon hierarchical orchestration, resumable checkpoints, re-planning, "
            "trace-based skill synthesis and evidence-gated causal impact analysis. It does not prove AGI, "
            "unrestricted autonomous self-improvement, consciousness, or safe open-ended real-world agency."
        ),
    }
