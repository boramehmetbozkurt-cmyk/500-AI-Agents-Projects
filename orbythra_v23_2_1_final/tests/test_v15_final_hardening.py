from __future__ import annotations

import uuid

import pytest

from app.action_chain_finalization_v15 import finalize_chain, verify_finalization
from app.action_chain_v12 import ACTION_CHAIN_V12, ChainAppendRequest
from app.agent_control_plane_v15 import AgentControlPolicy, CONTROL_PLANE_V15
from app.agent_models import AgentActionRequest
from app.agent_store import AGENT_STORE
from app.calibration_v15 import CalibrationObservation, CALIBRATION_V15, _adjust, _report
from app.crypto_core import commitment
from app.effect_verification_v15 import EffectObservation, EffectVerificationPolicy, EffectVerificationRequest, verify_effect
from app.failure_memory_v15 import FAILURE_MEMORY_V15, FailureObservation, FailureResolution
from app.multimodal_evidence_v15 import MultimodalArtifact, MultimodalBundleRequest, verify_bundle
from app.visual_identity_assurance_v15 import (
    FaceFidelityMetric,
    VisualIdentityEvaluationRequest,
    VisualRestorationPlanRequest,
    create_plan,
    evaluate_identity,
)


def wid(prefix: str = "w") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def test_calibration_report_and_empirical_adjustment():
    workspace = wid("cal")
    for index in range(40):
        CALIBRATION_V15.add(
            workspace,
            CalibrationObservation(
                domain="engineering",
                task_type="verification",
                predicted_probability=0.9,
                outcome_correct=index < 20,
                model_id="model-a",
                observed_at=1000 + index,
            ),
            now=2000,
        )
    rows = CALIBRATION_V15.rows(workspace, "engineering", "verification")
    report = _report(rows, "engineering", "verification")
    adjusted = _adjust(rows, 0.9, minimum_samples=30, shrinkage_strength=0)
    assert report.count == 40
    assert report.status == "DRIFT_RISK"
    assert report.ece is not None and report.ece >= 0.39
    assert adjusted.status == "ADJUSTED"
    assert adjusted.adjusted_probability == 0.5


def test_calibration_rejects_future_observation():
    workspace = wid("calfuture")
    with pytest.raises(ValueError, match="future_calibration_observation"):
        CALIBRATION_V15.add(
            workspace,
            CalibrationObservation(domain="x", predicted_probability=0.5, outcome_correct=True, observed_at=5000),
            now=1000,
        )


def test_agent_control_plane_kill_switch_capabilities_and_emergency_stop():
    workspace = wid("agent")
    agent_id = "agent-a"
    legacy = CONTROL_PLANE_V15.assert_execution_allowed(workspace, agent_id, "tool-a", "read", "moderate", now=1000)
    assert legacy["allowed"] is True and legacy["control_plane_registered"] is False

    record = CONTROL_PLANE_V15.put(
        workspace,
        agent_id,
        AgentControlPolicy(
            state="ACTIVE",
            allowed_tool_ids=["tool-a"],
            allowed_operations=["read"],
            maximum_risk_tier="moderate",
            reason="least privilege",
        ),
        now=1000,
    )
    assert record.epoch == 1
    allowed = CONTROL_PLANE_V15.assert_execution_allowed(workspace, agent_id, "tool-a", "read", "low", now=1001)
    assert allowed["control_plane_registered"] is True
    with pytest.raises(ValueError, match="agent_tool_not_allowed"):
        CONTROL_PLANE_V15.assert_execution_allowed(workspace, agent_id, "tool-b", "read", "low", now=1001)
    with pytest.raises(ValueError, match="agent_risk_exceeds"):
        CONTROL_PLANE_V15.assert_execution_allowed(workspace, agent_id, "tool-a", "read", "high", now=1001)

    killed = CONTROL_PLANE_V15.set_state(workspace, agent_id, "KILLED", "incident", now=1002)
    assert killed.epoch == 2
    with pytest.raises(ValueError, match="agent_killed"):
        CONTROL_PLANE_V15.assert_execution_allowed(workspace, agent_id, "tool-a", "read", "low", now=1003)

    CONTROL_PLANE_V15.set_state(workspace, agent_id, "ACTIVE", "reviewed", now=1004)
    CONTROL_PLANE_V15.set_workspace_emergency(workspace, True, "global incident", now=1005)
    with pytest.raises(ValueError, match="workspace_agent_emergency_stop"):
        CONTROL_PLANE_V15.assert_execution_allowed(workspace, agent_id, "tool-a", "read", "low", now=1006)


def _make_action(workspace: str, intended_effect: dict, *, risk_tier: str = "moderate") -> str:
    body = AgentActionRequest(
        agent_id="agent-effect",
        tool_id="tool-effect",
        operation="apply",
        parameters={},
        intended_effect=intended_effect,
        risk_tier=risk_tier,
    )
    stored = AGENT_STORE.create_action(
        workspace,
        request_data=body.model_dump(mode="json"),
        decision="ALLOW",
        status="AUTHORIZED",
        reasons=[],
        intent_digest="1" * 64,
        intended_effect_digest=commitment(intended_effect, domain="agent-effect")["sha256"],
        policy_snapshot_sha256="2" * 64,
        authorization_envelope=None,
    )
    return stored["action_id"]


def _obs(source: str, effect: dict, lineage: str | None = None, observed_at: int = 990) -> EffectObservation:
    return EffectObservation(
        source_id=source,
        source_lineage_id=lineage,
        actual_effect=effect,
        evidence_sha256=("a" if source.startswith("a") else "b") * 64,
        observed_at=observed_at,
        observer_kind="system",
    )


def test_effect_verification_requires_independent_consensus_and_matches_committed_effect():
    workspace = wid("effect")
    expected = {"state": "enabled", "value": 7}
    action_id = _make_action(workspace, expected)
    body = EffectVerificationRequest(
        action_id=action_id,
        nonce="nonce-effect-123",
        observations=[_obs("a-source", expected, "origin-a"), _obs("b-source", expected, "origin-b")],
        policy=EffectVerificationPolicy(minimum_independent_observations=2, minimum_consensus_fraction=1.0),
    )
    result = verify_effect(workspace, body, now=1000)
    assert result.status == "VERIFIED"
    assert result.independent_observations == 2
    assert result.consensus_effect_sha256 == result.expected_effect_sha256


def test_effect_verification_conflict_is_inconclusive_and_wrong_consensus_is_mismatch():
    workspace = wid("effect2")
    expected = {"state": "enabled"}
    action_id = _make_action(workspace, expected)
    conflict = EffectVerificationRequest(
        action_id=action_id,
        nonce="nonce-conflict-1",
        observations=[_obs("a-one", expected, "line-a"), _obs("b-two", {"state": "disabled"}, "line-b")],
        policy=EffectVerificationPolicy(minimum_independent_observations=2, minimum_consensus_fraction=1.0),
    )
    assert verify_effect(workspace, conflict, now=1000).status == "INCONCLUSIVE"

    wrong = EffectVerificationRequest(
        action_id=action_id,
        nonce="nonce-wrong-123",
        observations=[_obs("a-three", {"state": "disabled"}, "line-c"), _obs("b-four", {"state": "disabled"}, "line-d")],
        policy=EffectVerificationPolicy(minimum_independent_observations=2, minimum_consensus_fraction=1.0),
    )
    assert verify_effect(workspace, wrong, now=1000).status == "MISMATCH"


def test_high_risk_effect_requires_validator_quorum():
    workspace = wid("effecthigh")
    expected = {"state": "enabled"}
    action_id = _make_action(workspace, expected, risk_tier="high")
    body = EffectVerificationRequest(
        action_id=action_id,
        nonce="nonce-high-1234",
        observations=[_obs("a-high", expected, "line-a")],
    )
    result = verify_effect(workspace, body, now=1000)
    assert result.status == "INCONCLUSIVE"
    assert result.validator_quorum_status == "MISSING_REQUIRED_QUORUM"


def test_multimodal_manifest_verifies_structure_and_provenance():
    workspace = wid("mm")
    artifacts = [
        MultimodalArtifact(
            artifact_id="img-1",
            modality="image",
            content_sha256="a" * 64,
            metadata_sha256="b" * 64,
            source_id="camera-1",
            source_lineage_id="line-image",
            mime_type="image/png",
            byte_size=100,
            captured_at=900,
            acquired_at=910,
            claim_ids=["claim-1"],
        ),
        MultimodalArtifact(
            artifact_id="txt-1",
            modality="text",
            content_sha256="c" * 64,
            metadata_sha256="d" * 64,
            source_id="report-1",
            source_lineage_id="line-text",
            mime_type="text/plain",
            byte_size=50,
            captured_at=905,
            acquired_at=915,
            claim_ids=["claim-1"],
        ),
    ]
    result = verify_bundle(
        workspace,
        MultimodalBundleRequest(
            case_id="case-1",
            artifacts=artifacts,
            required_modalities=["image", "text"],
            minimum_modalities=2,
            minimum_independent_lineages=2,
        ),
        now=1000,
    )
    assert result.status == "VERIFIED_STRUCTURE"
    assert result.modality_count == 2
    assert result.independent_lineages == 2
    assert result.claim_coverage["claim-1"] == 2


def test_multimodal_future_artifact_fails_closed():
    workspace = wid("mmfuture")
    artifact = MultimodalArtifact(
        artifact_id="img-future",
        modality="image",
        content_sha256="a" * 64,
        metadata_sha256="b" * 64,
        source_id="camera",
        mime_type="image/png",
        byte_size=1,
        captured_at=5000,
        acquired_at=5000,
    )
    result = verify_bundle(workspace, MultimodalBundleRequest(case_id="future", artifacts=[artifact], maximum_future_skew_seconds=10), now=1000)
    assert result.status == "INVALID"
    assert result.invalid_artifact_ids


def _good_visual_request(plan):
    return VisualIdentityEvaluationRequest(
        plan=plan,
        output_image_sha256="b" * 64,
        output_width=600,
        output_height=600,
        output_detected_face_ids=["face-1"],
        face_metrics=[
            FaceFidelityMetric(
                face_id="face-1",
                identity_embedding_similarity=0.98,
                normalized_landmark_rmse=0.01,
                face_region_ssim=0.95,
                geometry_scale_drift=0.01,
                rotation_drift_degrees=0.5,
            )
        ],
        difference_map_sha256="c" * 64,
        identity_embedding_model_sha256="d" * 64,
        landmark_model_sha256="e" * 64,
        metric_adapter_id="vision-adapter",
        metric_adapter_version="1.0",
        background_alpha_verified=True,
    )


def test_visual_identity_gate_passes_good_metrics_and_rejects_tampered_plan():
    workspace = wid("vision")
    plan = create_plan(
        VisualRestorationPlanRequest(
            source_image_sha256="a" * 64,
            operations=["super_resolution", "background_removal"],
            source_width=300,
            source_height=300,
            detected_face_ids=["face-1"],
        ),
        now=1000,
    )
    good = evaluate_identity(workspace, _good_visual_request(plan), now=1001)
    assert good.status == "PASS"
    assert good.face_results[0].passed is True

    tampered = plan.model_copy(update={"operations": ["denoise"]})
    bad = evaluate_identity(workspace, _good_visual_request(tampered), now=1002)
    assert bad.status == "REJECT"
    assert "plan_integrity_mismatch" in bad.global_failures


def test_visual_identity_gate_rejects_face_drift():
    workspace = wid("visiondrift")
    plan = create_plan(
        VisualRestorationPlanRequest(
            source_image_sha256="a" * 64,
            operations=["super_resolution"],
            source_width=300,
            source_height=300,
            detected_face_ids=["face-1"],
        ),
        now=1000,
    )
    request = _good_visual_request(plan)
    request.face_metrics[0].identity_embedding_similarity = 0.5
    result = evaluate_identity(workspace, request, now=1001)
    assert result.status == "REJECT"
    assert "identity_similarity_below_threshold" in result.face_results[0].failures


def _complete_chain(workspace: str):
    current = ACTION_CHAIN_V12.create(workspace, {"objective": "finalize"}, now=1000)
    for index, stage in enumerate(("PLAN", "CANDIDATE", "SIMULATION", "APPROVAL", "ACTION", "EFFECT"), start=1):
        current = ACTION_CHAIN_V12.append(
            workspace,
            current.chain_id,
            ChainAppendRequest(stage=stage, payload={"stage": stage, "index": index}, expected_previous_entry_sha256=current.head_sha256),
            now=1000 + index,
        )
    return current


def test_action_chain_finalization_is_signed_and_reverifiable():
    workspace = wid("chain")
    chain = _complete_chain(workspace)
    finalized = finalize_chain(workspace, chain.chain_id, now=2000)
    verified = verify_finalization(workspace, chain.chain_id, finalized.signed_envelope)
    assert verified.valid is True
    assert verified.signer_verified is True
    assert verified.chain_head_matches is True
    assert verified.chain_receipt_matches is True


def test_failure_memory_blocks_high_severity_and_reopens_fixed_failure_as_regression():
    workspace = wid("failure")
    observation = FailureObservation(
        component="verification-firewall",
        error_class="unsupported-claim-bypass",
        invariant="unsupported claims must never be released",
        severity="critical",
        evidence_sha256="a" * 64,
        release_sha="abc1234",
    )
    first = FAILURE_MEMORY_V15.record(workspace, observation, now=1000)
    assert first.status == "OPEN"
    assert FAILURE_MEMORY_V15.release_gate(workspace).status == "BLOCK"

    fixed = FAILURE_MEMORY_V15.resolve(
        workspace,
        first.failure_id,
        FailureResolution(
            root_cause="missing gate",
            remediation="bind output claims",
            regression_test_ref="tests/test_claim_gate.py::test_bypass",
            fix_commit_sha="def5678",
        ),
    )
    assert fixed.status == "FIXED"
    assert FAILURE_MEMORY_V15.release_gate(workspace).status == "PASS"

    again = FAILURE_MEMORY_V15.record(workspace, observation.model_copy(update={"release_sha": "fedcba9"}), now=2000)
    assert again.status == "REGRESSION"
    assert again.occurrences == 2
    assert FAILURE_MEMORY_V15.release_gate(workspace).status == "BLOCK"


def test_failure_memory_survives_store_reinstantiation() -> None:
    from app.failure_memory_v15 import FailureMemoryV15

    workspace = wid("failure-restart")
    observation = FailureObservation(
        component="restart-persistence",
        error_class="persistent-regression",
        invariant="critical failure state must survive process restart",
        severity="critical",
        evidence_sha256="b" * 64,
        release_sha="restart1",
    )

    writer = FailureMemoryV15()
    created = writer.record(workspace, observation, now=1000)

    reader_after_restart = FailureMemoryV15()
    restored = reader_after_restart.get(workspace, created.failure_id)
    gate = reader_after_restart.release_gate(workspace)

    assert restored is not None
    assert restored.failure_id == created.failure_id
    assert restored.status == "OPEN"
    assert restored.occurrences == 1
    assert gate.status == "BLOCK"
    assert created.failure_id in gate.blocking_failure_ids
