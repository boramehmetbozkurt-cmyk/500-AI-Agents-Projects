from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = [
    "app/verification_firewall_v12.py",
    "app/distributed_verification_v12.py",
    "app/action_chain_v12.py",
    "app/temporal_reality_v12.py",
    "tests/test_verification_firewall_v12.py",
    "tests/test_distributed_verification_v12.py",
    "tests/test_action_chain_v12.py",
    "tests/test_temporal_reality_v12.py",
    "tests/test_v12_external_validation_package.py",
    "benchmarks/external_validation_protocol_v12.json",
    "docs/V12_RELEASE_CRITERIA.md",
    "docs/V12_INDEPENDENT_AUDIT_HANDOFF.md",
    "docs/V12_SECURITY_AUDIT_SCOPE.md",
    "docs/PENTEST_SCOPE_AND_ACCEPTANCE.md",
    "SECURITY.md",
    "deploy/kubernetes/orbythra.yaml",
    ".github/workflows/ci.yml"
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    fingerprints: dict[str, str] = {}
    for relative in ARTIFACTS:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing V12 validation artifact: {relative}")
        fingerprints[relative] = sha256_file(path)

    release_sha = os.getenv("GITHUB_SHA") or os.getenv("ORBYTHRA_RELEASE_SHA") or "local-or-unset"
    deployment_id = os.getenv("ORBYTHRA_DEPLOYMENT_ID", "local-or-unset")
    configuration_sha256 = os.getenv("ORBYTHRA_CONFIGURATION_SHA256", "external-assessor-to-freeze")

    bundle = {
        "bundle_id": "orbythra-v12-independent-validation-handoff",
        "product": "ORBYTHRA",
        "target": "V12 P0",
        "generated_at": int(time.time()),
        "release_sha": release_sha,
        "deployment_id": deployment_id,
        "configuration_sha256": configuration_sha256,
        "hash_algorithm": "sha256",
        "artifacts": fingerprints,
        "predeclared_protocol": "benchmarks/external_validation_protocol_v12.json",
        "release_criteria": "docs/V12_RELEASE_CRITERIA.md",
        "assessor_handoff": "docs/V12_INDEPENDENT_AUDIT_HANDOFF.md",
        "security_audit_scope": "docs/V12_SECURITY_AUDIT_SCOPE.md",
        "required_external_outputs": [
            "independent product-validation report",
            "independent penetration-test report",
            "independent cryptographic review or signed scoped findings",
            "independence/conflict-of-interest disclosure",
            "tested release SHA and deployment/configuration identity",
            "validation dataset fingerprint",
            "raw aggregate count tables and all primary metrics",
            "security remediation and independent retest disposition",
            "documented protocol deviations"
        ],
        "claim_boundary": "This manifest proves only which internal handoff artifacts were fingerprinted for a release candidate. It is not an independent validation result, certification, security guarantee, or proof of universal factual correctness."
    }
    canonical = json.dumps(bundle, separators=(",", ":"), sort_keys=True).encode("utf-8")
    bundle["bundle_sha256"] = hashlib.sha256(canonical).hexdigest()
    print(json.dumps(bundle, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
