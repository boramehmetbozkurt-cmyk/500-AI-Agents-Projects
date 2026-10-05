from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.continual_generalist_v16 import CONTINUAL_V16, WorldFact, WorldFactCreate
from app.crypto_core import canonical_json
from app.multimodal_evidence_v15 import (
    Modality,
    MultimodalArtifact,
    MultimodalBundleRequest,
    MultimodalBundleResponse,
    verify_bundle,
)
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v20/multimodal", tags=["v20-multimodal-world-fusion"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_OPERATOR = require_minimum_role("operator")


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _allowed_adapters() -> set[str]:
    raw = os.getenv("ORBYTHRA_MULTIMODAL_ALLOWED_ADAPTERS", "").strip()
    return {item.strip() for item in raw.split(",") if item.strip()}


class SemanticClaim(BaseModel):
    claim_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    subject: str = Field(min_length=1, max_length=300)
    predicate: str = Field(min_length=1, max_length=160)
    value: Any
    domain: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: int | None = Field(default=None, ge=0)
    valid_from: int | None = Field(default=None, ge=0)
    valid_to: int | None = Field(default=None, ge=0)


class ArtifactInterpretation(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=200)
    modality: Modality
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_id: str = Field(min_length=1, max_length=200)
    adapter_version: str = Field(min_length=1, max_length=100)
    adapter_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claims: list[SemanticClaim] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_claim_ids(self):
        ids = [claim.claim_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_interpretation_claim_id")
        return self


class MultimodalFusionRequest(BaseModel):
    bundle: MultimodalBundleRequest
    interpretations: list[ArtifactInterpretation] = Field(min_length=1, max_length=1000)
    minimum_modalities_per_fact: int = Field(default=2, ge=1, le=7)
    minimum_lineages_per_fact: int = Field(default=2, ge=1, le=1000)
    minimum_claim_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    minimum_mean_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    reject_any_supported_conflict: bool = True

    @model_validator(mode="after")
    def unique_interpretations(self):
        ids = [item.artifact_id for item in self.interpretations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_artifact_interpretation")
        return self


class FactSupport(BaseModel):
    subject: str
    predicate: str
    value_sha256: str
    modalities: list[str]
    lineages: list[str]
    artifact_ids: list[str]
    adapter_ids: list[str]
    mean_confidence: float
    claim_ids: list[str]
    eligible: bool
    reasons: list[str]


class ConflictGroup(BaseModel):
    subject: str
    predicate: str
    supported_values: list[FactSupport]


class MultimodalFusionResponse(BaseModel):
    bundle: MultimodalBundleResponse
    fusion_status: Literal["FUSED", "PARTIAL", "CONFLICT", "INVALID"]
    supports: list[FactSupport]
    conflicts: list[ConflictGroup]
    created_world_facts: list[WorldFact]
    fusion_sha256: str
    boundary: str


class MultimodalWorldFusionV20:
    def fuse(self, workspace_id: str, body: MultimodalFusionRequest) -> MultimodalFusionResponse:
        bundle_result = verify_bundle(workspace_id, body.bundle)
        if bundle_result.status != "VERIFIED_STRUCTURE":
            payload = {
                "bundle_id": bundle_result.bundle_id,
                "bundle_status": bundle_result.status,
                "fusion_status": "INVALID",
            }
            return MultimodalFusionResponse(
                bundle=bundle_result,
                fusion_status="INVALID",
                supports=[],
                conflicts=[],
                created_world_facts=[],
                fusion_sha256=_hash(payload),
                boundary=(
                    "Fusion requires a structurally verified V15 multimodal bundle. "
                    "No semantic fact was written to the world model."
                ),
            )

        artifacts: dict[str, MultimodalArtifact] = {item.artifact_id: item for item in body.bundle.artifacts}
        interpretations: dict[str, ArtifactInterpretation] = {}
        allowlist = _allowed_adapters()
        for item in body.interpretations:
            artifact = artifacts.get(item.artifact_id)
            if artifact is None:
                raise ValueError("multimodal_interpretation_artifact_not_in_bundle:" + item.artifact_id)
            if item.modality != artifact.modality:
                raise ValueError("multimodal_interpretation_modality_mismatch:" + item.artifact_id)
            if item.content_sha256 != artifact.content_sha256:
                raise ValueError("multimodal_interpretation_content_hash_mismatch:" + item.artifact_id)
            adapter_identity = item.adapter_id + "@" + item.adapter_version
            if allowlist and adapter_identity not in allowlist and item.adapter_id not in allowlist:
                raise ValueError("multimodal_adapter_not_allowed:" + adapter_identity)
            interpretations[item.artifact_id] = item

        grouped: dict[tuple[str, str], dict[str, list[tuple[SemanticClaim, MultimodalArtifact, ArtifactInterpretation]]]] = defaultdict(lambda: defaultdict(list))
        values: dict[tuple[str, str, str], Any] = {}
        for artifact_id, interpretation in interpretations.items():
            artifact = artifacts[artifact_id]
            for claim in interpretation.claims:
                if claim.confidence < body.minimum_claim_confidence:
                    continue
                value_sha = _hash(claim.value)
                key = (claim.subject, claim.predicate)
                grouped[key][value_sha].append((claim, artifact, interpretation))
                values[(claim.subject, claim.predicate, value_sha)] = claim.value

        supports: list[FactSupport] = []
        support_lookup: dict[tuple[str, str], list[FactSupport]] = defaultdict(list)
        for (subject, predicate), by_value in sorted(grouped.items()):
            for value_sha, rows in sorted(by_value.items()):
                modalities = sorted({artifact.modality for _, artifact, _ in rows})
                lineages = sorted({artifact.lineage_identity for _, artifact, _ in rows})
                artifact_ids = sorted({artifact.artifact_id for _, artifact, _ in rows})
                adapter_ids = sorted({interpretation.adapter_id + "@" + interpretation.adapter_version for _, _, interpretation in rows})
                claim_ids = sorted({claim.claim_id for claim, _, _ in rows})
                mean_confidence = sum(claim.confidence for claim, _, _ in rows) / len(rows)
                reasons: list[str] = []
                if len(modalities) < body.minimum_modalities_per_fact:
                    reasons.append("insufficient_modalities")
                if len(lineages) < body.minimum_lineages_per_fact:
                    reasons.append("insufficient_independent_lineages")
                if mean_confidence < body.minimum_mean_confidence:
                    reasons.append("mean_confidence_below_threshold")
                support = FactSupport(
                    subject=subject,
                    predicate=predicate,
                    value_sha256=value_sha,
                    modalities=modalities,
                    lineages=lineages,
                    artifact_ids=artifact_ids,
                    adapter_ids=adapter_ids,
                    mean_confidence=round(mean_confidence, 6),
                    claim_ids=claim_ids,
                    eligible=not reasons,
                    reasons=reasons or ["cross_modal_support_thresholds_satisfied"],
                )
                supports.append(support)
                support_lookup[(subject, predicate)].append(support)

        conflicts: list[ConflictGroup] = []
        conflicted_keys: set[tuple[str, str]] = set()
        for key, key_supports in sorted(support_lookup.items()):
            supported = [
                item for item in key_supports
                if item.modalities and item.lineages and item.mean_confidence >= body.minimum_claim_confidence
            ]
            distinct = {item.value_sha256 for item in supported}
            if len(distinct) > 1:
                conflicted_keys.add(key)
                conflicts.append(
                    ConflictGroup(
                        subject=key[0],
                        predicate=key[1],
                        supported_values=sorted(supported, key=lambda item: item.value_sha256),
                    )
                )

        created: list[WorldFact] = []
        for support in supports:
            key = (support.subject, support.predicate)
            if not support.eligible:
                continue
            if body.reject_any_supported_conflict and key in conflicted_keys:
                continue
            rows = grouped[key][support.value_sha256]
            claims = [claim for claim, _, _ in rows]
            observed = [claim.observed_at for claim in claims if claim.observed_at is not None]
            valid_from = [claim.valid_from for claim in claims if claim.valid_from is not None]
            valid_to = [claim.valid_to for claim in claims if claim.valid_to is not None]
            domains = sorted({claim.domain for claim in claims})
            domain = domains[0] if len(domains) == 1 else "multidomain:" + "+".join(domains)[:100]
            source_refs = [
                "bundle:" + bundle_result.bundle_id,
                *["artifact:" + item for item in support.artifact_ids],
                *["adapter:" + item for item in support.adapter_ids],
                *["claim:" + item for item in support.claim_ids],
            ]
            resolved_valid_from = max(valid_from) if valid_from else None
            resolved_valid_to = min(valid_to) if valid_to else None
            if resolved_valid_from is not None and resolved_valid_to is not None and resolved_valid_to < resolved_valid_from:
                support.eligible = False
                support.reasons = ["temporal_validity_conflict"]
                continue
            fact = CONTINUAL_V16.add_fact(
                workspace_id,
                WorldFactCreate(
                    subject=support.subject,
                    predicate=support.predicate,
                    value=values[(support.subject, support.predicate, support.value_sha256)],
                    domain=domain,
                    confidence=support.mean_confidence,
                    evidence_refs=source_refs,
                    observed_at=max(observed) if observed else None,
                    valid_from=resolved_valid_from,
                    valid_to=resolved_valid_to,
                ),
            )
            created.append(fact)

        if conflicts:
            status: Literal["FUSED", "PARTIAL", "CONFLICT", "INVALID"] = "CONFLICT"
        elif created and any(not item.eligible for item in supports):
            status = "PARTIAL"
        elif created:
            status = "FUSED"
        else:
            status = "PARTIAL"
        payload = {
            "bundle_id": bundle_result.bundle_id,
            "bundle_manifest_sha256": bundle_result.manifest_sha256,
            "fusion_status": status,
            "supports": [item.model_dump(mode="json") for item in supports],
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
            "world_fact_ids": [fact.fact_id for fact in created],
        }
        return MultimodalFusionResponse(
            bundle=bundle_result,
            fusion_status=status,
            supports=supports,
            conflicts=conflicts,
            created_world_facts=created,
            fusion_sha256=_hash(payload),
            boundary=(
                "V20 fuses semantic claims produced by approved modality adapters and binds them to V15 artifact hashes, independent lineages and V16 temporal facts. "
                "ORBYTHRA does not claim native pixel/audio/video decoding in this module; semantic correctness still depends on the validated modality adapters."
            ),
        )


MULTIMODAL_FUSION_V20 = MultimodalWorldFusionV20()


@router.post("/fuse", response_model=MultimodalFusionResponse)
def fuse(body: MultimodalFusionRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> MultimodalFusionResponse:
    try:
        result = MULTIMODAL_FUSION_V20.fuse(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.fusion_sha256),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="v20_multimodal_fusion",
        status=result.fusion_status,
        metadata={
            "bundle_id": result.bundle.bundle_id,
            "fusion_sha256": result.fusion_sha256,
            "created_world_fact_ids": [fact.fact_id for fact in result.created_world_facts],
            "conflict_count": len(result.conflicts),
        },
    )
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, Any]:
    _ = principal
    return {
        "version": "v20",
        "v15_artifact_hash_binding": True,
        "adapter_output_hash_binding": True,
        "adapter_allowlist_supported": True,
        "cross_modal_consensus": True,
        "independent_lineage_threshold": True,
        "semantic_conflict_detection": True,
        "v16_temporal_world_fact_write": True,
        "native_media_decoding_inside_core": False,
        "live_agi_claim": False,
        "boundary": (
            "V20 performs semantic cross-modal fusion over hash-bound outputs from approved modality adapters. "
            "Native image/audio/video decoding remains adapter-provided and must be independently validated."
        ),
    }
