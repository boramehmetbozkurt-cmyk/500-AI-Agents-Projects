from __future__ import annotations

from fastapi.testclient import TestClient

import app.crypto_core as crypto_core
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v2-execution"}


def _register(agent_id: str, tool_id: str) -> None:
    tool = client.post(
        "/v2/agents/tools",
        json={"tool_id": tool_id, "display_name": tool_id, "protocol": "internal", "allowed_operations": ["read"], "risk_tier": "low"},
        headers=HEADERS,
    )
    assert tool.status_code == 200, tool.text
    agent = client.post(
        "/v2/agents/registry",
        json={"agent_id": agent_id, "display_name": agent_id, "allowed_tool_ids": [tool_id], "max_risk_tier": "high"},
        headers=HEADERS,
    )
    assert agent.status_code == 200, agent.text


def _authorized_action(agent_id: str, tool_id: str, ttl: int = 30) -> dict:
    response = client.post(
        "/v2/agents/actions/propose",
        json={
            "agent_id": agent_id,
            "tool_id": tool_id,
            "operation": "read",
            "parameters": {"record": "r1"},
            "intended_effect": {"read": "r1"},
            "risk_tier": "low",
            "authorization_ttl_seconds": ttl,
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "AUTHORIZED"
    return body


def test_execution_check_verifies_policy_intent_signature_and_ttl():
    _register("exec-agent", "exec-tool")
    action = _authorized_action("exec-agent", "exec-tool")
    response = client.post(f"/v2/agents/actions/{action['action_id']}/execution-check", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["executable"] is True
    assert body["intent_digest"] == action["intent_digest"]
    assert body["policy_snapshot_sha256"] == action["policy_snapshot_sha256"]
    assert body["authorization_signer_verified"] is True
    assert body["authorization_expires_at"] > 0
    assert body["tool_id"] == "exec-tool"
    assert body["operation"] == "read"


def test_execution_check_rejects_expired_authorization_and_revokes_action(monkeypatch):
    _register("expiry-agent", "expiry-tool")
    action = _authorized_action("expiry-agent", "expiry-tool", ttl=30)
    expires_at = int(action["authorization_envelope"]["header"]["expires_at"])
    monkeypatch.setattr(crypto_core.time, "time", lambda: expires_at + 1)

    response = client.post(f"/v2/agents/actions/{action['action_id']}/execution-check", headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "agent_authorization_invalid:envelope_expired"

    stored = client.get(f"/v2/agents/actions/{action['action_id']}", headers=HEADERS)
    assert stored.status_code == 200
    assert stored.json()["status"] == "POLICY_REVOKED"
