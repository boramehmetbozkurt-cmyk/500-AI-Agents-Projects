from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("ORBYTHRA_ENV", "test")
os.environ.setdefault("ORBYTHRA_API_KEYS", "tester:test-secret,other:other-secret")
os.environ.setdefault("ORBYTHRA_DB_PATH", "/tmp/orbythra-fastapi-tests.db")
os.environ.setdefault("ORBYTHRA_RATE_LIMIT_PER_MINUTE", "100")

from fastapi.testclient import TestClient

from app.main import app
from app.security import RATE_LIMITER

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "workspace-a"}


def _good_evidence(now: str) -> list[dict[str, object]]:
    return [
        {"id": "e1", "support": 0.95, "authority": 0.9, "retrieved_at": now},
        {"id": "e2", "support": 0.85, "authority": 0.8, "retrieved_at": now},
    ]


def test_health_is_public_and_security_headers_exist() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_ready_reports_operational_dependencies() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_configured"] is True
    assert body["database_ready"] is True
    assert body["ready"] is True


def test_protected_endpoint_rejects_missing_api_key() -> None:
    response = client.post("/v1/plan", json={"query": "Analyze this technical system"})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_api_key"


def test_invalid_workspace_is_rejected() -> None:
    response = client.post(
        "/v1/plan",
        json={"query": "Analyze this technical system"},
        headers={"X-API-Key": "test-secret", "X-Workspace-ID": "../escape"},
    )
    assert response.status_code == 400


def test_supported_claim_passes_gate() -> None:
    now = datetime.now(UTC).isoformat()
    response = client.post(
        "/v1/verify",
        json={
            "claims": [
                {
                    "id": "c1",
                    "text": "A well-supported claim",
                    "evidence_ids": ["e1", "e2"],
                    "time_sensitive": True,
                }
            ],
            "evidence": _good_evidence(now),
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["disposition"] == "ANSWER"
    assert body["evidence_gate_pass_rate"] == 1.0


def test_unsupported_claim_forces_qualification() -> None:
    response = client.post(
        "/v1/verify",
        json={
            "claims": [{"text": "Unsupported claim", "evidence_ids": []}],
            "evidence": [],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["disposition"] == "ABSTAIN_OR_QUALIFY"
    assert body["verdicts"][0]["status"] == "INSUFFICIENT_EVIDENCE"


def test_contradicted_claim_is_never_supported() -> None:
    now = datetime.now(UTC).isoformat()
    response = client.post(
        "/v1/verify",
        json={
            "claims": [{"text": "Claim", "evidence_ids": ["e1"]}],
            "evidence": [
                {
                    "id": "e1",
                    "support": 1.0,
                    "authority": 1.0,
                    "retrieved_at": now,
                    "contradicts": True,
                }
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["verdicts"][0]["status"] == "CONTRADICTED"


def test_stale_evidence_is_blocked_for_time_sensitive_claim() -> None:
    old = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    response = client.post(
        "/v1/verify",
        json={
            "claims": [
                {
                    "text": "Time-sensitive claim",
                    "evidence_ids": ["e1"],
                    "time_sensitive": True,
                }
            ],
            "evidence": [
                {
                    "id": "e1",
                    "support": 1.0,
                    "authority": 1.0,
                    "retrieved_at": old,
                }
            ],
            "max_age_days": 30,
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["verdicts"][0]["status"] == "STALE_EVIDENCE"


def test_low_authority_evidence_is_blocked() -> None:
    now = datetime.now(UTC).isoformat()
    response = client.post(
        "/v1/verify",
        json={
            "claims": [{"text": "Claim", "evidence_ids": ["e1"]}],
            "evidence": [
                {
                    "id": "e1",
                    "support": 0.99,
                    "authority": 0.2,
                    "retrieved_at": now,
                }
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["verdicts"][0]["status"] == "LOW_AUTHORITY"


def test_adaptive_plan() -> None:
    response = client.post(
        "/v1/plan",
        json={"query": "Bu teknik sistemi analiz et ve doğrulama stratejisi geliştir"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["complexity"] >= 2
    assert "engineering_intelligence" in body["modes"]


def test_engineering_envelope_marks_missing_inputs() -> None:
    response = client.post(
        "/v1/engineering/envelope",
        json={"problem": "Reduce failure rate of a production component"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision_status"] == "NEEDS_MORE_INPUT"
    assert "target_or_acceptance_criteria" in body["unknowns"]


def test_engineering_envelope_can_be_ready() -> None:
    response = client.post(
        "/v1/engineering/envelope",
        json={
            "problem": "Reduce failure rate of a production component",
            "target": "Failure rate below 0.1%",
            "constraints": ["No material substitution"],
            "standards": ["Applicable standard to be verified"],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["decision_status"] == "READY_FOR_EVIDENCE"


def test_evidence_snapshot_is_workspace_isolated() -> None:
    response = client.post(
        "/v1/evidence/snapshots",
        json={
            "label": "validation-case-1",
            "evidence": [
                {"id": "e1", "support": 0.9, "authority": 0.9}
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    snapshot_id = response.json()["snapshot_id"]

    same_workspace = client.get(
        f"/v1/evidence/snapshots/{snapshot_id}",
        headers=HEADERS,
    )
    assert same_workspace.status_code == 200

    other_workspace = client.get(
        f"/v1/evidence/snapshots/{snapshot_id}",
        headers={"X-API-Key": "test-secret", "X-Workspace-ID": "workspace-b"},
    )
    assert other_workspace.status_code == 404


def test_pilot_run_passes_explicit_acceptance_and_is_retrievable() -> None:
    now = datetime.now(UTC).isoformat()
    response = client.post(
        "/v1/pilot/run",
        json={
            "scenario_id": "engineering-case-001",
            "query": "Analyze and verify the production failure reduction proposal",
            "verification": {
                "claims": [
                    {
                        "id": "c1",
                        "text": "Measured failure rate meets the threshold",
                        "evidence_ids": ["e1", "e2"],
                        "time_sensitive": True,
                    }
                ],
                "evidence": _good_evidence(now),
            },
            "engineering": {
                "problem": "Reduce component failure rate",
                "target": "Failure rate below 0.1%",
                "constraints": ["Existing production line"],
                "standards": ["Applicable standard to be verified"],
            },
            "acceptance": {
                "expected_disposition": "ANSWER",
                "minimum_evidence_gate_pass_rate": 1.0,
                "maximum_guarded_claims": 0,
                "require_engineering_ready": True,
            },
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["acceptance_passed"] is True
    run_id = body["run_id"]

    stored = client.get(f"/v1/pilot/runs/{run_id}", headers=HEADERS)
    assert stored.status_code == 200
    assert stored.json()["result"]["run_id"] == run_id


def test_negative_pilot_can_expect_abstention() -> None:
    response = client.post(
        "/v1/pilot/run",
        json={
            "scenario_id": "negative-evidence-case",
            "query": "Verify an intentionally unsupported claim",
            "verification": {
                "claims": [{"text": "Unsupported", "evidence_ids": []}],
                "evidence": [],
            },
            "acceptance": {
                "expected_disposition": "ABSTAIN_OR_QUALIFY",
                "minimum_evidence_gate_pass_rate": 0.0,
                "maximum_guarded_claims": 1,
                "require_engineering_ready": False,
            },
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["acceptance_passed"] is True


def test_audit_trail_contains_actions() -> None:
    response = client.get("/v1/audit/recent?limit=100", headers=HEADERS)
    assert response.status_code == 200
    actions = {row["action"] for row in response.json()}
    assert "verify" in actions
    assert "pilot_run" in actions


def test_rate_limit_is_enforced() -> None:
    original_limit = RATE_LIMITER.limit
    RATE_LIMITER.reset()
    RATE_LIMITER.limit = 2
    headers = {"X-API-Key": "other-secret", "X-Workspace-ID": "rate-limit-test"}
    try:
        assert client.post("/v1/plan", json={"query": "First request"}, headers=headers).status_code == 200
        assert client.post("/v1/plan", json={"query": "Second request"}, headers=headers).status_code == 200
        third = client.post("/v1/plan", json={"query": "Third request"}, headers=headers)
        assert third.status_code == 429
        assert "retry-after" in third.headers
    finally:
        RATE_LIMITER.limit = original_limit
        RATE_LIMITER.reset()
