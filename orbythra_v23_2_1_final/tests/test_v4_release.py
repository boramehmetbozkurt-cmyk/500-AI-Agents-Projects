from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v4-release"}


def test_v4_version_metadata_preserves_v1_v2_v3_and_exposes_v4():
    response = client.get("/v1/system/version")
    assert response.status_code == 200, response.text
    body = response.json()
    assert __version__ == "4.0.0"
    assert body["version"] == "4.0.0"
    assert body["api_major"] == 1
    assert body["latest_api_major"] == 4
    assert body["supported_api_majors"] == [1, 2, 3, 4]


def test_v4_assurance_manifest_hashes_adaptive_registries_and_keeps_external_gate_explicit():
    response = client.get("/v1/system/assurance-manifest", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == "4.0.0"
    evidence = body["evidence"]
    assert len(evidence["adaptive_world_state_sha256"]) == 64
    assert len(evidence["adaptive_learning_history_sha256"]) == 64
    assert len(evidence["adaptive_strategy_registry_sha256"]) == 64
    assert len(evidence["adaptive_transfer_registry_sha256"]) == 64
    assert body["external_gates"]["independent_adaptive_generalist_validation"] == "PENDING_EXTERNAL_PARTY"
    assert body["external_gates"]["foundation_model_weight_self_training"] == "NOT_IMPLEMENTED_OR_CLAIMED"
    assert body["external_gates"]["general_intelligence_or_agi_evidence"] == "NOT_CLAIMED"
    assert len(body["manifest_sha256"]) == 64


def test_v4_openapi_surface_is_composed():
    paths = app.openapi()["paths"]
    required = [
        "/v4/adaptive/world-state",
        "/v4/adaptive/world-state/{agent_id}/{domain}",
        "/v4/adaptive/learning/candidates",
        "/v4/adaptive/learning/{learning_id}/history",
        "/v4/adaptive/learning/{learning_id}/activate",
        "/v4/adaptive/learning/{learning_id}/rollback",
        "/v4/adaptive/transfer/propose",
        "/v4/adaptive/strategies",
        "/v4/adaptive/route",
        "/v4/adaptive/readiness",
    ]
    for path in required:
        assert path in paths, path


def test_v4_readiness_is_bounded_and_not_an_agi_claim():
    response = client.get("/v4/adaptive/readiness", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == "4.0.0"
    assert body["gated_continual_learning"] is True
    assert body["rollbackable_learning"] is True
    assert body["cross_domain_transfer_proposals"] is True
    assert body["model_weight_self_training"] is False
    assert body["agi_claim"] is False
