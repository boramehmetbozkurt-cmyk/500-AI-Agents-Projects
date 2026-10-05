from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app
from app.crypto_core import generate_ed25519_approval_keypair, sign_approval
from app.agent_store import AGENT_STORE

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "agent-v2"}


def _agent(agent_id: str, *, supervisor: str | None = None, max_risk: str = "critical", tools: list[str] | None = None):
    body = {
        "agent_id": agent_id,
        "display_name": agent_id,
        "allowed_tool_ids": tools or [],
        "max_risk_tier": max_risk,
        "human_approval_from_risk": "high",
        "signed_approval_from_risk": "critical",
        "max_actions_per_run": 20,
        "enabled": True,
    }
    if supervisor:
        body["supervisor_agent_id"] = supervisor
    response = client.post("/v2/agents/registry", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _tool(tool_id: str, *, risk: str = "moderate", writes: bool = False, enabled: bool = True):
    response = client.post(
        "/v2/agents/tools",
        json={
            "tool_id": tool_id,
            "display_name": tool_id,
            "protocol": "internal",
            "allowed_operations": ["read", "write", "transfer"],
            "risk_tier": risk,
            "writes_state": writes,
            "requires_idempotency_key": writes,
            "enabled": enabled,
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _propose(agent_id: str, tool_id: str, *, operation: str = "read", risk: str = "moderate", intended_effect: dict | None = None, run_id: str | None = None, idempotency_key: str | None = None):
    response = client.post(
        "/v2/agents/actions/propose",
        json={
            "agent_id": agent_id,
            "tool_id": tool_id,
            "operation": operation,
            "parameters": {"target": "record-1"},
            "intended_effect": intended_effect or {"state": "unchanged"},
            "risk_tier": risk,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
        },
        headers=HEADERS,
    )
    return response


def test_low_risk_action_is_authorized_and_exact_outcome_gets_signed_receipt():
    _tool("read-tool")
    _agent("reader", tools=["read-tool"])
    proposed = _propose("reader", "read-tool", intended_effect={"record": "record-1", "read": True})
    assert proposed.status_code == 200, proposed.text
    action = proposed.json()
    assert action["decision"] == "ALLOW"
    assert action["status"] == "AUTHORIZED"
    assert action["authorization_envelope"]["signature_b64"]

    outcome = client.post(
        f"/v2/agents/actions/{action['action_id']}/outcome",
        json={"actual_effect": {"record": "record-1", "read": True}, "result": {"ok": True}},
        headers=HEADERS,
    )
    assert outcome.status_code == 200, outcome.text
    body = outcome.json()
    assert body["status"] == "OUTCOME_VERIFIED"
    assert body["effect_match"] is True
    assert body["signed_receipt"]["signature_b64"]

    duplicate = client.post(
        f"/v2/agents/actions/{action['action_id']}/outcome",
        json={"actual_effect": {"record": "record-1", "read": True}},
        headers=HEADERS,
    )
    assert duplicate.status_code == 409


def test_state_changing_tool_requires_idempotency_key():
    _tool("write-tool", risk="high", writes=True)
    _agent("writer", tools=["write-tool"])
    proposed = _propose("writer", "write-tool", operation="write", risk="high", intended_effect={"record": "record-1", "value": 2})
    assert proposed.status_code == 200
    assert proposed.json()["decision"] == "BLOCK"
    assert "idempotency_key_required" in proposed.json()["reasons"]


def test_high_risk_action_moves_from_review_to_human_authorized():
    _tool("high-tool", risk="high", writes=True)
    _agent("high-agent", tools=["high-tool"])
    proposed = _propose("high-agent", "high-tool", operation="write", risk="high", intended_effect={"value": 2}, idempotency_key="idem-high-1")
    assert proposed.status_code == 200
    action = proposed.json()
    assert action["status"] == "REVIEW"
    assert "human_approval_required" in action["reasons"]

    authorized = client.post(
        f"/v2/agents/actions/{action['action_id']}/authorize",
        json={"human_approved": True, "approvals": []},
        headers=HEADERS,
    )
    assert authorized.status_code == 200, authorized.text
    assert authorized.json()["status"] == "AUTHORIZED"


def test_critical_action_requires_real_ed25519_intent_bound_approval():
    _tool("critical-tool", risk="critical", writes=True)
    _agent("critical-agent", tools=["critical-tool"])
    proposed = _propose("critical-agent", "critical-tool", operation="transfer", risk="critical", intended_effect={"recipient": "treasury", "amount": "10"}, idempotency_key="idem-critical-1")
    assert proposed.status_code == 200
    action = proposed.json()
    assert action["status"] == "REVIEW"
    assert "signed_approval_required" in action["reasons"]

    pair = generate_ed25519_approval_keypair()
    proof = sign_approval(pair["private_key_b64"], action["intent_digest"])
    authorized = client.post(
        f"/v2/agents/actions/{action['action_id']}/authorize",
        json={"human_approved": True, "approvals": [proof]},
        headers=HEADERS,
    )
    assert authorized.status_code == 200, authorized.text
    assert authorized.json()["decision"] == "ALLOW"
    assert authorized.json()["status"] == "AUTHORIZED"

    wrong = sign_approval(pair["private_key_b64"], "0" * 64)
    second = _propose("critical-agent", "critical-tool", operation="transfer", risk="critical", intended_effect={"recipient": "treasury", "amount": "11"}, idempotency_key="idem-critical-2").json()
    rejected = client.post(
        f"/v2/agents/actions/{second['action_id']}/authorize",
        json={"human_approved": True, "approvals": [wrong]},
        headers=HEADERS,
    )
    assert rejected.status_code == 200
    assert rejected.json()["decision"] == "BLOCK"
    assert "approval_not_bound_to_intent" in rejected.json()["reasons"]


def test_policy_drift_revokes_previously_authorized_action():
    _tool("drift-tool")
    _agent("drift-agent", tools=["drift-tool"])
    proposed = _propose("drift-agent", "drift-tool", intended_effect={"ok": True})
    assert proposed.status_code == 200
    action = proposed.json()
    assert action["status"] == "AUTHORIZED"

    _tool("drift-tool", enabled=False)
    revalidated = client.post(f"/v2/agents/actions/{action['action_id']}/revalidate", headers=HEADERS)
    assert revalidated.status_code == 200, revalidated.text
    assert revalidated.json()["status"] == "POLICY_REVOKED"
    assert revalidated.json()["decision"] == "BLOCK"

    outcome = client.post(f"/v2/agents/actions/{action['action_id']}/outcome", json={"actual_effect": {"ok": True}}, headers=HEADERS)
    assert outcome.status_code == 409


def test_multi_agent_supervision_halts_on_effect_mismatch():
    _tool("supervised-tool")
    _agent("supervisor", tools=["supervised-tool"])
    _agent("worker", supervisor="supervisor", tools=["supervised-tool"])
    started = client.post(
        "/v2/agents/runs",
        json={"objective": "verify supervised work", "supervisor_agent_id": "supervisor", "participant_agent_ids": ["worker"], "max_actions": 10},
        headers=HEADERS,
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]
    proposed = _propose("worker", "supervised-tool", intended_effect={"value": "expected"}, run_id=run_id)
    assert proposed.status_code == 200, proposed.text
    action_id = proposed.json()["action_id"]
    mismatch = client.post(f"/v2/agents/actions/{action_id}/outcome", json={"actual_effect": {"value": "different"}}, headers=HEADERS)
    assert mismatch.status_code == 200, mismatch.text
    assert mismatch.json()["status"] == "OUTCOME_MISMATCH"

    supervision = client.get(f"/v2/agents/runs/{run_id}/supervision", headers=HEADERS)
    assert supervision.status_code == 200, supervision.text
    assert supervision.json()["decision"] == "HALT"
    assert supervision.json()["status_counts"]["OUTCOME_MISMATCH"] == 1
    run = client.get(f"/v2/agents/runs/{run_id}", headers=HEADERS)
    assert run.json()["status"] == "HALTED"


def test_external_tool_registry_blocks_localhost_and_mcp_requires_endpoint():
    local = client.post(
        "/v2/agents/tools",
        json={"tool_id": "bad-http", "display_name": "bad", "protocol": "http", "endpoint_url": "https://127.0.0.1/tool", "allowed_operations": ["read"]},
        headers=HEADERS,
    )
    assert local.status_code == 400
    missing_mcp = client.post(
        "/v2/agents/tools",
        json={"tool_id": "bad-mcp", "display_name": "bad mcp", "protocol": "mcp", "allowed_operations": ["read"], "mcp_tool_name": "read"},
        headers=HEADERS,
    )
    assert missing_mcp.status_code == 422


def test_agent_action_payload_is_encrypted_at_rest():
    _tool("encrypted-tool")
    _agent("encrypted-agent", tools=["encrypted-tool"])
    proposed = _propose("encrypted-agent", "encrypted-tool", intended_effect={"protected": True})
    assert proposed.status_code == 200
    action_id = proposed.json()["action_id"]
    with AGENT_STORE.engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT request_json FROM agent_actions WHERE action_id=?", (action_id,)).first()
    assert row is not None
    assert str(row[0]).startswith("orbenc1:")


def test_v2_readiness_keeps_external_agentic_claims_pending():
    response = client.get("/v2/agents/readiness", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["product_version_target"] == "2.0.0"
    assert body["internal_status"] == "AUTONOMOUS_ASSURANCE_BASELINE"
    assert body["external_gates"]["independent_agentic_security_validation"] == "PENDING_EXTERNAL_PARTY"
