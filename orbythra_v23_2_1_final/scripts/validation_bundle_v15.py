from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = [
    "app/api.py",
    "app/agent_execution.py",
    "app/calibration_v15.py",
    "app/agent_control_plane_v15.py",
    "app/effect_verification_v15.py",
    "app/multimodal_evidence_v15.py",
    "app/visual_identity_assurance_v15.py",
    "app/action_chain_finalization_v15.py",
    "app/failure_memory_v15.py",
    "app/verification_firewall_v12.py",
    "app/distributed_verification_v12.py",
    "app/action_chain_v12.py",
    "app/temporal_reality_v12.py",
    "tests/test_v15_final_hardening.py",
    "tests/test_v15_release_package.py",
    "benchmarks/external_validation_protocol_v15.json",
    "docs/V15_RELEASE_CRITERIA.md",
    "docs/V15_FINAL_HARDENING.md",
    "docs/V12_SECURITY_AUDIT_SCOPE.md",
    "docs/PENTEST_SCOPE_AND_ACCEPTANCE.md",
    "SECURITY.md",
    "deploy/kubernetes/orbythra.yaml",
    ".github/workflows/ci.yml",
    ".github/workflows/v15-final-gate.yml",
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
            raise SystemExit(f"missing V15 validation artifact: {relative}")
        fingerprints[relative] = sha256_file(path)

    release_sha = os.getenv("GITHUB_SHA") or os.getenv("ORBYTHRA_RELEASE_SHA") or "local-or-unset"
    deployment_id = os.getenv("ORBYTHRA_DEPLOYMENT_ID", "local-or-unset")
    configuration_sha256 = os.getenv("ORBYTHRA_CONFIGURATION_SHA256", "external-assessor-to-freeze")
    bundle = {
        "bundle_id": "orbythra-v15-final-independent-validation-handoff",
        "product": "ORBYTHRA",
        "target": "V15.0 final hardening",
        "generated_at": int(time.time()),
        "release_sha": release_sha,
        "deployment_id": deployment_id,
        "configuration_sha256": configuration_sha256,
        "hash_algorithm": "sha256",
        "artifacts": fingerprints,
        "predeclared_protocol": "benchmarks/external_validation_protocol_v15.json",
        "release_criteria": "docs/V15_RELEASE_CRITERIA.md",
        "architecture_note": "docs/V15_FINAL_HARDENING.md",
        "required_external_outputs": [
            "independent product-validation report",
            "independent penetration-test report",
            "independent cryptographic review or signed scoped findings",
            "independence/conflict-of-interest disclosure",
            "tested release SHA and deployment/configuration identity",
            "validation dataset fingerprint and aggregate count tables",
            "visual metric adapter/model hashes where visual assurance is evaluated",
            "security remediation and independent retest disposition",
            "documented protocol deviations",
        ],
        "claim_boundary": (
            "This manifest proves only which internal V15 handoff artifacts were fingerprinted for the exact candidate. "
            "It is not an independent validation result, certification, commercial-production proof, universal factuality proof, "
            "or security guarantee outside the assessed scope."
        ),
    }
    canonical = json.dumps(bundle, separators=(",", ":"), sort_keys=True).encode("utf-8")
    bundle["bundle_sha256"] = hashlib.sha256(canonical).hexdigest()
    print(json.dumps(bundle, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
