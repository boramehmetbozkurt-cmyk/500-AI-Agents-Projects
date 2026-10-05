from __future__ import annotations

from fastapi.testclient import TestClient

from app import PLATFORM_RELEASE
from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v232-main"}
OTHER = {"X-API-Key": "test-secret", "X-Workspace-ID": "v232-other"}


def _goal(agent_id: str = "agent-v232") -> dict:
    response = client.post(
        "/v23.2/general-agent/goals",
        headers=HEADERS,
        json={
            "agent_id": agent_id,
            "objective": "Complete a traceable engineering objective.",
            "success_criteria": ["evidence linked", "receipt verified"],
            "priority": 90,
            "horizon_days": 45,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _cycle(goal_id: str, suffix: str) -> dict:
    response = client.post(
        "/v23.2/general-agent/cycle",
        headers=HEADERS,
        json={
            "goal_id": goal_id,
            "episode": {
                "agent_id": "agent-v232",
                "event_type": "verification",
                "summary": f"Verification cycle {suffix} completed.",
                "observations": {"gate": "green", "cycle": suffix},
                "evidence_refs": [f"evidence-{suffix}"],
            },
            "current_state": {"gate": "green", "cycle": suffix},
            "candidates": [
                {
                    "action_id": f"verify-{suffix}",
                    "description": "Perform a reversible evidence-backed verification step.",
                    "expected_utility": 0.8,
                    "failure_probability": 0.01,
                    "reversibility": 1.0,
                    "evidence_coverage": 1.0,
                    "risk_tier": "low",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_v232_release_metadata_and_openapi_surface() -> None:
    assert PLATFORM_RELEASE == "23.2.0"
    body = client.get("/v1/system/version").json()
    assert body["platform_release"] == "23.2.0"
    assert "v23_2_chained_cycle_receipts" in body["platform_capabilities"]
    paths = app.openapi()["paths"]
    for path in [
        "/v23.2/general-agent/episodes",
        "/v23.2/general-agent/episodes/{agent_id}",
        "/v23.2/general-agent/goals",
        "/v23.2/general-agent/goals/id/{goal_id}",
        "/v23.2/general-agent/world/simulate",
        "/v23.2/general-agent/context/{agent_id}",
        "/v23.2/general-agent/cycle",
        "/v23.2/general-agent/receipts/{cycle_id}",
        "/v23.2/general-agent/receipts/{cycle_id}/verify",
        "/v23.2/general-agent/goals/{goal_id}/status",
    ]:
        assert path in paths


def test_v232_context_snapshot_is_hashed_and_workspace_scoped() -> None:
    goal = _goal()
    created = client.post(
        "/v23.2/general-agent/episodes",
        headers=HEADERS,
        json={
            "agent_id": "agent-v232",
            "event_type": "observation",
            "summary": "Observed a traceable state.",
            "observations": {"state": "verified"},
            "evidence_refs": ["ctx-evidence-1"],
        },
    )
    assert created.status_code == 200
    context = client.get("/v23.2/general-agent/context/agent-v232", headers=HEADERS)
    assert context.status_code == 200, context.text
    data = context.json()
    assert len(data["context_sha256"]) == 64
    assert "ctx-evidence-1" in data["evidence_refs"]
    assert any(item["goal_id"] == goal["goal_id"] for item in data["goals"])

    isolated = client.get("/v23.2/general-agent/context/agent-v232", headers=OTHER)
    assert isolated.status_code == 200
    assert isolated.json()["goals"] == []
    assert isolated.json()["recent_episodes"] == []


def test_v232_goal_lifecycle_is_audited_and_terminal_states_fail_closed() -> None:
    goal = _goal("agent-v232-status")
    pause = client.patch(
        f"/v23.2/general-agent/goals/{goal['goal_id']}/status",
        headers=HEADERS,
        json={"status": "PAUSED", "reason": "Awaiting independent review."},
    )
    assert pause.status_code == 200, pause.text
    assert pause.json()["previous_status"] == "ACTIVE"
    assert pause.json()["new_status"] == "PAUSED"
    assert len(pause.json()["event_sha256"]) == 64

    history = client.get(f"/v23.2/general-agent/goals/{goal['goal_id']}/history", headers=HEADERS)
    assert history.status_code == 200
    assert history.json()[0]["reason"] == "Awaiting independent review."

    resume = client.patch(
        f"/v23.2/general-agent/goals/{goal['goal_id']}/status",
        headers=HEADERS,
        json={"status": "ACTIVE", "reason": "Review completed."},
    )
    assert resume.status_code == 200
    complete = client.patch(
        f"/v23.2/general-agent/goals/{goal['goal_id']}/status",
        headers=HEADERS,
        json={"status": "COMPLETED", "reason": "Acceptance criteria satisfied."},
    )
    assert complete.status_code == 200
    rejected = client.patch(
        f"/v23.2/general-agent/goals/{goal['goal_id']}/status",
        headers=HEADERS,
        json={"status": "ACTIVE", "reason": "Try to reopen terminal state."},
    )
    assert rejected.status_code == 409


def test_v232_cycles_persist_chain_linked_receipts_and_verify_integrity() -> None:
    goal = _goal()
    first = _cycle(goal["goal_id"], "one")
    second = _cycle(goal["goal_id"], "two")

    assert first["status"] == "READY"
    assert second["status"] == "READY"
    assert len(first["proof_sha256"]) == 64
    assert second["chain_position"] == first["chain_position"] + 1
    assert second["previous_proof_sha256"] == first["proof_sha256"]

    receipt = client.get(f"/v23.2/general-agent/receipts/{second['cycle_id']}", headers=HEADERS)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["receipt_sha256"] == second["proof_sha256"]
    assert len(receipt.json()["context_sha256"]) == 64
    assert len(receipt.json()["evidence_manifest_sha256"]) == 64

    verified = client.get(f"/v23.2/general-agent/receipts/{second['cycle_id']}/verify", headers=HEADERS)
    assert verified.status_code == 200, verified.text
    assert verified.json()["integrity_valid"] is True
    assert verified.json()["chain_link_valid"] is True
    assert verified.json()["current_chain_head"] is True

    isolated = client.get(f"/v23.2/general-agent/receipts/{second['cycle_id']}", headers=OTHER)
    assert isolated.status_code == 404


def test_v232_cycle_rejects_non_active_goal() -> None:
    goal = _goal()
    changed = client.patch(
        f"/v23.2/general-agent/goals/{goal['goal_id']}/status",
        headers=HEADERS,
        json={"status": "PAUSED", "reason": "Manual hold."},
    )
    assert changed.status_code == 200
    response = client.post(
        "/v23.2/general-agent/cycle",
        headers=HEADERS,
        json={
            "goal_id": goal["goal_id"],
            "episode": {
                "agent_id": "agent-v232",
                "event_type": "planning",
                "summary": "Should not run while paused.",
            },
            "current_state": {},
            "candidates": [
                {
                    "action_id": "safe",
                    "description": "Safe candidate.",
                    "expected_utility": 0.5,
                    "failure_probability": 0.0,
                    "reversibility": 1.0,
                    "evidence_coverage": 1.0,
                    "risk_tier": "low",
                }
            ],
        },
    )
    assert response.status_code == 409
