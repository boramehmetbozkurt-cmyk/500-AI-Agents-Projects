from __future__ import annotations

import hashlib
import math
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/visual-identity", tags=["v15-visual-identity"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

VisualOperation = Literal[
    "super_resolution",
    "background_removal",
    "denoise",
    "deblur",
    "compression_artifact_removal",
    "color_restoration",
    "exposure_correction",
]


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _constraints(operations: list[str]) -> list[str]:
    constraints = [
        "preserve_source_face_identity",
        "preserve_face_geometry",
        "forbid_face_beautification",
        "forbid_face_reconstruction",
        "generate_difference_map",
        "reject_output_on_identity_threshold_failure",
    ]
    if "background_removal" in operations:
        constraints.append("background_only_segmentation")
    return constraints


def _plan_payload(
    source_image_sha256: str,
    source_width: int,
    source_height: int,
    operations: list[str],
    locked_face_ids: list[str],
    immutable_constraints: list[str],
) -> dict[str, object]:
    return {
        "domain": "ORBYTHRA-V15-VISUAL-RESTORATION-PLAN",
        "source_image_sha256": source_image_sha256,
        "source_width": source_width,
        "source_height": source_height,
        "operations": operations,
        "locked_face_ids": locked_face_ids,
        "immutable_constraints": immutable_constraints,
    }


class VisualRestorationPlanRequest(BaseModel):
    source_image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operations: list[VisualOperation] = Field(min_length=1, max_length=20)
    source_width: int = Field(ge=1, le=100000)
    source_height: int = Field(ge=1, le=100000)
    detected_face_ids: list[str] = Field(default_factory=list, max_length=100)
    lock_all_detected_faces: bool = True
    preserve_face_geometry: bool = True
    forbid_face_beautification: bool = True
    forbid_face_reconstruction: bool = True

    @model_validator(mode="after")
    def identity_safety_defaults(self):
        if self.detected_face_ids and not self.lock_all_detected_faces:
            raise ValueError("v15_requires_all_detected_faces_locked")
        if self.detected_face_ids and not self.preserve_face_geometry:
            raise ValueError("v15_requires_face_geometry_preservation")
        if self.detected_face_ids and (not self.forbid_face_beautification or not self.forbid_face_reconstruction):
            raise ValueError("v15_requires_face_reconstruction_and_beautification_forbidden")
        if len(self.operations) != len(set(self.operations)):
            raise ValueError("duplicate_visual_operation")
        if len(self.detected_face_ids) != len(set(self.detected_face_ids)):
            raise ValueError("duplicate_detected_face_id")
        return self


class VisualRestorationPlan(BaseModel):
    plan_id: str
    source_image_sha256: str
    source_width: int
    source_height: int
    operations: list[VisualOperation]
    locked_face_ids: list[str]
    immutable_constraints: list[str]
    plan_sha256: str
    created_at: int


class FaceFidelityMetric(BaseModel):
    face_id: str = Field(min_length=1, max_length=200)
    identity_embedding_similarity: float = Field(ge=-1, le=1)
    normalized_landmark_rmse: float = Field(ge=0, le=10)
    face_region_ssim: float = Field(ge=0, le=1)
    geometry_scale_drift: float = Field(ge=0, le=10)
    rotation_drift_degrees: float = Field(ge=0, le=180)

    @model_validator(mode="after")
    def finite_values(self):
        for value in (
            self.identity_embedding_similarity,
            self.normalized_landmark_rmse,
            self.face_region_ssim,
            self.geometry_scale_drift,
            self.rotation_drift_degrees,
        ):
            if not math.isfinite(value):
                raise ValueError("visual_identity_metric_must_be_finite")
        return self


class VisualIdentityPolicy(BaseModel):
    minimum_identity_similarity: float = Field(default=0.92, ge=-1, le=1)
    maximum_landmark_rmse: float = Field(default=0.025, ge=0, le=1)
    minimum_face_region_ssim: float = Field(default=0.85, ge=0, le=1)
    maximum_geometry_scale_drift: float = Field(default=0.03, ge=0, le=1)
    maximum_rotation_drift_degrees: float = Field(default=2.0, ge=0, le=45)
    maximum_aspect_ratio_drift: float = Field(default=0.01, ge=0, le=0.5)
    require_background_alpha_if_requested: bool = True


class VisualIdentityEvaluationRequest(BaseModel):
    plan: VisualRestorationPlan
    output_image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_width: int = Field(ge=1, le=100000)
    output_height: int = Field(ge=1, le=100000)
    output_detected_face_ids: list[str] = Field(default_factory=list, max_length=100)
    face_metrics: list[FaceFidelityMetric] = Field(default_factory=list, max_length=100)
    difference_map_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_embedding_model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    landmark_model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metric_adapter_id: str = Field(min_length=1, max_length=200)
    metric_adapter_version: str = Field(min_length=1, max_length=100)
    background_alpha_verified: bool = False
    policy: VisualIdentityPolicy = Field(default_factory=VisualIdentityPolicy)

    @model_validator(mode="after")
    def unique_metric_faces(self):
        ids = [item.face_id for item in self.face_metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_face_fidelity_metric")
        if len(self.output_detected_face_ids) != len(set(self.output_detected_face_ids)):
            raise ValueError("duplicate_output_face_id")
        return self


class FaceGateResult(BaseModel):
    face_id: str
    passed: bool
    failures: list[str]


class VisualIdentityEvaluationResponse(BaseModel):
    evaluation_id: str
    status: Literal["PASS", "REJECT", "REVIEW"]
    plan_sha256: str
    source_image_sha256: str
    output_image_sha256: str
    face_results: list[FaceGateResult]
    global_failures: list[str]
    difference_map_sha256: str
    metric_models_sha256: str
    receipt_sha256: str
    boundary: str = (
        "V15 is a fail-closed identity-preservation assurance gate over measurements supplied by a declared vision adapter. "
        "It does not perform super-resolution, segmentation, face recognition or restoration itself, and PASS is not a legal identity determination."
    )


class VisualIdentityStoreV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS visual_identity_evaluations_v15(
                    evaluation_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    plan_sha256 TEXT NOT NULL,
                    source_image_sha256 TEXT NOT NULL,
                    output_image_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    difference_map_sha256 TEXT NOT NULL,
                    metric_models_sha256 TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    created_at BIGINT NOT NULL
                    )"""
                )
            )

    def persist(self, workspace_id: str, response: VisualIdentityEvaluationResponse, *, now: int) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO visual_identity_evaluations_v15(
                    evaluation_id,workspace_id,plan_sha256,source_image_sha256,output_image_sha256,status,
                    difference_map_sha256,metric_models_sha256,receipt_sha256,created_at
                    ) VALUES(:id,:w,:plan,:src,:out,:status,:diff,:models,:receipt,:created)"""
                ),
                {
                    "id": response.evaluation_id,
                    "w": workspace_id,
                    "plan": response.plan_sha256,
                    "src": response.source_image_sha256,
                    "out": response.output_image_sha256,
                    "status": response.status,
                    "diff": response.difference_map_sha256,
                    "models": response.metric_models_sha256,
                    "receipt": response.receipt_sha256,
                    "created": now,
                },
            )


VISUAL_IDENTITY_STORE_V15 = VisualIdentityStoreV15()


def create_plan(body: VisualRestorationPlanRequest, *, now: int | None = None) -> VisualRestorationPlan:
    created_at = int(time.time()) if now is None else int(now)
    plan_id = "vr15_" + uuid.uuid4().hex[:24]
    operations = sorted(set(body.operations))
    locked_faces = sorted(set(body.detected_face_ids))
    constraints = _constraints(operations)
    plan_payload = _plan_payload(
        body.source_image_sha256,
        body.source_width,
        body.source_height,
        operations,
        locked_faces,
        constraints,
    )
    return VisualRestorationPlan(
        plan_id=plan_id,
        source_image_sha256=body.source_image_sha256,
        source_width=body.source_width,
        source_height=body.source_height,
        operations=operations,
        locked_face_ids=locked_faces,
        immutable_constraints=constraints,
        plan_sha256=_hash(plan_payload),
        created_at=created_at,
    )


def evaluate_identity(workspace_id: str, body: VisualIdentityEvaluationRequest, *, now: int | None = None) -> VisualIdentityEvaluationResponse:
    current_time = int(time.time()) if now is None else int(now)
    global_failures: list[str] = []
    expected_faces = set(body.plan.locked_face_ids)
    output_faces = set(body.output_detected_face_ids)
    metric_by_face = {metric.face_id: metric for metric in body.face_metrics}

    expected_constraints = _constraints(list(body.plan.operations))
    recomputed_plan_sha = _hash(
        _plan_payload(
            body.plan.source_image_sha256,
            body.plan.source_width,
            body.plan.source_height,
            sorted(set(body.plan.operations)),
            sorted(set(body.plan.locked_face_ids)),
            expected_constraints,
        )
    )
    if body.plan.plan_sha256 != recomputed_plan_sha or body.plan.immutable_constraints != expected_constraints:
        global_failures.append("plan_integrity_mismatch")

    if output_faces != expected_faces:
        global_failures.append("detected_face_set_changed")
    if set(metric_by_face) != expected_faces:
        global_failures.append("face_metrics_do_not_cover_locked_faces")
    if "background_removal" in body.plan.operations and body.policy.require_background_alpha_if_requested and not body.background_alpha_verified:
        global_failures.append("background_alpha_not_verified")
    if body.output_image_sha256 == body.plan.source_image_sha256 and body.plan.operations:
        global_failures.append("output_hash_unchanged_despite_requested_operations")

    source_ratio = body.plan.source_width / body.plan.source_height
    output_ratio = body.output_width / body.output_height
    ratio_drift = abs(output_ratio - source_ratio) / source_ratio
    if ratio_drift > body.policy.maximum_aspect_ratio_drift:
        global_failures.append("aspect_ratio_drift_above_threshold")
    if "super_resolution" in body.plan.operations:
        if body.output_width < body.plan.source_width or body.output_height < body.plan.source_height:
            global_failures.append("super_resolution_output_smaller_than_source")
        if body.output_width == body.plan.source_width and body.output_height == body.plan.source_height:
            global_failures.append("super_resolution_dimensions_unchanged")

    face_results: list[FaceGateResult] = []
    for face_id in sorted(expected_faces):
        metric = metric_by_face.get(face_id)
        failures: list[str] = []
        if metric is None:
            failures.append("missing_face_metrics")
        else:
            if metric.identity_embedding_similarity < body.policy.minimum_identity_similarity:
                failures.append("identity_similarity_below_threshold")
            if metric.normalized_landmark_rmse > body.policy.maximum_landmark_rmse:
                failures.append("landmark_drift_above_threshold")
            if metric.face_region_ssim < body.policy.minimum_face_region_ssim:
                failures.append("face_region_ssim_below_threshold")
            if metric.geometry_scale_drift > body.policy.maximum_geometry_scale_drift:
                failures.append("geometry_scale_drift_above_threshold")
            if metric.rotation_drift_degrees > body.policy.maximum_rotation_drift_degrees:
                failures.append("rotation_drift_above_threshold")
        face_results.append(FaceGateResult(face_id=face_id, passed=not failures, failures=failures))

    any_face_failure = any(not item.passed for item in face_results)
    if global_failures or any_face_failure:
        status: Literal["PASS", "REJECT", "REVIEW"] = "REJECT"
    elif not expected_faces:
        status = "REVIEW"
        global_failures.append("no_locked_faces_to_identity_verify")
    else:
        status = "PASS"

    metric_models_sha = _hash(
        {
            "identity_embedding_model_sha256": body.identity_embedding_model_sha256,
            "landmark_model_sha256": body.landmark_model_sha256,
            "metric_adapter_id": body.metric_adapter_id,
            "metric_adapter_version": body.metric_adapter_version,
        }
    )
    evaluation_id = "vi15_" + uuid.uuid4().hex[:24]
    receipt_payload = {
        "domain": "ORBYTHRA-V15-VISUAL-IDENTITY-EVALUATION",
        "workspace_id": workspace_id,
        "evaluation_id": evaluation_id,
        "plan_sha256": body.plan.plan_sha256,
        "source_image_sha256": body.plan.source_image_sha256,
        "output_image_sha256": body.output_image_sha256,
        "difference_map_sha256": body.difference_map_sha256,
        "metric_models_sha256": metric_models_sha,
        "status": status,
        "face_results": [item.model_dump(mode="json") for item in face_results],
        "global_failures": global_failures,
    }
    response = VisualIdentityEvaluationResponse(
        evaluation_id=evaluation_id,
        status=status,
        plan_sha256=body.plan.plan_sha256,
        source_image_sha256=body.plan.source_image_sha256,
        output_image_sha256=body.output_image_sha256,
        face_results=face_results,
        global_failures=global_failures,
        difference_map_sha256=body.difference_map_sha256,
        metric_models_sha256=metric_models_sha,
        receipt_sha256=_hash(receipt_payload),
    )
    VISUAL_IDENTITY_STORE_V15.persist(workspace_id, response, now=current_time)
    return response


@router.post("/plans", response_model=VisualRestorationPlan)
def plan(body: VisualRestorationPlanRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> VisualRestorationPlan:
    try:
        result = create_plan(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.plan_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="visual_restoration_plan_v15",
        status="PLANNED",
        metadata={"plan_id": result.plan_id, "plan_sha256": result.plan_sha256, "operations": result.operations, "locked_face_count": len(result.locked_face_ids)},
    )
    return result


@router.post("/evaluate", response_model=VisualIdentityEvaluationResponse)
def evaluate(body: VisualIdentityEvaluationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> VisualIdentityEvaluationResponse:
    result = evaluate_identity(principal.workspace_id, body)
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.evaluation_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="visual_identity_assurance_v15",
        status=result.status,
        metadata={"evaluation_id": result.evaluation_id, "plan_sha256": result.plan_sha256, "receipt_sha256": result.receipt_sha256},
    )
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "immutable_plan_integrity_check": True,
        "face_region_lock_contract": True,
        "face_geometry_preservation_gate": True,
        "identity_embedding_similarity_gate": True,
        "landmark_drift_gate": True,
        "face_region_ssim_gate": True,
        "difference_map_binding": True,
        "background_alpha_gate": True,
        "super_resolution_dimension_gate": True,
        "aspect_ratio_drift_gate": True,
        "metric_model_version_binding": True,
        "fail_closed_rejection": True,
        "native_restoration_model": False,
        "native_face_metric_model": False,
        "boundary": "The V15 layer defines and enforces restoration fidelity gates; approved image-processing and metric adapters must supply the actual media transformations and measurements.",
    }
