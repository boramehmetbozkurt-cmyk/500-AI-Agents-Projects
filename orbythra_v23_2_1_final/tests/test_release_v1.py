from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app import __version__
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "release-v1"}


def test_system_version_exposes_stable_api_major():
    response = client.get("/v1/system/version")
    assert response.status_code == 200
    body = response.json()
    assert body["product"] == "ORBYTHRA"
    assert body["version"] == __version__
    assert body["api_major"] == 1


def test_assurance_manifest_is_hash_addressed_and_keeps_external_gates_explicit():
    response = client.get("/v1/system/assurance-manifest", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product"] == "ORBYTHRA"
    assert len(body["manifest_sha256"]) == 64
    assert len(body["evidence"]["provider_registry_sha256"]) == 64
    assert body["external_gates"]["independent_penetration_test"] == "PENDING_EXTERNAL_PARTY"
    assert "not independent certification" in body["validation_boundary"]


def test_assurance_manifest_does_not_expose_raw_identity_subjects():
    subject = "sensitive-subject-" + uuid.uuid4().hex[:10]
    created = client.put(f"/v1/enterprise/identities/{subject}", json={"subject": subject, "active": True, "role_override": "viewer"}, headers=HEADERS)
    assert created.status_code == 200
    manifest = client.get("/v1/system/assurance-manifest", headers=HEADERS)
    assert manifest.status_code == 200
    assert subject not in json.dumps(manifest.json())
    assert manifest.json()["evidence"]["identity_count"] >= 1
