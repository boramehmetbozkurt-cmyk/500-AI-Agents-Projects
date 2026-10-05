from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.security import Principal, require_minimum_role
from app.store import STORE
from app.validation_evidence_v45 import VALIDATION_EVIDENCE

router = APIRouter(prefix="/v4.5/validation", tags=["validation-v4.5"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")


class EvidenceSubmission(BaseModel):
    suite: str = Field(min_length=1, max_length=160)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: Literal["PASS", "FAIL"]
    total: int = Field(ge=1)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    external_validator: str | None = Field(default=None, max_length=200)


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "validation-v45"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **metadata},
    )


@router.post("/evidence")
def submit_evidence(body: EvidenceSubmission, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> dict:
    if body.total != body.passed + body.failed:
        raise HTTPException(status_code=422, detail="validation_counts_inconsistent")
    if body.result == "PASS" and body.failed != 0:
        raise HTTPException(status_code=422, detail="validation_pass_contains_failures")
    if body.result == "FAIL" and body.failed == 0:
        raise HTTPException(status_code=422, detail="validation_fail_without_failures")
    stored = VALIDATION_EVIDENCE.append(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "validation_v45_append", body.result, {"evidence_id": stored["evidence_id"], "evidence_sha256": stored["evidence_sha256"]})
    return stored


@router.get("/verify")
def verify_evidence(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict:
    result = VALIDATION_EVIDENCE.verify(principal.workspace_id)
    if not result["valid"]:
        raise HTTPException(status_code=409, detail={"code": "validation_evidence_invalid", **result})
    return result


@router.get("/export")
def export_evidence(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict:
    bundle = VALIDATION_EVIDENCE.export(principal.workspace_id)
    if not bundle["verification"]["valid"]:
        raise HTTPException(status_code=409, detail={"code": "validation_evidence_invalid", **bundle["verification"]})
    return bundle
