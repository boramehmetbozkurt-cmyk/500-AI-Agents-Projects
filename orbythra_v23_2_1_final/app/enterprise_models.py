from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

ProviderFamily = Literal[
    "openai", "anthropic", "google", "azure_openai", "aws_bedrock",
    "vertex", "mistral", "self_hosted", "generic",
]
RiskTier = Literal["low", "moderate", "high", "critical"]
PolicyDecision = Literal["ALLOW", "REVIEW", "BLOCK"]


class ProviderProfile(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    family: ProviderFamily
    model_ids: list[str] = Field(default_factory=list, max_length=100)
    deployment_region: str = Field(min_length=2, max_length=80)
    data_residency: str = Field(min_length=2, max_length=80)
    base_url: HttpUrl | None = None
    api_version: str | None = Field(default=None, max_length=80)
    zero_retention_supported: bool = False
    private_endpoint_supported: bool = False
    customer_key_supported: bool = False
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    max_retries: int = Field(default=1, ge=0, le=5)
    circuit_breaker_threshold: int = Field(default=5, ge=1, le=50)
    circuit_breaker_cooldown_seconds: int = Field(default=30, ge=1, le=600)
    enabled: bool = True


class EnterprisePolicy(BaseModel):
    policy_id: str = Field(default="default", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    allowed_provider_ids: list[str] = Field(default_factory=list, max_length=100)
    allowed_regions: list[str] = Field(default_factory=list, max_length=100)
    prohibited_data_categories: list[str] = Field(default_factory=list, max_length=100)
    minimum_evidence_pass_rate: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_guarded_claims: int = Field(default=0, ge=0, le=1000)
    maximum_retention_days: int = Field(default=365, ge=1, le=36500)
    human_approval_from_risk: RiskTier = "high"
    require_zero_retention_from_risk: RiskTier = "high"
    require_private_endpoint_from_risk: RiskTier = "critical"
    require_customer_key_from_risk: RiskTier = "critical"


class PolicyEvaluationRequest(BaseModel):
    policy_id: str = Field(default="default", min_length=1, max_length=80)
    provider_id: str = Field(min_length=1, max_length=80)
    risk_tier: RiskTier
    data_categories: list[str] = Field(default_factory=list, max_length=100)
    evidence_pass_rate: float = Field(ge=0.0, le=1.0)
    guarded_claims: int = Field(ge=0, le=1000)
    retention_days: int = Field(ge=0, le=36500)
    human_approved: bool = False


class PolicyEvaluationResponse(BaseModel):
    decision: PolicyDecision
    reasons: list[str]
    provider_id: str
    risk_tier: RiskTier


class ModelMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class ModelInvocationRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=160)
    messages: list[ModelMessage] = Field(min_length=1, max_length=200)
    policy_id: str = Field(default="default", min_length=1, max_length=80)
    risk_tier: RiskTier = "moderate"
    data_categories: list[str] = Field(default_factory=list, max_length=100)
    evidence_pass_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    guarded_claims: int = Field(default=0, ge=0, le=1000)
    retention_days: int = Field(default=0, ge=0, le=36500)
    human_approved: bool = False
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class ModelInvocationResponse(BaseModel):
    provider_id: str
    model_id: str
    policy_decision: PolicyDecision
    text: str
    request_reference: str
    latency_ms: float


class BenchmarkScenario(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=160)
    expected_disposition: Literal["ANSWER", "ABSTAIN_OR_QUALIFY"]
    actual_disposition: Literal["ANSWER", "ABSTAIN_OR_QUALIFY"]
    evidence_pass_rate: float = Field(ge=0.0, le=1.0)
    guarded_claims: int = Field(ge=0, le=1000)
    traceable: bool
    latency_ms: float = Field(ge=0.0, le=3_600_000)


class BenchmarkRunRequest(BaseModel):
    benchmark_name: str = Field(min_length=1, max_length=160)
    model_label: str = Field(min_length=1, max_length=160)
    scenarios: list[BenchmarkScenario] = Field(min_length=1, max_length=5000)
    minimum_disposition_accuracy: float = Field(default=0.95, ge=0.0, le=1.0)
    minimum_traceability_rate: float = Field(default=0.95, ge=0.0, le=1.0)
    minimum_mean_evidence_pass_rate: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_p95_latency_ms: float = Field(default=5000.0, ge=1.0, le=3_600_000)


class BenchmarkRunResponse(BaseModel):
    run_id: str
    benchmark_name: str
    model_label: str
    scenario_count: int
    disposition_accuracy: float
    traceability_rate: float
    mean_evidence_pass_rate: float
    guarded_claim_rate: float
    p95_latency_ms: float
    acceptance_passed: bool
    failures: list[str]
    created_at: int


class UsageEventRequest(BaseModel):
    event_type: Literal["verification", "pilot", "benchmark", "crypto", "engineering", "privacy", "model_inference"]
    units: int = Field(default=1, ge=1, le=1_000_000)
    request_reference: str | None = Field(default=None, max_length=160)


class UsageReport(BaseModel):
    workspace_id: str
    total_events: int
    total_units: int
    by_type: dict[str, int]
    generated_at: int


class IdentityLifecycleRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    active: bool = True
    role_override: Literal["admin", "operator", "evaluator", "viewer"] | None = None
    display_name: str | None = Field(default=None, max_length=200)


class IdentityLifecycleResponse(BaseModel):
    subject: str
    active: bool
    role_override: str | None = None
    display_name: str | None = None
    updated_at: int


class PolicyRevisionResponse(BaseModel):
    policy_id: str
    revision: int
    sha256: str
    policy: EnterprisePolicy
    created_at: int


class ProductionReadinessResponse(BaseModel):
    status: Literal["READY", "NOT_READY"]
    checks: dict[str, bool]
    blockers: list[str]
    claim: str


class EnterpriseReadinessResponse(BaseModel):
    internal_status: str
    internal_controls: list[str]
    external_gates: dict[str, str]
    claim: str

    @field_validator("internal_status")
    @classmethod
    def preserve_v06_contract(cls, value: str) -> str:
        if value == "PRODUCTION_HARDENING_BASELINE":
            return "ENTERPRISE_SCALE_BASELINE"
        return value
