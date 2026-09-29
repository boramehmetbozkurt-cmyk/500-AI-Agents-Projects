from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STALE_EVIDENCE = "STALE_EVIDENCE"
LOW_AUTHORITY = "LOW_AUTHORITY"

@dataclass(frozen=True)
class ClaimVerdict:
    status: str
    bound_evidence_ids: tuple[str, ...]
    support: float
    authority: float
    reasons: tuple[str, ...]

def _fresh(item: dict[str, Any], now: datetime, max_age_days: int) -> bool:
    if item.get("time_sensitive") is False:
        return True
    raw = item.get("retrieved_at") or item.get("published_at")
    if not raw:
        return False
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return (now - stamp.astimezone(timezone.utc)).days <= max_age_days
    except (TypeError, ValueError):
        return False

def verify_claim(
    claim: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    minimum_support: float = 0.75,
    minimum_authority: float = 0.60,
    max_age_days: int = 30,
    now: datetime | None = None,
) -> ClaimVerdict:
    now = now or datetime.now(timezone.utc)
    store = {str(item.get("id")): item for item in evidence if item.get("id")}
    requested = [str(x) for x in claim.get("evidence_ids") or []]
    bound = [store[x] for x in requested if x in store]
    ids = tuple(str(x["id"]) for x in bound)
    if not bound:
        return ClaimVerdict(INSUFFICIENT_EVIDENCE, ids, 0.0, 0.0, ("no_bound_evidence",))
    if any(bool(x.get("contradicts")) for x in bound):
        return ClaimVerdict(CONTRADICTED, ids, 0.0, 0.0, ("contradiction_detected",))
    if bool(claim.get("time_sensitive")) and any(not _fresh({**x, "time_sensitive": True}, now, max_age_days) for x in bound):
        return ClaimVerdict(STALE_EVIDENCE, ids, 0.0, 0.0, ("stale_or_undated_evidence",))
    support = sum(float(x.get("support", 0.0)) for x in bound) / len(bound)
    authority = sum(float(x.get("authority", 0.0)) for x in bound) / len(bound)
    reasons: list[str] = []
    if support < minimum_support:
        reasons.append("support_below_threshold")
    if authority < minimum_authority:
        reasons.append("authority_below_threshold")
    if support < minimum_support:
        return ClaimVerdict(INSUFFICIENT_EVIDENCE, ids, support, authority, tuple(reasons))
    if authority < minimum_authority:
        return ClaimVerdict(LOW_AUTHORITY, ids, support, authority, tuple(reasons))
    return ClaimVerdict(SUPPORTED, ids, support, authority, ())

def evaluate_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    verdicts = [verify_claim(claim, evidence, **kwargs) for claim in claims]
    supported = sum(v.status == SUPPORTED for v in verdicts)
    guarded = sum(v.status != SUPPORTED for v in verdicts)
    total = len(verdicts)
    return {
        "total_claims": total,
        "supported_claims": supported,
        "guarded_claims": guarded,
        "evidence_gate_pass_rate": round(supported / max(1, total), 4),
        "unsupported_or_guarded_rate": round(guarded / max(1, total), 4),
        "disposition": "ANSWER" if total and guarded == 0 else "ABSTAIN_OR_QUALIFY",
        "verdicts": [v.__dict__ for v in verdicts],
    }
