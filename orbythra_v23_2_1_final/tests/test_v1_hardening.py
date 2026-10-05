from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import app
from app.enterprise_models import EnterprisePolicy, ModelInvocationRequest, ModelMessage, PolicyEvaluationRequest, ProviderProfile
from app.enterprise import evaluate_policy
from app.provider_gateway import CIRCUIT_BREAKER, ProviderGatewayError, invoke_registered_model

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v1-hardening"}
OTHER = {"X-API-Key": "test-secret", "X-Workspace-ID": "v1-other"}


def _policy(policy_id: str, minimum: float) -> None:
    response = client.put(
        f"/v1/enterprise/policies/{policy_id}",
        json={
            "policy_id": policy_id,
            "allowed_provider_ids": [],
            "allowed_regions": [],
            "minimum_evidence_pass_rate": minimum,
            "maximum_guarded_claims": 0,
            "maximum_retention_days": 30,
            "human_approval_from_risk": "high",
            "require_zero_retention_from_risk": "high",
            "require_private_endpoint_from_risk": "critical",
            "require_customer_key_from_risk": "critical",
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text


def test_policy_revision_history_is_immutable_and_hash_addressed():
    policy_id = "rev-" + uuid.uuid4().hex[:8]
    _policy(policy_id, 0.90)
    _policy(policy_id, 0.95)
    history = client.get(f"/v1/enterprise/policies/{policy_id}/history", headers=HEADERS)
    assert history.status_code == 200
    rows = history.json()
    assert [row["revision"] for row in rows[:2]] == [2, 1]
    assert rows[0]["sha256"] != rows[1]["sha256"]
    assert len(rows[0]["sha256"]) == 64


def test_policy_can_activate_prior_revision():
    policy_id = "rollback-" + uuid.uuid4().hex[:8]
    _policy(policy_id, 0.80)
    _policy(policy_id, 0.99)
    activated = client.post(f"/v1/enterprise/policies/{policy_id}/activate/1", headers=HEADERS)
    assert activated.status_code == 200
    assert activated.json()["minimum_evidence_pass_rate"] == 0.80


def test_identity_lifecycle_is_workspace_scoped_and_deactivatable():
    subject = "user-" + uuid.uuid4().hex[:8]
    created = client.put(f"/v1/enterprise/identities/{subject}", json={"subject": subject, "active": True, "role_override": "evaluator", "display_name": "Evaluator"}, headers=HEADERS)
    assert created.status_code == 200
    listing = client.get("/v1/enterprise/identities", headers=HEADERS).json()
    assert any(row["subject"] == subject and row["active"] for row in listing)
    isolated = client.get("/v1/enterprise/identities", headers=OTHER).json()
    assert all(row["subject"] != subject for row in isolated)
    disabled = client.delete(f"/v1/enterprise/identities/{subject}", headers=HEADERS)
    assert disabled.status_code == 200
    assert disabled.json()["active"] is False


def test_production_readiness_fails_closed_in_test_configuration():
    response = client.get("/v1/enterprise/production/readiness", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_READY"
    assert "production_environment" in body["blockers"]
    assert "postgresql_configured" in body["blockers"]


def test_critical_risk_can_require_customer_managed_key():
    provider = ProviderProfile(provider_id="p", family="openai", model_ids=["m"], deployment_region="eu", data_residency="eu", base_url="https://api.example.test", zero_retention_supported=True, private_endpoint_supported=True, customer_key_supported=False)
    policy = EnterprisePolicy(policy_id="strict", require_customer_key_from_risk="critical")
    request = PolicyEvaluationRequest(policy_id="strict", provider_id="p", risk_tier="critical", evidence_pass_rate=1.0, guarded_claims=0, retention_days=0, human_approved=True)
    result = evaluate_policy(policy, provider, request)
    assert result.decision == "BLOCK"
    assert "customer_managed_key_required" in result.reasons


def test_circuit_breaker_opens_and_can_be_reset():
    CIRCUIT_BREAKER.reset()
    CIRCUIT_BREAKER.failure("p", threshold=2, cooldown_seconds=60, now=10.0)
    CIRCUIT_BREAKER.before_call("p", now=10.1)
    CIRCUIT_BREAKER.failure("p", threshold=2, cooldown_seconds=60, now=10.2)
    try:
        CIRCUIT_BREAKER.before_call("p", now=10.3)
    except ProviderGatewayError as exc:
        assert str(exc) == "provider_circuit_open"
    else:
        raise AssertionError("circuit should be open")
    CIRCUIT_BREAKER.reset()
    CIRCUIT_BREAKER.before_call("p", now=10.4)


def test_gateway_retries_transient_failure_then_succeeds(monkeypatch):
    CIRCUIT_BREAKER.reset()
    profile = ProviderProfile(provider_id="generic-retry", family="generic", model_ids=["m"], deployment_region="eu", data_residency="eu", base_url="https://api.example.test", max_retries=2, circuit_breaker_threshold=5)
    body = ModelInvocationRequest(provider_id="generic-retry", model_id="m", messages=[ModelMessage(role="user", content="hi")])
    calls = {"n": 0}
    def fake_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderGatewayError("provider_http_error:503")
        return {"choices": [{"message": {"content": "ok"}}]}
    monkeypatch.setattr("app.provider_gateway._post_json", fake_post)
    monkeypatch.setattr("app.provider_gateway.time.sleep", lambda *_: None)
    text, reference, latency = invoke_registered_model(profile, body)
    assert text == "ok"
    assert reference.startswith("inf_")
    assert latency >= 0
    assert calls["n"] == 2


def test_gateway_does_not_retry_nonretryable_response_error(monkeypatch):
    CIRCUIT_BREAKER.reset()
    profile = ProviderProfile(provider_id="generic-bad", family="generic", model_ids=["m"], deployment_region="eu", data_residency="eu", base_url="https://api.example.test", max_retries=3)
    body = ModelInvocationRequest(provider_id="generic-bad", model_id="m", messages=[ModelMessage(role="user", content="hi")])
    calls = {"n": 0}
    def fake_post(*args, **kwargs):
        calls["n"] += 1
        return {"unexpected": True}
    monkeypatch.setattr("app.provider_gateway._post_json", fake_post)
    try:
        invoke_registered_model(profile, body)
    except ProviderGatewayError as exc:
        assert str(exc) == "provider_response_text_not_found"
    else:
        raise AssertionError("expected provider response parse failure")
    assert calls["n"] == 1
