from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

@dataclass(frozen=True)
class ClaimVerdict:
    status: str
    bound_evidence_ids: tuple[str, ...]
    support: float

def verify_claim(claim: dict[str, Any], evidence: list[dict[str, Any]], minimum_support: float = 0.60) -> ClaimVerdict:
    store = {str(item.get("id")): item for item in evidence if item.get("id")}
    requested = [str(x) for x in claim.get("evidence_ids") or []]
    bound = [store[x] for x in requested if x in store]
    ids = tuple(str(x["id"]) for x in bound)
    if any(bool(x.get("contradicts")) for x in bound):
        return ClaimVerdict(CONTRADICTED, ids, 0.0)
    if not bound:
        return ClaimVerdict(INSUFFICIENT_EVIDENCE, ids, 0.0)
    support = sum(float(x.get("support", 1.0)) for x in bound) / len(bound)
    if support < minimum_support:
        return ClaimVerdict(INSUFFICIENT_EVIDENCE, ids, support)
    return ClaimVerdict(SUPPORTED, ids, support)

def evaluate_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = [verify_claim(claim, evidence) for claim in claims]
    supported = sum(v.status == SUPPORTED for v in verdicts)
    guarded = sum(v.status != SUPPORTED for v in verdicts)
    total = len(verdicts)
    return {
        "total_claims": total,
        "supported_claims": supported,
        "guarded_claims": guarded,
        "unsupported_claim_rate": round(guarded / max(1, total), 4),
        "disposition": "ANSWER" if total and guarded == 0 else "ABSTAIN_OR_QUALIFY",
        "verdicts": [v.__dict__ for v in verdicts],
    }
