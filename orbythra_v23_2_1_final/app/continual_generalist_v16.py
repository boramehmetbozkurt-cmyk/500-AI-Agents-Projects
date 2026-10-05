from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agent_store import AGENT_STORE
from app.autonomy_models import SkillDefinition
from app.autonomy_store import AUTONOMY_STORE
from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v16/continual", tags=["v16-continual-generalist"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class SkillExperience(BaseModel):
    task_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    skill_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    domain: str = Field(min_length=1, max_length=120)
    success: bool
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    regression_safe: bool
    novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list, max_length=100)


class SkillPromotionPolicy(BaseModel):
    minimum_observations: int = Field(default=5, ge=3, le=10000)
    minimum_domains: int = Field(default=2, ge=2, le=100)
    minimum_success_rate: float = Field(default=0.80, ge=0.0, le=1.0)
    minimum_evidence_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    minimum_regression_safe_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_high_novelty_successes: int = Field(default=1, ge=0, le=10000)
    high_novelty_threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class SkillPromotionDecision(BaseModel):
    skill_id: str
    eligible: bool
    observations: int
    domains: list[str]
    success_rate: float
    mean_evidence_coverage: float
    mean_confidence: float
    regression_safe_rate: float
    high_novelty_successes: int
    reasons: list[str]
    decision_sha256: str


class SkillPromotionRequest(BaseModel):
    skill: SkillDefinition
    policy: SkillPromotionPolicy = Field(default_factory=SkillPromotionPolicy)


class SkillCurriculumRequest(BaseModel):
    target_domains: list[str] = Field(min_length=1, max_length=100)
    minimum_observations_per_domain: int = Field(default=3, ge=1, le=1000)
    target_success_rate: float = Field(default=0.80, ge=0.0, le=1.0)
    target_evidence_coverage: float = Field(default=0.80, ge=0.0, le=1.0)


class SkillCurriculumTask(BaseModel):
    domain: str
    priority: float
    reason_codes: list[str]
    recommended_novelty: float
    existing_observations: int
    success_rate: float
    mean_evidence_coverage: float


class SkillCurriculumPlan(BaseModel):
    skill_id: str
    tasks: list[SkillCurriculumTask]
    covered_domains: list[str]
    gap_domains: list[str]
    plan_sha256: str


class WorldFactCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    predicate: str = Field(min_length=1, max_length=160)
    value: Any
    domain: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    observed_at: int | None = Field(default=None, ge=0)
    valid_from: int | None = Field(default=None, ge=0)
    valid_to: int | None = Field(default=None, ge=0)


class WorldFact(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    value: Any
    domain: str
    confidence: float
    evidence_refs: list[str]
    observed_at: int
    valid_from: int | None
    valid_to: int | None
    value_sha256: str
    created_at: int


class WorldFactQuery(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    predicate: str | None = Field(default=None, max_length=160)
    domain: str | None = Field(default=None, max_length=120)
    valid_at: int | None = Field(default=None, ge=0)
    minimum_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=500)


class WorldFactQueryResult(BaseModel):
    facts: list[WorldFact]
    contradiction_detected: bool
    contradiction_groups: list[dict[str, Any]]


class WorldMemoryConsolidationRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    subject: str = Field(min_length=1, max_length=300)
    predicate: str = Field(min_length=1, max_length=160)
    domain: str | None = Field(default=None, max_length=120)
    valid_at: int | None = Field(default=None, ge=0)
    minimum_confidence: float = Field(default=0.80, ge=0.0, le=1.0)


class WorldMemoryConsolidationResponse(BaseModel):
    memory_id: str
    fact_id: str
    agent_id: str
    content_sha256: str
    confidence: float
    source_refs: list[str]


class ContinualGeneralistV16:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS continual_skill_experiences_v16(
                workspace_id TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                success INTEGER NOT NULL,
                evidence_coverage TEXT NOT NULL,
                confidence TEXT NOT NULL,
                regression_safe INTEGER NOT NULL,
                novelty TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,observation_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_continual_v16_skill ON continual_skill_experiences_v16(workspace_id,skill_id,created_at)"
            ))
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS world_facts_v16(
                workspace_id TEXT NOT NULL,
                fact_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                domain TEXT NOT NULL,
                value_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                confidence TEXT NOT NULL,
                observed_at BIGINT NOT NULL,
                valid_from BIGINT,
                valid_to BIGINT,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,fact_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_world_v16_lookup ON world_facts_v16(workspace_id,subject,predicate,domain,observed_at)"
            ))

    def record_experience(self, workspace_id: str, body: SkillExperience) -> dict[str, Any]:
        now = int(time.time())
        observation_id = "exp16_" + uuid.uuid4().hex[:24]
        payload = body.model_dump(mode="json")
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="continual-skill-v16")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO continual_skill_experiences_v16(
                workspace_id,observation_id,skill_id,task_id,domain,success,evidence_coverage,confidence,
                regression_safe,novelty,payload_json,created_at
                ) VALUES(:w,:id,:skill,:task,:domain,:success,:evidence,:confidence,:safe,:novelty,:payload,:created)"""
            ), {
                "w": workspace_id,
                "id": observation_id,
                "skill": body.skill_id,
                "task": body.task_id,
                "domain": body.domain,
                "success": int(body.success),
                "evidence": str(body.evidence_coverage),
                "confidence": str(body.confidence),
                "safe": int(body.regression_safe),
                "novelty": str(body.novelty),
                "payload": protected,
                "created": now,
            })
        return {"observation_id": observation_id, **payload, "created_at": now}

    def experiences(self, workspace_id: str, skill_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT payload_json,created_at,observation_id FROM continual_skill_experiences_v16 WHERE workspace_id=:w AND skill_id=:skill ORDER BY created_at,observation_id"
            ), {"w": workspace_id, "skill": skill_id}).mappings().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="continual-skill-v16")
            out.append({"observation_id": row["observation_id"], **payload, "created_at": int(row["created_at"])})
        return out

    def evaluate_promotion(self, workspace_id: str, skill_id: str, policy: SkillPromotionPolicy) -> SkillPromotionDecision:
        rows = self.experiences(workspace_id, skill_id)
        count = len(rows)
        domains = sorted({str(row["domain"]) for row in rows})
        successes = sum(bool(row["success"]) for row in rows)
        success_rate = successes / count if count else 0.0
        evidence = sum(float(row["evidence_coverage"]) for row in rows) / count if count else 0.0
        confidence = sum(float(row["confidence"]) for row in rows) / count if count else 0.0
        safe_rate = sum(bool(row["regression_safe"]) for row in rows) / count if count else 0.0
        high_novelty_successes = sum(
            bool(row["success"]) and float(row["novelty"]) >= policy.high_novelty_threshold
            for row in rows
        )
        reasons: list[str] = []
        if count < policy.minimum_observations:
            reasons.append("insufficient_observations")
        if len(domains) < policy.minimum_domains:
            reasons.append("insufficient_domain_transfer")
        if success_rate < policy.minimum_success_rate:
            reasons.append("success_rate_below_threshold")
        if evidence < policy.minimum_evidence_coverage:
            reasons.append("evidence_coverage_below_threshold")
        if safe_rate < policy.minimum_regression_safe_rate:
            reasons.append("regression_safety_below_threshold")
        if high_novelty_successes < policy.minimum_high_novelty_successes:
            reasons.append("insufficient_high_novelty_success")
        eligible = not reasons
        payload = {
            "skill_id": skill_id,
            "eligible": eligible,
            "observations": count,
            "domains": domains,
            "success_rate": round(success_rate, 6),
            "mean_evidence_coverage": round(evidence, 6),
            "mean_confidence": round(confidence, 6),
            "regression_safe_rate": round(safe_rate, 6),
            "high_novelty_successes": high_novelty_successes,
            "reasons": reasons or ["promotion_thresholds_satisfied"],
        }
        return SkillPromotionDecision(**payload, decision_sha256=_hash(payload))

    def build_curriculum(self, workspace_id: str, skill_id: str, body: SkillCurriculumRequest) -> SkillCurriculumPlan:
        rows = self.experiences(workspace_id, skill_id)
        by_domain: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_domain.setdefault(str(row["domain"]), []).append(row)

        tasks: list[SkillCurriculumTask] = []
        covered: list[str] = []
        gaps: list[str] = []
        for domain in sorted(set(body.target_domains)):
            domain_rows = by_domain.get(domain, [])
            count = len(domain_rows)
            success_rate = sum(bool(row["success"]) for row in domain_rows) / count if count else 0.0
            evidence = sum(float(row["evidence_coverage"]) for row in domain_rows) / count if count else 0.0
            reasons: list[str] = []
            if count < body.minimum_observations_per_domain:
                reasons.append("insufficient_domain_experience")
            if success_rate < body.target_success_rate:
                reasons.append("domain_success_below_target")
            if evidence < body.target_evidence_coverage:
                reasons.append("domain_evidence_below_target")
            if reasons:
                gaps.append(domain)
                experience_gap = max(0.0, (body.minimum_observations_per_domain - count) / body.minimum_observations_per_domain)
                success_gap = max(0.0, body.target_success_rate - success_rate)
                evidence_gap = max(0.0, body.target_evidence_coverage - evidence)
                priority = min(1.0, 0.45 * experience_gap + 0.35 * success_gap + 0.20 * evidence_gap + (0.15 if count == 0 else 0.0))
                recommended_novelty = 0.75 if count == 0 else (0.65 if success_rate >= 0.5 else 0.45)
                tasks.append(SkillCurriculumTask(
                    domain=domain,
                    priority=round(priority, 6),
                    reason_codes=reasons,
                    recommended_novelty=recommended_novelty,
                    existing_observations=count,
                    success_rate=round(success_rate, 6),
                    mean_evidence_coverage=round(evidence, 6),
                ))
            else:
                covered.append(domain)
        tasks.sort(key=lambda task: (-task.priority, task.domain))
        payload = {
            "skill_id": skill_id,
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "covered_domains": covered,
            "gap_domains": gaps,
        }
        return SkillCurriculumPlan(**payload, plan_sha256=_hash(payload))

    def add_fact(self, workspace_id: str, body: WorldFactCreate) -> WorldFact:
        now = int(time.time())
        observed_at = now if body.observed_at is None else body.observed_at
        if body.valid_from is not None and body.valid_to is not None and body.valid_to < body.valid_from:
            raise ValueError("world_fact_invalid_validity_interval")
        fact_id = "wf16_" + uuid.uuid4().hex[:24]
        value_sha = _hash(body.value)
        payload = body.model_dump(mode="json")
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="world-fact-v16")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO world_facts_v16(
                workspace_id,fact_id,subject,predicate,domain,value_sha256,payload_json,confidence,
                observed_at,valid_from,valid_to,created_at
                ) VALUES(:w,:id,:subject,:predicate,:domain,:value_sha,:payload,:confidence,:observed,:valid_from,:valid_to,:created)"""
            ), {
                "w": workspace_id,
                "id": fact_id,
                "subject": body.subject,
                "predicate": body.predicate,
                "domain": body.domain,
                "value_sha": value_sha,
                "payload": protected,
                "confidence": str(body.confidence),
                "observed": observed_at,
                "valid_from": body.valid_from,
                "valid_to": body.valid_to,
                "created": now,
            })
        return WorldFact(
            fact_id=fact_id,
            subject=body.subject,
            predicate=body.predicate,
            value=body.value,
            domain=body.domain,
            confidence=body.confidence,
            evidence_refs=body.evidence_refs,
            observed_at=observed_at,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            value_sha256=value_sha,
            created_at=now,
        )

    def query_facts(self, workspace_id: str, body: WorldFactQuery) -> WorldFactQueryResult:
        clauses = ["workspace_id=:w"]
        params: dict[str, Any] = {"w": workspace_id}
        if body.subject is not None:
            clauses.append("subject=:subject")
            params["subject"] = body.subject
        if body.predicate is not None:
            clauses.append("predicate=:predicate")
            params["predicate"] = body.predicate
        if body.domain is not None:
            clauses.append("domain=:domain")
            params["domain"] = body.domain
        query = "SELECT * FROM world_facts_v16 WHERE " + " AND ".join(clauses) + " ORDER BY observed_at DESC,created_at DESC"
        with self.engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        facts: list[WorldFact] = []
        for row in rows:
            confidence = float(row["confidence"])
            if confidence < body.minimum_confidence:
                continue
            valid_from = None if row["valid_from"] is None else int(row["valid_from"])
            valid_to = None if row["valid_to"] is None else int(row["valid_to"])
            if body.valid_at is not None:
                if valid_from is not None and body.valid_at < valid_from:
                    continue
                if valid_to is not None and body.valid_at > valid_to:
                    continue
            payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="world-fact-v16")
            facts.append(WorldFact(
                fact_id=row["fact_id"],
                subject=row["subject"],
                predicate=row["predicate"],
                value=payload["value"],
                domain=row["domain"],
                confidence=confidence,
                evidence_refs=payload["evidence_refs"],
                observed_at=int(row["observed_at"]),
                valid_from=valid_from,
                valid_to=valid_to,
                value_sha256=row["value_sha256"],
                created_at=int(row["created_at"]),
            ))
            if len(facts) >= body.limit:
                break
        groups: dict[tuple[str, str], set[str]] = {}
        for fact in facts:
            groups.setdefault((fact.subject, fact.predicate), set()).add(fact.value_sha256)
        contradictions = [
            {"subject": subject, "predicate": predicate, "distinct_value_count": len(values)}
            for (subject, predicate), values in sorted(groups.items())
            if len(values) > 1
        ]
        return WorldFactQueryResult(
            facts=facts,
            contradiction_detected=bool(contradictions),
            contradiction_groups=contradictions,
        )


    def consolidate_world_memory(self, workspace_id: str, body: WorldMemoryConsolidationRequest) -> WorldMemoryConsolidationResponse:
        result = self.query_facts(
            workspace_id,
            WorldFactQuery(
                subject=body.subject,
                predicate=body.predicate,
                domain=body.domain,
                valid_at=body.valid_at,
                minimum_confidence=body.minimum_confidence,
                limit=100,
            ),
        )
        if not result.facts:
            raise ValueError("world_fact_not_found")
        if result.contradiction_detected:
            raise ValueError("world_fact_contradiction_requires_review")
        selected = sorted(
            result.facts,
            key=lambda fact: (-fact.confidence, -fact.observed_at, fact.fact_id),
        )[0]
        memory = AUTONOMY_STORE.add_memory(
            workspace_id,
            {
                "agent_id": body.agent_id,
                "kind": "semantic",
                "content": {
                    "source": "world_model_v16",
                    "fact_id": selected.fact_id,
                    "subject": selected.subject,
                    "predicate": selected.predicate,
                    "value": selected.value,
                    "domain": selected.domain,
                    "observed_at": selected.observed_at,
                    "valid_from": selected.valid_from,
                    "valid_to": selected.valid_to,
                    "value_sha256": selected.value_sha256,
                },
                "tags": ["v16", "world-model", selected.domain, selected.subject, selected.predicate],
                "confidence": selected.confidence,
                "source_refs": [selected.fact_id, *selected.evidence_refs],
                "sensitivity": "confidential",
                "ttl_seconds": None,
            },
        )
        return WorldMemoryConsolidationResponse(
            memory_id=memory["memory_id"],
            fact_id=selected.fact_id,
            agent_id=body.agent_id,
            content_sha256=memory["content_sha256"],
            confidence=selected.confidence,
            source_refs=memory["source_refs"],
        )


CONTINUAL_V16 = ContinualGeneralistV16()


@router.post("/skills/experiences")
def record_skill_experience(
    body: SkillExperience,
    request: Request,
    principal: Principal = Depends(_REQUIRE_OPERATOR),
) -> dict[str, Any]:
    result = CONTINUAL_V16.record_experience(principal.workspace_id, body)
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result["observation_id"]),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="continual_v16_skill_experience",
        status="SUCCESS" if body.success else "FAILURE",
        metadata={"skill_id": body.skill_id, "domain": body.domain, "regression_safe": body.regression_safe},
    )
    return result


@router.post("/skills/{skill_id}/promotion", response_model=SkillPromotionDecision)
def evaluate_skill_promotion(
    skill_id: str,
    policy: SkillPromotionPolicy,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> SkillPromotionDecision:
    return CONTINUAL_V16.evaluate_promotion(principal.workspace_id, skill_id, policy)


@router.post("/skills/{skill_id}/curriculum", response_model=SkillCurriculumPlan)
def build_skill_curriculum(
    skill_id: str,
    body: SkillCurriculumRequest,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> SkillCurriculumPlan:
    return CONTINUAL_V16.build_curriculum(principal.workspace_id, skill_id, body)


@router.post("/skills/{skill_id}/promote", response_model=SkillDefinition)
def promote_skill(
    skill_id: str,
    body: SkillPromotionRequest,
    request: Request,
    principal: Principal = Depends(_REQUIRE_ADMIN),
) -> SkillDefinition:
    skill = body.skill
    if skill.skill_id != skill_id:
        raise HTTPException(status_code=400, detail="skill_id_mismatch")
    decision = CONTINUAL_V16.evaluate_promotion(principal.workspace_id, skill_id, body.policy)
    if not decision.eligible:
        raise HTTPException(status_code=409, detail={"code": "skill_promotion_not_eligible", "reasons": decision.reasons})
    for tool_id in skill.required_tool_ids:
        tool = AGENT_STORE.get_tool(principal.workspace_id, tool_id)
        if tool is None or not tool.get("enabled", True):
            raise HTTPException(status_code=400, detail=f"skill_tool_not_active:{tool_id}")
    AUTONOMY_STORE.upsert_skill(principal.workspace_id, skill.model_dump(mode="json"))
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", decision.decision_sha256),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="continual_v16_skill_promote",
        status="PROMOTED",
        metadata={"skill_id": skill_id, "decision_sha256": decision.decision_sha256, "domains": decision.domains},
    )
    return skill


@router.post("/world/facts", response_model=WorldFact)
def add_world_fact(
    body: WorldFactCreate,
    request: Request,
    principal: Principal = Depends(_REQUIRE_OPERATOR),
) -> WorldFact:
    try:
        result = CONTINUAL_V16.add_fact(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.fact_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="continual_v16_world_fact",
        status="RECORDED",
        metadata={"fact_id": result.fact_id, "domain": result.domain, "value_sha256": result.value_sha256},
    )
    return result


@router.post("/world/consolidate-memory", response_model=WorldMemoryConsolidationResponse)
def consolidate_world_memory(
    body: WorldMemoryConsolidationRequest,
    request: Request,
    principal: Principal = Depends(_REQUIRE_OPERATOR),
) -> WorldMemoryConsolidationResponse:
    agent = AGENT_STORE.get_agent(principal.workspace_id, body.agent_id)
    if agent is None or not agent.get("enabled", True):
        raise HTTPException(status_code=400, detail="autonomy_agent_not_active")
    try:
        result = CONTINUAL_V16.consolidate_world_memory(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "contradiction" in str(exc) else 404, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.memory_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="continual_v16_world_memory_consolidation",
        status="CONSOLIDATED",
        metadata={"memory_id": result.memory_id, "fact_id": result.fact_id, "agent_id": result.agent_id},
    )
    return result


@router.post("/world/query", response_model=WorldFactQueryResult)
def query_world_facts(
    body: WorldFactQuery,
    principal: Principal = Depends(_REQUIRE_EVALUATOR),
) -> WorldFactQueryResult:
    return CONTINUAL_V16.query_facts(principal.workspace_id, body)


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v16",
        "persistent_experience_memory": True,
        "cross_domain_skill_promotion": True,
        "regression_safe_learning_gate": True,
        "high_novelty_transfer_gate": True,
        "self_directed_curriculum_planning": True,
        "temporal_evidence_bound_world_model": True,
        "semantic_memory_consolidation": True,
        "contradiction_detection": True,
        "human_governed_skill_activation": True,
        "model_weight_learning": False,
        "live_agi_claim": False,
        "boundary": (
            "V16 adds governed continual skill acquisition and a temporal evidence-bound world model. "
            "It is a bounded generalist-control layer, not proof of AGI, consciousness, unrestricted self-improvement, "
            "or human-level general intelligence."
        ),
    }
