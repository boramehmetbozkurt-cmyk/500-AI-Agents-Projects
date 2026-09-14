from __future__ import annotations

import math
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from saas import AuthContext, require_identity
from world import REALITY_BRANCH, WorldStore, world_store

METHODOLOGY_VERSION = "orbythra-intelligence-v1"
TRUTH_WEIGHTS = {
    "verified": 1.0,
    "verified_disputed": 0.78,
    "claimed": 0.58,
    "contested": 0.34,
    "belief_only": 0.24,
    "hypothetical": 0.18,
}


class IntelligenceScoreRequest(BaseModel):
    branch_id: str = Field(default=REALITY_BRANCH, min_length=1, max_length=100)
    entity_id: str | None = Field(default=None, max_length=200)
    observed_at: int | None = None
    valid_at: int | None = None
    pulse_window_seconds: int = Field(default=86_400, ge=300, le=31_536_000)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _score(value: float) -> float:
    return round(_clamp(value) * 100.0, 2)


def _freshness(observed_at: int, now: int, half_life_seconds: int) -> float:
    age = max(0, now - int(observed_at))
    if half_life_seconds <= 0:
        return 0.0
    return 0.5 ** (age / half_life_seconds)


def score_world_state(
    snapshot: dict[str, Any],
    graph: dict[str, Any],
    pulse: dict[str, Any],
    *,
    now: int | None = None,
) -> dict[str, Any]:
    """Produce transparent, deterministic ORBYTHRA-derived intelligence signals.

    These are decision-support heuristics, not calibrated forecasts. The method intentionally
    exposes its ingredients so an enterprise buyer can benchmark or replace the weighting.
    """

    current_time = int(time.time()) if now is None else int(now)
    states = list(snapshot.get("states") or [])
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    categories = list(pulse.get("categories") or [])

    evidence_values: list[float] = []
    truth_values: list[float] = []
    freshness_values: list[float] = []
    disputed = 0

    for state in states:
        effective = state.get("effective") or {}
        evidence = effective.get("evidence_ids") or []
        sources = effective.get("source_ids") or []
        evidence_values.append(1.0 if evidence else (0.65 if sources else 0.0))
        truth_status = str(state.get("truth_status") or "")
        truth_values.append(TRUTH_WEIGHTS.get(truth_status, 0.0))
        if truth_status in {"contested", "verified_disputed"}:
            disputed += 1
        observed = int(effective.get("observed_at") or snapshot.get("observed_at") or current_time)
        freshness_values.append(_freshness(observed, current_time, 7 * 86_400))

    evidence_coverage = _mean(evidence_values)
    truth_quality = _mean(truth_values)
    freshness = _mean(freshness_values)
    dispute_pressure = disputed / len(states) if states else 0.0
    relation_density = _clamp(len(edges) / max(len(nodes), 1) / 2.0)

    max_change = max((abs(float(item.get("change_score") or 0.0)) for item in categories), default=0.0)
    change_intensity = _clamp(max_change / 4.0)
    unusual_categories = [
        {
            "entity_type": item.get("entity_type"),
            "change_score": item.get("change_score"),
            "delta": item.get("delta"),
        }
        for item in categories
        if item.get("unusual")
    ][:10]

    discovery = (
        0.24 * evidence_coverage
        + 0.18 * truth_quality
        + 0.22 * change_intensity
        + 0.16 * relation_density
        + 0.20 * freshness
    )
    emergence = (
        0.45 * change_intensity
        + 0.25 * freshness
        + 0.20 * relation_density
        + 0.10 * (1.0 - dispute_pressure)
    )
    decision_confidence = (
        0.42 * evidence_coverage
        + 0.33 * truth_quality
        + 0.15 * (1.0 - dispute_pressure)
        + 0.10 * relation_density
    )

    # Deliberately marked uncalibrated. It is a comparable change signal expressed on a
    # probability-like 0-100 scale, not a statistical probability of a future event.
    logistic_input = (
        -2.3
        + 3.1 * change_intensity
        + 1.0 * freshness
        + 0.7 * relation_density
        + 0.5 * dispute_pressure
    )
    change_signal = 1.0 / (1.0 + math.exp(-logistic_input))

    return {
        "methodology": METHODOLOGY_VERSION,
        "calibrated_forecast": False,
        "warning": (
            "World Change Signal is an uncalibrated decision-support heuristic, not a "
            "statistical probability or a guarantee of future events."
        ),
        "scope": {
            "workspace_id": snapshot.get("workspace_id"),
            "branch_id": snapshot.get("branch_id"),
            "observed_at": snapshot.get("observed_at"),
            "valid_at": snapshot.get("valid_at"),
        },
        "scores": {
            "discovery_score": _score(discovery),
            "emergence_score": _score(emergence),
            "decision_confidence": _score(decision_confidence),
            "world_change_signal": _score(change_signal),
        },
        "components": {
            "evidence_coverage": _score(evidence_coverage),
            "truth_quality": _score(truth_quality),
            "freshness": _score(freshness),
            "relation_density": _score(relation_density),
            "change_intensity": _score(change_intensity),
            "dispute_pressure": _score(dispute_pressure),
        },
        "counts": {
            "states": len(states),
            "nodes": len(nodes),
            "edges": len(edges),
            "pulse_categories": len(categories),
        },
        "top_change_signals": unusual_categories,
        "weights": {
            "discovery": {
                "evidence": 0.24,
                "truth": 0.18,
                "change": 0.22,
                "relations": 0.16,
                "freshness": 0.20,
            },
            "emergence": {
                "change": 0.45,
                "freshness": 0.25,
                "relations": 0.20,
                "low_dispute": 0.10,
            },
            "decision_confidence": {
                "evidence": 0.42,
                "truth": 0.33,
                "low_dispute": 0.15,
                "relations": 0.10,
            },
        },
    }


class IntelligenceEngine:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or world_store

    def score(self, workspace_id: str, request: IntelligenceScoreRequest) -> dict[str, Any]:
        snapshot = self.store.snapshot(
            workspace_id,
            branch_id=request.branch_id,
            observed_at=request.observed_at,
            valid_at=request.valid_at,
            entity_id=request.entity_id,
        )
        graph = self.store.graph(
            workspace_id,
            branch_id=request.branch_id,
            observed_at=request.observed_at,
            valid_at=request.valid_at,
            limit=1000,
        )
        pulse = self.store.pulse(workspace_id, window_seconds=request.pulse_window_seconds)
        result = score_world_state(snapshot, graph, pulse)
        result["query"] = {
            "entity_id": request.entity_id,
            "pulse_window_seconds": request.pulse_window_seconds,
        }
        return result


engine = IntelligenceEngine()
router = APIRouter(prefix="/intelligence", tags=["orbythra-intelligence"])
Identity = Annotated[AuthContext, Depends(require_identity)]


@router.get("")
async def intelligence_info(auth: Identity) -> dict[str, Any]:
    return {
        "name": "ORBYTHRA Proprietary World Intelligence Engine",
        "workspace_id": auth.tenant_id,
        "methodology": METHODOLOGY_VERSION,
        "signals": [
            "Discovery Score",
            "Emergence Score",
            "Decision Confidence",
            "World Change Signal",
        ],
        "inputs": [
            "World truth state",
            "evidence/source coverage",
            "World Pulse change intensity",
            "relationship density",
            "freshness",
            "dispute pressure",
        ],
        "calibrated_forecast": False,
    }


@router.post("/scores")
async def intelligence_scores(body: IntelligenceScoreRequest, auth: Identity) -> dict[str, Any]:
    return engine.score(auth.tenant_id, body)


@router.get("/signals")
async def intelligence_signals(
    auth: Identity,
    branch_id: str = Query(default=REALITY_BRANCH, min_length=1, max_length=100),
    window_seconds: int = Query(default=86_400, ge=300, le=31_536_000),
) -> dict[str, Any]:
    return engine.score(
        auth.tenant_id,
        IntelligenceScoreRequest(branch_id=branch_id, pulse_window_seconds=window_seconds),
    )
