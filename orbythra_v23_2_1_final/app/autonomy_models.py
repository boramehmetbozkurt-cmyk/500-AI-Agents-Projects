from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.enterprise_models import RiskTier

MemoryKind = Literal["episodic", "semantic", "procedural", "evidence"]
MemorySensitivity = Literal["standard", "confidential", "restricted"]
MissionStatus = Literal["ACTIVE", "PAUSED", "COMPLETED", "FAILED"]
PlanStepKind = Literal["RETRIEVE_MEMORY", "APPLY_SKILL", "VERIFY_CRITERIA", "LEARN"]


class MemoryCreateRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    kind: MemoryKind
    content: dict[str, Any]
    tags: list[str] = Field(default_factory=list, max_length=50)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    ttl_seconds: int | None = Field(default=None, ge=60, le=31_536_000)
    sensitivity: MemorySensitivity = "standard"


class MemoryRecord(BaseModel):
    memory_id: str
    agent_id: str
    kind: MemoryKind
    content: dict[str, Any]
    tags: list[str]
    confidence: float
    source_refs: list[str]
    sensitivity: MemorySensitivity
    content_sha256: str
    created_at: int
    expires_at: int | None = None


class MemoryQuery(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    kinds: list[MemoryKind] = Field(default_factory=list, max_length=4)
    tags: list[str] = Field(default_factory=list, max_length=50)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=100)


class SkillDefinition(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1.0.0", min_length=1, max_length=40)
    description: str = Field(default="", max_length=2000)
    capabilities: list[str] = Field(min_length=1, max_length=100)
    required_tool_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_tier: RiskTier = "moderate"
    enabled: bool = True


class MissionCreateRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    objective: str = Field(min_length=1, max_length=20_000)
    success_criteria: list[str] = Field(min_length=1, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    risk_budget: RiskTier = "high"
    max_cycles: int = Field(default=12, ge=1, le=500)


class MissionRecord(BaseModel):
    mission_id: str
    agent_id: str
    objective: str
    success_criteria: list[str]
    constraints: list[str]
    required_capabilities: list[str]
    risk_budget: RiskTier
    max_cycles: int
    cycle_count: int
    status: MissionStatus
    plan_revision: int
    created_at: int
    updated_at: int


class PlanStep(BaseModel):
    step_id: str
    sequence: int
    kind: PlanStepKind
    capability: str | None = None
    skill_id: str | None = None
    required_tool_ids: list[str] = Field(default_factory=list)
    instruction: str


class MissionPlan(BaseModel):
    mission_id: str
    revision: int
    steps: list[PlanStep]
    selected_skill_ids: list[str]
    missing_capabilities: list[str]
    memory_context_ids: list[str]
    context_sha256: str
    plan_sha256: str
    created_at: int


class CycleEvaluationRequest(BaseModel):
    observations: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    criterion_results: dict[str, bool] = Field(default_factory=dict)
    action_ids: list[str] = Field(default_factory=list, max_length=100)
    write_memory: bool = True


class CycleEvaluationResponse(BaseModel):
    mission_id: str
    cycle: int
    status: MissionStatus
    criteria_satisfied: int
    criteria_total: int
    completion_ratio: float
    action_status_counts: dict[str, int]
    reasons: list[str]
    next_step: str
    memory_id: str | None = None
    evaluation_sha256: str


class DriftCheckResponse(BaseModel):
    mission_id: str
    drift_detected: bool
    stored_context_sha256: str
    current_context_sha256: str
    reasons: list[str]
    status: MissionStatus


class AutonomyReadinessResponse(BaseModel):
    version: str
    persistent_memory: bool
    skill_registry: bool
    deterministic_planner: bool
    criteria_self_evaluation: bool
    continuous_drift_check: bool
    v2_execution_gate_required: bool
    live_general_intelligence_claim: bool
    boundary: str
