from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class GeneralistCase(BaseModel):
    case_id: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=120)
    unseen: bool = True
    success: bool
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    transferred_skill: bool = False


class GeneralistEvaluationRequest(BaseModel):
    evaluation_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    cases: list[GeneralistCase] = Field(min_length=4, max_length=10000)
    minimum_domains: int = Field(default=3, ge=2, le=100)
    minimum_success_rate: float = Field(default=0.75, ge=0.0, le=1.0)
    minimum_unseen_success_rate: float = Field(default=0.70, ge=0.0, le=1.0)
    minimum_evidence_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    maximum_calibration_error: float = Field(default=0.20, ge=0.0, le=1.0)


def evaluate_generalist(body: GeneralistEvaluationRequest) -> dict[str, Any]:
    cases = body.cases
    domains = sorted({c.domain for c in cases})
    unseen = [c for c in cases if c.unseen]
    transfers = [c for c in cases if c.transferred_skill]
    success_rate = sum(c.success for c in cases) / len(cases)
    unseen_rate = sum(c.success for c in unseen) / len(unseen) if unseen else 0.0
    evidence = sum(c.evidence_coverage for c in cases) / len(cases)
    calibration = sum(abs(c.confidence - float(c.success)) for c in cases) / len(cases)
    transfer_rate = sum(c.success for c in transfers) / len(transfers) if transfers else None
    gates = {
        "domain_diversity": len(domains) >= body.minimum_domains,
        "overall_success": success_rate >= body.minimum_success_rate,
        "unseen_success": bool(unseen) and unseen_rate >= body.minimum_unseen_success_rate,
        "evidence_coverage": evidence >= body.minimum_evidence_coverage,
        "calibration": calibration <= body.maximum_calibration_error,
    }
    metrics = {
        "cases": len(cases),
        "domains": domains,
        "domain_count": len(domains),
        "unseen_cases": len(unseen),
        "transfer_cases": len(transfers),
        "success_rate": round(success_rate, 6),
        "unseen_success_rate": round(unseen_rate, 6),
        "evidence_coverage": round(evidence, 6),
        "calibration_error": round(calibration, 6),
        "transfer_success_rate": None if transfer_rate is None else round(transfer_rate, 6),
    }
    result = {
        "schema": "orbythra.generalist-evaluation.v5",
        "evaluation_id": body.evaluation_id,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "generalist_ready": all(gates.values()),
        "metrics": metrics,
        "gates": gates,
        "boundary": "Passing this application-level benchmark is evidence of bounded cross-domain generalization under the supplied cases; it is not proof of AGI or human-level general intelligence.",
    }
    return {**result, "evaluation_sha256": _sha(result)}
