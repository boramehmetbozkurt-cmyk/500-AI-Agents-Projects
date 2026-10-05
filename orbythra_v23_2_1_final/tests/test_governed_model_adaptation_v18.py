from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import app
from app.enterprise_store import ENTERPRISE_STORE
from app.governed_model_adaptation_v18 import (
    AdaptationPlanCreate,
    BenchmarkComparisonRequest,
    BenchmarkPair,
    CanaryObservationRequest,
    CandidateArtifactRegister,
    DatasetManifest,
    RouteResolutionRequest,
    V18,
)

HEADERS = {"X-API-Key": "test-secret"}


def wid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def register_provider(workspace: str, provider_id: str = "provider-a") -> None:
    ENTERPRISE_STORE.upsert_provider(
        workspace,
        {
            "provider_id": provider_id,
            "family": "self_hosted",
            "model_ids": ["base-model", "candidate-model"],
            "deployment_region": "eu",
            "data_residency": "eu",
            "enabled": True,
        },
    )


def dataset() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="dataset-v18",
        purpose="Improve bounded reasoning behavior",
        sample_count=1000,
        train_sha256="a" * 64,
        validation_sha256="b" * 64,
        holdout_sha256="c" * 64,
        provenance_refs=["dataset:source"],
        license_refs=["license:internal"],
        pii_reviewed=True,
        holdout_locked=True,
    )


def create_plan(workspace: str):
    register_provider(workspace)
    return V18.create_plan(
        workspace,
        AdaptationPlanCreate(
            route_id="default-reasoning",
            provider_id="provider-a",
            base_model_id="base-model",
            adaptation_kind="lora",
            dataset=dataset(),
            target_capabilities=["reasoning", "verification"],
            minimum_quality_improvement=0.01,
            maximum_metric_regression=0.005,
            maximum_latency_regression_fraction=0.20,
        ),
    )


def register_candidate(workspace: str, plan_id: str):
    return V18.register_candidate(
        workspace,
        plan_id,
        CandidateArtifactRegister(
            adapter_model_id="candidate-model",
            training_run_ref="trainer-run-001",
            trainer_name="external-trainer",
            artifact_sha256="d" * 64,
            training_config_sha256="e" * 64,
            artifact_size_bytes=123456,
            trainer_attestation_refs=["attestation:trainer:001"],
            base_model_fingerprint="base-model-fingerprint-v1",
        ),
    )


def save_benchmark(workspace: str, *, name: str, label: str, quality: float, latency: float, guarded: float = 0.0):
    return ENTERPRISE_STORE.save_benchmark(
        workspace,
        {
            "benchmark_name": name,
            "model_label": label,
            "scenario_count": 100,
            "disposition_accuracy": quality,
            "traceability_rate": quality,
            "mean_evidence_pass_rate": quality,
            "guarded_claim_rate": guarded,
            "p95_latency_ms": latency,
            "acceptance_passed": True,
            "failures": [],
        },
    )


def test_dataset_gate_rejects_unlocked_holdout_or_missing_pii_review() -> None:
    workspace = wid("dataset-gate")
    register_provider(workspace)

    unlocked = dataset().model_copy(update={"holdout_locked": False})
    try:
        V18.create_plan(
            workspace,
            AdaptationPlanCreate(
                route_id="route-a",
                provider_id="provider-a",
                base_model_id="base-model",
                adaptation_kind="adapter",
                dataset=unlocked,
                target_capabilities=["reasoning"],
            ),
        )
        assert False, "expected holdout gate failure"
    except ValueError as exc:
        assert str(exc) == "adaptation_holdout_must_be_locked"

    not_reviewed = dataset().model_copy(update={"pii_reviewed": False})
    try:
        V18.create_plan(
            workspace,
            AdaptationPlanCreate(
                route_id="route-b",
                provider_id="provider-a",
                base_model_id="base-model",
                adaptation_kind="adapter",
                dataset=not_reviewed,
                target_capabilities=["reasoning"],
            ),
        )
        assert False, "expected pii review gate failure"
    except ValueError as exc:
        assert str(exc) == "adaptation_dataset_pii_review_required"


def test_candidate_must_beat_baseline_before_canary() -> None:
    workspace = wid("benchmark")
    plan = create_plan(workspace)
    candidate = register_candidate(workspace, plan.plan_id)

    baseline = save_benchmark(workspace, name="reasoning-frozen", label="base-model", quality=0.90, latency=1000)
    contender = save_benchmark(workspace, name="reasoning-frozen", label="candidate-model", quality=0.95, latency=1050)

    decision = V18.compare_benchmarks(
        workspace,
        candidate.candidate_id,
        BenchmarkComparisonRequest(
            pairs=[BenchmarkPair(baseline_run_id=baseline["run_id"], candidate_run_id=contender["run_id"])]
        ),
    )
    assert decision.eligible is True
    assert decision.quality_improvement > 0.01
    assert decision.metric_deltas[0].passed is True

    started = V18.start_canary(workspace, candidate.candidate_id)
    assert started.status == "CANARY"
    assert started.rollout_percent == 0


def test_progressive_canary_reaches_active_and_manual_rollback_returns_base() -> None:
    workspace = wid("canary")
    plan = create_plan(workspace)
    candidate = register_candidate(workspace, plan.plan_id)
    baseline = save_benchmark(workspace, name="generalist-frozen", label="base-model", quality=0.90, latency=1000)
    contender = save_benchmark(workspace, name="generalist-frozen", label="candidate-model", quality=0.96, latency=1080)
    V18.compare_benchmarks(
        workspace,
        candidate.candidate_id,
        BenchmarkComparisonRequest(
            pairs=[BenchmarkPair(baseline_run_id=baseline["run_id"], candidate_run_id=contender["run_id"])]
        ),
    )
    V18.start_canary(workspace, candidate.candidate_id)

    for target in (5, 25, 50, 100):
        decision = V18.advance_canary(
            workspace,
            candidate.candidate_id,
            CanaryObservationRequest(
                target_rollout_percent=target,
                request_count=1000,
                error_rate=0.005,
                quality_failure_rate=0.01,
                p95_latency_ms=1100,
                baseline_p95_latency_ms=1000,
                regression_detected=False,
                evidence_refs=[f"canary:{target}"],
            ),
        )
        assert decision.passed is True
        assert decision.rollout_percent == target

    active = V18.get_candidate(workspace, candidate.candidate_id)
    assert active is not None
    assert active.status == "ACTIVE"

    routed = V18.resolve_route(workspace, plan.route_id, RouteResolutionRequest(request_key="request-1"))
    assert routed.rollout_percent == 100
    assert routed.candidate_selected is True
    assert routed.selected_model_id == "candidate-model"

    rolled = V18.rollback_candidate(workspace, candidate.candidate_id)
    assert rolled.status == "ROLLED_BACK"
    routed_after = V18.resolve_route(workspace, plan.route_id, RouteResolutionRequest(request_key="request-1"))
    assert routed_after.rollout_percent == 0
    assert routed_after.candidate_selected is False
    assert routed_after.selected_model_id == "base-model"


def test_bad_canary_automatically_rolls_back() -> None:
    workspace = wid("auto-rollback")
    plan = create_plan(workspace)
    candidate = register_candidate(workspace, plan.plan_id)
    baseline = save_benchmark(workspace, name="safety-frozen", label="base-model", quality=0.90, latency=1000)
    contender = save_benchmark(workspace, name="safety-frozen", label="candidate-model", quality=0.95, latency=1050)
    V18.compare_benchmarks(
        workspace,
        candidate.candidate_id,
        BenchmarkComparisonRequest(
            pairs=[BenchmarkPair(baseline_run_id=baseline["run_id"], candidate_run_id=contender["run_id"])]
        ),
    )
    V18.start_canary(workspace, candidate.candidate_id)

    decision = V18.advance_canary(
        workspace,
        candidate.candidate_id,
        CanaryObservationRequest(
            target_rollout_percent=5,
            request_count=1000,
            error_rate=0.25,
            quality_failure_rate=0.20,
            p95_latency_ms=1600,
            baseline_p95_latency_ms=1000,
            regression_detected=True,
            evidence_refs=["canary:bad"],
        ),
    )
    assert decision.passed is False
    assert decision.status == "ROLLED_BACK"
    assert "canary_regression_detected" in decision.reasons
    route = V18.resolve_route(workspace, plan.route_id, RouteResolutionRequest(request_key="request-2"))
    assert route.rollout_percent == 0
    assert route.selected_model_id == "base-model"


def test_route_resolution_is_deterministic_for_same_request_key() -> None:
    workspace = wid("routing")
    plan = create_plan(workspace)
    candidate = register_candidate(workspace, plan.plan_id)
    baseline = save_benchmark(workspace, name="routing-frozen", label="base-model", quality=0.90, latency=1000)
    contender = save_benchmark(workspace, name="routing-frozen", label="candidate-model", quality=0.95, latency=1000)
    V18.compare_benchmarks(
        workspace,
        candidate.candidate_id,
        BenchmarkComparisonRequest(
            pairs=[BenchmarkPair(baseline_run_id=baseline["run_id"], candidate_run_id=contender["run_id"])]
        ),
    )
    V18.start_canary(workspace, candidate.candidate_id)
    V18.advance_canary(
        workspace,
        candidate.candidate_id,
        CanaryObservationRequest(
            target_rollout_percent=5,
            request_count=1000,
            error_rate=0.0,
            quality_failure_rate=0.0,
            p95_latency_ms=1000,
            baseline_p95_latency_ms=1000,
            regression_detected=False,
            evidence_refs=["canary:5"],
        ),
    )
    first = V18.resolve_route(workspace, plan.route_id, RouteResolutionRequest(request_key="stable-key"))
    second = V18.resolve_route(workspace, plan.route_id, RouteResolutionRequest(request_key="stable-key"))
    assert first.selected_model_id == second.selected_model_id
    assert first.candidate_selected == second.candidate_selected
    assert first.route_sha256 == second.route_sha256


def test_v18_readiness_keeps_agi_and_self_modification_boundary() -> None:
    client = TestClient(app)
    workspace = wid("readiness")
    response = client.get("/v18/adaptation/readiness", headers={**HEADERS, "X-Workspace-ID": workspace})
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_provenance_and_locked_holdout"] is True
    assert payload["baseline_candidate_benchmark_gate"] is True
    assert payload["automatic_safety_rollback"] is True
    assert payload["foundation_model_weight_training_inside_orbythra"] is False
    assert payload["unrestricted_self_modification"] is False
    assert payload["live_agi_claim"] is False
    assert "does not itself train foundation-model weights" in payload["boundary"]
