from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "enterprise-lab"}
OTHER = {"X-API-Key": "test-secret", "X-Workspace-ID": "enterprise-other"}
VIEWER = {"X-API-Key": "other-secret", "X-Workspace-ID": "enterprise-lab"}


def _provider(provider_id: str = "openai-primary", **overrides):
    body = {
        "provider_id": provider_id,
        "family": "openai",
        "model_ids": ["model-a"],
        "deployment_region": "eu-west",
        "data_residency": "eu-west",
        "zero_retention_supported": True,
        "private_endpoint_supported": True,
        "customer_key_supported": False,
        "enabled": True,
    }
    body.update(overrides)
    response = client.post("/v1/enterprise/providers", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _policy(policy_id: str = "default", **overrides):
    body = {
        "policy_id": policy_id,
        "allowed_provider_ids": ["openai-primary"],
        "allowed_regions": ["eu-west"],
        "prohibited_data_categories": ["biometric_raw"],
        "minimum_evidence_pass_rate": 0.90,
        "maximum_guarded_claims": 0,
        "maximum_retention_days": 90,
        "human_approval_from_risk": "high",
        "require_zero_retention_from_risk": "high",
        "require_private_endpoint_from_risk": "critical",
    }
    body.update(overrides)
    response = client.put(f"/v1/enterprise/policies/{policy_id}", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def test_provider_registry_is_admin_managed_and_workspace_scoped():
    provider_id = "provider-" + uuid.uuid4().hex[:8]
    response = client.post("/v1/enterprise/providers", json={"provider_id": provider_id, "family": "generic", "model_ids": [], "deployment_region": "eu-central", "data_residency": "eu-central", "enabled": True}, headers=VIEWER)
    assert response.status_code == 403
    _provider(provider_id)
    listed = client.get("/v1/enterprise/providers", headers=HEADERS)
    assert listed.status_code == 200
    assert any(item["provider_id"] == provider_id for item in listed.json())
    isolated = client.get("/v1/enterprise/providers", headers=OTHER)
    assert all(item["provider_id"] != provider_id for item in isolated.json())


def test_policy_allows_compliant_high_risk_use():
    _provider()
    _policy()
    response = client.post("/v1/enterprise/policy/evaluate", json={"policy_id": "default", "provider_id": "openai-primary", "risk_tier": "high", "data_categories": ["service_usage"], "evidence_pass_rate": 0.98, "guarded_claims": 0, "retention_days": 30, "human_approved": True}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "ALLOW"


def test_policy_routes_missing_human_approval_to_review():
    _provider()
    _policy()
    response = client.post("/v1/enterprise/policy/evaluate", json={"policy_id": "default", "provider_id": "openai-primary", "risk_tier": "high", "data_categories": [], "evidence_pass_rate": 0.95, "guarded_claims": 0, "retention_days": 30, "human_approved": False}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["decision"] == "REVIEW"
    assert "human_approval_required" in response.json()["reasons"]


def test_policy_blocks_prohibited_data_and_region():
    _provider("blocked-provider", deployment_region="us-east", data_residency="us-east")
    _policy("strict", allowed_provider_ids=["blocked-provider"])
    response = client.post("/v1/enterprise/policy/evaluate", json={"policy_id": "strict", "provider_id": "blocked-provider", "risk_tier": "moderate", "data_categories": ["biometric_raw"], "evidence_pass_rate": 1.0, "guarded_claims": 0, "retention_days": 30, "human_approved": True}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    text = " ".join(response.json()["reasons"])
    assert "prohibited_data_categories" in text
    assert "region_not_allowed" in text


def test_critical_risk_requires_private_endpoint_and_full_evidence():
    _provider("critical-provider", private_endpoint_supported=False)
    _policy("critical", allowed_provider_ids=["critical-provider"])
    response = client.post("/v1/enterprise/policy/evaluate", json={"policy_id": "critical", "provider_id": "critical-provider", "risk_tier": "critical", "data_categories": [], "evidence_pass_rate": 0.99, "guarded_claims": 0, "retention_days": 10, "human_approved": True}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    assert "private_endpoint_required" in response.json()["reasons"]
    assert "critical_risk_requires_full_evidence_gate" in response.json()["reasons"]


def test_benchmark_scorecard_passes_predeclared_thresholds():
    response = client.post("/v1/enterprise/benchmarks/run", json={"benchmark_name": "enterprise-gate", "model_label": "candidate-a", "scenarios": [{"scenario_id": "s1", "expected_disposition": "ANSWER", "actual_disposition": "ANSWER", "evidence_pass_rate": 1.0, "guarded_claims": 0, "traceable": True, "latency_ms": 100}, {"scenario_id": "s2", "expected_disposition": "ABSTAIN_OR_QUALIFY", "actual_disposition": "ABSTAIN_OR_QUALIFY", "evidence_pass_rate": 0.95, "guarded_claims": 1, "traceable": True, "latency_ms": 180}], "minimum_disposition_accuracy": 1.0, "minimum_traceability_rate": 1.0, "minimum_mean_evidence_pass_rate": 0.90, "maximum_p95_latency_ms": 250}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["acceptance_passed"] is True
    assert body["disposition_accuracy"] == 1.0
    fetched = client.get(f"/v1/enterprise/benchmarks/{body['run_id']}", headers=HEADERS)
    assert fetched.status_code == 200


def test_benchmark_fails_when_accuracy_or_latency_misses_threshold():
    response = client.post("/v1/enterprise/benchmarks/run", json={"benchmark_name": "negative-control", "model_label": "candidate-b", "scenarios": [{"scenario_id": "s1", "expected_disposition": "ANSWER", "actual_disposition": "ABSTAIN_OR_QUALIFY", "evidence_pass_rate": 0.5, "guarded_claims": 2, "traceable": False, "latency_ms": 8000}], "minimum_disposition_accuracy": 0.95, "minimum_traceability_rate": 0.95, "minimum_mean_evidence_pass_rate": 0.90, "maximum_p95_latency_ms": 1000}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["acceptance_passed"] is False
    assert len(body["failures"]) >= 3


def test_usage_metering_aggregates_billable_units_without_billing_claim():
    client.post("/v1/enterprise/usage/events", json={"event_type": "verification", "units": 3, "request_reference": "req-1"}, headers=HEADERS)
    client.post("/v1/enterprise/usage/events", json={"event_type": "benchmark", "units": 5, "request_reference": "req-2"}, headers=HEADERS)
    report = client.get("/v1/enterprise/usage/report", headers=HEADERS)
    assert report.status_code == 200
    body = report.json()
    assert body["total_units"] >= 8
    assert body["by_type"]["verification"] >= 3


def test_enterprise_readiness_keeps_external_gates_explicitly_pending():
    response = client.get("/v1/enterprise/readiness", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["internal_status"] == "ENTERPRISE_SCALE_BASELINE"
    assert body["external_gates"]["paid_enterprise_customers"] == "PENDING_COMMERCIAL_EXECUTION"
    assert body["external_gates"]["independent_security_assessment"] == "PENDING_EXTERNAL_PARTY"
    assert "does not claim" in body["claim"]
