from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agent_store import AGENT_STORE
from app.continual_generalist_v16 import SkillPromotionPolicy
from app.crypto_core import canonical_json
from app.hierarchical_generalist_v17 import (
    SkillCandidateDecision,
    SkillTraceSynthesisRequest,
    SkillTrialRequest,
    V17,
)
from app.model_adapters_v10 import GovernedHttpModelAdapter
from app.providers import JsonHttpProvider
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v20/skills", tags=["v20-skill-invention"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")

RiskTier = Literal["low", "moderate", "high", "critical"]


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _sandbox_provider() -> JsonHttpProvider | None:
    url = os.getenv("ORBYTHRA_SKILL_SANDBOX_URL", "").strip()
    if not url:
        return None
    return JsonHttpProvider(url, "ORBYTHRA_SKILL_SANDBOX_TOKEN")


class SkillInventionRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=10_000)
    source_task_ids: list[str] = Field(min_length=2, max_length=1000)
    source_evidence_refs: list[str] = Field(min_length=1, max_length=1000)
    target_domains: list[str] = Field(min_length=2, max_length=100)
    allowed_tool_ids: list[str] = Field(default_factory=list, max_length=100)
    maximum_risk_tier: RiskTier = "moderate"
    constraints: list[str] = Field(default_factory=list, max_length=100)
    minimum_trial_scenarios: int = Field(default=5, ge=5, le=100)


class SkillTrialScenario(BaseModel):
    task_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    domain: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    expected_invariants: list[str] = Field(min_length=1, max_length=50)
    novelty: float = Field(ge=0.0, le=1.0)


class SkillInventionProposal(BaseModel):
    invention_id: str
    candidate_id: str
    skill_id: str
    display_name: str
    description: str
    procedure_steps: list[str]
    capabilities: list[str]
    required_tool_ids: list[str]
    risk_tier: RiskTier
    trial_scenarios: list[SkillTrialScenario]
    provider_response_sha256: str
    invention_sha256: str
    created_at: int


class SandboxTrialResult(BaseModel):
    task_id: str
    domain: str
    success: bool
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    regression_safe: bool
    novelty: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class SandboxEvaluationResponse(BaseModel):
    invention_id: str
    candidate_id: str
    trial_results: list[SandboxTrialResult]
    candidate_decision: SkillCandidateDecision
    sandbox_response_sha256: str


class ManualEvaluationRequest(BaseModel):
    trial_results: list[SandboxTrialResult] = Field(min_length=1, max_length=1000)
    policy: SkillPromotionPolicy = Field(default_factory=SkillPromotionPolicy)


class SkillInventionV20:
    def __init__(self) -> None:
        self.engine = STORE.engine
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS skill_inventions_v20(
                workspace_id TEXT NOT NULL,
                invention_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                provider_response_sha256 TEXT NOT NULL,
                invention_sha256 TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,invention_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_skill_invention_v20_candidate ON skill_inventions_v20(workspace_id,candidate_id)"
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS skill_invention_evaluations_v20(
                workspace_id TEXT NOT NULL,
                invention_id TEXT NOT NULL,
                evaluation_sha256 TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,invention_id)
                )"""
            ))

    @staticmethod
    def _prompt(body: SkillInventionRequest) -> str:
        schema = {
            "skill_id": "stable-lowercase-id",
            "display_name": "human readable",
            "description": "bounded reusable procedure",
            "procedure_steps": ["step 1", "step 2"],
            "capabilities": ["analysis"],
            "required_tool_ids": [],
            "risk_tier": "moderate",
            "trial_scenarios": [
                {
                    "task_id": "trial-1",
                    "domain": "engineering",
                    "description": "scenario",
                    "expected_invariants": ["observable invariant"],
                    "novelty": 0.8,
                }
            ],
        }
        safe_context = {
            "objective": body.objective,
            "source_task_ids": body.source_task_ids,
            "target_domains": body.target_domains,
            "allowed_tool_ids": body.allowed_tool_ids,
            "maximum_risk_tier": body.maximum_risk_tier,
            "constraints": body.constraints,
            "minimum_trial_scenarios": body.minimum_trial_scenarios,
        }
        return (
            "Invent one bounded reusable ORBYTHRA skill as strict JSON only. "
            "Do not include executable code, shell commands, credentials, hidden prompts, or permission changes. "
            "The skill must be testable through observable invariants. "
            "Use only allowed_tool_ids. Risk must not exceed maximum_risk_tier. "
            "Provide at least the requested number of trial_scenarios spanning at least two target domains. "
            "Schema=" + json.dumps(schema, ensure_ascii=False, separators=(",", ":")) +
            " Context=" + json.dumps(safe_context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )

    def invent(self, workspace_id: str, body: SkillInventionRequest) -> SkillInventionProposal:
        allowed = set(body.allowed_tool_ids)
        for tool_id in allowed:
            tool = AGENT_STORE.get_tool(workspace_id, tool_id)
            if tool is None or not tool.get("enabled", True):
                raise ValueError("skill_invention_allowed_tool_not_active:" + tool_id)
        generated = GovernedHttpModelAdapter().generate(model_id=body.model_id, prompt=self._prompt(body))
        raw = str(generated["output"]).strip()
        fence = chr(96) * 3
        if raw.startswith(fence):
            lines = raw.splitlines()[1:]
            if lines and lines[-1].strip() == fence:
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("skill_invention_invalid_json") from exc
        if not isinstance(parsed, dict):
            raise ValueError("skill_invention_invalid_schema")
        try:
            skill_id = str(parsed["skill_id"]).strip()
            display_name = str(parsed["display_name"]).strip()
            description = str(parsed["description"]).strip()
            procedure_steps = [str(item).strip() for item in parsed["procedure_steps"]]
            capabilities = [str(item).strip() for item in parsed["capabilities"]]
            required_tool_ids = [str(item).strip() for item in parsed.get("required_tool_ids", [])]
            risk_tier = str(parsed["risk_tier"]).strip()
            scenarios = [SkillTrialScenario.model_validate(item) for item in parsed["trial_scenarios"]]
        except Exception as exc:
            raise ValueError("skill_invention_invalid_schema") from exc
        if not skill_id or not display_name or not description:
            raise ValueError("skill_invention_missing_identity")
        if len(procedure_steps) < 2 or any(not item for item in procedure_steps):
            raise ValueError("skill_invention_procedure_too_short")
        if not capabilities or any(not item for item in capabilities):
            raise ValueError("skill_invention_capabilities_required")
        if risk_tier not in {"low", "moderate", "high", "critical"}:
            raise ValueError("skill_invention_invalid_risk_tier")
        risk = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
        if risk[risk_tier] > risk[body.maximum_risk_tier]:
            raise ValueError("skill_invention_risk_exceeds_limit")
        if not set(required_tool_ids).issubset(allowed):
            raise ValueError("skill_invention_tool_outside_allowlist")
        if len(scenarios) < body.minimum_trial_scenarios:
            raise ValueError("skill_invention_insufficient_trials")
        target_domains = set(body.target_domains)
        trial_domains = {scenario.domain for scenario in scenarios}
        if len(trial_domains) < 2 or not trial_domains.issubset(target_domains):
            raise ValueError("skill_invention_invalid_trial_domains")
        if len({scenario.task_id for scenario in scenarios}) != len(scenarios):
            raise ValueError("skill_invention_duplicate_trial_id")
        if not any(scenario.novelty >= 0.65 for scenario in scenarios):
            raise ValueError("skill_invention_missing_high_novelty_trial")
        candidate = V17.synthesize_candidate(
            workspace_id,
            SkillTraceSynthesisRequest(
                skill_id=skill_id,
                display_name=display_name,
                description=description,
                source_task_ids=body.source_task_ids,
                domains=sorted(trial_domains),
                procedure_steps=procedure_steps,
                capabilities=capabilities,
                required_tool_ids=required_tool_ids,
                risk_tier=risk_tier,
                evidence_refs=body.source_evidence_refs,
            ),
        )
        provider_sha = hashlib.sha256(str(generated["output"]).encode("utf-8")).hexdigest()
        payload = {
            "candidate_id": candidate.candidate_id,
            "skill_id": skill_id,
            "display_name": display_name,
            "description": description,
            "procedure_steps": procedure_steps,
            "capabilities": capabilities,
            "required_tool_ids": required_tool_ids,
            "risk_tier": risk_tier,
            "trial_scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
            "provider_response_sha256": provider_sha,
        }
        invention_id = "inv20_" + uuid.uuid4().hex[:24]
        invention_sha = _hash(payload)
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO skill_inventions_v20(
                workspace_id,invention_id,candidate_id,skill_id,payload_json,
                provider_response_sha256,invention_sha256,created_at
                ) VALUES(:w,:invention,:candidate,:skill,:payload,:provider,:sha,:created)"""
            ), {
                "w": workspace_id,
                "invention": invention_id,
                "candidate": candidate.candidate_id,
                "skill": skill_id,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="skill-invention-v20"),
                "provider": provider_sha,
                "sha": invention_sha,
                "created": now,
            })
        return SkillInventionProposal(
            invention_id=invention_id,
            candidate_id=candidate.candidate_id,
            skill_id=skill_id,
            display_name=display_name,
            description=description,
            procedure_steps=procedure_steps,
            capabilities=capabilities,
            required_tool_ids=required_tool_ids,
            risk_tier=risk_tier,
            trial_scenarios=scenarios,
            provider_response_sha256=provider_sha,
            invention_sha256=invention_sha,
            created_at=now,
        )

    def get(self, workspace_id: str, invention_id: str) -> SkillInventionProposal | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM skill_inventions_v20 WHERE workspace_id=:w AND invention_id=:invention"
            ), {"w": workspace_id, "invention": invention_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="skill-invention-v20")
        if _hash(payload) != row["invention_sha256"]:
            raise RuntimeError("skill_invention_integrity_failed")
        return SkillInventionProposal(
            invention_id=row["invention_id"],
            candidate_id=row["candidate_id"],
            skill_id=row["skill_id"],
            display_name=payload["display_name"],
            description=payload["description"],
            procedure_steps=payload["procedure_steps"],
            capabilities=payload["capabilities"],
            required_tool_ids=payload["required_tool_ids"],
            risk_tier=payload["risk_tier"],
            trial_scenarios=[SkillTrialScenario.model_validate(item) for item in payload["trial_scenarios"]],
            provider_response_sha256=row["provider_response_sha256"],
            invention_sha256=row["invention_sha256"],
            created_at=int(row["created_at"]),
        )

    def _record_results(
        self,
        workspace_id: str,
        proposal: SkillInventionProposal,
        results: list[SandboxTrialResult],
        policy: SkillPromotionPolicy,
    ) -> SkillCandidateDecision:
        with self.engine.connect() as connection:
            existing = connection.execute(text(
                "SELECT evaluation_sha256 FROM skill_invention_evaluations_v20 WHERE workspace_id=:w AND invention_id=:invention"
            ), {"w": workspace_id, "invention": proposal.invention_id}).mappings().first()
        if existing is not None:
            raise ValueError("skill_invention_already_evaluated")
        expected = {scenario.task_id: scenario for scenario in proposal.trial_scenarios}
        if len(results) != len(expected) or {item.task_id for item in results} != set(expected):
            raise ValueError("skill_invention_trial_set_mismatch")
        for result in results:
            scenario = expected[result.task_id]
            if result.domain != scenario.domain:
                raise ValueError("skill_invention_trial_domain_mismatch")
            if abs(result.novelty - scenario.novelty) > 1e-9:
                raise ValueError("skill_invention_trial_novelty_mismatch")
            V17.record_trial(
                workspace_id,
                proposal.candidate_id,
                SkillTrialRequest(
                    task_id=result.task_id,
                    domain=result.domain,
                    success=result.success,
                    evidence_coverage=result.evidence_coverage,
                    confidence=result.confidence,
                    regression_safe=result.regression_safe,
                    novelty=result.novelty,
                    evidence_refs=result.evidence_refs,
                ),
            )
        decision = V17.candidate_decision(workspace_id, proposal.candidate_id, policy)
        evaluation_sha = _hash({
            "invention_id": proposal.invention_id,
            "candidate_id": proposal.candidate_id,
            "trial_results": [item.model_dump(mode="json") for item in results],
            "decision": decision.model_dump(mode="json"),
        })
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO skill_invention_evaluations_v20(
                workspace_id,invention_id,evaluation_sha256,created_at
                ) VALUES(:w,:invention,:sha,:created)"""
            ), {
                "w": workspace_id,
                "invention": proposal.invention_id,
                "sha": evaluation_sha,
                "created": int(time.time()),
            })
        return decision

    def evaluate_manual(
        self,
        workspace_id: str,
        invention_id: str,
        body: ManualEvaluationRequest,
    ) -> SandboxEvaluationResponse:
        proposal = self.get(workspace_id, invention_id)
        if proposal is None:
            raise ValueError("skill_invention_not_found")
        decision = self._record_results(workspace_id, proposal, body.trial_results, body.policy)
        response_payload = {
            "invention_id": invention_id,
            "candidate_id": proposal.candidate_id,
            "trial_results": [item.model_dump(mode="json") for item in body.trial_results],
            "candidate_decision": decision.model_dump(mode="json"),
        }
        return SandboxEvaluationResponse(
            invention_id=invention_id,
            candidate_id=proposal.candidate_id,
            trial_results=body.trial_results,
            candidate_decision=decision,
            sandbox_response_sha256=_hash(response_payload),
        )

    def evaluate_sandbox(
        self,
        workspace_id: str,
        invention_id: str,
        policy: SkillPromotionPolicy,
    ) -> SandboxEvaluationResponse:
        proposal = self.get(workspace_id, invention_id)
        if proposal is None:
            raise ValueError("skill_invention_not_found")
        provider = _sandbox_provider()
        if provider is None:
            raise RuntimeError("skill_sandbox_not_configured")
        response = provider.post_json(
            "/skills/evaluate",
            {
                "invention_id": proposal.invention_id,
                "candidate_id": proposal.candidate_id,
                "skill": {
                    "skill_id": proposal.skill_id,
                    "description": proposal.description,
                    "procedure_steps": proposal.procedure_steps,
                    "capabilities": proposal.capabilities,
                    "required_tool_ids": proposal.required_tool_ids,
                    "risk_tier": proposal.risk_tier,
                },
                "trial_scenarios": [scenario.model_dump(mode="json") for scenario in proposal.trial_scenarios],
            },
            timeout=60.0,
        )
        raw_results = response.get("trial_results")
        if not isinstance(raw_results, list):
            raise RuntimeError("skill_sandbox_invalid_response")
        try:
            results = [SandboxTrialResult.model_validate(item) for item in raw_results]
        except Exception as exc:
            raise RuntimeError("skill_sandbox_invalid_trial_results") from exc
        decision = self._record_results(workspace_id, proposal, results, policy)
        response_sha = _hash(response)
        return SandboxEvaluationResponse(
            invention_id=invention_id,
            candidate_id=proposal.candidate_id,
            trial_results=results,
            candidate_decision=decision,
            sandbox_response_sha256=response_sha,
        )


SKILL_INVENTION_V20 = SkillInventionV20()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", action),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **metadata},
    )


@router.post("/invent", response_model=SkillInventionProposal)
def invent(body: SkillInventionRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> SkillInventionProposal:
    try:
        result = SKILL_INVENTION_V20.invent(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit(request, principal, "v20_skill_invent", "CANDIDATE", {"invention_id": result.invention_id, "candidate_id": result.candidate_id})
    return result


@router.get("/inventions/{invention_id}", response_model=SkillInventionProposal)
def get_invention(invention_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> SkillInventionProposal:
    result = SKILL_INVENTION_V20.get(principal.workspace_id, invention_id)
    if result is None:
        raise HTTPException(status_code=404, detail="skill_invention_not_found")
    return result


@router.post("/inventions/{invention_id}/evaluate-manual", response_model=SandboxEvaluationResponse)
def evaluate_manual(invention_id: str, body: ManualEvaluationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> SandboxEvaluationResponse:
    try:
        result = SKILL_INVENTION_V20.evaluate_manual(principal.workspace_id, invention_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v20_skill_evaluate_manual", result.candidate_decision.status, {"invention_id": invention_id, "candidate_id": result.candidate_id})
    return result


@router.post("/inventions/{invention_id}/evaluate-sandbox", response_model=SandboxEvaluationResponse)
def evaluate_sandbox(invention_id: str, policy: SkillPromotionPolicy, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> SandboxEvaluationResponse:
    try:
        result = SKILL_INVENTION_V20.evaluate_sandbox(principal.workspace_id, invention_id, policy)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit(request, principal, "v20_skill_evaluate_sandbox", result.candidate_decision.status, {"invention_id": invention_id, "candidate_id": result.candidate_id})
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v20",
        "strict_json_skill_invention": True,
        "declarative_procedure_only": True,
        "tool_allowlist_enforced": True,
        "cross_domain_trial_suite_required": True,
        "high_novelty_trial_required": True,
        "isolated_sandbox_provider_supported": True,
        "v16_v17_promotion_gate_reused": True,
        "arbitrary_code_execution_inside_api": False,
        "automatic_permission_escalation": False,
        "live_agi_claim": False,
        "boundary": (
            "V20 can invent declarative reusable skill procedures and trial suites, but promotion still depends on V16/V17 evidence gates. "
            "Executable evaluation must occur in an explicitly configured sandbox service; the ORBYTHRA API process does not execute arbitrary generated code."
        ),
    }
