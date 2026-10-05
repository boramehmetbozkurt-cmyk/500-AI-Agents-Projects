from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v4-adaptive"}


def _ids() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return f"agent-{suffix}", f"tool-{suffix}"


def _register_agent_tool(*, max_risk: str = "high") -> tuple[str, str]:
    agent_id, tool_id = _ids()
    tool = client.post("/v2/agents/tools", json={"tool_id": tool_id, "display_name": "Adaptive Test Tool", "protocol": "internal", "allowed_operations": ["read", "write"], "risk_tier": "moderate", "writes_state": True, "requires_idempotency_key": True}, headers=HEADERS)
    assert tool.status_code == 200, tool.text
    agent = client.post("/v2/agents/registry", json={"agent_id": agent_id, "display_name": "Adaptive Agent", "allowed_tool_ids": [tool_id], "max_risk_tier": max_risk}, headers=HEADERS)
    assert agent.status_code == 200, agent.text
    return agent_id, tool_id


def _candidate(agent_id: str, tool_id: str, **overrides):
    body = {
        "agent_id": agent_id,
        "source_domain": "engineering",
        "capability": "diagnose-system",
        "procedure": {"steps": ["inspect", "compare", "verify"]},
        "evidence_refs": ["eval:baseline", "eval:candidate"],
        "required_tool_ids": [tool_id],
        "risk_tier": "moderate",
        "baseline_score": 0.60,
        "candidate_score": 0.82,
        "minimum_improvement": 0.05,
    }
    body.update(overrides)
    return body


def test_world_state_is_revisioned_and_hash_chained():
    agent_id, _ = _register_agent_tool()
    first = client.post("/v4/adaptive/world-state", json={"agent_id": agent_id, "domain": "engineering", "state": {"load": "normal"}, "evidence_refs": ["metric:1"], "confidence": 0.9}, headers=HEADERS)
    assert first.status_code == 200, first.text
    second = client.post("/v4/adaptive/world-state", json={"agent_id": agent_id, "domain": "engineering", "state": {"load": "high"}, "evidence_refs": ["metric:2"], "confidence": 0.95}, headers=HEADERS)
    assert second.status_code == 200, second.text
    assert first.json()["revision"] == 1
    assert second.json()["revision"] == 2
    assert second.json()["previous_sha256"] == first.json()["state_sha256"]
    fetched = client.get(f"/v4/adaptive/world-state/{agent_id}/engineering", headers=HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["state"]["load"] == "high"


def test_learning_activation_materializes_skill_and_rollback_disables_it():
    agent_id, tool_id = _register_agent_tool()
    created = client.post("/v4/adaptive/learning/candidates", json=_candidate(agent_id, tool_id), headers=HEADERS)
    assert created.status_code == 200, created.text
    learning_id = created.json()["learning_id"]
    activated = client.post(f"/v4/adaptive/learning/{learning_id}/activate", json={"human_approved": False}, headers=HEADERS)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    skill_id = activated.json()["derived_skill_id"]
    skills = client.get("/v3/autonomy/skills", headers=HEADERS)
    assert skills.status_code == 200
    assert any(item["skill_id"] == skill_id and item["enabled"] for item in skills.json())
    rolled = client.post(f"/v4/adaptive/learning/{learning_id}/rollback", headers=HEADERS)
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["status"] == "ROLLED_BACK"
    skills2 = client.get("/v3/autonomy/skills", headers=HEADERS)
    assert any(item["skill_id"] == skill_id and not item["enabled"] for item in skills2.json())
    history = client.get(f"/v4/adaptive/learning/{learning_id}/history", headers=HEADERS)
    assert [item["status"] for item in history.json()] == ["CANDIDATE", "ACTIVE", "ROLLED_BACK"]
    assert history.json()[1]["previous_sha256"] == history.json()[0]["learning_sha256"]


def test_learning_below_improvement_gate_is_rejected():
    agent_id, tool_id = _register_agent_tool()
    created = client.post("/v4/adaptive/learning/candidates", json=_candidate(agent_id, tool_id, baseline_score=0.70, candidate_score=0.72, minimum_improvement=0.05), headers=HEADERS)
    assert created.status_code == 200
    learning_id = created.json()["learning_id"]
    response = client.post(f"/v4/adaptive/learning/{learning_id}/activate", json={"human_approved": True}, headers=HEADERS)
    assert response.status_code == 409
    history = client.get(f"/v4/adaptive/learning/{learning_id}/history", headers=HEADERS)
    assert history.json()[-1]["status"] == "REJECTED"


def test_high_risk_learning_requires_explicit_human_approval():
    agent_id, tool_id = _register_agent_tool(max_risk="critical")
    created = client.post("/v4/adaptive/learning/candidates", json=_candidate(agent_id, tool_id, risk_tier="high"), headers=HEADERS)
    assert created.status_code == 200
    learning_id = created.json()["learning_id"]
    denied = client.post(f"/v4/adaptive/learning/{learning_id}/activate", json={"human_approved": False}, headers=HEADERS)
    assert denied.status_code == 409
    approved = client.post(f"/v4/adaptive/learning/{learning_id}/activate", json={"human_approved": True}, headers=HEADERS)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "ACTIVE"


def test_cross_domain_transfer_is_proposal_only():
    agent_id, tool_id = _register_agent_tool()
    created = client.post("/v4/adaptive/learning/candidates", json=_candidate(agent_id, tool_id), headers=HEADERS)
    learning_id = created.json()["learning_id"]
    assert client.post(f"/v4/adaptive/learning/{learning_id}/activate", json={"human_approved": False}, headers=HEADERS).status_code == 200
    transfer = client.post("/v4/adaptive/transfer/propose", json={"learning_id": learning_id, "target_domain": "technical-support", "target_capability": "diagnose-service", "evidence_refs": ["transfer-eval:1"]}, headers=HEADERS)
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["status"] == "PROPOSED"
    assert "grants no tool authority" in transfer.json()["boundary"]
    assert len(transfer.json()["transfer_sha256"]) == 64


def test_meta_routing_is_deterministic_and_constraint_bound():
    low = client.post("/v4/adaptive/strategies", json={"strategy_id": "safe-fast", "display_name": "Safe Fast", "domains": ["engineering"], "capabilities": ["reason", "verify"], "risk_tier": "moderate", "success_score": 0.80, "latency_score": 0.20, "cost_score": 0.20}, headers=HEADERS)
    assert low.status_code == 200, low.text
    high = client.post("/v4/adaptive/strategies", json={"strategy_id": "risky-best", "display_name": "Risky Best", "domains": ["engineering"], "capabilities": ["reason", "verify"], "risk_tier": "critical", "success_score": 0.99, "latency_score": 0.10, "cost_score": 0.10}, headers=HEADERS)
    assert high.status_code == 200
    routed = client.post("/v4/adaptive/route", json={"domain": "engineering", "required_capabilities": ["reason", "verify"], "max_risk_tier": "high"}, headers=HEADERS)
    assert routed.status_code == 200, routed.text
    assert routed.json()["strategy_id"] == "safe-fast"
    assert len(routed.json()["routing_sha256"]) == 64


def test_v4_readiness_keeps_agi_and_weight_training_claims_false():
    response = client.get("/v4/adaptive/readiness", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["gated_continual_learning"] is True
    assert body["rollbackable_learning"] is True
    assert body["model_weight_self_training"] is False
    assert body["agi_claim"] is False
