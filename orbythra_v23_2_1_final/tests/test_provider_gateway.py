from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import app
from app.enterprise_models import ModelInvocationRequest, ModelMessage, ProviderProfile
from app.provider_gateway import prepare_provider_request, provider_secret_env

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "gateway-lab"}


def test_provider_secret_env_is_deterministic_and_safe():
    assert provider_secret_env("azure-openai.primary") == "ORBYTHRA_PROVIDER_AZURE_OPENAI_PRIMARY_TOKEN"


def test_openai_request_shape():
    profile = ProviderProfile(provider_id="oa", family="openai", model_ids=["gpt-x"], deployment_region="eu", data_residency="eu", base_url="https://api.example.test")
    body = ModelInvocationRequest(provider_id="oa", model_id="gpt-x", messages=[ModelMessage(role="user", content="hello")])
    prepared = prepare_provider_request(profile, body, "secret")
    assert prepared.url == "https://api.example.test/v1/chat/completions"
    assert prepared.headers["Authorization"] == "Bearer secret"
    assert prepared.payload["model"] == "gpt-x"


def test_anthropic_request_shape_moves_system_prompt():
    profile = ProviderProfile(provider_id="anth", family="anthropic", model_ids=["claude-x"], deployment_region="eu", data_residency="eu", base_url="https://api.example.test")
    body = ModelInvocationRequest(provider_id="anth", model_id="claude-x", messages=[ModelMessage(role="system", content="be precise"), ModelMessage(role="user", content="hello")])
    prepared = prepare_provider_request(profile, body, "secret")
    assert prepared.url.endswith("/v1/messages")
    assert prepared.headers["x-api-key"] == "secret"
    assert prepared.payload["system"] == "be precise"
    assert prepared.payload["messages"] == [{"role": "user", "content": "hello"}]


def test_google_request_shape():
    profile = ProviderProfile(provider_id="gem", family="google", model_ids=["gemini-x"], deployment_region="eu", data_residency="eu", base_url="https://generativelanguage.example.test")
    body = ModelInvocationRequest(provider_id="gem", model_id="gemini-x", messages=[ModelMessage(role="user", content="hello")])
    prepared = prepare_provider_request(profile, body, "secret")
    assert prepared.url.endswith("/v1beta/models/gemini-x:generateContent")
    assert prepared.headers["x-goog-api-key"] == "secret"
    assert prepared.payload["contents"][0]["parts"][0]["text"] == "hello"


def _register(provider_id: str, *, region: str = "eu-west", base_url: str = "https://api.example.test"):
    response = client.post("/v1/enterprise/providers", json={"provider_id": provider_id, "family": "openai", "model_ids": ["model-a"], "deployment_region": region, "data_residency": region, "base_url": base_url, "zero_retention_supported": True, "private_endpoint_supported": True, "enabled": True}, headers=HEADERS)
    assert response.status_code == 200, response.text


def _policy(provider_id: str, policy_id: str):
    response = client.put(f"/v1/enterprise/policies/{policy_id}", json={"policy_id": policy_id, "allowed_provider_ids": [provider_id], "allowed_regions": ["eu-west"], "prohibited_data_categories": ["raw_biometric"], "minimum_evidence_pass_rate": 0.9, "maximum_guarded_claims": 0, "maximum_retention_days": 30, "human_approval_from_risk": "high", "require_zero_retention_from_risk": "high", "require_private_endpoint_from_risk": "critical"}, headers=HEADERS)
    assert response.status_code == 200, response.text


def test_model_gateway_blocks_policy_violation_before_provider_call(monkeypatch):
    provider_id = "blocked-" + uuid.uuid4().hex[:8]
    policy_id = "policy-" + uuid.uuid4().hex[:8]
    _register(provider_id, region="us-east")
    _policy(provider_id, policy_id)
    called = {"value": False}
    def fake(*args, **kwargs):
        called["value"] = True
        return "should not run", "x", 1.0
    monkeypatch.setattr("app.enterprise.invoke_registered_model", fake)
    response = client.post("/v1/enterprise/models/invoke", json={"provider_id": provider_id, "model_id": "model-a", "messages": [{"role": "user", "content": "hello"}], "policy_id": policy_id, "risk_tier": "moderate", "evidence_pass_rate": 1.0, "guarded_claims": 0, "retention_days": 0}, headers=HEADERS)
    assert response.status_code == 403
    assert called["value"] is False


def test_model_gateway_routes_review_without_provider_call(monkeypatch):
    provider_id = "review-" + uuid.uuid4().hex[:8]
    policy_id = "policy-" + uuid.uuid4().hex[:8]
    _register(provider_id)
    _policy(provider_id, policy_id)
    called = {"value": False}
    monkeypatch.setattr("app.enterprise.invoke_registered_model", lambda *args, **kwargs: called.__setitem__("value", True))
    response = client.post("/v1/enterprise/models/invoke", json={"provider_id": provider_id, "model_id": "model-a", "messages": [{"role": "user", "content": "hello"}], "policy_id": policy_id, "risk_tier": "high", "evidence_pass_rate": 1.0, "guarded_claims": 0, "retention_days": 0, "human_approved": False}, headers=HEADERS)
    assert response.status_code == 409
    assert called["value"] is False


def test_model_gateway_allow_records_usage(monkeypatch):
    provider_id = "allow-" + uuid.uuid4().hex[:8]
    policy_id = "policy-" + uuid.uuid4().hex[:8]
    _register(provider_id)
    _policy(provider_id, policy_id)
    monkeypatch.setattr("app.enterprise.invoke_registered_model", lambda *args, **kwargs: ("verified model output", "inf_test123", 12.5))
    response = client.post("/v1/enterprise/models/invoke", json={"provider_id": provider_id, "model_id": "model-a", "messages": [{"role": "user", "content": "hello"}], "policy_id": policy_id, "risk_tier": "moderate", "evidence_pass_rate": 1.0, "guarded_claims": 0, "retention_days": 0, "human_approved": False}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["policy_decision"] == "ALLOW"
    assert body["text"] == "verified model output"
    report = client.get("/v1/enterprise/usage/report", headers=HEADERS).json()
    assert report["by_type"]["model_inference"] >= 1
