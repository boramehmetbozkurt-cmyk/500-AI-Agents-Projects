from __future__ import annotations

from datetime import UTC, datetime

from app.models import ClaimVerdict, VerifyRequest, VerifyResponse

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STALE_EVIDENCE = "STALE_EVIDENCE"
LOW_AUTHORITY = "LOW_AUTHORITY"


def _is_fresh(stamp: datetime | None, now: datetime, max_age_days: int) -> bool:
    if stamp is None:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return (now - stamp.astimezone(UTC)).days <= max_age_days


def verify(request: VerifyRequest, now: datetime | None = None) -> VerifyResponse:
    now = now or datetime.now(UTC)
    evidence_store = {item.id: item for item in request.evidence}
    verdicts: list[ClaimVerdict] = []

    for claim in request.claims:
        bound = [evidence_store[eid] for eid in claim.evidence_ids if eid in evidence_store]
        bound_ids = [item.id for item in bound]

        if not bound:
            verdicts.append(ClaimVerdict(
                claim_id=claim.id,
                claim=claim.text,
                status=INSUFFICIENT_EVIDENCE,
                bound_evidence_ids=[],
                support=0.0,
                authority=0.0,
                reasons=["no_bound_evidence"],
            ))
            continue

        if any(item.contradicts for item in bound):
            verdicts.append(ClaimVerdict(
                claim_id=claim.id,
                claim=claim.text,
                status=CONTRADICTED,
                bound_evidence_ids=bound_ids,
                support=0.0,
                authority=0.0,
                reasons=["contradiction_detected"],
            ))
            continue

        if claim.time_sensitive and any(
            not _is_fresh(item.retrieved_at or item.published_at, now, request.max_age_days)
            for item in bound
        ):
            verdicts.append(ClaimVerdict(
                claim_id=claim.id,
                claim=claim.text,
                status=STALE_EVIDENCE,
                bound_evidence_ids=bound_ids,
                support=0.0,
                authority=0.0,
                reasons=["stale_or_undated_evidence"],
            ))
            continue

        support = sum(item.support for item in bound) / len(bound)
        authority = sum(item.authority for item in bound) / len(bound)
        reasons: list[str] = []
        if support < request.minimum_support:
            reasons.append("support_below_threshold")
        if authority < request.minimum_authority:
            reasons.append("authority_below_threshold")

        if support < request.minimum_support:
            status = INSUFFICIENT_EVIDENCE
        elif authority < request.minimum_authority:
            status = LOW_AUTHORITY
        else:
            status = SUPPORTED

        verdicts.append(ClaimVerdict(
            claim_id=claim.id,
            claim=claim.text,
            status=status,
            bound_evidence_ids=bound_ids,
            support=round(support, 4),
            authority=round(authority, 4),
            reasons=reasons,
        ))

    supported = sum(item.status == SUPPORTED for item in verdicts)
    guarded = len(verdicts) - supported
    total = len(verdicts)

    return VerifyResponse(
        total_claims=total,
        supported_claims=supported,
        guarded_claims=guarded,
        evidence_gate_pass_rate=round(supported / max(1, total), 4),
        unsupported_or_guarded_rate=round(guarded / max(1, total), 4),
        disposition="ANSWER" if total and guarded == 0 else "ABSTAIN_OR_QUALIFY",
        verdicts=verdicts,
    )
