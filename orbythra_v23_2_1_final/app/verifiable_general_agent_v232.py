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
from app.vault import VAULT
from app.verifiable_general_agent_v23 import (
    ActionCandidate,
    EpisodeCreate,
    EpisodeRecord,
    GoalCreate,
    GoalRecord,
    SimulationRequest,
    SimulationResponse,
    V23,
)

router = APIRouter(prefix="/v23.2/general-agent", tags=["v23.2-verifiable-general-agent"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")

CycleStatus = Literal["READY", "REVIEW", "BLOCK"]
GoalStatus = Literal["ACTIVE", "PAUSED", "COMPLETED", "CANCELLED"]


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class GoalStatusUpdate(BaseModel):
    status: GoalStatus
    reason: str = Field(min_length=1, max_length=2000)


class GoalStatusEvent(BaseModel):
    event_id: str
    goal_id: str
    previous_status: GoalStatus
    new_status: GoalStatus
    reason: str
    event_sha256: str
    created_at: int


class ContextSnapshot(BaseModel):
    agent_id: str
    goals: list[GoalRecord]
    recent_episodes: list[EpisodeRecord]
    evidence_refs: list[str]
    context_sha256: str
    generated_at: int


class AgentCycleRequestV232(BaseModel):
    goal_id: str = Field(min_length=1, max_length=100)
    episode: EpisodeCreate
    current_state: dict[str, Any]
    candidates: list[ActionCandidate] = Field(min_length=1, max_length=100)
    context_episode_limit: int = Field(default=20, ge=1, le=100)


class CycleReceiptRecord(BaseModel):
    cycle_id: str
    chain_position: int
    agent_id: str
    goal_id: str
    episode_id: str
    status: CycleStatus
    selected_action_id: str | None
    context_sha256: str
    simulation_sha256: str
    evidence_manifest_sha256: str
    previous_receipt_sha256: str | None
    receipt_sha256: str
    created_at: int


class AgentCycleResponseV232(BaseModel):
    cycle_id: str
    status: CycleStatus
    goal_id: str
    episode_id: str
    selected_action_id: str | None
    context_sha256: str
    proof_sha256: str
    previous_proof_sha256: str | None
    chain_position: int
    simulation: SimulationResponse
    review_candidates_present: bool
    execution_boundary: str


class ReceiptVerification(BaseModel):
    cycle_id: str
    integrity_valid: bool
    chain_link_valid: bool
    current_chain_head: bool
    receipt_sha256: str
    recomputed_sha256: str
    previous_receipt_sha256: str | None
    expected_previous_receipt_sha256: str | None


class VerifiableGeneralAgentV232:
    def __init__(self) -> None:
        self.engine = V23.engine
        self._init_tables()

    def _init_tables(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS agent_cycle_receipts_v232(
                workspace_id TEXT NOT NULL,
                cycle_id TEXT NOT NULL,
                chain_position BIGINT NOT NULL,
                agent_id TEXT NOT NULL,
                goal_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                status TEXT NOT NULL,
                selected_action_id TEXT,
                context_sha256 TEXT NOT NULL,
                simulation_sha256 TEXT NOT NULL,
                evidence_manifest_sha256 TEXT NOT NULL,
                previous_receipt_sha256 TEXT,
                receipt_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,cycle_id),
                UNIQUE(workspace_id,chain_position),
                UNIQUE(workspace_id,receipt_sha256)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_v232_receipt_agent ON agent_cycle_receipts_v232(workspace_id,agent_id,chain_position)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_v232_receipt_goal ON agent_cycle_receipts_v232(workspace_id,goal_id,chain_position)"
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS goal_status_history_v232(
                workspace_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                goal_id TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                reason_json TEXT NOT NULL,
                event_sha256 TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,event_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_v232_goal_status ON goal_status_history_v232(workspace_id,goal_id,created_at)"
            ))

    def list_goals(self, workspace_id: str, agent_id: str, status: GoalStatus | None, limit: int) -> list[GoalRecord]:
        query = (
            "SELECT goal_id FROM persistent_goals_v23 "
            "WHERE workspace_id=:w AND agent_id=:agent"
        )
        params: dict[str, Any] = {"w": workspace_id, "agent": agent_id, "limit": limit}
        if status is not None:
            query += " AND status=:status"
            params["status"] = status
        query += " ORDER BY created_at DESC LIMIT :limit"
        with self.engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [goal for row in rows if (goal := V23.get_goal(workspace_id, str(row["goal_id"]))) is not None]

    def update_goal_status(self, workspace_id: str, goal_id: str, body: GoalStatusUpdate) -> GoalStatusEvent:
        goal = V23.get_goal(workspace_id, goal_id)
        if goal is None:
            raise HTTPException(status_code=404, detail="v232_goal_not_found")
        previous_status = goal.status
        if previous_status == body.status:
            raise HTTPException(status_code=409, detail="v232_goal_status_unchanged")
        if previous_status in {"COMPLETED", "CANCELLED"}:
            raise HTTPException(status_code=409, detail="v232_terminal_goal_status")

        now = int(time.time())
        event_id = "gse232_" + uuid.uuid4().hex[:24]
        event_payload = {
            "event_id": event_id,
            "goal_id": goal_id,
            "previous_status": previous_status,
            "new_status": body.status,
            "reason": body.reason,
            "created_at": now,
        }
        event_sha = _sha(event_payload)
        protected_reason = VAULT.encrypt_json(
            {"reason": body.reason}, workspace_id=workspace_id, purpose="goal-status-v232"
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                "UPDATE persistent_goals_v23 SET status=:status WHERE workspace_id=:w AND goal_id=:goal_id"
            ), {"status": body.status, "w": workspace_id, "goal_id": goal_id})
            connection.execute(text(
                """INSERT INTO goal_status_history_v232(
                workspace_id,event_id,goal_id,previous_status,new_status,reason_json,event_sha256,created_at
                ) VALUES(:w,:event_id,:goal_id,:previous_status,:new_status,:reason_json,:event_sha256,:created_at)"""
            ), {
                "w": workspace_id,
                "event_id": event_id,
                "goal_id": goal_id,
                "previous_status": previous_status,
                "new_status": body.status,
                "reason_json": protected_reason,
                "event_sha256": event_sha,
                "created_at": now,
            })
        return GoalStatusEvent(
            event_id=event_id,
            goal_id=goal_id,
            previous_status=previous_status,
            new_status=body.status,
            reason=body.reason,
            event_sha256=event_sha,
            created_at=now,
        )

    def goal_history(self, workspace_id: str, goal_id: str, limit: int) -> list[GoalStatusEvent]:
        if V23.get_goal(workspace_id, goal_id) is None:
            raise HTTPException(status_code=404, detail="v232_goal_not_found")
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """SELECT event_id,goal_id,previous_status,new_status,reason_json,event_sha256,created_at
                FROM goal_status_history_v232
                WHERE workspace_id=:w AND goal_id=:goal_id
                ORDER BY created_at DESC,event_id DESC LIMIT :limit"""
            ), {"w": workspace_id, "goal_id": goal_id, "limit": limit}).mappings().all()
        out: list[GoalStatusEvent] = []
        for row in rows:
            reason = VAULT.decrypt_json(row["reason_json"], workspace_id=workspace_id, purpose="goal-status-v232")
            out.append(GoalStatusEvent(
                event_id=row["event_id"],
                goal_id=row["goal_id"],
                previous_status=row["previous_status"],
                new_status=row["new_status"],
                reason=str(reason.get("reason", "")),
                event_sha256=row["event_sha256"],
                created_at=int(row["created_at"]),
            ))
        return out

    def context_snapshot(self, workspace_id: str, agent_id: str, episode_limit: int = 20) -> ContextSnapshot:
        goals = self.list_goals(workspace_id, agent_id, None, 100)
        episodes = V23.episodes(workspace_id, agent_id, episode_limit)
        evidence_refs = sorted({ref for episode in episodes for ref in episode.evidence_refs})
        generated_at = int(time.time())
        context_payload = {
            "agent_id": agent_id,
            "goals": [goal.model_dump(mode="json") for goal in goals],
            "recent_episodes": [episode.model_dump(mode="json") for episode in episodes],
            "evidence_refs": evidence_refs,
        }
        return ContextSnapshot(
            agent_id=agent_id,
            goals=goals,
            recent_episodes=episodes,
            evidence_refs=evidence_refs,
            context_sha256=_sha(context_payload),
            generated_at=generated_at,
        )

    def _last_receipt(self, workspace_id: str) -> tuple[int, str | None]:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                """SELECT chain_position,receipt_sha256 FROM agent_cycle_receipts_v232
                WHERE workspace_id=:w ORDER BY chain_position DESC LIMIT 1"""
            ), {"w": workspace_id}).mappings().first()
        if row is None:
            return 0, None
        return int(row["chain_position"]), str(row["receipt_sha256"])

    def persist_receipt(
        self,
        workspace_id: str,
        *,
        agent_id: str,
        goal_id: str,
        episode_id: str,
        status: CycleStatus,
        selected_action_id: str | None,
        context_sha256: str,
        simulation_sha256: str,
        evidence_refs: list[str],
    ) -> CycleReceiptRecord:
        now = int(time.time())
        cycle_id = "cy232_" + uuid.uuid4().hex[:24]
        previous_position, previous_sha = self._last_receipt(workspace_id)
        chain_position = previous_position + 1
        evidence_manifest_sha = _sha(sorted(set(evidence_refs)))
        payload = {
            "cycle_id": cycle_id,
            "chain_position": chain_position,
            "agent_id": agent_id,
            "goal_id": goal_id,
            "episode_id": episode_id,
            "status": status,
            "selected_action_id": selected_action_id,
            "context_sha256": context_sha256,
            "simulation_sha256": simulation_sha256,
            "evidence_manifest_sha256": evidence_manifest_sha,
            "previous_receipt_sha256": previous_sha,
            "created_at": now,
        }
        receipt_sha = _sha(payload)
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="cycle-receipt-v232")
        try:
            with self.engine.begin() as connection:
                connection.execute(text(
                    """INSERT INTO agent_cycle_receipts_v232(
                    workspace_id,cycle_id,chain_position,agent_id,goal_id,episode_id,status,selected_action_id,
                    context_sha256,simulation_sha256,evidence_manifest_sha256,previous_receipt_sha256,
                    receipt_sha256,payload_json,created_at
                    ) VALUES(
                    :w,:cycle_id,:chain_position,:agent_id,:goal_id,:episode_id,:status,:selected_action_id,
                    :context_sha256,:simulation_sha256,:evidence_manifest_sha256,:previous_receipt_sha256,
                    :receipt_sha256,:payload_json,:created_at
                    )"""
                ), {
                    "w": workspace_id,
                    **payload,
                    "receipt_sha256": receipt_sha,
                    "payload_json": protected,
                })
        except Exception as exc:  # pragma: no cover - defensive concurrency failure path
            raise HTTPException(status_code=409, detail="v232_receipt_chain_conflict_retry_cycle") from exc
        return CycleReceiptRecord(receipt_sha256=receipt_sha, **payload)

    def get_receipt(self, workspace_id: str, cycle_id: str) -> CycleReceiptRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                """SELECT payload_json,receipt_sha256 FROM agent_cycle_receipts_v232
                WHERE workspace_id=:w AND cycle_id=:cycle_id"""
            ), {"w": workspace_id, "cycle_id": cycle_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="cycle-receipt-v232")
        return CycleReceiptRecord(receipt_sha256=row["receipt_sha256"], **payload)

    def list_receipts(self, workspace_id: str, agent_id: str, limit: int) -> list[CycleReceiptRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """SELECT cycle_id FROM agent_cycle_receipts_v232
                WHERE workspace_id=:w AND agent_id=:agent_id
                ORDER BY chain_position DESC LIMIT :limit"""
            ), {"w": workspace_id, "agent_id": agent_id, "limit": limit}).mappings().all()
        return [receipt for row in rows if (receipt := self.get_receipt(workspace_id, str(row["cycle_id"]))) is not None]

    def verify_receipt(self, workspace_id: str, cycle_id: str) -> ReceiptVerification:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                """SELECT chain_position,payload_json,receipt_sha256,previous_receipt_sha256
                FROM agent_cycle_receipts_v232 WHERE workspace_id=:w AND cycle_id=:cycle_id"""
            ), {"w": workspace_id, "cycle_id": cycle_id}).mappings().first()
            if row is None:
                raise HTTPException(status_code=404, detail="v232_cycle_receipt_not_found")
            position = int(row["chain_position"])
            previous = connection.execute(text(
                """SELECT receipt_sha256 FROM agent_cycle_receipts_v232
                WHERE workspace_id=:w AND chain_position=:position"""
            ), {"w": workspace_id, "position": position - 1}).mappings().first() if position > 1 else None
            head = connection.execute(text(
                """SELECT chain_position FROM agent_cycle_receipts_v232
                WHERE workspace_id=:w ORDER BY chain_position DESC LIMIT 1"""
            ), {"w": workspace_id}).mappings().first()

        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="cycle-receipt-v232")
        recomputed = _sha(payload)
        expected_previous = str(previous["receipt_sha256"]) if previous is not None else None
        stored_previous = row["previous_receipt_sha256"]
        return ReceiptVerification(
            cycle_id=cycle_id,
            integrity_valid=recomputed == row["receipt_sha256"],
            chain_link_valid=stored_previous == expected_previous,
            current_chain_head=head is not None and int(head["chain_position"]) == position,
            receipt_sha256=row["receipt_sha256"],
            recomputed_sha256=recomputed,
            previous_receipt_sha256=stored_previous,
            expected_previous_receipt_sha256=expected_previous,
        )


V232 = VerifiableGeneralAgentV232()


@router.post("/episodes", response_model=EpisodeRecord)
def record_episode_v232(body: EpisodeCreate, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> EpisodeRecord:
    return V23.record_episode(principal.workspace_id, body)


@router.get("/episodes/{agent_id}", response_model=list[EpisodeRecord])
def list_episodes_v232(
    agent_id: str,
    limit: int = 50,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> list[EpisodeRecord]:
    return V23.episodes(principal.workspace_id, agent_id, max(1, min(limit, 500)))


@router.post("/goals", response_model=GoalRecord)
def create_goal_v232(body: GoalCreate, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> GoalRecord:
    return V23.create_goal(principal.workspace_id, body)


@router.get("/goals/id/{goal_id}", response_model=GoalRecord)
def get_goal_v232(goal_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> GoalRecord:
    goal = V23.get_goal(principal.workspace_id, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="v232_goal_not_found")
    return goal


@router.post("/world/simulate", response_model=SimulationResponse)
def simulate_world_v232(body: SimulationRequest, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> SimulationResponse:
    del principal
    return V23.simulate(body)


@router.get("/goals/{agent_id}", response_model=list[GoalRecord])
def list_goals(
    agent_id: str,
    status: GoalStatus | None = None,
    limit: int = 100,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> list[GoalRecord]:
    return V232.list_goals(principal.workspace_id, agent_id, status, max(1, min(limit, 500)))


@router.patch("/goals/{goal_id}/status", response_model=GoalStatusEvent)
def update_goal_status(
    goal_id: str,
    body: GoalStatusUpdate,
    principal: Principal = Depends(_REQUIRE_OPERATOR),
) -> GoalStatusEvent:
    return V232.update_goal_status(principal.workspace_id, goal_id, body)


@router.get("/goals/{goal_id}/history", response_model=list[GoalStatusEvent])
def goal_status_history(
    goal_id: str,
    limit: int = 100,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> list[GoalStatusEvent]:
    return V232.goal_history(principal.workspace_id, goal_id, max(1, min(limit, 500)))


@router.get("/context/{agent_id}", response_model=ContextSnapshot)
def context_snapshot(
    agent_id: str,
    episode_limit: int = 20,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> ContextSnapshot:
    return V232.context_snapshot(principal.workspace_id, agent_id, max(1, min(episode_limit, 100)))


@router.post("/cycle", response_model=AgentCycleResponseV232)
def run_cycle_v232(body: AgentCycleRequestV232, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AgentCycleResponseV232:
    goal = V23.get_goal(principal.workspace_id, body.goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="v232_goal_not_found")
    if goal.agent_id != body.episode.agent_id:
        raise HTTPException(status_code=400, detail="v232_goal_agent_mismatch")
    if goal.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"v232_goal_not_active:{goal.status.lower()}")

    episode = V23.record_episode(principal.workspace_id, body.episode)
    context = V232.context_snapshot(principal.workspace_id, goal.agent_id, body.context_episode_limit)
    simulation = V23.simulate(SimulationRequest(current_state=body.current_state, candidates=body.candidates))

    if simulation.selected_action_id is not None:
        status: CycleStatus = "READY"
    elif any(item.decision == "REVIEW" for item in simulation.actions):
        status = "REVIEW"
    else:
        status = "BLOCK"

    receipt = V232.persist_receipt(
        principal.workspace_id,
        agent_id=goal.agent_id,
        goal_id=goal.goal_id,
        episode_id=episode.episode_id,
        status=status,
        selected_action_id=simulation.selected_action_id,
        context_sha256=context.context_sha256,
        simulation_sha256=simulation.simulation_sha256,
        evidence_refs=episode.evidence_refs,
    )
    return AgentCycleResponseV232(
        cycle_id=receipt.cycle_id,
        status=status,
        goal_id=goal.goal_id,
        episode_id=episode.episode_id,
        selected_action_id=simulation.selected_action_id,
        context_sha256=context.context_sha256,
        proof_sha256=receipt.receipt_sha256,
        previous_proof_sha256=receipt.previous_receipt_sha256,
        chain_position=receipt.chain_position,
        simulation=simulation,
        review_candidates_present=any(item.decision == "REVIEW" for item in simulation.actions),
        execution_boundary=(
            "V23.2 records a tamper-evident decision receipt but still stops before real-world execution. "
            "External side effects remain gated by ORBYTHRA's established authorization and execution-control layers."
        ),
    )


@router.get("/receipts/agent/{agent_id}", response_model=list[CycleReceiptRecord])
def list_cycle_receipts(
    agent_id: str,
    limit: int = 50,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> list[CycleReceiptRecord]:
    return V232.list_receipts(principal.workspace_id, agent_id, max(1, min(limit, 500)))


@router.get("/receipts/{cycle_id}", response_model=CycleReceiptRecord)
def get_cycle_receipt(cycle_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> CycleReceiptRecord:
    receipt = V232.get_receipt(principal.workspace_id, cycle_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="v232_cycle_receipt_not_found")
    return receipt


@router.get("/receipts/{cycle_id}/verify", response_model=ReceiptVerification)
def verify_cycle_receipt(cycle_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ReceiptVerification:
    return V232.verify_receipt(principal.workspace_id, cycle_id)
