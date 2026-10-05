from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/multimodal", tags=["v15-multimodal-evidence"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

Modality = Literal["text", "image", "audio", "video", "document", "sensor", "structured_data"]


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class MultimodalArtifact(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=200)
    modality: Modality
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1, max_length=300)
    source_lineage_id: str | None = Field(default=None, max_length=300)
    mime_type: str = Field(min_length=1, max_length=200)
    byte_size: int = Field(ge=0, le=10_000_000_000)
    captured_at: int | None = None
    acquired_at: int
    claim_ids: list[str] = Field(default_factory=list, max_length=500)

    @property
    def lineage_identity(self) -> str:
        return self.source_lineage_id or self.source_id


class MultimodalBundleRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=200)
    artifacts: list[MultimodalArtifact] = Field(min_length=1, max_length=1000)
    required_modalities: list[Modality] = Field(default_factory=list, max_length=7)
    minimum_modalities: int = Field(default=1, ge=1, le=7)
    minimum_independent_lineages: int = Field(default=1, ge=1, le=1000)
    maximum_artifact_age_seconds: int = Field(default=31_536_000, ge=1, le=315_360_000)
    maximum_future_skew_seconds: int = Field(default=300, ge=0, le=3600)

    @model_validator(mode="after")
    def unique_artifact_ids(self):
        ids = [item.artifact_id for item in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_multimodal_artifact_id")
        return self


class ModalitySummary(BaseModel):
    modality: Modality
    artifact_count: int
    independent_lineages: int
    unique_content_hashes: int


class MultimodalBundleResponse(BaseModel):
    bundle_id: str
    case_id: str
    status: Literal["VERIFIED_STRUCTURE", "INSUFFICIENT_EVIDENCE", "INVALID"]
    manifest_sha256: str
    modality_count: int
    independent_lineages: int
    summaries: list[ModalitySummary]
    stale_artifact_ids: list[str]
    invalid_artifact_ids: list[str]
    missing_required_modalities: list[str]
    duplicated_content_groups: list[list[str]]
    claim_coverage: dict[str, int]
    receipt_sha256: str
    boundary: str = (
        "V15 verifies multimodal artifact integrity, provenance structure, lineage independence, timing and claim coverage. "
        "It does not by itself perform image/audio/video semantic interpretation or prove that different modalities agree on factual meaning."
    )


class MultimodalStoreV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS multimodal_bundles_v15(
                    bundle_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    artifact_count INTEGER NOT NULL,
                    modality_count INTEGER NOT NULL,
                    independent_lineages INTEGER NOT NULL,
                    created_at BIGINT NOT NULL
                    )"""
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_multimodal_v15_case ON multimodal_bundles_v15(workspace_id,case_id,created_at)"))

    def persist(self, workspace_id: str, response: MultimodalBundleResponse, artifact_count: int, *, now: int) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO multimodal_bundles_v15(
                    bundle_id,workspace_id,case_id,status,manifest_sha256,receipt_sha256,
                    artifact_count,modality_count,independent_lineages,created_at
                    ) VALUES(:id,:w,:case,:status,:manifest,:receipt,:artifacts,:modalities,:lineages,:created)"""
                ),
                {
                    "id": response.bundle_id,
                    "w": workspace_id,
                    "case": response.case_id,
                    "status": response.status,
                    "manifest": response.manifest_sha256,
                    "receipt": response.receipt_sha256,
                    "artifacts": artifact_count,
                    "modalities": response.modality_count,
                    "lineages": response.independent_lineages,
                    "created": now,
                },
            )


MULTIMODAL_STORE_V15 = MultimodalStoreV15()


def verify_bundle(workspace_id: str, body: MultimodalBundleRequest, *, now: int | None = None) -> MultimodalBundleResponse:
    current_time = int(time.time()) if now is None else int(now)
    stale: list[str] = []
    invalid: list[str] = []
    content_groups: dict[str, list[str]] = defaultdict(list)
    modality_groups: dict[str, list[MultimodalArtifact]] = defaultdict(list)
    lineages: set[str] = set()
    claim_coverage: dict[str, int] = defaultdict(int)

    for artifact in body.artifacts:
        content_groups[artifact.content_sha256].append(artifact.artifact_id)
        modality_groups[artifact.modality].append(artifact)
        lineages.add(artifact.lineage_identity)
        for claim_id in sorted(set(artifact.claim_ids)):
            claim_coverage[claim_id] += 1
        if artifact.acquired_at > current_time + body.maximum_future_skew_seconds:
            invalid.append(artifact.artifact_id + ":future_acquisition")
        elif current_time - artifact.acquired_at > body.maximum_artifact_age_seconds:
            stale.append(artifact.artifact_id)
        if artifact.captured_at is not None:
            if artifact.captured_at > artifact.acquired_at + body.maximum_future_skew_seconds:
                invalid.append(artifact.artifact_id + ":capture_after_acquisition")
            if artifact.captured_at > current_time + body.maximum_future_skew_seconds:
                invalid.append(artifact.artifact_id + ":future_capture")

    present_modalities = set(modality_groups)
    missing = sorted(set(body.required_modalities) - present_modalities)
    summaries: list[ModalitySummary] = []
    for modality in sorted(modality_groups):
        artifacts = modality_groups[modality]
        summaries.append(
            ModalitySummary(
                modality=modality,
                artifact_count=len(artifacts),
                independent_lineages=len({item.lineage_identity for item in artifacts}),
                unique_content_hashes=len({item.content_sha256 for item in artifacts}),
            )
        )

    duplicates = sorted(
        [sorted(ids) for ids in content_groups.values() if len(ids) > 1],
        key=lambda group: group[0],
    )
    manifest_items = [
        {
            "artifact_id": item.artifact_id,
            "modality": item.modality,
            "content_sha256": item.content_sha256,
            "metadata_sha256": item.metadata_sha256,
            "source_id": item.source_id,
            "source_lineage_id": item.source_lineage_id,
            "mime_type": item.mime_type,
            "byte_size": item.byte_size,
            "captured_at": item.captured_at,
            "acquired_at": item.acquired_at,
            "claim_ids": sorted(set(item.claim_ids)),
        }
        for item in sorted(body.artifacts, key=lambda artifact: artifact.artifact_id)
    ]
    manifest_sha = _hash(
        {
            "domain": "ORBYTHRA-V15-MULTIMODAL-MANIFEST",
            "workspace_id": workspace_id,
            "case_id": body.case_id,
            "artifacts": manifest_items,
        }
    )

    if invalid:
        status: Literal["VERIFIED_STRUCTURE", "INSUFFICIENT_EVIDENCE", "INVALID"] = "INVALID"
    elif stale or missing or len(present_modalities) < body.minimum_modalities or len(lineages) < body.minimum_independent_lineages:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        status = "VERIFIED_STRUCTURE"

    bundle_id = "mm15_" + uuid.uuid4().hex[:24]
    receipt_payload = {
        "domain": "ORBYTHRA-V15-MULTIMODAL-RECEIPT",
        "workspace_id": workspace_id,
        "bundle_id": bundle_id,
        "case_id": body.case_id,
        "status": status,
        "manifest_sha256": manifest_sha,
        "modality_count": len(present_modalities),
        "independent_lineages": len(lineages),
        "stale_artifact_ids": sorted(stale),
        "invalid_artifact_ids": sorted(invalid),
        "missing_required_modalities": missing,
    }
    response = MultimodalBundleResponse(
        bundle_id=bundle_id,
        case_id=body.case_id,
        status=status,
        manifest_sha256=manifest_sha,
        modality_count=len(present_modalities),
        independent_lineages=len(lineages),
        summaries=summaries,
        stale_artifact_ids=sorted(set(stale)),
        invalid_artifact_ids=sorted(set(invalid)),
        missing_required_modalities=missing,
        duplicated_content_groups=duplicates,
        claim_coverage=dict(sorted(claim_coverage.items())),
        receipt_sha256=_hash(receipt_payload),
    )
    MULTIMODAL_STORE_V15.persist(workspace_id, response, len(body.artifacts), now=current_time)
    return response


@router.post("/bundles/verify", response_model=MultimodalBundleResponse)
def verify(body: MultimodalBundleRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> MultimodalBundleResponse:
    try:
        result = verify_bundle(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.bundle_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="multimodal_evidence_v15",
        status=result.status,
        metadata={
            "bundle_id": result.bundle_id,
            "case_id": result.case_id,
            "manifest_sha256": result.manifest_sha256,
            "receipt_sha256": result.receipt_sha256,
            "modality_count": result.modality_count,
            "independent_lineages": result.independent_lineages,
        },
    )
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "modalities": ["text", "image", "audio", "video", "document", "sensor", "structured_data"],
        "content_and_metadata_hash_binding": True,
        "source_lineage_independence": True,
        "capture_and_acquisition_time_checks": True,
        "duplicate_content_detection": True,
        "claim_to_artifact_coverage": True,
        "tamper_evident_manifest_receipt": True,
        "semantic_cross_modal_entailment": False,
        "native_media_decoding": False,
        "boundary": "Semantic media understanding requires approved modality adapters and remains a separate validation gate.",
    }
