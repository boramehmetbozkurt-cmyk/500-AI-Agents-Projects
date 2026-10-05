from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from app import PLATFORM_RELEASE, __version__

ROOT = Path(__file__).resolve().parents[1]
CRITICAL_FILES = [
    "README.md",
    "CHANGELOG.md",
    "requirements.txt",
    "requirements-dev.txt",
    "Dockerfile",
    "docker-compose.production.yml",
    "SECURITY.md",
    "requirements.lock",
    "client/package-lock.json",
    "RADIANODE_READINESS.md",
    "scripts/external_validation_harness.py",
    "deploy/kubernetes/orbythra.yaml",
    "app/api.py",
    "app/assurance_lab_v21.py",
    "app/telemetry.py",
    "tests/test_v21_assurance_observability.py",
    "docs/V21_ASSURANCE_OBSERVABILITY.md",
    "docs/V21_RELEASE_CRITERIA.md",
    ".github/workflows/v21-assurance-observability-gate.yml",
    "docs/CRYPTO_ARCHITECTURE.md",
    "docs/V22_RELEASE_CRITERIA.md",
    "tests/test_v22_crypto_hardening.py",
    ".github/workflows/v22-crypto-hardening-gate.yml",
    "app/verifiable_general_agent_v23.py",
    "app/verifiable_general_agent_v232.py",
    "app/unified_answer_export.py",
    "app/unified_answer_policy.py",
    "client/src/api.js",
    "client/src/main.jsx",
    "client/src/styles.css",
    "tests/test_v23_verifiable_general_agent.py",
    "tests/test_v23_1_search_and_attachments.py",
    "tests/test_v23_2_verifiable_agent.py",
    "docs/V23_VERIFIABLE_GENERAL_AGENT.md",
    "docs/V23_2_VERIFIABLE_AGENT.md",
    "docs/V23_2_RELEASE_CRITERIA.md",
    ".github/workflows/v23-general-agent-gate.yml",
    ".github/workflows/v23-2-verifiable-agent-gate.yml",
    "app/main.py",
    "app/config.py",
    "app/security.py",
    "app/identity.py",
    "app/crypto_core.py",
    "app/crypto_recipient.py",
    "app/crypto_models.py",
    "app/privacy.py",
    "app/enterprise.py",
    "app/enterprise_models.py",
    "app/enterprise_store.py",
    "app/provider_gateway.py",
    "app/release.py",
    "app/validation.py",
    "app/agents.py",
    "app/agent_execution.py",
    "app/agent_models.py",
    "app/agent_policy.py",
    "app/agent_store.py",
    "app/autonomy.py",
    "app/autonomy_models.py",
    "app/autonomy_store.py",
    "app/adaptive.py",
    "app/adaptive_core.py",
    "app/adaptive_models.py",
    "app/adaptive_store.py",
    "benchmarks/assurance_core_v1.json",
    "benchmarks/assurance_challenge_v2.json",
    "benchmarks/assurance_challenge_v3.json",
    "benchmarks/external_validation_protocol_v1.json",
    "benchmarks/agentic_policy_challenge_v1.json",
    "benchmarks/autonomy_planning_challenge_v1.json",
    "benchmarks/adaptive_generalist_challenge_v1.json",
    "scripts/benchmark_gate.py",
    "scripts/agent_policy_gate.py",
    "scripts/autonomy_planning_gate.py",
    "scripts/adaptive_generalist_gate.py",
    "scripts/performance_gate.py",
    "scripts/deployment_gate.py",
    "scripts/validation_bundle.py",
    "scripts/restore_drill.py",
    "docs/API_STABILITY.md",
    "docs/V1_RELEASE_CRITERIA.md",
    "docs/V1_3_RELEASE_CRITERIA.md",
    "docs/V1_3_EXTERNAL_VALIDATION_PROTOCOL.md",
    "docs/V2_RELEASE_CRITERIA.md",
    "docs/V2_AGENTIC_SECURITY_MODEL.md",
    "docs/V3_RELEASE_CRITERIA.md",
    "docs/V4_RELEASE_CRITERIA.md",
    "docs/EXTERNAL_VALIDATION_REPORT_TEMPLATE.md",
    "docs/IP_INVENTION_DISCLOSURE.md",
    "docs/PRIOR_ART_AND_IP_DIFFERENTIATION.md",
    "docs/EXTERNAL_VALIDATION_BUNDLE.md",
    "docs/PENTEST_SCOPE_AND_ACCEPTANCE.md",
    "docs/VALUATION_100M_EXECUTION_GATES.md",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest() -> dict[str, object]:
    files: dict[str, str] = {}
    missing: list[str] = []
    for relative in CRITICAL_FILES:
        path = ROOT / relative
        if path.is_file():
            files[relative] = sha256_file(path)
        else:
            missing.append(relative)
    if missing:
        raise SystemExit("missing critical release files: " + ", ".join(missing))
    for directory in ('app', 'scripts', 'tests'):
        for path in sorted((ROOT / directory).rglob('*.py')):
            files[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    major = __version__.split(".")[0]
    platform_major = int(PLATFORM_RELEASE.split(".")[0])
    return {
        "product": "ORBYTHRA",
        "version": __version__,
        "platform_release": PLATFORM_RELEASE,
        "commit_sha": os.getenv("GITHUB_SHA", "local-or-unset"),
        "generated_at": int(time.time()),
        "hash_algorithm": "sha256",
        "files": files,
        "validation_candidate": True,
        "v21_assurance_observability_baseline": platform_major >= 21,
        "v22_crypto_hardening_baseline": platform_major >= 22,
        "v23_verifiable_general_agent_baseline": platform_major >= 23,
        "v23_2_traceable_cycle_receipts": PLATFORM_RELEASE.startswith("23.2."),
        "agentic_assurance_baseline": major in {"2", "3", "4"},
        "bounded_autonomy_baseline": major in {"3", "4"},
        "adaptive_generalist_baseline": major == "4",
        "foundation_model_weight_self_training": False,
        "general_intelligence_claim": False,
        "validation_boundary": "internal reproducible release evidence, agentic-control, bounded-autonomy and application-level adaptive-generalist regression evidence only; not independent certification, penetration-test approval, live autonomous/adaptive-system safety proof, foundation-model self-training evidence, AGI evidence, customer acceptance, revenue evidence, patentability or freedom-to-operate clearance",
    }


if __name__ == "__main__":
    print(json.dumps(build_manifest(), indent=2, sort_keys=True))
