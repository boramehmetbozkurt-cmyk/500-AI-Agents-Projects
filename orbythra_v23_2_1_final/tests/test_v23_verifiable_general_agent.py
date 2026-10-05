from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)
A = {"X-API-Key": "test-secret", "X-Workspace-ID": "v23-a"}
B = {"X-API-Key": "test-secret", "X-Workspace-ID": "v23-b"}


def _goal():
    response = client.post(
        "/v23/general-agent/goals",
        headers=A,
        json={
            "agent_id": "agent-v23",
            "objective": "Complete a verifiable long-horizon engineering task.",
            "success_criteria": ["evidence verified", "no critical unresolved risk"],
            "priority": 80,
            "horizon_days": 30,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_v23_episode_is_persistent_hashed_and_workspace_scoped():
    created = client.post(
        "/v23/general-agent/episodes",
        headers=A,
        json={
            "agent_id": "agent-v23",
            "event_type": "observation",
            "summary": "Observed a verified state transition.",
            "observations": {"state": "green"},
            "evidence_refs": ["ev-1"],
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert len(payload["content_sha256"]) == 64

    own = client.get("/v23/general-agent/episodes/agent-v23", headers=A)
    assert own.status_code == 200
    assert any(item["episode_id"] == payload["episode_id"] for item in own.json())

    isolated = client.get("/v23/general-agent/episodes/agent-v23", headers=B)
    assert isolated.status_code == 200
    assert all(item["episode_id"] != payload["episode_id"] for item in isolated.json())


def test_v23_persistent_goal_is_workspace_scoped():
    goal = _goal()
    fetched = client.get(f"/v23/general-agent/goals/{goal['goal_id']}", headers=A)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "ACTIVE"
    assert len(fetched.json()["objective_sha256"]) == 64

    isolated = client.get(f"/v23/general-agent/goals/{goal['goal_id']}", headers=B)
    assert isolated.status_code == 404


def test_v23_world_simulation_prefers_safe_evidence_backed_action():
    response = client.post(
        "/v23/general-agent/world/simulate",
        headers=A,
        json={
            "current_state": {"deployment": "candidate"},
            "candidates": [
                {
                    "action_id": "safe",
                    "description": "Run a reversible validation step.",
                    "expected_utility": 0.7,
                    "failure_probability": 0.05,
                    "reversibility": 1.0,
                    "evidence_coverage": 0.95,
                    "risk_tier": "low",
                },
                {
                    "action_id": "risky",
                    "description": "Perform a high risk write.",
                    "expected_utility": 1.0,
                    "failure_probability": 0.2,
                    "reversibility": 0.2,
                    "evidence_coverage": 0.9,
                    "risk_tier": "high",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_action_id"] == "safe"
    assert len(body["simulation_sha256"]) == 64
    decisions = {item["action_id"]: item["decision"] for item in body["actions"]}
    assert decisions["safe"] == "ELIGIBLE"
    assert decisions["risky"] == "REVIEW"


def test_v23_critical_action_fails_closed():
    response = client.post(
        "/v23/general-agent/world/simulate",
        headers=A,
        json={
            "current_state": {"mode": "production"},
            "candidates": [
                {
                    "action_id": "critical-write",
                    "description": "Irreversible critical external mutation.",
                    "expected_utility": 1.0,
                    "failure_probability": 0.01,
                    "reversibility": 0.0,
                    "evidence_coverage": 1.0,
                    "risk_tier": "critical",
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected_action_id"] is None
    assert body["actions"][0]["decision"] == "BLOCK"


def test_v23_integrated_cycle_emits_proof_and_stops_before_execution():
    goal = _goal()
    response = client.post(
        "/v23/general-agent/cycle",
        headers=A,
        json={
            "goal_id": goal["goal_id"],
            "episode": {
                "agent_id": "agent-v23",
                "event_type": "planning",
                "summary": "Planning next bounded action.",
                "observations": {"tests": "green"},
                "evidence_refs": ["ci-green"],
            },
            "current_state": {"tests": "green"},
            "candidates": [
                {
                    "action_id": "verify-next",
                    "description": "Perform another reversible verification step.",
                    "expected_utility": 0.8,
                    "failure_probability": 0.02,
                    "reversibility": 1.0,
                    "evidence_coverage": 1.0,
                    "risk_tier": "low",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "READY"
    assert body["selected_action_id"] == "verify-next"
    assert len(body["proof_sha256"]) == 64
    assert "stops before real-world execution" in body["execution_boundary"]
