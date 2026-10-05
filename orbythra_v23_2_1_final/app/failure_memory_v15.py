from __future__ import annotations

import hashlib
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/failures", tags=["v15-failure-memory"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

Severity = Literal["low", "medium", "high", "critical"]
FailureStatus = Literal["OPEN", "FIXED", "REGRESSION"]


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class FailureObservation(BaseModel):
    component: str = Field(min_length=1, max_length=200)
    error_class: str = Field(min_length=1, max_length=200)
    invariant: str = Field(min_length=1, max_length=1000)
    severity: Severity
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_sha: str = Field(min_length=7, max_length=80)


class FailureResolution(BaseModel):
    root_cause: str = Field(min_length=1, max_length=4000)
    remediation: str = Field(min_length=1, max_length=4000)
    regression_test_ref: str = Field(min_length=1, max_length=500)
    fix_commit_sha: str = Field(min_length=7, max_length=80)


class FailureRecord(BaseModel):
    failure_id: str
    fingerprint: str
    component: str
    error_class: str
    invariant: str
    severity: Severity
    status: FailureStatus
    occurrences: int
    first_seen_at: int
    last_seen_at: int
    first_release_sha: str
    last_release_sha: str
    last_evidence_sha256: str
    root_cause: str | None
    remediation: str | None
    regression_test_ref: str | None
    fix_commit_sha: str | None


class FailureReleaseGate(BaseModel):
    status: Literal["PASS", "BLOCK"]
    blocking_failure_ids: list[str]
    open_count: int
    regression_count: int
    receipt_sha256: str


class FailureMemoryV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS failure_memory_v15(
                    workspace_id TEXT NOT NULL,
                    failure_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    component TEXT NOT NULL,
                    error_class TEXT NOT NULL,
                    invariant_text TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurrences INTEGER NOT NULL,
                    first_seen_at BIGINT NOT NULL,
                    last_seen_at BIGINT NOT NULL,
                    first_release_sha TEXT NOT NULL,
                    last_release_sha TEXT NOT NULL,
                    last_evidence_sha256 TEXT NOT NULL,
                    root_cause TEXT,
                    remediation TEXT,
                    regression_test_ref TEXT,
                    fix_commit_sha TEXT,
                    PRIMARY KEY(workspace_id,failure_id),
                    UNIQUE(workspace_id,fingerprint)
                    )"""
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_failure_v15_gate ON failure_memory_v15(workspace_id,status,severity)"))

    @staticmethod
    def fingerprint(body: FailureObservation) -> str:
        return _hash(
            {
                "domain": "ORBYTHRA-V15-FAILURE-FINGERPRINT",
                "component": body.component.strip().casefold(),
                "error_class": body.error_class.strip().casefold(),
                "invariant": body.invariant.strip().casefold(),
            }
        )

    def record(self, workspace_id: str, body: FailureObservation, *, now: int | None = None) -> FailureRecord:
        observed_at = int(time.time()) if now is None else int(now)
        fingerprint = self.fingerprint(body)
        with STORE.engine.begin() as connection:
            row = connection.execute(
                text("SELECT failure_id,status,occurrences FROM failure_memory_v15 WHERE workspace_id=:w AND fingerprint=:f"),
                {"w": workspace_id, "f": fingerprint},
            ).mappings().first()
            if row is None:
                failure_id = "fm15_" + uuid.uuid4().hex[:24]
                connection.execute(
                    text(
                        """INSERT INTO failure_memory_v15(
                        workspace_id,failure_id,fingerprint,component,error_class,invariant_text,severity,status,occurrences,
                        first_seen_at,last_seen_at,first_release_sha,last_release_sha,last_evidence_sha256,
                        root_cause,remediation,regression_test_ref,fix_commit_sha
                        ) VALUES(:w,:id,:fp,:component,:error,:invariant,:severity,'OPEN',1,:first,:last,:first_release,:last_release,:evidence,NULL,NULL,NULL,NULL)"""
                    ),
                    {
                        "w": workspace_id,
                        "id": failure_id,
                        "fp": fingerprint,
                        "component": body.component,
                        "error": body.error_class,
                        "invariant": body.invariant,
                        "severity": body.severity,
                        "first": observed_at,
                        "last": observed_at,
                        "first_release": body.release_sha,
                        "last_release": body.release_sha,
                        "evidence": body.evidence_sha256,
                    },
                )
            else:
                failure_id = row["failure_id"]
                new_status = "REGRESSION" if row["status"] == "FIXED" else row["status"]
                connection.execute(
                    text(
                        """UPDATE failure_memory_v15 SET status=:status,occurrences=occurrences+1,last_seen_at=:last,
                        last_release_sha=:release,last_evidence_sha256=:evidence,severity=:severity
                        WHERE workspace_id=:w AND failure_id=:id"""
                    ),
                    {
                        "status": new_status,
                        "last": observed_at,
                        "release": body.release_sha,
                        "evidence": body.evidence_sha256,
                        "severity": body.severity,
                        "w": workspace_id,
                        "id": failure_id,
                    },
                )
        record = self.get(workspace_id, failure_id)
        if record is None:
            raise RuntimeError("failure_memory_not_persisted")
        return record

    def resolve(self, workspace_id: str, failure_id: str, body: FailureResolution) -> FailureRecord:
        with STORE.engine.begin() as connection:
            updated = connection.execute(
                text(
                    """UPDATE failure_memory_v15 SET status='FIXED',root_cause=:root,remediation=:remediation,
                    regression_test_ref=:test,fix_commit_sha=:commit WHERE workspace_id=:w AND failure_id=:id"""
                ),
                {
                    "root": body.root_cause,
                    "remediation": body.remediation,
                    "test": body.regression_test_ref,
                    "commit": body.fix_commit_sha,
                    "w": workspace_id,
                    "id": failure_id,
                },
            )
        if not updated.rowcount:
            raise ValueError("failure_not_found")
        record = self.get(workspace_id, failure_id)
        if record is None:
            raise RuntimeError("failure_resolution_not_persisted")
        return record

    def get(self, workspace_id: str, failure_id: str) -> FailureRecord | None:
        with STORE.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM failure_memory_v15 WHERE workspace_id=:w AND failure_id=:id"),
                {"w": workspace_id, "id": failure_id},
            ).mappings().first()
        if row is None:
            return None
        return FailureRecord(
            failure_id=row["failure_id"],
            fingerprint=row["fingerprint"],
            component=row["component"],
            error_class=row["error_class"],
            invariant=row["invariant_text"],
            severity=row["severity"],
            status=row["status"],
            occurrences=int(row["occurrences"]),
            first_seen_at=int(row["first_seen_at"]),
            last_seen_at=int(row["last_seen_at"]),
            first_release_sha=row["first_release_sha"],
            last_release_sha=row["last_release_sha"],
            last_evidence_sha256=row["last_evidence_sha256"],
            root_cause=row["root_cause"],
            remediation=row["remediation"],
            regression_test_ref=row["regression_test_ref"],
            fix_commit_sha=row["fix_commit_sha"],
        )

    def release_gate(self, workspace_id: str) -> FailureReleaseGate:
        with STORE.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT failure_id,status,severity FROM failure_memory_v15 WHERE workspace_id=:w"),
                {"w": workspace_id},
            ).mappings().all()
        blockers = sorted(
            row["failure_id"]
            for row in rows
            if row["status"] in {"OPEN", "REGRESSION"} and row["severity"] in {"high", "critical"}
        )
        open_count = sum(1 for row in rows if row["status"] == "OPEN")
        regression_count = sum(1 for row in rows if row["status"] == "REGRESSION")
        payload = {
            "domain": "ORBYTHRA-V15-FAILURE-RELEASE-GATE",
            "workspace_id": workspace_id,
            "blocking_failure_ids": blockers,
            "open_count": open_count,
            "regression_count": regression_count,
        }
        return FailureReleaseGate(
            status="BLOCK" if blockers else "PASS",
            blocking_failure_ids=blockers,
            open_count=open_count,
            regression_count=regression_count,
            receipt_sha256=_hash(payload),
        )


FAILURE_MEMORY_V15 = FailureMemoryV15()


@router.post("/record", response_model=FailureRecord)
def record(body: FailureObservation, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> FailureRecord:
    result = FAILURE_MEMORY_V15.record(principal.workspace_id, body)
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.failure_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="failure_memory_v15_record",
        status=result.status,
        metadata={"failure_id": result.failure_id, "fingerprint": result.fingerprint, "severity": result.severity, "occurrences": result.occurrences},
    )
    return result


@router.post("/{failure_id}/resolve", response_model=FailureRecord)
def resolve(failure_id: str, body: FailureResolution, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> FailureRecord:
    try:
        result = FAILURE_MEMORY_V15.resolve(principal.workspace_id, failure_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", failure_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="failure_memory_v15_resolve",
        status="FIXED",
        metadata={"failure_id": failure_id, "regression_test_ref": body.regression_test_ref, "fix_commit_sha": body.fix_commit_sha},
    )
    return result


@router.get("/release-gate", response_model=FailureReleaseGate)
def release_gate(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> FailureReleaseGate:
    return FAILURE_MEMORY_V15.release_gate(principal.workspace_id)


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "stable_failure_fingerprint": True,
        "repeat_occurrence_counting": True,
        "fixed_failure_reopens_as_regression": True,
        "root_cause_and_remediation_binding": True,
        "regression_test_reference_required_for_resolution": True,
        "high_and_critical_release_blocking": True,
        "workspace_isolation": True,
    }
