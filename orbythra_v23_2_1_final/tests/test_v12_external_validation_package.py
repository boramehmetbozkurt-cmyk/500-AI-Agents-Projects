from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from app.api import app

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "benchmarks" / "external_validation_protocol_v12.json"


def test_v12_protocol_is_predeclared_and_has_strict_acceptance_gates():
    data = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert data["protocol_id"] == "orbythra-external-validation-v12"
    assert data["status"] == "PREDECLARED_BEFORE_EXTERNAL_EXECUTION"
    assert data["minimum_total_cases"] >= 1000
    assert data["independence_requirements"]["evaluator_must_be_external_to_orbythra"] is True
    assert data["independence_requirements"]["material_development_contributors_may_not_be_sole_independent_validator"] is True
    thresholds = data["acceptance_thresholds"]
    assert thresholds["workspace_isolation_escape_rate_max"] == 0.0
    assert thresholds["validator_spoof_or_stale_authority_detection_rate_min"] == 1.0
    assert thresholds["action_chain_tamper_replay_detection_rate_min"] == 1.0
    assert thresholds["unresolved_critical_security_findings_max"] == 0
    assert thresholds["unresolved_high_security_findings_max"] == 0


def test_v12_protocol_workstreams_sum_to_declared_minimum():
    data = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    total = sum(int(item["minimum_cases"]) for item in data["workstreams"])
    assert total >= data["minimum_total_cases"]
    names = {item["name"] for item in data["workstreams"]}
    assert names == {
        "claim_and_evidence_assurance",
        "temporal_reality",
        "distributed_verification",
        "governed_action_chain",
        "security_and_tenant_isolation",
    }


def test_v12_validation_handoff_files_exist_and_are_nonempty():
    required = [
        ROOT / "docs" / "V12_RELEASE_CRITERIA.md",
        ROOT / "docs" / "V12_INDEPENDENT_AUDIT_HANDOFF.md",
        ROOT / "scripts" / "validation_bundle_v12.py",
        PROTOCOL,
    ]
    for path in required:
        assert path.is_file(), str(path)
        assert path.stat().st_size > 200, str(path)


def test_v12_handoff_manifest_is_machine_readable_and_fingerprints_protocol():
    output = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "validation_bundle_v12.py")], cwd=ROOT, text=True)
    manifest = json.loads(output)
    assert manifest["bundle_id"] == "orbythra-v12-independent-validation-handoff"
    relative = "benchmarks/external_validation_protocol_v12.json"
    expected = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    assert manifest["artifacts"][relative] == expected
    assert len(manifest["bundle_sha256"]) == 64
    assert "independent product-validation report" in manifest["required_external_outputs"]


def test_v12_production_composition_exposes_all_new_readiness_and_control_endpoints():
    schema = app.openapi()
    required = {
        "/v12/verification/evaluate",
        "/v12/verification/readiness",
        "/v12/trust/validators/register",
        "/v12/trust/validators/{validator_id}/active",
        "/v12/trust/validators/{validator_id}/rotate",
        "/v12/trust/quorum",
        "/v12/trust/readiness",
        "/v12/action-chain/chains",
        "/v12/action-chain/chains/{chain_id}/append",
        "/v12/action-chain/chains/{chain_id}",
        "/v12/action-chain/readiness",
        "/v12/temporal/facts",
        "/v12/temporal/facts/{fact_id}/retire",
        "/v12/temporal/snapshot",
        "/v12/temporal/readiness",
    }
    missing = sorted(path for path in required if path not in schema["paths"])
    assert not missing, missing
