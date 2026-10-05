from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v12/temporal", tags=["v12-temporal-reality"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class TemporalAssertionIn(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    predicate: str = Field(min_length=1, max_length=200)
    object: Any
    valid_from: int
    valid_to: int | None = None
    observed_at: int
    published_at: int | None = None
    source_id: str = Field(min_length=1, max_length=300)
    source_lineage_id: str | None = Field(default=None, max_length=300)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to_must_be_after_valid_from")
        return self

    @property
    def lineage_identity(self) -> str:
        return self.source_lineage_id or self.source_id


class TemporalRecord(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    object: Any
    valid_from: int
    valid_to: int | None
    observed_at: int
    published_at: int | None
    recorded_at: int
    retired_at: int | None
    source_id: str
    source_lineage_id: str | None
    evidence_sha256: str
    confidence: float
    assertion_sha256: str
    record_sha256: str


class TemporalGroup(BaseModel):
    subject: str
    predicate: str
    status: Literal["CONSISTENT", "CONFLICT"]
    fact_ids: list[str]
    source_count: int
    independent_lineages: int
    object_digests: list[str]


class TemporalSnapshotResponse(BaseModel):
    valid_at: int
    known_at: int
    facts: list[TemporalRecord]
    groups: list[TemporalGroup]
    stale_fact_ids: list[str]
    snapshot_sha256: str


class RetireRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class TemporalStoreV12:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS temporal_facts_v12(
                    fact_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_json TEXT NOT NULL,
                    valid_from BIGINT NOT NULL,
                    valid_to BIGINT,
                    observed_at BIGINT NOT NULL,
                    published_at BIGINT,
                    recorded_at BIGINT NOT NULL,
                    retired_at BIGINT,
                    retirement_reason TEXT,
                    source_id TEXT NOT NULL,
                    source_lineage_id TEXT,
                    evidence_sha256 TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    assertion_sha256 TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    UNIQUE(workspace_id, assertion_sha256)
                    )"""
                )
            )
            connection.execute(
                text(
                    """CREATE INDEX IF NOT EXISTS idx_temporal_v12_snapshot
                    ON temporal_facts_v12(workspace_id,subject,predicate,valid_from,valid_to,recorded_at,retired_at)"""
                )
            )
            connection.execute(
                text(
                    """CREATE INDEX IF NOT EXISTS idx_temporal_v12_freshness
                    ON temporal_facts_v12(workspace_id,observed_at,published_at)"""
                )
            )

    def add(self, workspace_id: str, assertion: TemporalAssertionIn, *, now: int | None = None, future_skew_seconds: int = 300) -> TemporalRecord:
        recorded_at = int(time.time()) if now is None else int(now)
        if assertion.observed_at > recorded_at + future_skew_seconds:
            raise ValueError("future_observation")
        if assertion.published_at is not None and assertion.published_at > recorded_at + future_skew_seconds:
            raise ValueError("future_publication")
        if assertion.published_at is not None and assertion.published_at < assertion.observed_at:
            # A source cannot publish an observation before the source says it observed it.
            raise ValueError("publication_precedes_observation")

        semantic = assertion.model_dump(mode="json")
        assertion_sha = _hash({"domain": "ORBYTHRA-V12-TEMPORAL-ASSERTION", "workspace_id": workspace_id, **semantic})
        fact_id = "tf12_" + uuid.uuid4().hex[:24]
        record_sha = _hash(
            {
                "domain": "ORBYTHRA-V12-TEMPORAL-RECORD",
                "workspace_id": workspace_id,
                "fact_id": fact_id,
                "assertion_sha256": assertion_sha,
                "recorded_at": recorded_at,
            }
        )
        object_json = VAULT.encrypt_json(assertion.object, workspace_id=workspace_id, purpose="temporal-fact-v12")
        try:
            with STORE.engine.begin() as connection:
                connection.execute(
                    text(
                        """INSERT INTO temporal_facts_v12(
                        fact_id,workspace_id,subject,predicate,object_json,valid_from,valid_to,observed_at,published_at,
                        recorded_at,retired_at,retirement_reason,source_id,source_lineage_id,evidence_sha256,confidence,assertion_sha256,record_sha256
                        ) VALUES(:id,:w,:s,:p,:o,:vf,:vt,:obs,:pub,:rec,NULL,NULL,:src,:lineage,:e,:conf,:ash,:rsh)"""
                    ),
                    {
                        "id": fact_id,
                        "w": workspace_id,
                        "s": assertion.subject,
                        "p": assertion.predicate,
                        "o": object_json,
                        "vf": assertion.valid_from,
                        "vt": assertion.valid_to,
                        "obs": assertion.observed_at,
                        "pub": assertion.published_at,
                        "rec": recorded_at,
                        "src": assertion.source_id,
                        "lineage": assertion.source_lineage_id,
                        "e": assertion.evidence_sha256,
                        "conf": assertion.confidence,
                        "ash": assertion_sha,
                        "rsh": record_sha,
                    },
                )
        except IntegrityError as exc:
            raise ValueError("duplicate_temporal_assertion") from exc
        return self.get(workspace_id, fact_id)

    def get(self, workspace_id: str, fact_id: str) -> TemporalRecord:
        with STORE.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM temporal_facts_v12 WHERE workspace_id=:w AND fact_id=:id"),
                {"w": workspace_id, "id": fact_id},
            ).mappings().first()
        if row is None:
            raise ValueError("temporal_fact_not_found")
        return self._record(workspace_id, row)

    def _record(self, workspace_id: str, row) -> TemporalRecord:
        return TemporalRecord(
            fact_id=row["fact_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=VAULT.decrypt_json(row["object_json"], workspace_id=workspace_id, purpose="temporal-fact-v12"),
            valid_from=int(row["valid_from"]),
            valid_to=None if row["valid_to"] is None else int(row["valid_to"]),
            observed_at=int(row["observed_at"]),
            published_at=None if row["published_at"] is None else int(row["published_at"]),
            recorded_at=int(row["recorded_at"]),
            retired_at=None if row["retired_at"] is None else int(row["retired_at"]),
            source_id=row["source_id"],
            source_lineage_id=row["source_lineage_id"],
            evidence_sha256=row["evidence_sha256"],
            confidence=float(row["confidence"]),
            assertion_sha256=row["assertion_sha256"],
            record_sha256=row["record_sha256"],
        )

    def retire(self, workspace_id: str, fact_id: str, reason: str, *, now: int | None = None) -> TemporalRecord:
        retired_at = int(time.time()) if now is None else int(now)
        with STORE.engine.begin() as connection:
            row = connection.execute(
                text("SELECT recorded_at,retired_at FROM temporal_facts_v12 WHERE workspace_id=:w AND fact_id=:id"),
                {"w": workspace_id, "id": fact_id},
            ).mappings().first()
            if row is None:
                raise ValueError("temporal_fact_not_found")
            if row["retired_at"] is not None:
                raise ValueError("temporal_fact_already_retired")
            if retired_at < int(row["recorded_at"]):
                raise ValueError("retirement_precedes_recording")
            connection.execute(
                text("UPDATE temporal_facts_v12 SET retired_at=:r,retirement_reason=:reason WHERE workspace_id=:w AND fact_id=:id AND retired_at IS NULL"),
                {"r": retired_at, "reason": reason, "w": workspace_id, "id": fact_id},
            )
        return self.get(workspace_id, fact_id)

    def snapshot(
        self,
        workspace_id: str,
        *,
        valid_at: int,
        known_at: int | None = None,
        max_observation_age_seconds: int = 2592000,
    ) -> TemporalSnapshotResponse:
        known = int(time.time()) if known_at is None else int(known_at)
        with STORE.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT * FROM temporal_facts_v12
                    WHERE workspace_id=:w
                    AND valid_from<=:valid_at
                    AND (valid_to IS NULL OR valid_to>:valid_at)
                    AND recorded_at<=:known_at
                    AND (retired_at IS NULL OR retired_at>:known_at)
                    ORDER BY subject ASC,predicate ASC,valid_from ASC,observed_at ASC,
                    COALESCE(published_at,observed_at) ASC,recorded_at ASC,assertion_sha256 ASC"""
                ),
                {"w": workspace_id, "valid_at": valid_at, "known_at": known},
            ).mappings().all()
        facts = [self._record(workspace_id, row) for row in rows]
        stale = sorted(
            fact.fact_id
            for fact in facts
            if known - fact.observed_at > max_observation_age_seconds
        )
        grouped: dict[tuple[str, str], list[TemporalRecord]] = {}
        for fact in facts:
            grouped.setdefault((fact.subject, fact.predicate), []).append(fact)
        groups: list[TemporalGroup] = []
        for (subject, predicate), items in grouped.items():
            object_digests = sorted({_hash(item.object) for item in items})
            lineages = {item.source_lineage_id or item.source_id for item in items}
            groups.append(
                TemporalGroup(
                    subject=subject,
                    predicate=predicate,
                    status="CONSISTENT" if len(object_digests) <= 1 else "CONFLICT",
                    fact_ids=[item.fact_id for item in items],
                    source_count=len({item.source_id for item in items}),
                    independent_lineages=len(lineages),
                    object_digests=object_digests,
                )
            )
        snapshot_payload = {
            "domain": "ORBYTHRA-V12-TEMPORAL-SNAPSHOT",
            "workspace_id": workspace_id,
            "valid_at": valid_at,
            "known_at": known,
            "fact_assertion_sha256s": [fact.assertion_sha256 for fact in facts],
            "groups": [group.model_dump(mode="json") for group in groups],
            "stale_fact_ids": stale,
        }
        return TemporalSnapshotResponse(
            valid_at=valid_at,
            known_at=known,
            facts=facts,
            groups=groups,
            stale_fact_ids=stale,
            snapshot_sha256=_hash(snapshot_payload),
        )


TEMPORAL_V12 = TemporalStoreV12()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "temporal-v12"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata=metadata,
    )


@router.post("/facts", response_model=TemporalRecord)
def create_fact(body: TemporalAssertionIn, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> TemporalRecord:
    try:
        result = TEMPORAL_V12.add(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc) == "duplicate_temporal_assertion" else 400, detail=str(exc)) from exc
    _audit(request, principal, "temporal_v12_add", "CREATED", {"fact_id": result.fact_id, "assertion_sha256": result.assertion_sha256})
    return result


@router.post("/facts/{fact_id}/retire", response_model=TemporalRecord)
def retire_fact(fact_id: str, body: RetireRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> TemporalRecord:
    try:
        result = TEMPORAL_V12.retire(principal.workspace_id, fact_id, body.reason)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "temporal_fact_not_found" else 409, detail=detail) from exc
    _audit(request, principal, "temporal_v12_retire", "RETIRED", {"fact_id": fact_id, "retired_at": result.retired_at})
    return result


@router.get("/snapshot", response_model=TemporalSnapshotResponse)
def snapshot(
    valid_at: int = Query(...),
    known_at: int | None = Query(default=None),
    max_observation_age_seconds: int = Query(default=2592000, ge=60, le=31536000),
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> TemporalSnapshotResponse:
    return TEMPORAL_V12.snapshot(
        principal.workspace_id,
        valid_at=valid_at,
        known_at=known_at,
        max_observation_age_seconds=max_observation_age_seconds,
    )


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "12.0-p0",
        "workspace_id": principal.workspace_id,
        "bitemporal_valid_and_known_time": True,
        "explicit_observation_time": True,
        "explicit_publication_time": True,
        "effective_validity_intervals": True,
        "future_observation_rejection": True,
        "future_publication_rejection": True,
        "publication_observation_order_check": True,
        "deterministic_snapshot_order": True,
        "conflict_preservation_without_silent_winner": True,
        "source_lineage_independence": True,
        "observation_age_staleness": True,
        "duplicate_assertion_rejection": True,
        "workspace_isolation": True,
        "encrypted_object_at_rest": True,
        "snapshot_receipt_hash": True,
    }
