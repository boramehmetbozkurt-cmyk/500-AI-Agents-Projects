from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v2-release"}


def test_v2_surfaces_remain_supported_after_later_releases():
    response = client.get("/v1/system/version")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == __version__
    assert body["api_major"] == 1
    assert body["latest_api_major"] >= 3
    assert 2 in body["supported_api_majors"]


def test_v2_assurance_manifest_fingerprints_agent_and_tool_registries():
    agent = client.post(
        "/v2/agents/registry",
        json={"agent_id": "manifest-agent", "display_name": "Manifest Agent", "allowed_tool_ids": ["manifest-tool"]},
        headers=HEADERS,
    )
    assert agent.status_code == 200, agent.text
    tool = client.post(
        "/v2/agents/tools",
        json={"tool_id": "manifest-tool", "display_name": "Manifest Tool", "protocol": "internal", "allowed_operations": ["read"]},
        headers=HEADERS,
    )
    assert tool.status_code == 200, tool.text

    response = client.get("/v1/system/assurance-manifest", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == __version__
    assert body["evidence"]["agent_count"] >= 1
    assert body["evidence"]["tool_count"] >= 1
    assert len(body["evidence"]["agent_registry_sha256"]) == 64
    assert len(body["evidence"]["tool_registry_sha256"]) == 64
    assert body["external_gates"]["independent_agentic_security_validation"] == "PENDING_EXTERNAL_PARTY"
    assert len(body["manifest_sha256"]) == 64
