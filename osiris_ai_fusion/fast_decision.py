from __future__ import annotations

import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator

from config import get_settings

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|password|passwd|secret|access[_-]?token|private[_-]?key)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?<![A-Fa-f0-9])0x[A-Fa-f0-9]{64}(?![A-Fa-f0-9])"),
    re.compile(r"\b(?:seed|recovery|mnemonic)\s+(?:phrase|words?)?\s*[:=]\s*(?:[a-z]+\s+){7,23}[a-z]+\b", re.IGNORECASE),
)


def contains_secret_like(query: str) -> bool:
    """Fail closed before any user text is sent to an external decision service."""
    return any(pattern.search(query) for pattern in SECRET_PATTERNS)


class FastDecision(BaseModel):
    """Typed, advisory output from a System-One decision service.

    The service may narrow routing, but it cannot grant a capability. The caller
    must intersect ``selected_tools`` with its own deterministic allow-list and
    SEAL still authorizes execution immediately before any tool call.
    """

    action: Literal["allow", "deny", "escalate"] = "escalate"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_reasoning: bool = True
    needs_research: bool = True
    needs_code_agent: bool = False
    selected_tools: list[str] = Field(default_factory=list, max_length=24)
    reason: str = Field(default="", max_length=500)

    @field_validator("selected_tools")
    @classmethod
    def normalize_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(str(item).strip().lower() for item in value if str(item).strip()))


class FastDecisionResult(BaseModel):
    decision: FastDecision
    provider: str
    model: str
    used_remote: bool
    fallback_reason: str | None = None


def deterministic_decision(query: str, candidate_tools: list[str]) -> FastDecision:
    lowered = query.casefold()
    code_terms = ("code", "kod", "debug", "bug", "patch", "düzelt", "refactor")
    research_terms = (
        "araştır",
        "research",
        "latest",
        "güncel",
        "haber",
        "news",
        "kaynak",
        "source",
        "compare",
        "karşılaştır",
    )
    needs_code = any(term in lowered for term in code_terms)
    needs_research = "provider_federation" in candidate_tools or any(
        term in lowered for term in research_terms
    )
    return FastDecision(
        action="allow",
        confidence=1.0,
        risk_score=0.0,
        needs_reasoning=not needs_research or len(candidate_tools) > 1,
        needs_research=needs_research,
        needs_code_agent=needs_code,
        selected_tools=candidate_tools,
        reason="deterministic-read-only-fallback",
    )


class FastDecisionClient:
    """Vendor-neutral adapter for Jev or another typed decision endpoint.

    Contract: POST ``FAST_DECISION_PATH`` with the payload built below and
    return either a decision object directly or ``{"decision": {...}}``.
    No tool output, secrets, memory, or authorization token is sent.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.fast_decision_enabled
        self.base_url = settings.fast_decision_base_url
        self.path = settings.fast_decision_path
        self.api_key = settings.fast_decision_api_key
        self.model = settings.fast_decision_model
        self.timeout = settings.fast_decision_timeout_seconds

    async def decide(
        self,
        query: str,
        candidate_tools: list[str],
        scope: dict[str, Any],
    ) -> FastDecisionResult:
        fallback = deterministic_decision(query, candidate_tools)
        if not self.enabled:
            return FastDecisionResult(
                decision=fallback.model_copy(
                    update={"action": "escalate", "reason": "fast-decision-disabled"}
                ),
                provider="deterministic",
                model="osiris-fast-router-v1",
                used_remote=False,
                fallback_reason="disabled",
            )
        if contains_secret_like(query):
            return FastDecisionResult(
                decision=fallback.model_copy(
                    update={"action": "escalate", "reason": "secret-like-input-local-only"}
                ),
                provider="deterministic",
                model="osiris-fast-router-v1",
                used_remote=False,
                fallback_reason="secret-like-input",
            )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "candidate_tools": candidate_tools,
                "scope": {
                    key: scope[key]
                    for key in ("region", "time_range")
                    if key in scope and scope[key] is not None
                },
                "policy": {
                    "mode": "read_only",
                    "allowed_actions": ["allow", "deny", "escalate"],
                    "selected_tools_must_be_subset": True,
                },
            },
            "output_schema": FastDecision.model_json_schema(),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.post(
                    self.base_url + self.path,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                raw = response.json()
            decision = FastDecision.model_validate(raw.get("decision", raw))
            unknown = sorted(set(decision.selected_tools).difference(candidate_tools))
            if unknown:
                raise ValueError(f"decision service requested unauthorized tools: {unknown}")
            return FastDecisionResult(
                decision=decision,
                provider="fast-decision",
                model=self.model,
                used_remote=True,
            )
        except Exception as exc:
            return FastDecisionResult(
                decision=fallback.model_copy(
                    update={"action": "escalate", "reason": "fast-decision-unavailable"}
                ),
                provider="deterministic",
                model="osiris-fast-router-v1",
                used_remote=False,
                fallback_reason=type(exc).__name__,
            )
