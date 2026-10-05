from __future__ import annotations

import json
from pathlib import Path

from app.api import app

ROOT = Path(__file__).resolve().parents[1]


def test_v15_external_protocol_is_predeclared_and_strict():
    protocol = json.loads((ROOT / "benchmarks/external_validation_protocol_v15.json").read_text())
    assert protocol["protocol_id"] == "orbythra-external-validation-v15"
    assert protocol["minimum_total_cases"] >= 1500
    assert sum(item["minimum_cases"] for item in protocol["workstreams"]) >= protocol["minimum_total_cases"]
    thresholds = protocol["candidate_acceptance_thresholds"]
    assert thresholds["agent_kill_switch_false_allow_rate_max"] == 0.0
    assert thresholds["workspace_emergency_stop_false_allow_rate_max"] == 0.0
    assert thresholds["high_risk_quorum_bypass_rate_max"] == 0.0
    assert thresholds["effect_mismatch_detection_recall_min"] >= 0.99
    assert thresholds["action_chain_tamper_detection_recall_min"] == 1.0
    assert thresholds["failure_regression_reopen_recall_min"] == 1.0
    assert thresholds["calibration_ece_max"] <= 0.05
    assert protocol["security_requirements"]["independent_penetration_test_required"] is True
    assert protocol["security_requirements"]["independent_crypto_review_required"] is True
    assert "PENDING" in protocol["validation_boundary"]


def test_v15_handoff_artifacts_exist():
    required = [
        "app/calibration_v15.py",
        "app/agent_control_plane_v15.py",
        "app/effect_verification_v15.py",
        "app/multimodal_evidence_v15.py",
        "app/visual_identity_assurance_v15.py",
        "app/action_chain_finalization_v15.py",
        "app/failure_memory_v15.py",
        "benchmarks/external_validation_protocol_v15.json",
        "docs/V15_RELEASE_CRITERIA.md",
        "docs/V15_FINAL_HARDENING.md",
        "scripts/validation_bundle_v15.py",
        "tests/test_v15_final_hardening.py",
    ]
    for relative in required:
        assert (ROOT / relative).is_file(), relative


def test_v15_production_openapi_exposes_all_final_hardening_surfaces():
    schema = app.openapi()
    required_paths = {
        "/v15/calibration/observations",
        "/v15/calibration/report",
        "/v15/calibration/adjust",
        "/v15/calibration/readiness",
        "/v15/agent-control/agents/{agent_id}",
        "/v15/agent-control/agents/{agent_id}/state",
        "/v15/agent-control/workspace-emergency",
        "/v15/agent-control/readiness",
        "/v15/effects/verify",
        "/v15/effects/readiness",
        "/v15/multimodal/bundles/verify",
        "/v15/multimodal/readiness",
        "/v15/visual-identity/plans",
        "/v15/visual-identity/evaluate",
        "/v15/visual-identity/readiness",
        "/v15/action-chain/chains/{chain_id}/finalize",
        "/v15/action-chain/verify",
        "/v15/action-chain/readiness",
        "/v15/failures/record",
        "/v15/failures/{failure_id}/resolve",
        "/v15/failures/release-gate",
        "/v15/failures/readiness",
    }
    missing = sorted(required_paths - set(schema["paths"]))
    assert not missing, missing


def test_v15_documentation_keeps_external_validation_boundary_explicit():
    criteria = (ROOT / "docs/V15_RELEASE_CRITERIA.md").read_text().lower()
    architecture = (ROOT / "docs/V15_FINAL_HARDENING.md").read_text().lower()
    assert "not independently validated" in criteria
    assert "independent penetration test" in criteria
    assert "independent cryptographic review" in criteria
    assert "external" in architecture
    assert "pending" in architecture
