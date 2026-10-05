from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v23/general-agent", tags=["v23-verifiable-general-agent"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")

RiskTier = Literal["low", "moderate", "high", "critical"]
Decision = Literal["ELIGIBLE", "REVIEW", "BLOCK"]


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class EpisodeCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    event_type: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=4000)
    observations: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list, max_length=200)
    occurred_at: int | None = Field(default=None, ge=0)


class EpisodeRecord(BaseModel):
    episode_id: str
    agent_id: str
    event_type: str
    summary: str
    observations: dict[str, Any]
    evidence_refs: list[str]
    occurred_at: int
    content_sha256: str
    created_at: int


class GoalCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    objective: str = Field(min_length=1, max_length=4000)
    success_criteria: list[str] = Field(min_length=1, max_length=100)
    priority: int = Field(default=50, ge=0, le=100)
    horizon_days: int = Field(default=30, ge=1, le=3650)


class GoalRecord(BaseModel):
    goal_id: str
    agent_id: str
    objective: str
    success_criteria: list[str]
    priority: int
    horizon_days: int
    status: Literal["ACTIVE", "PAUSED", "COMPLETED", "CANCELLED"]
    objective_sha256: str
    created_at: int


class ActionCandidate(BaseModel):
    action_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    description: str = Field(min_length=1, max_length=4000)
    expected_utility: float = Field(ge=-1.0, le=1.0)
    failure_probability: float = Field(ge=0.0, le=1.0)
    reversibility: float = Field(ge=0.0, le=1.0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    risk_tier: RiskTier


class SimulatedAction(BaseModel):
    action_id: str
    decision: Decision
    score: float
    reasons: list[str]


class SimulationRequest(BaseModel):
    current_state: dict[str, Any]
    candidates: list[ActionCandidate] = Field(min_length=1, max_length=100)


class SimulationResponse(BaseModel):
    selected_action_id: str | None
    requires_human_review: bool
    actions: list[SimulatedAction]
    current_state_sha256: str
    simulation_sha256: str
    boundary: str


class AgentCycleRequest(BaseModel):
    goal_id: str = Field(min_length=1, max_length=100)
    episode: EpisodeCreate
    current_state: dict[str, Any]
    candidates: list[ActionCandidate] = Field(min_length=1, max_length=100)


class AgentCycleResponse(BaseModel):
    status: Literal["READY", "REVIEW", "BLOCK"]
    goal_id: str
    episode_id: str
    selected_action_id: str | None
    proof_sha256: str
    simulation: SimulationResponse
    execution_boundary: str


class VerifiableGeneralAgentV23:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS episodic_memory_v23(
                workspace_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                occurred_at BIGINT NOT NULL,
                content_sha256 TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,episode_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_episode_v23_agent ON episodic_memory_v23(workspace_id,agent_id,occurred_at)"
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS persistent_goals_v23(
                workspace_id TEXT NOT NULL,
                goal_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                objective_sha256 TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,goal_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_goal_v23_agent ON persistent_goals_v23(workspace_id,agent_id,status,created_at)"
            ))

    def record_episode(self, workspace_id: str, body: EpisodeCreate) -> EpisodeRecord:
        now = int(time.time())
        occurred = body.occurred_at or now
        episode_id = "ep23_" + uuid.uuid4().hex[:24]
        payload = body.model_dump(mode="json")
        payload["occurred_at"] = occurred
        digest = _sha(payload)
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="episodic-memory-v23")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO episodic_memory_v23(
                workspace_id,episode_id,agent_id,event_type,payload_json,occurred_at,content_sha256,created_at
                ) VALUES(:w,:id,:agent,:event,:payload,:occurred,:sha,:created)"""
            ), {
                "w": workspace_id,
                "id": episode_id,
                "agent": body.agent_id,
                "event": body.event_type,
                "payload": protected,
                "occurred": occurred,
                "sha": digest,
                "created": now,
            })
        return EpisodeRecord(
            episode_id=episode_id,
            agent_id=body.agent_id,
            event_type=body.event_type,
            summary=body.summary,
            observations=body.observations,
            evidence_refs=body.evidence_refs,
            occurred_at=occurred,
            content_sha256=digest,
            created_at=now,
        )

    def episodes(self, workspace_id: str, agent_id: str, limit: int) -> list[EpisodeRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """SELECT episode_id,payload_json,content_sha256,created_at
                FROM episodic_memory_v23
                WHERE workspace_id=:w AND agent_id=:agent
                ORDER BY occurred_at DESC,created_at DESC LIMIT :limit"""
            ), {"w": workspace_id, "agent": agent_id, "limit": limit}).mappings().all()
        out: list[EpisodeRecord] = []
        for row in rows:
            payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="episodic-memory-v23")
            out.append(EpisodeRecord(
                episode_id=row["episode_id"],
                agent_id=payload["agent_id"],
                event_type=payload["event_type"],
                summary=payload["summary"],
                observations=payload.get("observations", {}),
                evidence_refs=payload.get("evidence_refs", []),
                occurred_at=int(payload["occurred_at"]),
                content_sha256=row["content_sha256"],
                created_at=int(row["created_at"]),
            ))
        return out

    def create_goal(self, workspace_id: str, body: GoalCreate) -> GoalRecord:
        now = int(time.time())
        goal_id = "goal23_" + uuid.uuid4().hex[:24]
        payload = body.model_dump(mode="json")
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="persistent-goal-v23")
        objective_sha = _sha({
            "agent_id": body.agent_id,
            "objective": body.objective,
            "success_criteria": body.success_criteria,
        })
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO persistent_goals_v23(
                workspace_id,goal_id,agent_id,status,payload_json,objective_sha256,created_at
                ) VALUES(:w,:id,:agent,'ACTIVE',:payload,:sha,:created)"""
            ), {
                "w": workspace_id,
                "id": goal_id,
                "agent": body.agent_id,
                "payload": protected,
                "sha": objective_sha,
                "created": now,
            })
        return GoalRecord(
            goal_id=goal_id,
            agent_id=body.agent_id,
            objective=body.objective,
            success_criteria=body.success_criteria,
            priority=body.priority,
            horizon_days=body.horizon_days,
            status="ACTIVE",
            objective_sha256=objective_sha,
            created_at=now,
        )

    def get_goal(self, workspace_id: str, goal_id: str) -> GoalRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                """SELECT goal_id,agent_id,status,payload_json,objective_sha256,created_at
                FROM persistent_goals_v23 WHERE workspace_id=:w AND goal_id=:id"""
            ), {"w": workspace_id, "id": goal_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="persistent-goal-v23")
        return GoalRecord(
            goal_id=row["goal_id"],
            agent_id=row["agent_id"],
            objective=payload["objective"],
            success_criteria=payload["success_criteria"],
            priority=int(payload["priority"]),
            horizon_days=int(payload["horizon_days"]),
            status=row["status"],
            objective_sha256=row["objective_sha256"],
            created_at=int(row["created_at"]),
        )

    @staticmethod
    def simulate(body: SimulationRequest) -> SimulationResponse:
        actions: list[SimulatedAction] = []
        eligible: list[tuple[float, str]] = []
        risk_penalty = {"low": 0.0, "moderate": 0.15, "high": 0.40, "critical": 1.0}
        for candidate in body.candidates:
            reasons: list[str] = []
            if candidate.risk_tier == "critical":
                decision: Decision = "BLOCK"
                reasons.append("critical_risk_fail_closed")
            elif candidate.risk_tier == "high":
                decision = "REVIEW"
                reasons.append("high_risk_requires_human_review")
            elif candidate.evidence_coverage < 0.50:
                decision = "REVIEW"
                reasons.append("insufficient_evidence_coverage")
            else:
                decision = "ELIGIBLE"
                reasons.append("bounded_risk_and_evidence_thresholds_satisfied")

            score = (
                candidate.expected_utility
                + 0.25 * candidate.evidence_coverage
                + 0.15 * candidate.reversibility
                - 0.75 * candidate.failure_probability
                - risk_penalty[candidate.risk_tier]
            )
            score = round(score, 6)
            actions.append(SimulatedAction(
                action_id=candidate.action_id,
                decision=decision,
                score=score,
                reasons=reasons,
            ))
            if decision == "ELIGIBLE":
                eligible.append((score, candidate.action_id))

        selected = max(eligible)[1] if eligible else None
        state_sha = _sha(body.current_state)
        payload = {
            "current_state_sha256": state_sha,
            "selected_action_id": selected,
            "actions": [item.model_dump(mode="json") for item in actions],
        }
        return SimulationResponse(
            selected_action_id=selected,
            requires_human_review=selected is None or any(item.decision == "REVIEW" for item in actions),
            actions=actions,
            current_state_sha256=state_sha,
            simulation_sha256=_sha(payload),
            boundary=(
                "V23 simulation ranks bounded candidate actions only. "
                "It does not execute tools, mutate external systems, or bypass human approval."
            ),
        )


V23 = VerifiableGeneralAgentV23()


@router.post("/episodes", response_model=EpisodeRecord)
def record_episode(body: EpisodeCreate, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> EpisodeRecord:
    return V23.record_episode(principal.workspace_id, body)


@router.get("/episodes/{agent_id}", response_model=list[EpisodeRecord])
def list_episodes(
    agent_id: str,
    limit: int = 50,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> list[EpisodeRecord]:
    return V23.episodes(principal.workspace_id, agent_id, max(1, min(limit, 500)))


@router.post("/goals", response_model=GoalRecord)
def create_goal(body: GoalCreate, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> GoalRecord:
    return V23.create_goal(principal.workspace_id, body)


@router.get("/goals/{goal_id}", response_model=GoalRecord)
def get_goal(goal_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> GoalRecord:
    goal = V23.get_goal(principal.workspace_id, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="v23_goal_not_found")
    return goal


@router.post("/world/simulate", response_model=SimulationResponse)
def simulate_world(body: SimulationRequest, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> SimulationResponse:
    del principal
    return V23.simulate(body)


@router.post("/cycle", response_model=AgentCycleResponse)
def run_cycle(body: AgentCycleRequest, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentCycleResponse:
    goal = V23.get_goal(principal.workspace_id, body.goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="v23_goal_not_found")
    if goal.agent_id != body.episode.agent_id:
        raise HTTPException(status_code=400, detail="v23_goal_agent_mismatch")

    episode = V23.record_episode(principal.workspace_id, body.episode)
    simulation = V23.simulate(SimulationRequest(current_state=body.current_state, candidates=body.candidates))

    if simulation.selected_action_id is not None:
        status: Literal["READY", "REVIEW", "BLOCK"] = "READY"
    elif any(item.decision == "REVIEW" for item in simulation.actions):
        status = "REVIEW"
    else:
        status = "BLOCK"

    proof_payload = {
        "workspace_id": principal.workspace_id,
        "goal_id": goal.goal_id,
        "goal_sha256": goal.objective_sha256,
        "episode_id": episode.episode_id,
        "episode_sha256": episode.content_sha256,
        "simulation_sha256": simulation.simulation_sha256,
        "selected_action_id": simulation.selected_action_id,
        "status": status,
    }
    return AgentCycleResponse(
        status=status,
        goal_id=goal.goal_id,
        episode_id=episode.episode_id,
        selected_action_id=simulation.selected_action_id,
        proof_sha256=_sha(proof_payload),
        simulation=simulation,
        execution_boundary=(
            "V23 proof-of-concept stops before real-world execution. "
            "External side effects remain gated by the established ORBYTHRA execution/control-plane layers."
        ),
    )
