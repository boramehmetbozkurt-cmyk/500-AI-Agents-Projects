from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/calibration", tags=["v15-calibration"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")


class CalibrationObservation(BaseModel):
    domain: str = Field(min_length=1, max_length=120)
    task_type: str = Field(default="general", min_length=1, max_length=120)
    predicted_probability: float = Field(ge=0, le=1)
    outcome_correct: bool
    model_id: str = Field(default="unknown", min_length=1, max_length=200)
    source: str = Field(default="production", min_length=1, max_length=80)
    observed_at: int | None = None

    @model_validator(mode="after")
    def finite_probability(self):
        if not math.isfinite(self.predicted_probability):
            raise ValueError("predicted_probability_must_be_finite")
        return self


class CalibrationBin(BaseModel):
    lower: float
    upper: float
    count: int
    mean_confidence: float
    empirical_accuracy: float
    absolute_gap: float


class CalibrationReport(BaseModel):
    domain: str
    task_type: str | None
    count: int
    brier_score: float | None
    ece: float | None
    mean_confidence: float | None
    empirical_accuracy: float | None
    status: Literal["NO_DATA", "UNDER_SAMPLED", "CALIBRATED", "DRIFT_RISK"]
    bins: list[CalibrationBin]


class CalibrationAdjustmentRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=120)
    task_type: str = Field(default="general", min_length=1, max_length=120)
    raw_probability: float = Field(ge=0, le=1)
    minimum_samples: int = Field(default=30, ge=1, le=100000)
    shrinkage_strength: float = Field(default=20.0, ge=0, le=10000)


class CalibrationAdjustmentResponse(BaseModel):
    raw_probability: float
    adjusted_probability: float
    sample_count: int
    empirical_bin_accuracy: float | None
    method: str
    status: str


class CalibrationStoreV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS calibration_events_v15(
                    event_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    predicted_probability REAL NOT NULL,
                    outcome_correct INTEGER NOT NULL,
                    model_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at BIGINT NOT NULL,
                    recorded_at BIGINT NOT NULL
                    )"""
                )
            )
            connection.execute(
                text(
                    """CREATE INDEX IF NOT EXISTS idx_calibration_v15_scope
                    ON calibration_events_v15(workspace_id,domain,task_type,observed_at)"""
                )
            )

    def add(self, workspace_id: str, body: CalibrationObservation, *, now: int | None = None) -> str:
        recorded_at = int(time.time()) if now is None else int(now)
        observed_at = recorded_at if body.observed_at is None else int(body.observed_at)
        if observed_at > recorded_at + 300:
            raise ValueError("future_calibration_observation")
        event_id = "cal15_" + uuid.uuid4().hex[:24]
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO calibration_events_v15(
                    event_id,workspace_id,domain,task_type,predicted_probability,outcome_correct,
                    model_id,source,observed_at,recorded_at
                    ) VALUES(:id,:w,:d,:t,:p,:o,:m,:s,:obs,:rec)"""
                ),
                {
                    "id": event_id,
                    "w": workspace_id,
                    "d": body.domain,
                    "t": body.task_type,
                    "p": float(body.predicted_probability),
                    "o": 1 if body.outcome_correct else 0,
                    "m": body.model_id,
                    "s": body.source,
                    "obs": observed_at,
                    "rec": recorded_at,
                },
            )
        return event_id

    def rows(self, workspace_id: str, domain: str, task_type: str | None = None) -> list[tuple[float, bool]]:
        sql = "SELECT predicted_probability,outcome_correct FROM calibration_events_v15 WHERE workspace_id=:w AND domain=:d"
        params: dict[str, object] = {"w": workspace_id, "d": domain}
        if task_type is not None:
            sql += " AND task_type=:t"
            params["t"] = task_type
        sql += " ORDER BY observed_at ASC,event_id ASC"
        with STORE.engine.connect() as connection:
            rows = connection.execute(text(sql), params).all()
        return [(float(row[0]), bool(row[1])) for row in rows]


CALIBRATION_V15 = CalibrationStoreV15()


def _report(rows: list[tuple[float, bool]], domain: str, task_type: str | None, *, bin_count: int = 10) -> CalibrationReport:
    if not rows:
        return CalibrationReport(
            domain=domain,
            task_type=task_type,
            count=0,
            brier_score=None,
            ece=None,
            mean_confidence=None,
            empirical_accuracy=None,
            status="NO_DATA",
            bins=[],
        )

    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for probability, outcome in rows:
        index = min(bin_count - 1, int(probability * bin_count))
        bins[index].append((probability, outcome))

    total = len(rows)
    rendered: list[CalibrationBin] = []
    ece = 0.0
    for index in range(bin_count):
        values = bins.get(index, [])
        if not values:
            continue
        mean_confidence = sum(item[0] for item in values) / len(values)
        accuracy = sum(1.0 if item[1] else 0.0 for item in values) / len(values)
        gap = abs(mean_confidence - accuracy)
        ece += (len(values) / total) * gap
        rendered.append(
            CalibrationBin(
                lower=round(index / bin_count, 6),
                upper=round((index + 1) / bin_count, 6),
                count=len(values),
                mean_confidence=round(mean_confidence, 6),
                empirical_accuracy=round(accuracy, 6),
                absolute_gap=round(gap, 6),
            )
        )

    brier = sum((p - (1.0 if outcome else 0.0)) ** 2 for p, outcome in rows) / total
    mean_conf = sum(p for p, _ in rows) / total
    accuracy = sum(1.0 if outcome else 0.0 for _, outcome in rows) / total
    if total < 30:
        status: Literal["NO_DATA", "UNDER_SAMPLED", "CALIBRATED", "DRIFT_RISK"] = "UNDER_SAMPLED"
    elif ece <= 0.05:
        status = "CALIBRATED"
    else:
        status = "DRIFT_RISK"
    return CalibrationReport(
        domain=domain,
        task_type=task_type,
        count=total,
        brier_score=round(brier, 6),
        ece=round(ece, 6),
        mean_confidence=round(mean_conf, 6),
        empirical_accuracy=round(accuracy, 6),
        status=status,
        bins=rendered,
    )


def _adjust(rows: list[tuple[float, bool]], raw_probability: float, minimum_samples: int, shrinkage_strength: float) -> CalibrationAdjustmentResponse:
    if len(rows) < minimum_samples:
        return CalibrationAdjustmentResponse(
            raw_probability=raw_probability,
            adjusted_probability=raw_probability,
            sample_count=len(rows),
            empirical_bin_accuracy=None,
            method="identity_until_sufficient_data",
            status="UNDER_SAMPLED",
        )
    bin_index = min(9, int(raw_probability * 10))
    selected = [(p, outcome) for p, outcome in rows if min(9, int(p * 10)) == bin_index]
    if not selected:
        return CalibrationAdjustmentResponse(
            raw_probability=raw_probability,
            adjusted_probability=raw_probability,
            sample_count=len(rows),
            empirical_bin_accuracy=None,
            method="identity_empty_bin",
            status="NO_LOCAL_BIN_DATA",
        )
    empirical = sum(1.0 if outcome else 0.0 for _, outcome in selected) / len(selected)
    weight = len(selected) / (len(selected) + shrinkage_strength) if shrinkage_strength > 0 else 1.0
    adjusted = (weight * empirical) + ((1.0 - weight) * raw_probability)
    return CalibrationAdjustmentResponse(
        raw_probability=round(raw_probability, 6),
        adjusted_probability=round(min(1.0, max(0.0, adjusted)), 6),
        sample_count=len(rows),
        empirical_bin_accuracy=round(empirical, 6),
        method="empirical_bin_with_shrinkage",
        status="ADJUSTED",
    )


@router.post("/observations")
def add_observation(body: CalibrationObservation, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> dict[str, object]:
    try:
        event_id = CALIBRATION_V15.add(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", event_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="calibration_v15_observation",
        status="RECORDED",
        metadata={"event_id": event_id, "domain": body.domain, "task_type": body.task_type},
    )
    return {"event_id": event_id, "status": "RECORDED"}


@router.get("/report", response_model=CalibrationReport)
def report(
    domain: str = Query(..., min_length=1, max_length=120),
    task_type: str | None = Query(default=None, min_length=1, max_length=120),
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> CalibrationReport:
    return _report(CALIBRATION_V15.rows(principal.workspace_id, domain, task_type), domain, task_type)


@router.post("/adjust", response_model=CalibrationAdjustmentResponse)
def adjust(body: CalibrationAdjustmentRequest, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> CalibrationAdjustmentResponse:
    rows = CALIBRATION_V15.rows(principal.workspace_id, body.domain, body.task_type)
    return _adjust(rows, body.raw_probability, body.minimum_samples, body.shrinkage_strength)


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "brier_score": True,
        "expected_calibration_error": True,
        "domain_and_task_scoping": True,
        "empirical_shrinkage_adjustment": True,
        "future_observation_rejection": True,
        "workspace_isolation": True,
        "boundary": "Calibration reflects observed labeled outcomes only. It does not convert model confidence into guaranteed truth or replace external validation.",
    }
