from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

QuestionType = Literal[
    "lookup",
    "briefing",
    "anomaly",
    "correlation",
    "comparison",
    "risk",
]


class InvestigationPlan(BaseModel):
    question_type: QuestionType = "briefing"
    region: str | None = None
    time_range: str | None = None
    tools: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = ""
    max_tool_calls: int = Field(default=8, ge=1, le=24)
    commercial_warnings: list[str] = Field(default_factory=list)

    @field_validator("tools")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))


class EvidenceRef(BaseModel):
    evidence_id: str
    tool: str
    source_url: str
    fetched_at: int
    ok: bool
    digest: str


class EvidenceItem(BaseModel):
    """One citable source, normalized out of any provider or AI-research payload.

    Providers and research engines each answer in their own shape; this is the
    single schema the answer layer, the UI and any consumer can rely on. Items
    that resolve to the same canonical URL are merged rather than repeated, so
    `corroboration` counts how many independent origins surfaced this source.
    """

    item_id: str
    title: str = Field(max_length=400)
    url: str | None = None
    domain: str | None = None
    snippet: str = Field(default="", max_length=1200)
    published_at: int | None = None
    tools: list[str] = Field(default_factory=list, max_length=24)
    providers: list[str] = Field(default_factory=list, max_length=24)
    evidence_ids: list[str] = Field(default_factory=list, max_length=24)
    corroboration: int = Field(default=1, ge=1)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    score_reasons: list[str] = Field(default_factory=list, max_length=8)


class Claim(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    kind: Literal["observation", "inference", "correlation"] = "observation"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list, max_length=24)


class MapMarker(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(max_length=300)
    tool: str | None = None
    evidence_id: str | None = None
    timestamp: str | int | None = None


class AnalysisReport(BaseModel):
    bluf: str = Field(min_length=1, max_length=4000)
    claims: list[Claim] = Field(default_factory=list, max_length=40)
    correlations: list[str] = Field(default_factory=list, max_length=20)
    data_gaps: list[str] = Field(default_factory=list, max_length=30)
    next_checks: list[str] = Field(default_factory=list, max_length=20)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = "tr"
    map_markers: list[MapMarker] = Field(default_factory=list, max_length=200)


class CorrelationCandidate(BaseModel):
    tools: list[str]
    distance_km: float | None = None
    time_delta_seconds: int | None = None
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class InvestigationScopeModel(BaseModel):
    region: str | None = Field(default=None, max_length=200)
    time_range: str | None = Field(default=None, max_length=100)
    case_id: str | None = Field(default=None, max_length=100)
    workspace_id: str = Field(default="default", max_length=100)


class InvestigationRequestModel(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    allowed_tools: list[str] | None = Field(default=None, max_length=12)
    scope: InvestigationScopeModel = Field(default_factory=InvestigationScopeModel)
    save: bool = True


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    workspace_id: str = Field(default="default", max_length=100)


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    query: str = Field(min_length=3, max_length=4000)
    workspace_id: str = Field(default="default", max_length=100)
    scope: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] | None = Field(default=None, max_length=12)
    cadence_seconds: int = Field(default=3600, ge=60, le=604800)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    enabled: bool = True
