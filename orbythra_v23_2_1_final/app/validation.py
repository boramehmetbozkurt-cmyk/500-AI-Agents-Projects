from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from app import __version__
from app.config import SETTINGS
from app.security import Principal, require_minimum_role

router = APIRouter(tags=["validation"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.get("/v1/validation/protocol")
def validation_protocol(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    protocol_path = ROOT / "benchmarks" / "external_validation_protocol_v1.json"
    body = json.loads(protocol_path.read_text(encoding="utf-8"))
    return {
        "product": "ORBYTHRA",
        "version": __version__,
        "workspace_id": principal.workspace_id,
        "release_sha": SETTINGS.release_sha,
        "deployment_id": SETTINGS.deployment_id,
        "protocol_sha256": _sha256(protocol_path),
        "protocol": body,
    }


@router.get("/v1/validation/readiness")
def validation_readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    artifacts = [
        "benchmarks/assurance_challenge_v2.json",
        "benchmarks/assurance_challenge_v3.json",
        "benchmarks/external_validation_protocol_v1.json",
        "docs/EXTERNAL_VALIDATION_BUNDLE.md",
        "docs/PENTEST_SCOPE_AND_ACCEPTANCE.md",
        "docs/V1_RELEASE_CRITERIA.md",
    ]
    fingerprints: dict[str, str] = {}
    missing: list[str] = []
    for relative in artifacts:
        path = ROOT / relative
        if path.is_file():
            fingerprints[relative] = _sha256(path)
        else:
            missing.append(relative)
    return {
        "product": "ORBYTHRA",
        "version": __version__,
        "candidate_status": "EXTERNAL_VALIDATION_CANDIDATE" if not missing else "VALIDATION_PACKAGE_INCOMPLETE",
        "release_sha": SETTINGS.release_sha,
        "deployment_id": SETTINGS.deployment_id,
        "artifact_fingerprints": fingerprints,
        "missing_artifacts": missing,
        "internal_gates": {
            "deterministic_test_suite": "CI_GATED",
            "frozen_benchmark_v2": "CI_GATED",
            "expanded_benchmark_v3": "CI_GATED",
            "performance_smoke": "CI_GATED",
            "backup_restore_drill": "CI_GATED",
            "static_security_scan": "CI_GATED",
            "dependency_audit": "CI_GATED",
            "sbom": "CI_GATED",
            "secret_scan": "CI_GATED",
            "release_evidence": "CI_GATED",
            "recipient_only_x25519_open": "IMPLEMENTED",
        },
        "external_gates": {
            "independent_penetration_test": "PENDING_EXTERNAL_PARTY",
            "independent_crypto_review": "PENDING_EXTERNAL_PARTY",
            "independent_product_validation": "PENDING_EXTERNAL_PARTY",
            "live_production_reliability_history": "PENDING_DEPLOYMENT_EVIDENCE",
            "enterprise_customer_acceptance": "PENDING_COMMERCIAL_EXECUTION",
        },
        "claim": "v1.3 readiness means the package is prepared for independent execution; it does not claim that independent validation has already occurred.",
    }
