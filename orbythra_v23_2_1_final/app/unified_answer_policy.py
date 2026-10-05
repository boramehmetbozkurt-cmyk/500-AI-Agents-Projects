from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.security import Principal, require_minimum_role
from app.unified_answer import (
    UnifiedAnswerRequest,
    UnifiedAnswerResponse,
    answer as core_answer,
    readiness as core_readiness,
)
from app.unified_answer_export import build_unified_answer_xlsx

router = APIRouter(prefix="/v11/answer", tags=["v11-unified-answer"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

# These failures mean the model produced a draft but ORBYTHRA had no external
# evidence strong enough to release it as VERIFIED. They are presentation-level
# review conditions in AI_ANALYSIS mode, not reasons to hide the draft entirely.
_EVIDENCE_ONLY_FAILURES = {
    "evidence_present",
    "claim_support",
    "evidence_coverage",
    "nli_verifier",
    "direct_source_evidence",
    "v1_evidence_gate",
}


def _apply_console_policy(result: UnifiedAnswerResponse) -> UnifiedAnswerResponse:
    if result.status != "BLOCKED" or result.effective_mode != "AI_ANALYSIS" or not result.answer:
        return result

    failed = set(result.verification.get("failed_gates") or [])
    if not failed or not failed.issubset(_EVIDENCE_ONLY_FAILURES):
        return result

    result.status = "REVIEW"
    result.verification["passed"] = False
    result.verification["verified_release"] = False
    result.verification["review_reason"] = "external_evidence_unavailable"
    warning = "unverified_ai_answer:external_evidence_required_for_verified_pass"
    if warning not in result.warnings:
        result.warnings.append(warning)
    return result


@router.post("", response_model=UnifiedAnswerResponse)
def answer(
    body: UnifiedAnswerRequest,
    request: Request,
    principal: Principal = Depends(_REQUIRE_OPERATOR),
) -> UnifiedAnswerResponse:
    return _apply_console_policy(core_answer(body, request, principal))


@router.post("/export/xlsx")
def export_xlsx(
    result: UnifiedAnswerResponse,
    principal: Principal = Depends(_REQUIRE_OPERATOR),
) -> StreamingResponse:
    payload = build_unified_answer_xlsx(result)
    request_id = str((result.receipt or {}).get("request_id") or "result")
    safe_id = "".join(ch for ch in request_id if ch.isalnum() or ch in ("-", "_"))[:64] or "result"
    filename = f"orbythra-arama-claim-{safe_id}.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    state = core_readiness(principal)
    state["ai_only_unverified_answer_policy"] = "REVIEW"
    state["evidence_only_failures_hidden"] = False
    return state
