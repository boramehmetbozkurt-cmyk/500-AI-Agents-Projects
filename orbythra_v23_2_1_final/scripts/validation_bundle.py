from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from app import PLATFORM_RELEASE, __version__

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = [
    "benchmarks/assurance_challenge_v2.json",
    "benchmarks/assurance_challenge_v3.json",
    "benchmarks/external_validation_protocol_v1.json",
    "benchmarks/agentic_policy_challenge_v1.json",
    "benchmarks/autonomy_planning_challenge_v1.json",
    "benchmarks/adaptive_generalist_challenge_v1.json",
    "deploy/kubernetes/orbythra.yaml",
    "docs/EXTERNAL_VALIDATION_BUNDLE.md",
    "docs/V1_3_EXTERNAL_VALIDATION_PROTOCOL.md",
    "docs/V1_3_RELEASE_CRITERIA.md",
    "docs/V2_RELEASE_CRITERIA.md",
    "docs/V2_AGENTIC_SECURITY_MODEL.md",
    "docs/V3_RELEASE_CRITERIA.md",
    "docs/V4_RELEASE_CRITERIA.md",
    "docs/EXTERNAL_VALIDATION_REPORT_TEMPLATE.md",
    "docs/PENTEST_SCOPE_AND_ACCEPTANCE.md",
    "docs/V1_RELEASE_CRITERIA.md",
    "docs/CRYPTO_ARCHITECTURE.md",
    "docs/V22_RELEASE_CRITERIA.md",
    "tests/test_v22_crypto_hardening.py",
    ".github/workflows/v22-crypto-hardening-gate.yml",
    "SECURITY.md",
    "requirements.lock",
    "client/package-lock.json",
    "RADIANODE_READINESS.md",
    "scripts/external_validation_harness.py",
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
            raise SystemExit(f"missing validation artifact: {relative}")
        fingerprints[relative] = sha256_file(path)
    bundle = {
        "bundle_id": "orbythra-v22-crypto-hardening-handoff",
        "product": "ORBYTHRA",
        "version": __version__,
        "platform_release": PLATFORM_RELEASE,
        "release_sha": os.getenv("GITHUB_SHA", "local-or-unset"),
        "generated_at": int(time.time()),
        "hash_algorithm": "sha256",
        "artifacts": fingerprints,
        "required_external_outputs": [
            "independent penetration-test report",
            "independent cryptographic review or scoped crypto findings",
            "independent product-validation report executed against the predeclared protocol",
            "independent agentic/autonomy/adaptive red-team findings for real tool execution",
            "independent adaptive-generalist evaluation on representative cross-domain workloads",
            "real MCP interoperability evidence where MCP is in scope",
            "measured mission success, false-block, false-allow, transfer and rollback rates on representative workloads",
            "tested release SHA and deployment identity",
            "dataset fingerprints and aggregate count tables",
        ],
        "claim": "Reproducible V22 handoff bundle only. PASS means required internal artifacts are present and fingerprinted; it does not mean an external evaluator has approved ORBYTHRA, completed an independent cryptographic audit or penetration test, certified autonomous/adaptive-system safety, established foundation-model self-training, or established AGI/general intelligence.",
    }
    canonical = json.dumps(bundle, separators=(",", ":"), sort_keys=True).encode("utf-8")
    bundle["bundle_sha256"] = hashlib.sha256(canonical).hexdigest()
    print(json.dumps(bundle, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
