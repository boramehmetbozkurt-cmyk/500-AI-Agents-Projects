from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.governed_model_adaptation_v18 import CandidateArtifactRegister, V18
from app.providers import JsonHttpProvider
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v20/learning", tags=["v20-learning-engine"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_ADMIN = require_minimum_role("admin")

TrainingStatus = Literal[
    "PREPARED",
    "SUBMITTED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "CANDIDATE_REGISTERED",
]


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _training_provider() -> JsonHttpProvider | None:
    url = os.getenv("ORBYTHRA_TRAINING_PROVIDER_URL", "").strip()
    if not url:
        return None
    return JsonHttpProvider(url, "ORBYTHRA_TRAINING_PROVIDER_TOKEN")


class TrainingJobCreate(BaseModel):
    plan_id: str = Field(min_length=1, max_length=120)
    trainer_name: str = Field(min_length=1, max_length=200)
    trainer_profile: str = Field(default="adapter-training-v1", min_length=1, max_length=200)
    epochs: int = Field(default=1, ge=1, le=1000)
    learning_rate: float = Field(default=0.0002, gt=0.0, le=1.0)
    batch_size: int = Field(default=4, ge=1, le=100_000)
    gradient_accumulation_steps: int = Field(default=1, ge=1, le=100_000)
    max_train_seconds: int = Field(default=21_600, ge=60, le=2_592_000)
    seed: int = Field(default=17, ge=0, le=2_147_483_647)
    requested_artifact_model_id: str = Field(min_length=1, max_length=160)
    training_constraints: list[str] = Field(default_factory=list, max_length=100)


class TrainingArtifact(BaseModel):
    adapter_model_id: str = Field(min_length=1, max_length=160)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_size_bytes: int = Field(ge=1, le=10_000_000_000_000)
    trainer_attestation_refs: list[str] = Field(min_length=1, max_length=100)
    base_model_fingerprint: str = Field(min_length=8, max_length=500)


class TrainingJob(BaseModel):
    job_id: str
    plan_id: str
    trainer_name: str
    trainer_profile: str
    epochs: int
    learning_rate: float
    batch_size: int
    gradient_accumulation_steps: int
    max_train_seconds: int
    seed: int
    requested_artifact_model_id: str
    training_constraints: list[str]
    status: TrainingStatus
    remote_job_id: str | None
    command_manifest_sha256: str
    trainer_response_sha256: str | None
    artifact: TrainingArtifact | None
    registered_candidate_id: str | None
    created_at: int
    updated_at: int


class TrainingRefreshRequest(BaseModel):
    timeout_seconds: float = Field(default=20.0, gt=0.0, le=120.0)


class LearningEngineV20:
    def __init__(self) -> None:
        self.engine = STORE.engine
        with self.engine.begin() as connection:
            connection.execute(text(
                """CREATE TABLE IF NOT EXISTS learning_jobs_v20(
                workspace_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                remote_job_id TEXT,
                command_manifest_sha256 TEXT NOT NULL,
                trainer_response_sha256 TEXT,
                artifact_json TEXT,
                registered_candidate_id TEXT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,job_id)
                )"""
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_learning_v20_plan ON learning_jobs_v20(workspace_id,plan_id,created_at)"
            ))

    def _plan_or_error(self, workspace_id: str, plan_id: str):
        plan = V18.get_plan(workspace_id, plan_id)
        if plan is None:
            raise ValueError("learning_adaptation_plan_not_found")
        if plan.status not in {"PLANNED", "CANDIDATE"}:
            raise ValueError("learning_adaptation_plan_not_trainable")
        return plan

    def create(self, workspace_id: str, body: TrainingJobCreate) -> TrainingJob:
        plan = self._plan_or_error(workspace_id, body.plan_id)
        if body.requested_artifact_model_id == plan.base_model_id:
            raise ValueError("learning_artifact_model_must_differ_from_base")
        now = int(time.time())
        job_id = "lrn20_" + uuid.uuid4().hex[:24]
        payload = body.model_dump(mode="json")
        command_manifest = {
            "domain": "ORBYTHRA-V20-TRAINING-MANIFEST",
            "workspace_id": workspace_id,
            "job_id": job_id,
            "plan_id": plan.plan_id,
            "provider_id": plan.provider_id,
            "base_model_id": plan.base_model_id,
            "adaptation_kind": plan.adaptation_kind,
            "dataset": plan.dataset.model_dump(mode="json"),
            "target_capabilities": plan.target_capabilities,
            "training": payload,
        }
        manifest_sha = _hash(command_manifest)
        with self.engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO learning_jobs_v20(
                workspace_id,job_id,plan_id,payload_json,status,remote_job_id,command_manifest_sha256,
                trainer_response_sha256,artifact_json,registered_candidate_id,created_at,updated_at
                ) VALUES(:w,:job,:plan,:payload,'PREPARED',NULL,:manifest,NULL,NULL,NULL,:created,:updated)"""
            ), {
                "w": workspace_id,
                "job": job_id,
                "plan": body.plan_id,
                "payload": VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="learning-job-v20"),
                "manifest": manifest_sha,
                "created": now,
                "updated": now,
            })
        result = self.get(workspace_id, job_id)
        if result is None:
            raise RuntimeError("learning_job_not_persisted")
        return result

    def get(self, workspace_id: str, job_id: str) -> TrainingJob | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT * FROM learning_jobs_v20 WHERE workspace_id=:w AND job_id=:job"
            ), {"w": workspace_id, "job": job_id}).mappings().first()
        if row is None:
            return None
        payload = VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="learning-job-v20")
        artifact = None
        if row["artifact_json"]:
            artifact = TrainingArtifact.model_validate(
                VAULT.decrypt_json(row["artifact_json"], workspace_id=workspace_id, purpose="learning-artifact-v20")
            )
        return TrainingJob(
            job_id=row["job_id"],
            **payload,
            status=row["status"],
            remote_job_id=row["remote_job_id"],
            command_manifest_sha256=row["command_manifest_sha256"],
            trainer_response_sha256=row["trainer_response_sha256"],
            artifact=artifact,
            registered_candidate_id=row["registered_candidate_id"],
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def submit(self, workspace_id: str, job_id: str) -> TrainingJob:
        job = self.get(workspace_id, job_id)
        if job is None:
            raise ValueError("learning_job_not_found")
        if job.status != "PREPARED":
            raise ValueError("learning_job_not_prepared")
        plan = self._plan_or_error(workspace_id, job.plan_id)
        provider = _training_provider()
        if provider is None:
            raise RuntimeError("training_provider_not_configured")
        request_payload = {
            "job_id": job.job_id,
            "command_manifest_sha256": job.command_manifest_sha256,
            "base_model_id": plan.base_model_id,
            "adaptation_kind": plan.adaptation_kind,
            "dataset": plan.dataset.model_dump(mode="json"),
            "target_capabilities": plan.target_capabilities,
            "trainer_profile": job.trainer_profile,
            "epochs": job.epochs,
            "learning_rate": job.learning_rate,
            "batch_size": job.batch_size,
            "gradient_accumulation_steps": job.gradient_accumulation_steps,
            "max_train_seconds": job.max_train_seconds,
            "seed": job.seed,
            "requested_artifact_model_id": job.requested_artifact_model_id,
            "training_constraints": job.training_constraints,
        }
        response = provider.post_json("/train/jobs", request_payload, timeout=30.0)
        remote_job_id = response.get("job_id")
        if not isinstance(remote_job_id, str) or not remote_job_id.strip():
            raise RuntimeError("training_provider_invalid_job_id")
        response_sha = _hash(response)
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """UPDATE learning_jobs_v20
                SET status='SUBMITTED',remote_job_id=:remote,trainer_response_sha256=:response_sha,updated_at=:updated
                WHERE workspace_id=:w AND job_id=:job"""
            ), {
                "remote": remote_job_id.strip(),
                "response_sha": response_sha,
                "updated": now,
                "w": workspace_id,
                "job": job_id,
            })
        result = self.get(workspace_id, job_id)
        assert result is not None
        return result

    def refresh(self, workspace_id: str, job_id: str, timeout_seconds: float = 20.0) -> TrainingJob:
        job = self.get(workspace_id, job_id)
        if job is None:
            raise ValueError("learning_job_not_found")
        if job.status not in {"SUBMITTED", "RUNNING"}:
            raise ValueError("learning_job_not_refreshable")
        if not job.remote_job_id:
            raise RuntimeError("learning_remote_job_missing")
        provider = _training_provider()
        if provider is None:
            raise RuntimeError("training_provider_not_configured")
        response = provider.post_json(
            "/train/jobs/status",
            {"job_id": job.remote_job_id, "command_manifest_sha256": job.command_manifest_sha256},
            timeout=timeout_seconds,
        )
        remote_status = str(response.get("status") or "").strip().upper()
        mapping = {
            "QUEUED": "SUBMITTED",
            "SUBMITTED": "SUBMITTED",
            "RUNNING": "RUNNING",
            "SUCCEEDED": "SUCCEEDED",
            "FAILED": "FAILED",
            "CANCELLED": "CANCELLED",
        }
        status = mapping.get(remote_status)
        if status is None:
            raise RuntimeError("training_provider_invalid_status")
        artifact_payload = None
        if status == "SUCCEEDED":
            artifact_payload = response.get("artifact")
            if not isinstance(artifact_payload, dict):
                raise RuntimeError("training_provider_missing_artifact")
            artifact = TrainingArtifact.model_validate(artifact_payload)
            if artifact.adapter_model_id != job.requested_artifact_model_id:
                raise RuntimeError("training_artifact_model_id_mismatch")
            artifact_payload = artifact.model_dump(mode="json")
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """UPDATE learning_jobs_v20
                SET status=:status,trainer_response_sha256=:response_sha,artifact_json=:artifact,updated_at=:updated
                WHERE workspace_id=:w AND job_id=:job"""
            ), {
                "status": status,
                "response_sha": _hash(response),
                "artifact": None if artifact_payload is None else VAULT.encrypt_json(
                    artifact_payload, workspace_id=workspace_id, purpose="learning-artifact-v20"
                ),
                "updated": now,
                "w": workspace_id,
                "job": job_id,
            })
        result = self.get(workspace_id, job_id)
        assert result is not None
        return result

    def register_candidate(self, workspace_id: str, job_id: str) -> TrainingJob:
        job = self.get(workspace_id, job_id)
        if job is None:
            raise ValueError("learning_job_not_found")
        if job.status != "SUCCEEDED" or job.artifact is None:
            raise ValueError("learning_job_not_successful")
        candidate = V18.register_candidate(
            workspace_id,
            job.plan_id,
            CandidateArtifactRegister(
                adapter_model_id=job.artifact.adapter_model_id,
                training_run_ref=job.remote_job_id or job.job_id,
                trainer_name=job.trainer_name,
                artifact_sha256=job.artifact.artifact_sha256,
                training_config_sha256=job.artifact.training_config_sha256,
                artifact_size_bytes=job.artifact.artifact_size_bytes,
                trainer_attestation_refs=job.artifact.trainer_attestation_refs,
                base_model_fingerprint=job.artifact.base_model_fingerprint,
            ),
        )
        now = int(time.time())
        with self.engine.begin() as connection:
            connection.execute(text(
                """UPDATE learning_jobs_v20
                SET status='CANDIDATE_REGISTERED',registered_candidate_id=:candidate,updated_at=:updated
                WHERE workspace_id=:w AND job_id=:job"""
            ), {
                "candidate": candidate.candidate_id,
                "updated": now,
                "w": workspace_id,
                "job": job_id,
            })
        result = self.get(workspace_id, job_id)
        assert result is not None
        return result


LEARNING_V20 = LearningEngineV20()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", action),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata={"role": principal.role, **metadata},
    )


@router.post("/jobs", response_model=TrainingJob)
def create_job(body: TrainingJobCreate, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> TrainingJob:
    try:
        result = LEARNING_V20.create(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v20_learning_create", result.status, {"job_id": result.job_id, "plan_id": result.plan_id})
    return result


@router.get("/jobs/{job_id}", response_model=TrainingJob)
def get_job(job_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> TrainingJob:
    result = LEARNING_V20.get(principal.workspace_id, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="learning_job_not_found")
    return result


@router.post("/jobs/{job_id}/submit", response_model=TrainingJob)
def submit_job(job_id: str, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> TrainingJob:
    try:
        result = LEARNING_V20.submit(principal.workspace_id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit(request, principal, "v20_learning_submit", result.status, {"job_id": job_id, "remote_job_id": result.remote_job_id})
    return result


@router.post("/jobs/{job_id}/refresh", response_model=TrainingJob)
def refresh_job(job_id: str, body: TrainingRefreshRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> TrainingJob:
    try:
        result = LEARNING_V20.refresh(principal.workspace_id, job_id, body.timeout_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit(request, principal, "v20_learning_refresh", result.status, {"job_id": job_id})
    return result


@router.post("/jobs/{job_id}/register-candidate", response_model=TrainingJob)
def register_candidate(job_id: str, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> TrainingJob:
    try:
        result = LEARNING_V20.register_candidate(principal.workspace_id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, principal, "v20_learning_register_candidate", result.status, {"job_id": job_id, "candidate_id": result.registered_candidate_id})
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v20",
        "training_job_orchestration": True,
        "dataset_manifest_binding": True,
        "training_config_hash_binding": True,
        "trainer_attestation_required": True,
        "v18_candidate_handoff": True,
        "benchmark_and_canary_required_after_training": True,
        "trainer_provider_configured": _training_provider() is not None,
        "foundation_model_training_embedded_in_api_process": False,
        "unrestricted_self_modification": False,
        "live_agi_claim": False,
        "boundary": (
            "V20 Learning Engine controls adapter-training job manifests, trainer handoff, artifact verification and V18 candidate registration. "
            "Actual GPU training runs in an explicitly configured trainer service; trained artifacts still must pass V18 benchmark and canary gates."
        ),
    }
