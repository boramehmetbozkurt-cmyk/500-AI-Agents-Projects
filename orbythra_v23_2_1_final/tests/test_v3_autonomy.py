from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v3-autonomy"}


def _register_baseline() -> None:
    tool = client.post(
        "/v2/agents/tools",
        json={
            "tool_id": "research-tool",
            "display_name": "Research Tool",
            "protocol": "internal",
            "allowed_operations": ["read"],
            "risk_tier": "moderate",
        },
        headers=HEADERS,
    )
    assert tool.status_code == 200, tool.text
    agent = client.post(
        "/v2/agents/registry",
        json={
            "agent_id": "autonomy-agent",
            "display_name": "Autonomy Agent",
            "allowed_tool_ids": ["research-tool"],
            "max_risk_tier": "high",
        },
        headers=HEADERS,
    )
    assert agent.status_code == 200, agent.text


def test_v3_memory_is_persistent_queryable_and_hashed():
    _register_baseline()
    response = client.post(
        "/v3/autonomy/memory",
        json={
            "agent_id": "autonomy-agent",
            "kind": "semantic",
            "content": {"fact": "bounded-memory-test"},
            "tags": ["test", "memory"],
            "confidence": 0.9,
            "source_refs": ["unit-test"],
            "sensitivity": "confidential",
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert len(created["content_sha256"]) == 64

    query = client.post(
        "/v3/autonomy/memory/query",
        json={"agent_id": "autonomy-agent", "kinds": ["semantic"], "tags": ["memory"], "min_confidence": 0.8},
        headers=HEADERS,
    )
    assert query.status_code == 200, query.text
    assert any(item["memory_id"] == created["memory_id"] for item in query.json())


def test_v3_plan_drift_replan_and_completion_cycle():
    _register_baseline()
    skill = client.post(
        "/v3/autonomy/skills",
        json={
            "skill_id": "research-skill",
            "display_name": "Research Skill",
            "version": "1.0.0",
            "capabilities": ["research"],
            "required_tool_ids": ["research-tool"],
            "risk_tier": "moderate",
        },
        headers=HEADERS,
    )
    assert skill.status_code == 200, skill.text

    mission = client.post(
        "/v3/autonomy/missions",
        json={
            "agent_id": "autonomy-agent",
            "objective": "Collect evidence and verify completion",
            "success_criteria": ["evidence-collected"],
            "required_capabilities": ["research"],
            "risk_budget": "high",
            "max_cycles": 3,
        },
        headers=HEADERS,
    )
    assert mission.status_code == 200, mission.text
    mission_id = mission.json()["mission_id"]

    plan = client.post(f"/v3/autonomy/missions/{mission_id}/plan", headers=HEADERS)
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["missing_capabilities"] == []
    assert body["selected_skill_ids"] == ["research-skill"]
    assert len(body["plan_sha256"]) == 64

    stable = client.post(f"/v3/autonomy/missions/{mission_id}/drift", headers=HEADERS)
    assert stable.status_code == 200, stable.text
    assert stable.json()["drift_detected"] is False

    changed_skill = client.post(
        "/v3/autonomy/skills",
        json={
            "skill_id": "research-skill",
            "display_name": "Research Skill",
            "version": "1.1.0",
            "capabilities": ["research"],
            "required_tool_ids": ["research-tool"],
            "risk_tier": "moderate",
        },
        headers=HEADERS,
    )
    assert changed_skill.status_code == 200, changed_skill.text

    drift = client.post(f"/v3/autonomy/missions/{mission_id}/drift", headers=HEADERS)
    assert drift.status_code == 200, drift.text
    assert drift.json()["drift_detected"] is True
    assert drift.json()["status"] == "PAUSED"

    replan = client.post(f"/v3/autonomy/missions/{mission_id}/plan", headers=HEADERS)
    assert replan.status_code == 200, replan.text
    assert replan.json()["revision"] == 2

    evaluation = client.post(
        f"/v3/autonomy/missions/{mission_id}/evaluate",
        json={
            "observations": [{"evidence": "verified"}],
            "criterion_results": {"evidence-collected": True},
            "action_ids": [],
            "write_memory": True,
        },
        headers=HEADERS,
    )
    assert evaluation.status_code == 200, evaluation.text
    result = evaluation.json()
    assert result["status"] == "COMPLETED"
    assert result["completion_ratio"] == 1.0
    assert result["memory_id"].startswith("mem_")
    assert len(result["evaluation_sha256"]) == 64


def test_v3_missing_capability_pauses_instead_of_inventing_skill():
    _register_baseline()
    mission = client.post(
        "/v3/autonomy/missions",
        json={
            "agent_id": "autonomy-agent",
            "objective": "Use a capability that does not exist",
            "success_criteria": ["done"],
            "required_capabilities": ["nonexistent-capability"],
            "risk_budget": "high",
        },
        headers=HEADERS,
    )
    assert mission.status_code == 200, mission.text
    mission_id = mission.json()["mission_id"]
    plan = client.post(f"/v3/autonomy/missions/{mission_id}/plan", headers=HEADERS)
    assert plan.status_code == 200, plan.text
    assert plan.json()["missing_capabilities"] == ["nonexistent-capability"]
    state = client.get(f"/v3/autonomy/missions/{mission_id}", headers=HEADERS)
    assert state.json()["status"] == "PAUSED"


def test_v3_readiness_explicitly_denies_agi_claim():
    response = client.get("/v3/autonomy/readiness", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["persistent_memory"] is True
    assert body["deterministic_planner"] is True
    assert body["v2_execution_gate_required"] is True
    assert body["live_general_intelligence_claim"] is False
