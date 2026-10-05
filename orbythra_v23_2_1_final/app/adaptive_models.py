from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.enterprise_models import RiskTier

LearningStatus = Literal["CANDIDATE", "ACTIVE", "ROLLED_BACK", "REJECTED"]


class WorldStateUpdateRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    domain: str = Field(min_length=1, max_length=120)
    state: dict[str, Any]
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class WorldStateRecord(BaseModel):
    agent_id: str
    domain: str
    revision: int
    state: dict[str, Any]
    evidence_refs: list[str]
    confidence: float
    state_sha256: str
    previous_sha256: str | None = None
    created_at: int


class LearningCandidateRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    source_domain: str = Field(min_length=1, max_length=120)
    capability: str = Field(min_length=1, max_length=160)
    procedure: dict[str, Any]
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    required_tool_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_tier: RiskTier = "moderate"
    baseline_score: float = Field(ge=0.0, le=1.0)
    candidate_score: float = Field(ge=0.0, le=1.0)
    minimum_improvement: float = Field(default=0.05, ge=0.0, le=1.0)


class LearningActivationRequest(BaseModel):
    human_approved: bool = False


class LearningRecord(BaseModel):
    learning_id: str
    revision: int
    status: LearningStatus
    agent_id: str
    source_domain: str
    capability: str
    procedure: dict[str, Any]
    evidence_refs: list[str]
    required_tool_ids: list[str]
    risk_tier: RiskTier
    baseline_score: float
    candidate_score: float
    minimum_improvement: float
    improvement: float
    derived_skill_id: str
    learning_sha256: str
    previous_sha256: str | None = None
    created_at: int


class TransferProposalRequest(BaseModel):
    learning_id: str = Field(min_length=1, max_length=100)
    target_domain: str = Field(min_length=1, max_length=120)
    target_capability: str = Field(min_length=1, max_length=160)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class TransferProposalResponse(BaseModel):
    transfer_id: str
    learning_id: str
    source_domain: str
    target_domain: str
    source_capability: str
    target_capability: str
    status: Literal["PROPOSED"]
    transfer_sha256: str
    boundary: str


class StrategyDefinition(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    domains: list[str] = Field(default_factory=list, max_length=100)
    capabilities: list[str] = Field(min_length=1, max_length=100)
    risk_tier: RiskTier = "moderate"
    provider_id: str | None = Field(default=None, max_length=120)
    success_score: float = Field(default=0.5, ge=0.0, le=1.0)
    latency_score: float = Field(default=0.5, ge=0.0, le=1.0)
    cost_score: float = Field(default=0.5, ge=0.0, le=1.0)
    enabled: bool = True


class MetaRouteRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=120)
    required_capabilities: list[str] = Field(min_length=1, max_length=100)
    max_risk_tier: RiskTier = "high"


class MetaRouteResponse(BaseModel):
    strategy_id: str
    provider_id: str | None
    utility_score: float
    reasons: list[str]
    routing_sha256: str


class AdaptiveReadinessResponse(BaseModel):
    version: str
    world_state_revisioning: bool
    gated_continual_learning: bool
    rollbackable_learning: bool
    cross_domain_transfer_proposals: bool
    derived_skill_acquisition: bool
    deterministic_meta_routing: bool
    v3_memory_and_missions_preserved: bool
    v2_execution_gate_required: bool
    model_weight_self_training: bool
    agi_claim: bool
    boundary: str
