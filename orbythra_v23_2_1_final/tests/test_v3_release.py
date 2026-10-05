from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v3-release"}


def test_v3_surfaces_remain_supported_after_later_releases():
    response = client.get("/v1/system/version")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == __version__
    assert body["api_major"] == 1
    assert body["latest_api_major"] >= 3
    assert 3 in body["supported_api_majors"]


def test_v3_assurance_manifest_hashes_skill_registry_and_denies_agi_claim():
    response = client.get("/v1/system/assurance-manifest", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == __version__
    assert len(body["evidence"]["skill_registry_sha256"]) == 64
    assert body["external_gates"]["independent_autonomy_validation"] == "PENDING_EXTERNAL_PARTY"
    assert body["external_gates"]["general_intelligence_or_agi_evidence"] == "NOT_CLAIMED"
    assert len(body["manifest_sha256"]) == 64
