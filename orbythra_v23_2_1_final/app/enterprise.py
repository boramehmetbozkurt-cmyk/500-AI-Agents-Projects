from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import SETTINGS
from app.enterprise_models import (
    BenchmarkRunRequest, BenchmarkRunResponse, EnterprisePolicy, EnterpriseReadinessResponse,
    IdentityLifecycleRequest, IdentityLifecycleResponse, ModelInvocationRequest, ModelInvocationResponse,
    PolicyEvaluationRequest, PolicyEvaluationResponse, PolicyRevisionResponse, ProductionReadinessResponse,
    ProviderProfile, UsageEventRequest, UsageReport,
)
from app.enterprise_store import ENTERPRISE_STORE
from app.provider_gateway import ProviderGatewayError, invoke_registered_model
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v1/enterprise", tags=["enterprise"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")
_RISK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object] | None = None) -> None:
    STORE.record_audit(request_id=getattr(request.state, "request_id", "enterprise"), principal_id=principal.principal_id, workspace_id=principal.workspace_id, action=action, status=status, metadata={"role": principal.role, **(metadata or {})})


def _at_or_above(actual: str, threshold: str) -> bool:
    return _RISK[actual] >= _RISK[threshold]


def evaluate_policy(policy: EnterprisePolicy, provider: ProviderProfile, body: PolicyEvaluationRequest) -> PolicyEvaluationResponse:
    blocks: list[str] = []
    reviews: list[str] = []
    if not provider.enabled:
        blocks.append("provider_disabled")
    if policy.allowed_provider_ids and provider.provider_id not in policy.allowed_provider_ids:
        blocks.append("provider_not_allowlisted")
    if policy.allowed_regions and provider.deployment_region not in policy.allowed_regions and provider.data_residency not in policy.allowed_regions:
        blocks.append("region_not_allowed")
    prohibited = sorted(set(body.data_categories) & set(policy.prohibited_data_categories))
    if prohibited:
        blocks.append("prohibited_data_categories:" + ",".join(prohibited))
    if body.retention_days > policy.maximum_retention_days:
        blocks.append("retention_exceeds_policy")
    if body.evidence_pass_rate < policy.minimum_evidence_pass_rate:
        reviews.append("evidence_pass_rate_below_policy")
    if body.guarded_claims > policy.maximum_guarded_claims:
        reviews.append("guarded_claims_above_policy")
    if _at_or_above(body.risk_tier, policy.human_approval_from_risk) and not body.human_approved:
        reviews.append("human_approval_required")
    if _at_or_above(body.risk_tier, policy.require_zero_retention_from_risk) and not provider.zero_retention_supported:
        blocks.append("zero_retention_required")
    if _at_or_above(body.risk_tier, policy.require_private_endpoint_from_risk) and not provider.private_endpoint_supported:
        blocks.append("private_endpoint_required")
    if _at_or_above(body.risk_tier, policy.require_customer_key_from_risk) and not provider.customer_key_supported:
        blocks.append("customer_managed_key_required")
    if body.risk_tier == "critical" and body.evidence_pass_rate < 1.0:
        reviews.append("critical_risk_requires_full_evidence_gate")
    if blocks:
        return PolicyEvaluationResponse(decision="BLOCK", reasons=blocks + reviews, provider_id=body.provider_id, risk_tier=body.risk_tier)
    if reviews:
        return PolicyEvaluationResponse(decision="REVIEW", reasons=reviews, provider_id=body.provider_id, risk_tier=body.risk_tier)
    return PolicyEvaluationResponse(decision="ALLOW", reasons=["policy_requirements_satisfied"], provider_id=body.provider_id, risk_tier=body.risk_tier)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return float(ordered[index])


@router.post("/providers", response_model=ProviderProfile)
def register_provider(body: ProviderProfile, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> ProviderProfile:
    ENTERPRISE_STORE.upsert_provider(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "enterprise_provider_upsert", "OK", {"provider_id": body.provider_id, "family": body.family})
    return body


@router.get("/providers", response_model=list[ProviderProfile])
def list_providers(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[ProviderProfile]:
    return [ProviderProfile(**item) for item in ENTERPRISE_STORE.list_providers(principal.workspace_id)]


@router.put("/policies/{policy_id}", response_model=EnterprisePolicy)
def put_policy(policy_id: str, body: EnterprisePolicy, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> EnterprisePolicy:
    if policy_id != body.policy_id:
        raise HTTPException(status_code=400, detail="policy_id_mismatch")
    stored = ENTERPRISE_STORE.upsert_policy(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "enterprise_policy_upsert", "OK", {"policy_id": body.policy_id, "revision": stored["revision"], "sha256": stored["sha256"]})
    return body


@router.get("/policies/{policy_id}", response_model=EnterprisePolicy)
def get_policy(policy_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> EnterprisePolicy:
    item = ENTERPRISE_STORE.get_policy(principal.workspace_id, policy_id)
    if item is None:
        raise HTTPException(status_code=404, detail="policy_not_found")
    return EnterprisePolicy(**item)


@router.get("/policies/{policy_id}/history", response_model=list[PolicyRevisionResponse])
def policy_history(policy_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[PolicyRevisionResponse]:
    return [PolicyRevisionResponse(**item) for item in ENTERPRISE_STORE.policy_history(principal.workspace_id, policy_id)]


@router.post("/policies/{policy_id}/activate/{revision}", response_model=EnterprisePolicy)
def policy_activate(policy_id: str, revision: int, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> EnterprisePolicy:
    item = ENTERPRISE_STORE.activate_policy_revision(principal.workspace_id, policy_id, revision)
    if item is None:
        raise HTTPException(status_code=404, detail="policy_revision_not_found")
    _audit(request, principal, "enterprise_policy_activate_revision", "OK", {"policy_id": policy_id, "revision": revision})
    return EnterprisePolicy(**item)


@router.put("/identities/{subject}", response_model=IdentityLifecycleResponse)
def identity_put(subject: str, body: IdentityLifecycleRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> IdentityLifecycleResponse:
    if subject != body.subject:
        raise HTTPException(status_code=400, detail="subject_mismatch")
    stored = ENTERPRISE_STORE.upsert_identity(principal.workspace_id, body.model_dump(mode="json"))
    _audit(request, principal, "enterprise_identity_upsert", "OK", {"subject": subject, "active": body.active, "role_override": body.role_override})
    return IdentityLifecycleResponse(**stored)


@router.get("/identities", response_model=list[IdentityLifecycleResponse])
def identity_list(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> list[IdentityLifecycleResponse]:
    return [IdentityLifecycleResponse(**item) for item in ENTERPRISE_STORE.list_identities(principal.workspace_id)]


@router.delete("/identities/{subject}", response_model=IdentityLifecycleResponse)
def identity_deactivate(subject: str, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> IdentityLifecycleResponse:
    existing = ENTERPRISE_STORE.get_identity(principal.workspace_id, subject)
    stored = ENTERPRISE_STORE.upsert_identity(principal.workspace_id, {"subject": subject, "active": False, "role_override": None if existing is None else existing.get("role_override"), "display_name": None if existing is None else existing.get("display_name")})
    _audit(request, principal, "enterprise_identity_deactivate", "OK", {"subject": subject})
    return IdentityLifecycleResponse(**stored)


@router.post("/policy/evaluate", response_model=PolicyEvaluationResponse)
def policy_evaluate(body: PolicyEvaluationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> PolicyEvaluationResponse:
    stored_policy = ENTERPRISE_STORE.get_policy(principal.workspace_id, body.policy_id)
    if stored_policy is None:
        raise HTTPException(status_code=404, detail="policy_not_found")
    stored_provider = ENTERPRISE_STORE.get_provider(principal.workspace_id, body.provider_id)
    if stored_provider is None:
        raise HTTPException(status_code=404, detail="provider_not_found")
    result = evaluate_policy(EnterprisePolicy(**stored_policy), ProviderProfile(**stored_provider), body)
    _audit(request, principal, "enterprise_policy_evaluate", result.decision, {"provider_id": body.provider_id, "risk_tier": body.risk_tier, "reasons": result.reasons})
    return result


@router.post("/models/invoke", response_model=ModelInvocationResponse)
def model_invoke(body: ModelInvocationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> ModelInvocationResponse:
    stored_policy = ENTERPRISE_STORE.get_policy(principal.workspace_id, body.policy_id)
    if stored_policy is None:
        raise HTTPException(status_code=404, detail="policy_not_found")
    stored_provider = ENTERPRISE_STORE.get_provider(principal.workspace_id, body.provider_id)
    if stored_provider is None:
        raise HTTPException(status_code=404, detail="provider_not_found")
    provider = ProviderProfile(**stored_provider)
    policy_input = PolicyEvaluationRequest(policy_id=body.policy_id, provider_id=body.provider_id, risk_tier=body.risk_tier, data_categories=body.data_categories, evidence_pass_rate=body.evidence_pass_rate, guarded_claims=body.guarded_claims, retention_days=body.retention_days, human_approved=body.human_approved)
    decision = evaluate_policy(EnterprisePolicy(**stored_policy), provider, policy_input)
    if decision.decision == "BLOCK":
        _audit(request, principal, "enterprise_model_invoke", "BLOCK", {"provider_id": body.provider_id, "model_id": body.model_id, "reasons": decision.reasons})
        raise HTTPException(status_code=403, detail={"policy_decision": "BLOCK", "reasons": decision.reasons})
    if decision.decision == "REVIEW":
        _audit(request, principal, "enterprise_model_invoke", "REVIEW", {"provider_id": body.provider_id, "model_id": body.model_id, "reasons": decision.reasons})
        raise HTTPException(status_code=409, detail={"policy_decision": "REVIEW", "reasons": decision.reasons})
    try:
        text, reference, latency_ms = invoke_registered_model(provider, body)
    except ProviderGatewayError as exc:
        status_code = 503 if str(exc) in {"provider_secret_not_configured", "provider_transport_error", "provider_dns_resolution_failed", "provider_circuit_open"} else 502
        _audit(request, principal, "enterprise_model_invoke", "PROVIDER_ERROR", {"provider_id": body.provider_id, "model_id": body.model_id, "error": str(exc)})
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    ENTERPRISE_STORE.record_usage(principal.workspace_id, "model_inference", 1, reference)
    _audit(request, principal, "enterprise_model_invoke", "ALLOW", {"provider_id": body.provider_id, "model_id": body.model_id, "request_reference": reference, "latency_ms": round(latency_ms, 3)})
    return ModelInvocationResponse(provider_id=body.provider_id, model_id=body.model_id, policy_decision="ALLOW", text=text, request_reference=reference, latency_ms=round(latency_ms, 3))


@router.post("/benchmarks/run", response_model=BenchmarkRunResponse)
def benchmark_run(body: BenchmarkRunRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> BenchmarkRunResponse:
    scenarios = body.scenarios
    count = len(scenarios)
    correct = sum(item.expected_disposition == item.actual_disposition for item in scenarios)
    traceable = sum(item.traceable for item in scenarios)
    evidence_mean = sum(item.evidence_pass_rate for item in scenarios) / count
    guarded_total = sum(item.guarded_claims for item in scenarios)
    p95 = _p95([item.latency_ms for item in scenarios])
    disposition_accuracy = correct / count
    traceability_rate = traceable / count
    guarded_claim_rate = guarded_total / count
    failures: list[str] = []
    if disposition_accuracy < body.minimum_disposition_accuracy:
        failures.append("disposition_accuracy_below_threshold")
    if traceability_rate < body.minimum_traceability_rate:
        failures.append("traceability_rate_below_threshold")
    if evidence_mean < body.minimum_mean_evidence_pass_rate:
        failures.append("mean_evidence_pass_rate_below_threshold")
    if p95 > body.maximum_p95_latency_ms:
        failures.append("p95_latency_above_threshold")
    stored = ENTERPRISE_STORE.save_benchmark(principal.workspace_id, {"benchmark_name": body.benchmark_name, "model_label": body.model_label, "scenario_count": count, "disposition_accuracy": round(disposition_accuracy, 6), "traceability_rate": round(traceability_rate, 6), "mean_evidence_pass_rate": round(evidence_mean, 6), "guarded_claim_rate": round(guarded_claim_rate, 6), "p95_latency_ms": round(p95, 3), "acceptance_passed": not failures, "failures": failures})
    _audit(request, principal, "enterprise_benchmark_run", "PASS" if not failures else "FAIL", {"run_id": stored["run_id"], "benchmark_name": body.benchmark_name, "model_label": body.model_label})
    return BenchmarkRunResponse(**stored)


@router.get("/benchmarks/{run_id}", response_model=BenchmarkRunResponse)
def benchmark_get(run_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> BenchmarkRunResponse:
    item = ENTERPRISE_STORE.get_benchmark(principal.workspace_id, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="benchmark_not_found")
    return BenchmarkRunResponse(**item)


@router.post("/usage/events")
def usage_event(body: UsageEventRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> dict[str, object]:
    event_id = ENTERPRISE_STORE.record_usage(principal.workspace_id, body.event_type, body.units, body.request_reference)
    _audit(request, principal, "enterprise_usage_event", "RECORDED", {"event_id": event_id, "event_type": body.event_type, "units": body.units})
    return {"event_id": event_id, "recorded": True}


@router.get("/usage/report", response_model=UsageReport)
def usage_report(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> UsageReport:
    return UsageReport(**ENTERPRISE_STORE.usage_report(principal.workspace_id))


@router.get("/production/readiness", response_model=ProductionReadinessResponse)
def production_readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ProductionReadinessResponse:
    providers = ENTERPRISE_STORE.list_providers(principal.workspace_id)
    checks = {
        "production_environment": SETTINGS.environment == "production",
        "postgresql_configured": bool(SETTINGS.database_url and SETTINGS.database_url.startswith(("postgresql://", "postgresql+"))),
        "authentication_configured": SETTINGS.auth_configured,
        "oidc_configured": SETTINGS.oidc_configured,
        "crypto_master_key_configured": SETTINGS.crypto_configured,
        "provider_registry_nonempty": bool(providers),
        "enabled_provider_urls_https": all((not item.get("enabled", True)) or str(item.get("base_url") or "").startswith("https://") for item in providers),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return ProductionReadinessResponse(status="READY" if not blockers else "NOT_READY", checks=checks, blockers=blockers, claim="Configuration readiness only; this does not prove uptime, external KMS custody, penetration-test approval or customer production use.")


@router.get("/readiness", response_model=EnterpriseReadinessResponse)
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> EnterpriseReadinessResponse:
    return EnterpriseReadinessResponse(
        internal_status="PRODUCTION_HARDENING_BASELINE",
        internal_controls=[
            "evidence-first verification", "pilot acceptance protocol", "RBAC and workspace isolation",
            "API-key and OIDC/JWT authentication", "identity lifecycle registry", "cryptographic trust layer",
            "GDPR-aligned privacy engineering", "provider registry", "governed multi-provider model gateway",
            "retry and circuit-breaker resilience", "risk policy engine", "immutable policy revision history",
            "benchmark scorecards", "usage metering", "audit trail", "security CI gates", "production runbook",
            "procurement documentation pack",
        ],
        external_gates={
            "enterprise_oidc_idp_configuration": "PENDING_DEPLOYMENT_CONFIGURATION",
            "independent_security_assessment": "PENDING_EXTERNAL_PARTY",
            "independent_product_validation": "PENDING_EXTERNAL_PARTY",
            "live_production_reference": "PENDING_DEPLOYMENT",
            "paid_enterprise_customers": "PENDING_COMMERCIAL_EXECUTION",
            "recurring_revenue": "PENDING_COMMERCIAL_EXECUTION",
            "soc2_or_iso27001_certification": "PENDING_FORMAL_AUDIT",
        },
        claim="Internal production-hardening controls are implemented; this endpoint does not claim certification, customer traction, revenue or independent validation.",
    )
