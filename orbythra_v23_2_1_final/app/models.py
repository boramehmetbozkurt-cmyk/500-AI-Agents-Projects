from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class EvidenceItem(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    url: HttpUrl | None = None
    title: str | None = Field(default=None, max_length=500)
    support: float = Field(default=0.0, ge=0.0, le=1.0)
    authority: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    contradicts: bool = False


class Claim(BaseModel):
    id: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=12000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    time_sensitive: bool = False


class VerifyRequest(BaseModel):
    claims: list[Claim] = Field(min_length=1, max_length=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=500)
    minimum_support: float = Field(default=0.75, ge=0.0, le=1.0)
    minimum_authority: float = Field(default=0.60, ge=0.0, le=1.0)
    max_age_days: int = Field(default=30, ge=0, le=36500)


class ClaimVerdict(BaseModel):
    claim_id: str | None
    claim: str
    status: Literal[
        "SUPPORTED",
        "CONTRADICTED",
        "INSUFFICIENT_EVIDENCE",
        "STALE_EVIDENCE",
        "LOW_AUTHORITY",
    ]
    bound_evidence_ids: list[str]
    support: float
    authority: float
    reasons: list[str]


class VerifyResponse(BaseModel):
    total_claims: int
    supported_claims: int
    guarded_claims: int
    evidence_gate_pass_rate: float
    unsupported_or_guarded_rate: float
    disposition: Literal["ANSWER", "ABSTAIN_OR_QUALIFY"]
    verdicts: list[ClaimVerdict]


class PlanRequest(BaseModel):
    query: str = Field(min_length=3, max_length=12000)


class PlanResponse(BaseModel):
    complexity: int
    objectives: list[str]
    success_criteria: list[str]
    modes: list[str]
    requires_fresh_evidence: bool


class EngineeringRequest(BaseModel):
    problem: str = Field(min_length=3, max_length=12000)
    target: str | None = Field(default=None, max_length=2000)
    constraints: list[str] = Field(default_factory=list, max_length=64)
    standards: list[str] = Field(default_factory=list, max_length=32)


class EngineeringEnvelope(BaseModel):
    decision_status: Literal["READY_FOR_EVIDENCE", "NEEDS_MORE_INPUT"]
    problem: str
    target: str | None
    assumptions: list[str]
    unknowns: list[str]
    required_evidence: list[str]
    verification_plan: list[str]
    fmea_prompts: list[str]


class EvidenceSnapshotRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=500)


class EvidenceSnapshotResponse(BaseModel):
    snapshot_id: str
    workspace_id: str
    label: str | None
    evidence_count: int
    created_at: int


class PilotAcceptanceCriteria(BaseModel):
    expected_disposition: Literal["ANSWER", "ABSTAIN_OR_QUALIFY"] = "ANSWER"
    minimum_evidence_gate_pass_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    maximum_guarded_claims: int = Field(default=0, ge=0, le=100)
    require_engineering_ready: bool = False


class PilotRunRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=3, max_length=12000)
    verification: VerifyRequest
    engineering: EngineeringRequest | None = None
    acceptance: PilotAcceptanceCriteria = Field(default_factory=PilotAcceptanceCriteria)


class PilotRunResponse(BaseModel):
    run_id: str
    scenario_id: str
    acceptance_passed: bool
    acceptance_failures: list[str]
    plan: PlanResponse
    verification: VerifyResponse
    engineering: EngineeringEnvelope | None


class AuditEvent(BaseModel):
    event_id: str
    request_id: str
    principal_id: str
    workspace_id: str
    action: str
    status: str
    metadata: dict[str, object]
    created_at: int
