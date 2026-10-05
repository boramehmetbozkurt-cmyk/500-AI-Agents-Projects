from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.enterprise_store import ENTERPRISE_STORE
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v18/adaptation", tags=["v18-governed-model-adaptation"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")

AdaptationKind = Literal["lora", "adapter", "prompt_tuning", "routing_policy"]
RiskTier = Literal["low", "moderate", "high", "critical"]
AdaptationStatus = Literal["PLANNED", "CANDIDATE", "BENCHMARKED", "CANARY", "ACTIVE", "ROLLED_BACK", "REJECTED"]


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class DatasetManifest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._-]+$")
    purpose: str = Field(min_length=1, max_length=1000)
    sample_count: int = Field(ge=1, le=1_000_000_000)
    train_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_refs: list[str] = Field(min_length=1, max_length=1000)
    license_refs: list[str] = Field(default_factory=list, max_length=100)
    pii_reviewed: bool
    holdout_locked: bool = True


class AdaptationPlanCreate(BaseModel):
    route_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    provider_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    base_model_id: str = Field(min_length=1, max_length=160)
    adaptation_kind: AdaptationKind
    dataset: DatasetManifest
    target_capabilities: list[str] = Field(min_length=1, max_length=100)
    risk_tier: RiskTier = "moderate"
    minimum_quality_improvement: float = Field(default=0.01, ge=0.0, le=1.0)
    maximum_metric_regression: float = Field(default=0.005, ge=0.0, le=0.25)
    maximum_latency_regression_fraction: float = Field(default=0.20, ge=0.0, le=5.0)
    maximum_canary_error_rate: float = Field(default=0.02, ge=0.0, le=1.0)
    maximum_canary_quality_failure_rate: float = Field(default=0.05, ge=0.0, le=1.0)


class AdaptationPlan(BaseModel):
    plan_id: str
    route_id: str
    provider_id: str
    base_model_id: str
    adaptation_kind: AdaptationKind
    dataset: DatasetManifest
    target_capabilities: list[str]
    risk_tier: RiskTier
    minimum_quality_improvement: float
    maximum_metric_regression: float
    maximum_latency_regression_fraction: float
    maximum_canary_error_rate: float
    maximum_canary_quality_failure_rate: float
    status: AdaptationStatus
    created_at: int
    updated_at: int


class CandidateArtifactRegister(BaseModel):
    adapter_model_id: str = Field(min_length=1, max_length=160)
    training_run_ref: str = Field(min_length=1, max_length=500)
    trainer_name: str = Field(min_length=1, max_length=200)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_size_bytes: int = Field(ge=1, le=10_000_000_000_000)
    trainer_attestation_refs: list[str] = Field(min_length=1, max_length=100)
    base_model_fingerprint: str = Field(min_length=8, max_length=500)


class AdaptationCandidate(BaseModel):
    candidate_id: str
    plan_id: str
    adapter_model_id: str
    training_run_ref: str
    trainer_name: str
    artifact_sha256: str
    training_config_sha256: str
    artifact_size_bytes: int
    trainer_attestation_refs: list[str]
    base_model_fingerprint: str
    status: AdaptationStatus
    created_at: int
    updated_at: int


class BenchmarkPair(BaseModel):
    baseline_run_id: str = Field(min_length=1, max_length=160)
    candidate_run_id: str = Field(min_length=1, max_length=160)


class BenchmarkComparisonRequest(BaseModel):
    pairs: list[BenchmarkPair] = Field(min_length=1, max_length=100)


class BenchmarkMetricDelta(BaseModel):
    benchmark_name: str
    disposition_accuracy_delta: float
    traceability_rate_delta: float
    evidence_pass_rate_delta: float
    guarded_claim_rate_delta: float
    latency_regression_fraction: float
    passed: bool
    reasons: list[str]


class AdaptationBenchmarkDecision(BaseModel):
    candidate_id: str
    eligible: bool
    baseline_quality_score: float
    candidate_quality_score: float
    quality_improvement: float
    metric_deltas: list[BenchmarkMetricDelta]
    reasons: list[str]
    decision_sha256: str


class CanaryObservationRequest(BaseModel):
    target_rollout_percent: Literal[5, 25, 50, 100]
    request_count: int = Field(ge=100, le=1_000_000_000)
    error_rate: float = Field(ge=0.0, le=1.0)
    quality_failure_rate: float = Field(ge=0.0, le=1.0)
    p95_latency_ms: float = Field(ge=0.0, le=3_600_000)
    baseline_p95_latency_ms: float = Field(gt=0.0, le=3_600_000)
    regression_detected: bool = False
    evidence_refs: list[str] = Field(min_length=1, max_length=500)


class CanaryDecision(BaseModel):
    candidate_id: str
    route_id: str
    rollout_percent: int
    status: AdaptationStatus
    passed: bool
    reasons: list[str]
    observation_sha256: str


class RouteResolutionRequest(BaseModel):
    request_key: str = Field(min_length=1, max_length=500)


class RouteResolution(BaseModel):
    route_id: str
    request_key_sha256: str
    rollout_percent: int
    selected_model_id: str
    base_model_id: str
    candidate_model_id: str | None
    candidate_selected: bool
    route_sha256: str


class GovernedAdaptationV18:
    def __init__(self) -> None:
        self.engine = STORE.engine
        self._init_tables()

    def _init_tables(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS adaptation_plans_v18(
            workspace_id TEXT NOT NULL, plan_id TEXT NOT NULL, route_id TEXT NOT NULL, provider_id TEXT NOT NULL,
            base_model_id TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,plan_id))""",
            "CREATE INDEX IF NOT EXISTS idx_adaptation_plan_route_v18 ON adaptation_plans_v18(workspace_id,route_id,created_at)",
            """CREATE TABLE IF NOT EXISTS adaptation_candidates_v18(
            workspace_id TEXT NOT NULL, candidate_id TEXT NOT NULL, plan_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, status TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
            PRIMARY KEY(workspace_id,candidate_id))""",
            """CREATE TABLE IF NOT EXISTS adaptation_benchmarks_v18(
            workspace_id TEXT NOT NULL, decision_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, decision_sha256 TEXT NOT NULL, created_at BIGINT NOT NULL,
            PRIMARY KEY(workspace_id,decision_id))""",
            """CREATE TABLE IF NOT EXISTS adaptation_canary_v18(
            workspace_id TEXT NOT NULL, observation_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
            rollout_percent BIGINT NOT NULL, payload_json TEXT NOT NULL, observation_sha256 TEXT NOT NULL,
            created_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,observation_id))""",
            """CREATE TABLE IF NOT EXISTS adaptation_routes_v18(
            workspace_id TEXT NOT NULL, route_id TEXT NOT NULL, provider_id TEXT NOT NULL, base_model_id TEXT NOT NULL,
            candidate_id TEXT, candidate_model_id TEXT, rollout_percent BIGINT NOT NULL, previous_model_id TEXT,
            updated_at BIGINT NOT NULL, PRIMARY KEY(workspace_id,route_id))""",
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def create_plan(self, workspace_id: str, body: AdaptationPlanCreate) -> AdaptationPlan:
        provider = ENTERPRISE_STORE.get_provider(workspace_id, body.provider_id)
        if provider is None or not provider.get("enabled", True):
            raise ValueError("adaptation_provider_not_active")
        provider_models = set(provider.get("model_ids", []))
        if provider_models and body.base_model_id not in provider_models:
            raise ValueError("adaptation_base_model_not_registered")
        if not body.dataset.holdout_locked:
            raise ValueError("adaptation_holdout_must_be_locked")
        if not body.dataset.pii_reviewed:
            raise ValueError("adaptation_dataset_pii_review_required")
        if len({body.dataset.train_sha256, body.dataset.validation_sha256, body.dataset.holdout_sha256}) != 3:
            raise ValueError("adaptation_dataset_split_hashes_must_differ")
        now = int(time.time())
        plan_id = "adp18_" + uuid.uuid4().hex[:24]
        payload = body.model_dump(mode="json")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO adaptation_plans_v18(
                workspace_id,plan_id,route_id,provider_id,base_model_id,payload_json,status,created_at,updated_at
                ) VALUES(:w,:plan,:route,:provider,:base,:payload,'PLANNED',:created,:updated)"""
            ), {
                "w": workspace_id, "plan": plan_id, "route": body.route_id, "provider": body.provider_id,
                "base": body.base_model_id,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="adaptation-plan-v18"),
                "created": now, "updated": now,
            })
        return self.get_plan(workspace_id, plan_id)

    def get_plan(self, workspace_id: str, plan_id: str) -> AdaptationPlan | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM adaptation_plans_v18 WHERE workspace_id=:w AND plan_id=:plan"
            ), {"w": workspace_id, "plan": plan_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="adaptation-plan-v18")
        return AdaptationPlan(
            plan_id=row["plan_id"], **payload, status=row["status"],
            created_at=int(row["created_at"]), updated_at=int(row["updated_at"]),
        )

    def register_candidate(self, workspace_id: str, plan_id: str, body: CandidateArtifactRegister) -> AdaptationCandidate:
        plan = self.get_plan(workspace_id, plan_id)
        if plan is None:
            raise ValueError("adaptation_plan_not_found")
        if plan.status not in {"PLANNED", "CANDIDATE"}:
            raise ValueError("adaptation_plan_not_accepting_candidate")
        provider = ENTERPRISE_STORE.get_provider(workspace_id, plan.provider_id)
        provider_models = set((provider or {}).get("model_ids", []))
        if provider_models and body.adapter_model_id not in provider_models:
            raise ValueError("adaptation_candidate_model_not_registered")
        now = int(time.time())
        candidate_id = "adc18_" + uuid.uuid4().hex[:24]
        payload = body.model_dump(mode="json")
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO adaptation_candidates_v18(
                workspace_id,candidate_id,plan_id,payload_json,status,created_at,updated_at
                ) VALUES(:w,:candidate,:plan,:payload,'CANDIDATE',:created,:updated)"""
            ), {
                "w": workspace_id, "candidate": candidate_id, "plan": plan_id,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="adaptation-candidate-v18"),
                "created": now, "updated": now,
            })
            connection.execute(text(
                "UPDATE adaptation_plans_v18 SET status='CANDIDATE',updated_at=:updated WHERE workspace_id=:w AND plan_id=:plan"
            ), {"updated": now, "w": workspace_id, "plan": plan_id})
        return self.get_candidate(workspace_id, candidate_id)

    def get_candidate(self, workspace_id: str, candidate_id: str) -> AdaptationCandidate | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM adaptation_candidates_v18 WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"w": workspace_id, "candidate": candidate_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="adaptation-candidate-v18")
        return AdaptationCandidate(
            candidate_id=row["candidate_id"], plan_id=row["plan_id"], **payload, status=row["status"],
            created_at=int(row["created_at"]), updated_at=int(row["updated_at"]),
        )

    @staticmethod
    def _quality_score(run: dict[str, Any]) -> float:
        guarded = min(1.0, float(run["guarded_claim_rate"]))
        return (
            0.40 * float(run["disposition_accuracy"])
            + 0.25 * float(run["traceability_rate"])
            + 0.25 * float(run["mean_evidence_pass_rate"])
            + 0.10 * (1.0 - guarded)
        )

    def compare_benchmarks(self, workspace_id: str, candidate_id: str, body: BenchmarkComparisonRequest) -> AdaptationBenchmarkDecision:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("adaptation_candidate_not_found")
        plan = self.get_plan(workspace_id, candidate.plan_id)
        if plan is None:
            raise RuntimeError("adaptation_plan_missing")
        deltas: list[BenchmarkMetricDelta] = []
        baseline_scores: list[float] = []
        candidate_scores: list[float] = []
        global_reasons: list[str] = []
        for pair in body.pairs:
            baseline = ENTERPRISE_STORE.get_benchmark(workspace_id, pair.baseline_run_id)
            contender = ENTERPRISE_STORE.get_benchmark(workspace_id, pair.candidate_run_id)
            if baseline is None or contender is None:
                raise ValueError("adaptation_benchmark_run_not_found")
            if baseline["benchmark_name"] != contender["benchmark_name"]:
                raise ValueError("adaptation_benchmark_name_mismatch")
            if int(contender["scenario_count"]) < int(baseline["scenario_count"]):
                raise ValueError("adaptation_candidate_benchmark_has_fewer_scenarios")
            reasons: list[str] = []
            disposition_delta = float(contender["disposition_accuracy"]) - float(baseline["disposition_accuracy"])
            trace_delta = float(contender["traceability_rate"]) - float(baseline["traceability_rate"])
            evidence_delta = float(contender["mean_evidence_pass_rate"]) - float(baseline["mean_evidence_pass_rate"])
            guarded_delta = float(contender["guarded_claim_rate"]) - float(baseline["guarded_claim_rate"])
            latency_base = max(1e-9, float(baseline["p95_latency_ms"]))
            latency_regression = (float(contender["p95_latency_ms"]) - latency_base) / latency_base
            if not bool(contender["acceptance_passed"]):
                reasons.append("candidate_benchmark_acceptance_failed")
            if disposition_delta < -plan.maximum_metric_regression:
                reasons.append("disposition_accuracy_regressed")
            if trace_delta < -plan.maximum_metric_regression:
                reasons.append("traceability_regressed")
            if evidence_delta < -plan.maximum_metric_regression:
                reasons.append("evidence_pass_rate_regressed")
            if guarded_delta > plan.maximum_metric_regression:
                reasons.append("guarded_claim_rate_regressed")
            if latency_regression > plan.maximum_latency_regression_fraction:
                reasons.append("latency_regression_above_limit")
            baseline_scores.append(self._quality_score(baseline))
            candidate_scores.append(self._quality_score(contender))
            deltas.append(BenchmarkMetricDelta(
                benchmark_name=baseline["benchmark_name"],
                disposition_accuracy_delta=round(disposition_delta, 6),
                traceability_rate_delta=round(trace_delta, 6),
                evidence_pass_rate_delta=round(evidence_delta, 6),
                guarded_claim_rate_delta=round(guarded_delta, 6),
                latency_regression_fraction=round(latency_regression, 6),
                passed=not reasons,
                reasons=reasons or ["benchmark_pair_passed"],
            ))
            global_reasons.extend(reasons)
        baseline_score = sum(baseline_scores) / len(baseline_scores)
        candidate_score = sum(candidate_scores) / len(candidate_scores)
        improvement = candidate_score - baseline_score
        if improvement < plan.minimum_quality_improvement:
            global_reasons.append("minimum_quality_improvement_not_met")
        eligible = not global_reasons and all(delta.passed for delta in deltas)
        payload = {
            "candidate_id": candidate_id,
            "eligible": eligible,
            "baseline_quality_score": round(baseline_score, 6),
            "candidate_quality_score": round(candidate_score, 6),
            "quality_improvement": round(improvement, 6),
            "metric_deltas": [delta.model_dump(mode="json") for delta in deltas],
            "reasons": sorted(set(global_reasons)) or ["adaptation_benchmark_gate_passed"],
        }
        decision_sha = _hash(payload)
        now = int(time.time())
        decision_id = "adb18_" + uuid.uuid4().hex[:24]
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO adaptation_benchmarks_v18(
                workspace_id,decision_id,candidate_id,payload_json,decision_sha256,created_at
                ) VALUES(:w,:decision,:candidate,:payload,:sha,:created)"""
            ), {
                "w": workspace_id, "decision": decision_id, "candidate": candidate_id,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="adaptation-benchmark-v18"),
                "sha": decision_sha, "created": now,
            })
            new_status = "BENCHMARKED" if eligible else "REJECTED"
            connection.execute(text(
                "UPDATE adaptation_candidates_v18 SET status=:status,updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"status": new_status, "updated": now, "w": workspace_id, "candidate": candidate_id})
            connection.execute(text(
                "UPDATE adaptation_plans_v18 SET status=:status,updated_at=:updated WHERE workspace_id=:w AND plan_id=:plan"
            ), {"status": new_status, "updated": now, "w": workspace_id, "plan": candidate.plan_id})
        return AdaptationBenchmarkDecision(**payload, decision_sha256=decision_sha)

    def start_canary(self, workspace_id: str, candidate_id: str) -> CanaryDecision:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("adaptation_candidate_not_found")
        if candidate.status != "BENCHMARKED":
            raise ValueError("adaptation_candidate_not_benchmarked")
        plan = self.get_plan(workspace_id, candidate.plan_id)
        if plan is None:
            raise RuntimeError("adaptation_plan_missing")
        with self.engine.connect() as connection:
            current = connection.execute(text(
                "SELECT candidate_model_id FROM adaptation_routes_v18 WHERE workspace_id=:w AND route_id=:route"
            ), {"w": workspace_id, "route": plan.route_id}).mappings().first()
        previous_model = None if current is None else current["candidate_model_id"]
        effective_base = previous_model or plan.base_model_id
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                "DELETE FROM adaptation_routes_v18 WHERE workspace_id=:w AND route_id=:route"
            ), {"w": workspace_id, "route": plan.route_id})
            connection.execute(text(
                """INSERT INTO adaptation_routes_v18(
                workspace_id,route_id,provider_id,base_model_id,candidate_id,candidate_model_id,rollout_percent,previous_model_id,updated_at
                ) VALUES(:w,:route,:provider,:base,:candidate,:candidate_model,0,:previous,:updated)"""
            ), {
                "w": workspace_id, "route": plan.route_id, "provider": plan.provider_id,
                "base": effective_base, "candidate": candidate_id, "candidate_model": candidate.adapter_model_id,
                "previous": previous_model, "updated": now,
            })
            connection.execute(text(
                "UPDATE adaptation_candidates_v18 SET status='CANARY',updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"updated": now, "w": workspace_id, "candidate": candidate_id})
            connection.execute(text(
                "UPDATE adaptation_plans_v18 SET status='CANARY',updated_at=:updated WHERE workspace_id=:w AND plan_id=:plan"
            ), {"updated": now, "w": workspace_id, "plan": plan.plan_id})
        return CanaryDecision(
            candidate_id=candidate_id, route_id=plan.route_id, rollout_percent=0, status="CANARY",
            passed=True, reasons=["canary_initialized"], observation_sha256=_hash({"candidate_id": candidate_id, "rollout": 0}),
        )

    def advance_canary(self, workspace_id: str, candidate_id: str, body: CanaryObservationRequest) -> CanaryDecision:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("adaptation_candidate_not_found")
        if candidate.status not in {"CANARY", "ACTIVE"}:
            raise ValueError("adaptation_candidate_not_in_canary")
        plan = self.get_plan(workspace_id, candidate.plan_id)
        if plan is None:
            raise RuntimeError("adaptation_plan_missing")
        with self.engine.connect() as connection:
            route = connection.execute(text(
                "SELECT * FROM adaptation_routes_v18 WHERE workspace_id=:w AND route_id=:route AND candidate_id=:candidate"
            ), {"w": workspace_id, "route": plan.route_id, "candidate": candidate_id}).mappings().first()
        if route is None:
            raise ValueError("adaptation_route_not_initialized")
        current = int(route["rollout_percent"])
        allowed = {0: 5, 5: 25, 25: 50, 50: 100}
        if allowed.get(current) != body.target_rollout_percent:
            raise ValueError("adaptation_invalid_rollout_transition")
        reasons: list[str] = []
        latency_regression = (body.p95_latency_ms - body.baseline_p95_latency_ms) / body.baseline_p95_latency_ms
        if body.error_rate > plan.maximum_canary_error_rate:
            reasons.append("canary_error_rate_above_limit")
        if body.quality_failure_rate > plan.maximum_canary_quality_failure_rate:
            reasons.append("canary_quality_failure_rate_above_limit")
        if latency_regression > plan.maximum_latency_regression_fraction:
            reasons.append("canary_latency_regression_above_limit")
        if body.regression_detected:
            reasons.append("canary_regression_detected")
        passed = not reasons
        observation_payload = body.model_dump(mode="json")
        observation_sha = _hash(observation_payload)
        observation_id = "adcobs18_" + uuid.uuid4().hex[:24]
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO adaptation_canary_v18(
                workspace_id,observation_id,candidate_id,rollout_percent,payload_json,observation_sha256,created_at
                ) VALUES(:w,:observation,:candidate,:rollout,:payload,:sha,:created)"""
            ), {
                "w": workspace_id, "observation": observation_id, "candidate": candidate_id,
                "rollout": body.target_rollout_percent,
                "payload": VAULT.encrypt_json(observation_payload, workspace_id=workspace_id, purpose="adaptation-canary-v18"),
                "sha": observation_sha, "created": now,
            })
            if passed:
                status: AdaptationStatus = "ACTIVE" if body.target_rollout_percent == 100 else "CANARY"
                connection.execute(text(
                    "UPDATE adaptation_routes_v18 SET rollout_percent=:rollout,updated_at=:updated WHERE workspace_id=:w AND route_id=:route"
                ), {"rollout": body.target_rollout_percent, "updated": now, "w": workspace_id, "route": plan.route_id})
                connection.execute(text(
                    "UPDATE adaptation_candidates_v18 SET status=:status,updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
                ), {"status": status, "updated": now, "w": workspace_id, "candidate": candidate_id})
                connection.execute(text(
                    "UPDATE adaptation_plans_v18 SET status=:status,updated_at=:updated WHERE workspace_id=:w AND plan_id=:plan"
                ), {"status": status, "updated": now, "w": workspace_id, "plan": plan.plan_id})
            else:
                status = "ROLLED_BACK"
                rollback_model = route["previous_model_id"] or route["base_model_id"]
                connection.execute(text(
                    """UPDATE adaptation_routes_v18
                    SET base_model_id=:rollback,candidate_id=NULL,candidate_model_id=NULL,rollout_percent=0,previous_model_id=NULL,updated_at=:updated
                    WHERE workspace_id=:w AND route_id=:route"""
                ), {"rollback": rollback_model, "updated": now, "w": workspace_id, "route": plan.route_id})
                connection.execute(text(
                    "UPDATE adaptation_candidates_v18 SET status='ROLLED_BACK',updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
                ), {"updated": now, "w": workspace_id, "candidate": candidate_id})
                connection.execute(text(
                    "UPDATE adaptation_plans_v18 SET status='ROLLED_BACK',updated_at=:updated WHERE workspace_id=:w AND plan_id=:plan"
                ), {"updated": now, "w": workspace_id, "plan": plan.plan_id})
        return CanaryDecision(
            candidate_id=candidate_id, route_id=plan.route_id,
            rollout_percent=body.target_rollout_percent if passed else 0,
            status=status, passed=passed, reasons=reasons or ["canary_gate_passed"],
            observation_sha256=observation_sha,
        )

    def rollback_candidate(self, workspace_id: str, candidate_id: str) -> CanaryDecision:
        candidate = self.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise ValueError("adaptation_candidate_not_found")
        if candidate.status not in {"CANARY", "ACTIVE"}:
            raise ValueError("adaptation_candidate_not_active_for_rollback")
        plan = self.get_plan(workspace_id, candidate.plan_id)
        if plan is None:
            raise RuntimeError("adaptation_plan_missing")
        with self.engine.connect() as connection:
            route = connection.execute(text(
                "SELECT * FROM adaptation_routes_v18 WHERE workspace_id=:w AND route_id=:route"
            ), {"w": workspace_id, "route": plan.route_id}).mappings().first()
        if route is None or route["candidate_id"] != candidate_id:
            raise ValueError("adaptation_candidate_not_current_route")
        rollback_model = route["previous_model_id"] or route["base_model_id"]
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """UPDATE adaptation_routes_v18
                SET base_model_id=:rollback,candidate_id=NULL,candidate_model_id=NULL,rollout_percent=0,previous_model_id=NULL,updated_at=:updated
                WHERE workspace_id=:w AND route_id=:route"""
            ), {"rollback": rollback_model, "updated": now, "w": workspace_id, "route": plan.route_id})
            connection.execute(text(
                "UPDATE adaptation_candidates_v18 SET status='ROLLED_BACK',updated_at=:updated WHERE workspace_id=:w AND candidate_id=:candidate"
            ), {"updated": now, "w": workspace_id, "candidate": candidate_id})
            connection.execute(text(
                "UPDATE adaptation_plans_v18 SET status='ROLLED_BACK',updated_at=:updated WHERE workspace_id=:w AND plan_id=:plan"
            ), {"updated": now, "w": workspace_id, "plan": plan.plan_id})
        payload = {"candidate_id": candidate_id, "route_id": plan.route_id, "rollback_model": rollback_model}
        return CanaryDecision(
            candidate_id=candidate_id, route_id=plan.route_id, rollout_percent=0, status="ROLLED_BACK",
            passed=False, reasons=["manual_rollback"], observation_sha256=_hash(payload),
        )

    def resolve_route(self, workspace_id: str, route_id: str, body: RouteResolutionRequest) -> RouteResolution:
        with self.engine.connect() as connection:
            route = connection.execute(text(
                "SELECT * FROM adaptation_routes_v18 WHERE workspace_id=:w AND route_id=:route"
            ), {"w": workspace_id, "route": route_id}).mappings().first()
        if route is None:
            raise ValueError("adaptation_route_not_found")
        request_key_sha = hashlib.sha256(body.request_key.encode("utf-8")).hexdigest()
        bucket = int(hashlib.sha256(f"{workspace_id}|{route_id}|{body.request_key}".encode("utf-8")).hexdigest()[:8], 16) % 100
        rollout = int(route["rollout_percent"])
        candidate_model = route["candidate_model_id"]
        candidate_selected = candidate_model is not None and bucket < rollout
        selected = candidate_model if candidate_selected else route["base_model_id"]
        payload = {
            "route_id": route_id, "request_key_sha256": request_key_sha, "rollout_percent": rollout,
            "selected_model_id": selected, "base_model_id": route["base_model_id"],
            "candidate_model_id": candidate_model, "candidate_selected": candidate_selected,
        }
        return RouteResolution(**payload, route_sha256=_hash(payload))


V18 = GovernedAdaptationV18()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", action),
        principal_id=principal.principal_id, workspace_id=principal.workspace_id,
        action=action, status=status, metadata={"role": principal.role, **metadata},
    )


@router.post("/plans", response_model=AdaptationPlan)
def create_plan(body: AdaptationPlanCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AdaptationPlan:
    try:
        result = V18.create_plan(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, principal, "v18_adaptation_plan", "PLANNED", {"plan_id": result.plan_id, "route_id": result.route_id})
    return result


@router.post("/plans/{plan_id}/candidate", response_model=AdaptationCandidate)
def register_candidate(plan_id: str, body: CandidateArtifactRegister, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AdaptationCandidate:
    try:
        result = V18.register_candidate(principal.workspace_id, plan_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v18_adaptation_candidate", "CANDIDATE", {"candidate_id": result.candidate_id, "plan_id": plan_id})
    return result


@router.post("/candidates/{candidate_id}/benchmark", response_model=AdaptationBenchmarkDecision)
def benchmark_candidate(candidate_id: str, body: BenchmarkComparisonRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AdaptationBenchmarkDecision:
    try:
        result = V18.compare_benchmarks(principal.workspace_id, candidate_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v18_adaptation_benchmark", "PASS" if result.eligible else "FAIL", {"candidate_id": candidate_id, "decision_sha256": result.decision_sha256})
    return result


@router.post("/candidates/{candidate_id}/canary/start", response_model=CanaryDecision)
def start_canary(candidate_id: str, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> CanaryDecision:
    try:
        result = V18.start_canary(principal.workspace_id, candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v18_canary_start", "CANARY", {"candidate_id": candidate_id, "route_id": result.route_id})
    return result


@router.post("/candidates/{candidate_id}/canary/advance", response_model=CanaryDecision)
def advance_canary(candidate_id: str, body: CanaryObservationRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> CanaryDecision:
    try:
        result = V18.advance_canary(principal.workspace_id, candidate_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v18_canary_advance", result.status, {"candidate_id": candidate_id, "rollout_percent": result.rollout_percent, "passed": result.passed})
    return result


@router.post("/candidates/{candidate_id}/rollback", response_model=CanaryDecision)
def rollback_candidate(candidate_id: str, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> CanaryDecision:
    try:
        result = V18.rollback_candidate(principal.workspace_id, candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v18_adaptation_rollback", "ROLLED_BACK", {"candidate_id": candidate_id, "route_id": result.route_id})
    return result


@router.post("/routes/{route_id}/resolve", response_model=RouteResolution)
def resolve_route(route_id: str, body: RouteResolutionRequest, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> RouteResolution:
    try:
        return V18.resolve_route(principal.workspace_id, route_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v18",
        "dataset_provenance_and_locked_holdout": True,
        "external_training_artifact_registry": True,
        "baseline_candidate_benchmark_gate": True,
        "deterministic_canary_routing": True,
        "progressive_rollout": [5, 25, 50, 100],
        "automatic_safety_rollback": True,
        "foundation_model_weight_training_inside_orbythra": False,
        "unrestricted_self_modification": False,
        "live_agi_claim": False,
        "boundary": (
            "V18 governs externally produced model/adapter adaptations with locked holdouts, benchmark comparison, "
            "progressive canary rollout and rollback. It does not itself train foundation-model weights, authorize "
            "unbounded self-modification, or prove AGI."
        ),
    }
