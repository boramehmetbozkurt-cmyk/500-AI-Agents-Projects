from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.crypto_models import ApprovalProof
from app.enterprise_models import RiskTier

AgentDecision = Literal["ALLOW", "REVIEW", "BLOCK"]
AgentActionStatus = Literal[
    "AUTHORIZED", "REVIEW", "BLOCKED", "POLICY_REVOKED",
    "OUTCOME_VERIFIED", "OUTCOME_MISMATCH",
]
ToolProtocol = Literal["mcp", "http", "internal"]


class AgentProfile(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    model_provider_id: str | None = Field(default=None, max_length=80)
    model_id: str | None = Field(default=None, max_length=160)
    allowed_tool_ids: list[str] = Field(default_factory=list, max_length=200)
    max_risk_tier: RiskTier = "high"
    human_approval_from_risk: RiskTier = "high"
    signed_approval_from_risk: RiskTier = "critical"
    prohibited_data_categories: list[str] = Field(default_factory=list, max_length=100)
    max_actions_per_run: int = Field(default=50, ge=1, le=10_000)
    supervisor_agent_id: str | None = Field(default=None, max_length=100)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_supervisor(self) -> "AgentProfile":
        if self.supervisor_agent_id and self.supervisor_agent_id == self.agent_id:
            raise ValueError("agent_cannot_supervise_itself")
        return self


class ToolProfile(BaseModel):
    tool_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    protocol: ToolProtocol
    endpoint_url: HttpUrl | None = None
    mcp_server_name: str | None = Field(default=None, max_length=160)
    mcp_tool_name: str | None = Field(default=None, max_length=160)
    allowed_operations: list[str] = Field(min_length=1, max_length=200)
    risk_tier: RiskTier = "moderate"
    data_categories: list[str] = Field(default_factory=list, max_length=100)
    writes_state: bool = False
    requires_idempotency_key: bool = False
    max_input_bytes: int = Field(default=262_144, ge=1024, le=10_000_000)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_protocol(self) -> "ToolProfile":
        if self.protocol in {"mcp", "http"} and self.endpoint_url is None:
            raise ValueError("external_tool_endpoint_required")
        if self.protocol == "mcp" and not self.mcp_tool_name:
            raise ValueError("mcp_tool_name_required")
        if self.writes_state and not self.requires_idempotency_key:
            self.requires_idempotency_key = True
        return self


class AgentRunStartRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=20_000)
    supervisor_agent_id: str = Field(min_length=1, max_length=100)
    participant_agent_ids: list[str] = Field(min_length=1, max_length=50)
    max_actions: int = Field(default=100, ge=1, le=10_000)


class AgentRunResponse(BaseModel):
    run_id: str
    objective: str
    supervisor_agent_id: str
    participant_agent_ids: list[str]
    max_actions: int
    action_count: int
    status: Literal["ACTIVE", "HALTED", "COMPLETED"]
    created_at: int
    updated_at: int


class AgentActionRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    tool_id: str = Field(min_length=1, max_length=120)
    operation: str = Field(min_length=1, max_length=160)
    parameters: dict[str, Any] = Field(default_factory=dict)
    intended_effect: dict[str, Any] = Field(default_factory=dict)
    risk_tier: RiskTier = "moderate"
    data_categories: list[str] = Field(default_factory=list, max_length=100)
    run_id: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=200)
    human_approved: bool = False
    approvals: list[ApprovalProof] = Field(default_factory=list, max_length=10)
    authorization_ttl_seconds: int = Field(default=300, ge=30, le=3600)


class AgentAuthorizationRequest(BaseModel):
    human_approved: bool = True
    approvals: list[ApprovalProof] = Field(default_factory=list, max_length=10)
    authorization_ttl_seconds: int = Field(default=300, ge=30, le=3600)


class AgentActionResponse(BaseModel):
    action_id: str
    decision: AgentDecision
    status: AgentActionStatus
    reasons: list[str]
    intent_digest: str
    intended_effect_digest: str
    policy_snapshot_sha256: str
    authorization_envelope: dict[str, Any] | None = None
    created_at: int
    updated_at: int


class AgentExecutionCheckResponse(BaseModel):
    action_id: str
    executable: bool
    intent_digest: str
    policy_snapshot_sha256: str
    authorization_expires_at: int
    authorization_signer_verified: bool
    tool_id: str
    operation: str


class AgentOutcomeRequest(BaseModel):
    actual_effect: dict[str, Any]
    result: dict[str, Any] = Field(default_factory=dict)


class AgentOutcomeResponse(BaseModel):
    outcome_id: str
    action_id: str
    status: Literal["OUTCOME_VERIFIED", "OUTCOME_MISMATCH"]
    expected_effect_digest: str
    actual_effect_digest: str
    effect_match: bool
    signed_receipt: dict[str, Any]
    created_at: int


class AgentSupervisionResponse(BaseModel):
    run_id: str
    decision: Literal["PROCEED", "REVIEW", "HALT"]
    action_count: int
    status_counts: dict[str, int]
    reasons: list[str]
    policy_snapshot_sha256: str
