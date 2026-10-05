from __future__ import annotations

import time
import uuid

import pytest

import app.learning_engine_v20 as learningmod
import app.skill_invention_v20 as skillmod
from app.continual_generalist_v16 import CONTINUAL_V16, WorldFactQuery
from app.enterprise_store import ENTERPRISE_STORE
from app.governed_model_adaptation_v18 import AdaptationPlanCreate, DatasetManifest, V18
from app.learning_engine_v20 import LEARNING_V20, TrainingJobCreate
from app.multimodal_evidence_v15 import MultimodalArtifact, MultimodalBundleRequest
from app.multimodal_world_v20 import (
    ArtifactInterpretation,
    MULTIMODAL_FUSION_V20,
    MultimodalFusionRequest,
    SemanticClaim,
)
from app.skill_invention_v20 import (
    ManualEvaluationRequest,
    SandboxTrialResult,
    SKILL_INVENTION_V20,
    SkillInventionRequest,
)


def wid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def register_provider(workspace: str) -> None:
    ENTERPRISE_STORE.upsert_provider(
        workspace,
        {
            "provider_id": "provider-v20",
            "family": "self_hosted",
            "model_ids": ["base-model", "adapter-model"],
            "deployment_region": "eu",
            "data_residency": "eu",
            "enabled": True,
        },
    )


def create_adaptation_plan(workspace: str):
    register_provider(workspace)
    return V18.create_plan(
        workspace,
        AdaptationPlanCreate(
            route_id="reasoning-v20",
            provider_id="provider-v20",
            base_model_id="base-model",
            adaptation_kind="lora",
            dataset=DatasetManifest(
                dataset_id="dataset-v20",
                purpose="governed adapter learning",
                sample_count=1000,
                train_sha256="a" * 64,
                validation_sha256="b" * 64,
                holdout_sha256="c" * 64,
                provenance_refs=["dataset:source"],
                license_refs=["license:internal"],
                pii_reviewed=True,
                holdout_locked=True,
            ),
            target_capabilities=["reasoning", "verification"],
        ),
    )


def test_learning_engine_hands_successful_training_artifact_to_v18(monkeypatch) -> None:
    workspace = wid("learning")
    plan = create_adaptation_plan(workspace)

    class FakeTrainer:
        def post_json(self, path, payload, timeout=20.0):
            if path == "/train/jobs":
                assert payload["base_model_id"] == "base-model"
                assert payload["requested_artifact_model_id"] == "adapter-model"
                assert len(payload["command_manifest_sha256"]) == 64
                return {"job_id": "remote-train-1", "status": "QUEUED"}
            if path == "/train/jobs/status":
                return {
                    "status": "SUCCEEDED",
                    "artifact": {
                        "adapter_model_id": "adapter-model",
                        "artifact_sha256": "d" * 64,
                        "training_config_sha256": "e" * 64,
                        "artifact_size_bytes": 123456,
                        "trainer_attestation_refs": ["attestation:v20:1"],
                        "base_model_fingerprint": "base-model-fingerprint-v20",
                    },
                }
            raise AssertionError(path)

    monkeypatch.setattr(learningmod, "_training_provider", lambda: FakeTrainer())

    job = LEARNING_V20.create(
        workspace,
        TrainingJobCreate(
            plan_id=plan.plan_id,
            trainer_name="isolated-trainer",
            requested_artifact_model_id="adapter-model",
            epochs=2,
            seed=42,
        ),
    )
    assert job.status == "PREPARED"
    assert len(job.command_manifest_sha256) == 64

    submitted = LEARNING_V20.submit(workspace, job.job_id)
    assert submitted.status == "SUBMITTED"
    assert submitted.remote_job_id == "remote-train-1"

    completed = LEARNING_V20.refresh(workspace, job.job_id)
    assert completed.status == "SUCCEEDED"
    assert completed.artifact is not None
    assert completed.artifact.artifact_sha256 == "d" * 64

    handed_off = LEARNING_V20.register_candidate(workspace, job.job_id)
    assert handed_off.status == "CANDIDATE_REGISTERED"
    assert handed_off.registered_candidate_id is not None
    candidate = V18.get_candidate(workspace, handed_off.registered_candidate_id)
    assert candidate is not None
    assert candidate.adapter_model_id == "adapter-model"
    assert candidate.status == "CANDIDATE"


def test_learning_engine_refuses_provider_artifact_model_mismatch(monkeypatch) -> None:
    workspace = wid("learning-mismatch")
    plan = create_adaptation_plan(workspace)

    class BadTrainer:
        def post_json(self, path, payload, timeout=20.0):
            if path == "/train/jobs":
                return {"job_id": "remote-bad"}
            return {
                "status": "SUCCEEDED",
                "artifact": {
                    "adapter_model_id": "wrong-model",
                    "artifact_sha256": "d" * 64,
                    "training_config_sha256": "e" * 64,
                    "artifact_size_bytes": 100,
                    "trainer_attestation_refs": ["attestation:bad"],
                    "base_model_fingerprint": "base-model-fingerprint-v20",
                },
            }

    monkeypatch.setattr(learningmod, "_training_provider", lambda: BadTrainer())
    job = LEARNING_V20.create(
        workspace,
        TrainingJobCreate(
            plan_id=plan.plan_id,
            trainer_name="bad-trainer",
            requested_artifact_model_id="adapter-model",
        ),
    )
    LEARNING_V20.submit(workspace, job.job_id)
    with pytest.raises(RuntimeError, match="training_artifact_model_id_mismatch"):
        LEARNING_V20.refresh(workspace, job.job_id)


def test_skill_invention_becomes_promotable_only_after_own_cross_domain_trials(monkeypatch) -> None:
    workspace = wid("invent")
    output = {
        "skill_id": "invented-analysis",
        "display_name": "Invented Analysis",
        "description": "A bounded reusable analysis and verification procedure.",
        "procedure_steps": ["decompose problem", "collect evidence", "verify claims", "record result"],
        "capabilities": ["analysis", "verification"],
        "required_tool_ids": [],
        "risk_tier": "moderate",
        "trial_scenarios": [
            {"task_id": "inv-trial-1", "domain": "engineering", "description": "engineering one", "expected_invariants": ["traceable"], "novelty": 0.80},
            {"task_id": "inv-trial-2", "domain": "engineering", "description": "engineering two", "expected_invariants": ["traceable"], "novelty": 0.75},
            {"task_id": "inv-trial-3", "domain": "engineering", "description": "engineering three", "expected_invariants": ["traceable"], "novelty": 0.70},
            {"task_id": "inv-trial-4", "domain": "operations", "description": "operations one", "expected_invariants": ["traceable"], "novelty": 0.85},
            {"task_id": "inv-trial-5", "domain": "operations", "description": "operations two", "expected_invariants": ["traceable"], "novelty": 0.90},
        ],
    }

    def fake_generate(self, *, model_id: str, prompt: str):
        assert "Do not include executable code" in prompt
        return {"output": __import__("json").dumps(output), "confidence": 0.9, "provider_response_sha256": "0" * 64}

    monkeypatch.setattr(skillmod.GovernedHttpModelAdapter, "generate", fake_generate)

    proposal = SKILL_INVENTION_V20.invent(
        workspace,
        SkillInventionRequest(
            model_id="planner-model",
            objective="Invent a reusable cross-domain verification skill",
            source_task_ids=["source-a", "source-b"],
            source_evidence_refs=["trace:a", "trace:b"],
            target_domains=["engineering", "operations"],
            allowed_tool_ids=[],
            maximum_risk_tier="moderate",
        ),
    )
    assert proposal.skill_id == "invented-analysis"
    assert len(proposal.trial_scenarios) == 5

    results = [
        SandboxTrialResult(
            task_id=scenario.task_id,
            domain=scenario.domain,
            success=True,
            evidence_coverage=0.95,
            confidence=0.90,
            regression_safe=True,
            novelty=scenario.novelty,
            evidence_refs=[f"trial-evidence:{scenario.task_id}"],
        )
        for scenario in proposal.trial_scenarios
    ]
    evaluated = SKILL_INVENTION_V20.evaluate_manual(
        workspace,
        proposal.invention_id,
        ManualEvaluationRequest(trial_results=results),
    )
    assert evaluated.candidate_decision.status == "PROMOTABLE"
    assert evaluated.candidate_decision.v16_eligible is True

    with pytest.raises(ValueError, match="skill_invention_already_evaluated"):
        SKILL_INVENTION_V20.evaluate_manual(
            workspace,
            proposal.invention_id,
            ManualEvaluationRequest(trial_results=results),
        )


def test_multimodal_consensus_writes_temporal_world_fact(monkeypatch) -> None:
    workspace = wid("fusion")
    now = int(time.time())
    monkeypatch.setenv("ORBYTHRA_MULTIMODAL_ALLOWED_ADAPTERS", "vision@1,sensor@1")
    bundle = MultimodalBundleRequest(
        case_id="case-v20",
        artifacts=[
            MultimodalArtifact(
                artifact_id="img-1",
                modality="image",
                content_sha256="1" * 64,
                metadata_sha256="2" * 64,
                source_id="camera-a",
                source_lineage_id="camera-lineage",
                mime_type="image/png",
                byte_size=1000,
                captured_at=now - 10,
                acquired_at=now - 5,
                claim_ids=["pressure-claim"],
            ),
            MultimodalArtifact(
                artifact_id="sensor-1",
                modality="sensor",
                content_sha256="3" * 64,
                metadata_sha256="4" * 64,
                source_id="sensor-a",
                source_lineage_id="sensor-lineage",
                mime_type="application/json",
                byte_size=100,
                captured_at=now - 9,
                acquired_at=now - 4,
                claim_ids=["pressure-claim"],
            ),
        ],
        required_modalities=["image", "sensor"],
        minimum_modalities=2,
        minimum_independent_lineages=2,
    )
    interpretations = [
        ArtifactInterpretation(
            artifact_id="img-1",
            modality="image",
            content_sha256="1" * 64,
            adapter_id="vision",
            adapter_version="1",
            adapter_output_sha256="5" * 64,
            claims=[
                SemanticClaim(
                    claim_id="claim-image-pressure",
                    subject="line-a",
                    predicate="pressure_bar",
                    value=8.5,
                    domain="engineering",
                    confidence=0.95,
                    observed_at=now - 10,
                    valid_from=now - 100,
                    valid_to=now + 100,
                )
            ],
        ),
        ArtifactInterpretation(
            artifact_id="sensor-1",
            modality="sensor",
            content_sha256="3" * 64,
            adapter_id="sensor",
            adapter_version="1",
            adapter_output_sha256="6" * 64,
            claims=[
                SemanticClaim(
                    claim_id="claim-sensor-pressure",
                    subject="line-a",
                    predicate="pressure_bar",
                    value=8.5,
                    domain="engineering",
                    confidence=0.97,
                    observed_at=now - 9,
                    valid_from=now - 100,
                    valid_to=now + 100,
                )
            ],
        ),
    ]
    fused = MULTIMODAL_FUSION_V20.fuse(
        workspace,
        MultimodalFusionRequest(bundle=bundle, interpretations=interpretations),
    )
    assert fused.fusion_status == "FUSED"
    assert len(fused.created_world_facts) == 1
    assert fused.created_world_facts[0].value == 8.5
    queried = CONTINUAL_V16.query_facts(
        workspace,
        WorldFactQuery(subject="line-a", predicate="pressure_bar", valid_at=now),
    )
    assert any(fact.value == 8.5 for fact in queried.facts)


def test_multimodal_supported_conflict_blocks_world_fact(monkeypatch) -> None:
    workspace = wid("conflict")
    now = int(time.time())
    monkeypatch.setenv("ORBYTHRA_MULTIMODAL_ALLOWED_ADAPTERS", "vision@1,sensor@1")
    bundle = MultimodalBundleRequest(
        case_id="case-conflict",
        artifacts=[
            MultimodalArtifact(
                artifact_id="img-c",
                modality="image",
                content_sha256="7" * 64,
                metadata_sha256="8" * 64,
                source_id="camera-c",
                source_lineage_id="camera-lineage-c",
                mime_type="image/png",
                byte_size=1000,
                acquired_at=now,
            ),
            MultimodalArtifact(
                artifact_id="sensor-c",
                modality="sensor",
                content_sha256="9" * 64,
                metadata_sha256="a" * 64,
                source_id="sensor-c",
                source_lineage_id="sensor-lineage-c",
                mime_type="application/json",
                byte_size=100,
                acquired_at=now,
            ),
        ],
        minimum_modalities=2,
        minimum_independent_lineages=2,
    )
    interpretations = [
        ArtifactInterpretation(
            artifact_id="img-c",
            modality="image",
            content_sha256="7" * 64,
            adapter_id="vision",
            adapter_version="1",
            adapter_output_sha256="b" * 64,
            claims=[
                SemanticClaim(
                    claim_id="claim-conflict-a",
                    subject="asset-c",
                    predicate="state",
                    value="open",
                    domain="engineering",
                    confidence=0.95,
                )
            ],
        ),
        ArtifactInterpretation(
            artifact_id="sensor-c",
            modality="sensor",
            content_sha256="9" * 64,
            adapter_id="sensor",
            adapter_version="1",
            adapter_output_sha256="c" * 64,
            claims=[
                SemanticClaim(
                    claim_id="claim-conflict-b",
                    subject="asset-c",
                    predicate="state",
                    value="closed",
                    domain="engineering",
                    confidence=0.96,
                )
            ],
        ),
    ]
    fused = MULTIMODAL_FUSION_V20.fuse(
        workspace,
        MultimodalFusionRequest(bundle=bundle, interpretations=interpretations),
    )
    assert fused.fusion_status == "CONFLICT"
    assert len(fused.conflicts) == 1
    assert fused.created_world_facts == []
