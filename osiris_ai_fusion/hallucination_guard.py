from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STALE_EVIDENCE = "STALE_EVIDENCE"
LOW_AUTHORITY = "LOW_AUTHORITY"
INVALID_PROVENANCE = "INVALID_PROVENANCE"
MEMORY_ONLY = "MEMORY_ONLY"
PROVIDER_BLOCKED = "PROVIDER_BLOCKED"

@dataclass(frozen=True)
class ClaimVerdict:
    status: str
    bound_evidence_ids: tuple[str, ...]
    support: float
    authority: float
    reasons: tuple[str, ...]

def _fresh(item: dict[str, Any], now: datetime, max_age_days: int) -> bool:
    raw = item.get("retrieved_at") or item.get("published_at")
    if not raw:
        return False
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        age = now - stamp.astimezone(UTC)
        return 0 <= age.days <= max_age_days
    except (TypeError, ValueError):
        return False

def _valid_provenance(item: dict[str, Any]) -> bool:
    if item.get("fresh_evidence") is False or item.get("memory_kind"):
        return False
    uri = str(item.get("url") or item.get("uri") or "").strip()
    digest = str(item.get("digest") or item.get("content_digest") or "").strip()
    locator = str(item.get("locator") or item.get("excerpt") or item.get("snippet") or "").strip()
    return bool(uri and (digest or locator))

def verify_claim(
    claim: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    minimum_support: float = 0.75,
    minimum_authority: float = 0.60,
    max_age_days: int = 30,
    now: datetime | None = None,
) -> ClaimVerdict:
    now = now or datetime.now(UTC)
    store = {str(item.get("id")): item for item in evidence if item.get("id")}
    requested = list(dict.fromkeys(str(x) for x in claim.get("evidence_ids") or [] if str(x)))
    bound = [store[x] for x in requested if x in store]
    ids = tuple(str(x["id"]) for x in bound)
    if not bound:
        return ClaimVerdict(INSUFFICIENT_EVIDENCE, ids, 0.0, 0.0, ("no_bound_evidence",))
    if all(x.get("fresh_evidence") is False or x.get("memory_kind") for x in bound):
        return ClaimVerdict(MEMORY_ONLY, ids, 0.0, 0.0, ("memory_is_not_fresh_evidence",))
    if any(bool(x.get("provider_blocked")) for x in bound):
        return ClaimVerdict(PROVIDER_BLOCKED, ids, 0.0, 0.0, ("provider_runtime_unavailable",))
    if any(bool(x.get("contradicts")) for x in bound):
        return ClaimVerdict(CONTRADICTED, ids, 0.0, 0.0, ("contradiction_detected",))
    if any(not _valid_provenance(x) for x in bound):
        return ClaimVerdict(INVALID_PROVENANCE, ids, 0.0, 0.0, ("missing_addressable_provenance",))
    if bool(claim.get("time_sensitive")) and any(not _fresh(x, now, max_age_days) for x in bound):
        return ClaimVerdict(STALE_EVIDENCE, ids, 0.0, 0.0, ("stale_future_or_undated_evidence",))
    support = sum(float(x.get("support", 0.0)) for x in bound) / len(bound)
    authority = sum(float(x.get("authority", 0.0)) for x in bound) / len(bound)
    reasons = tuple(
        reason
        for reason, failed in (
            ("support_below_threshold", support < minimum_support),
            ("authority_below_threshold", authority < minimum_authority),
        )
        if failed
    )
    if support < minimum_support:
        return ClaimVerdict(INSUFFICIENT_EVIDENCE, ids, support, authority, reasons)
    if authority < minimum_authority:
        return ClaimVerdict(LOW_AUTHORITY, ids, support, authority, reasons)
    return ClaimVerdict(SUPPORTED, ids, support, authority, ())

def evaluate_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    verdicts = [verify_claim(claim, evidence, **kwargs) for claim in claims]
    supported = sum(v.status == SUPPORTED for v in verdicts)
    guarded = sum(v.status != SUPPORTED for v in verdicts)
    total = len(verdicts)
    confidences = [max(0.0, min(1.0, float(c.get("confidence", 0.0)))) for c in claims]
    unsupported_confidences = [confidences[i] for i, v in enumerate(verdicts) if v.status != SUPPORTED]
    overconfident = sum(value > 0.50 for value in unsupported_confidences)
    return {
        "total_claims": total,
        "supported_claims": supported,
        "guarded_claims": guarded,
        "evidence_gate_pass_rate": round(supported / max(1, total), 4),
        "unsupported_or_guarded_rate": round(guarded / max(1, total), 4),
        "overconfidence_rate": round(overconfident / max(1, len(unsupported_confidences)), 4),
        "disposition": "ANSWER" if total and guarded == 0 else "ABSTAIN_OR_QUALIFY",
        "verdicts": [asdict(v) for v in verdicts],
    }
