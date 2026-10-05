from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.agent_models import AgentActionRequest
from app.agent_store import AGENT_STORE
from app.crypto_core import canonical_json, commitment
from app.distributed_verification_v12 import QuorumRequestV12, TRUST_V12
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v15/effects", tags=["v15-effect-verification"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class EffectObservation(BaseModel):
    source_id: str = Field(min_length=1, max_length=200)
    source_lineage_id: str | None = Field(default=None, max_length=200)
    actual_effect: dict[str, Any] = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: int
    observer_kind: Literal["tool", "system", "human", "sensor", "validator"] = "system"

    @property
    def lineage_identity(self) -> str:
        return self.source_lineage_id or self.source_id

    @property
    def effect_sha256(self) -> str:
        return commitment(self.actual_effect, domain="agent-effect")["sha256"]


class EffectVerificationPolicy(BaseModel):
    minimum_independent_observations: int = Field(default=1, ge=1, le=100)
    minimum_consensus_fraction: float = Field(default=1.0, gt=0.5, le=1.0)
    maximum_observation_age_seconds: int = Field(default=3600, ge=1, le=31536000)
    maximum_future_skew_seconds: int = Field(default=60, ge=0, le=3600)
    require_validator_quorum_for_high_risk: bool = True


class EffectVerificationRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=160)
    nonce: str = Field(min_length=8, max_length=200)
    observations: list[EffectObservation] = Field(min_length=1, max_length=200)
    policy: EffectVerificationPolicy = Field(default_factory=EffectVerificationPolicy)
    validator_quorum: QuorumRequestV12 | None = None

    @model_validator(mode="after")
    def unique_sources(self):
        source_ids = [item.source_id for item in self.observations]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate_effect_observation_source")
        return self


class EffectVerificationResponse(BaseModel):
    verification_id: str
    action_id: str
    status: Literal["VERIFIED", "MISMATCH", "INCONCLUSIVE"]
    expected_effect_sha256: str
    consensus_effect_sha256: str | None
    independent_observations: int
    consensus_fraction: float
    conflicting_effect_digests: list[str]
    stale_sources: list[str]
    invalid_sources: list[str]
    observation_manifest_sha256: str
    validator_quorum_status: str
    receipt_sha256: str
    boundary: str = (
        "V15 verifies agreement between the action's committed intended effect and supplied independent observations. "
        "It does not itself acquire real-world observations; observation authenticity remains bounded by evidence provenance "
        "and, where required, V12 validator attestations."
    )


class EffectVerificationStoreV15:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS effect_verifications_v15(
                    verification_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_effect_sha256 TEXT NOT NULL,
                    consensus_effect_sha256 TEXT,
                    observation_manifest_sha256 TEXT NOT NULL,
                    validator_quorum_status TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    created_at BIGINT NOT NULL
                    )"""
                )
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS idx_effect_v15_action ON effect_verifications_v15(workspace_id,action_id,created_at)")
            )

    def persist(self, workspace_id: str, response: EffectVerificationResponse, created_at: int) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO effect_verifications_v15(
                    verification_id,workspace_id,action_id,status,expected_effect_sha256,consensus_effect_sha256,
                    observation_manifest_sha256,validator_quorum_status,receipt_sha256,created_at
                    ) VALUES(:id,:w,:a,:s,:e,:c,:m,:q,:r,:t)"""
                ),
                {
                    "id": response.verification_id,
                    "w": workspace_id,
                    "a": response.action_id,
                    "s": response.status,
                    "e": response.expected_effect_sha256,
                    "c": response.consensus_effect_sha256,
                    "m": response.observation_manifest_sha256,
                    "q": response.validator_quorum_status,
                    "r": response.receipt_sha256,
                    "t": created_at,
                },
            )


EFFECT_STORE_V15 = EffectVerificationStoreV15()


def verify_effect(
    workspace_id: str,
    body: EffectVerificationRequest,
    *,
    now: int | None = None,
) -> EffectVerificationResponse:
    current_time = int(time.time()) if now is None else int(now)
    action = AGENT_STORE.get_action(workspace_id, body.action_id)
    if action is None:
        raise ValueError("agent_action_not_found")
    action_body = AgentActionRequest(**action["request"])
    expected_digest = str(action["intended_effect_digest"])

    stale: list[str] = []
    invalid: list[str] = []
    valid_observations: list[EffectObservation] = []
    for observation in body.observations:
        if observation.observed_at > current_time + body.policy.maximum_future_skew_seconds:
            invalid.append(observation.source_id + ":future_observation")
            continue
        if current_time - observation.observed_at > body.policy.maximum_observation_age_seconds:
            stale.append(observation.source_id)
            continue
        valid_observations.append(observation)

    # Count only one vote per independent lineage. If a single lineage supplies
    # conflicting effects, exclude that lineage instead of letting it self-vote.
    lineage_votes: dict[str, set[str]] = defaultdict(set)
    for observation in valid_observations:
        lineage_votes[observation.lineage_identity].add(observation.effect_sha256)
    independent_votes: dict[str, str] = {}
    for lineage, digests in lineage_votes.items():
        if len(digests) != 1:
            invalid.append(lineage + ":lineage_internal_conflict")
            continue
        independent_votes[lineage] = next(iter(digests))

    counts: dict[str, int] = defaultdict(int)
    for digest in independent_votes.values():
        counts[digest] += 1
    consensus_digest: str | None = None
    consensus_fraction = 0.0
    if counts:
        consensus_digest, winner_count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
        consensus_fraction = winner_count / len(independent_votes)

    manifest = [
        {
            "source_id": observation.source_id,
            "source_lineage_id": observation.source_lineage_id,
            "effect_sha256": observation.effect_sha256,
            "evidence_sha256": observation.evidence_sha256,
            "observed_at": observation.observed_at,
            "observer_kind": observation.observer_kind,
        }
        for observation in sorted(body.observations, key=lambda item: item.source_id)
    ]
    manifest_sha = _hash(
        {
            "domain": "ORBYTHRA-V15-EFFECT-OBSERVATIONS",
            "workspace_id": workspace_id,
            "action_id": body.action_id,
            "nonce": body.nonce,
            "observations": manifest,
        }
    )

    quorum_status = "NOT_REQUIRED"
    high_risk = action_body.risk_tier in {"high", "critical"}
    quorum_required = high_risk and body.policy.require_validator_quorum_for_high_risk
    if body.validator_quorum is not None:
        if body.validator_quorum.payload_sha256 != manifest_sha or body.validator_quorum.nonce != body.nonce:
            quorum_status = "BINDING_MISMATCH"
        else:
            quorum_result = TRUST_V12.quorum(workspace_id, body.validator_quorum, now=current_time)
            quorum_status = str(quorum_result["status"])
    elif quorum_required:
        quorum_status = "MISSING_REQUIRED_QUORUM"

    enough_observers = len(independent_votes) >= body.policy.minimum_independent_observations
    enough_consensus = consensus_fraction >= body.policy.minimum_consensus_fraction
    quorum_ok = (not quorum_required and quorum_status in {"NOT_REQUIRED", "PASS"}) or (quorum_required and quorum_status == "PASS")

    if invalid or stale or not enough_observers or not enough_consensus or not quorum_ok or consensus_digest is None:
        status: Literal["VERIFIED", "MISMATCH", "INCONCLUSIVE"] = "INCONCLUSIVE"
    elif consensus_digest == expected_digest:
        status = "VERIFIED"
    else:
        status = "MISMATCH"

    verification_id = "ev15_" + uuid.uuid4().hex[:24]
    conflicting = sorted(digest for digest in counts if digest != consensus_digest)
    receipt_payload = {
        "domain": "ORBYTHRA-V15-EFFECT-VERIFICATION",
        "workspace_id": workspace_id,
        "verification_id": verification_id,
        "action_id": body.action_id,
        "expected_effect_sha256": expected_digest,
        "consensus_effect_sha256": consensus_digest,
        "independent_observations": len(independent_votes),
        "consensus_fraction": round(consensus_fraction, 6),
        "observation_manifest_sha256": manifest_sha,
        "validator_quorum_status": quorum_status,
        "status": status,
    }
    response = EffectVerificationResponse(
        verification_id=verification_id,
        action_id=body.action_id,
        status=status,
        expected_effect_sha256=expected_digest,
        consensus_effect_sha256=consensus_digest,
        independent_observations=len(independent_votes),
        consensus_fraction=round(consensus_fraction, 6),
        conflicting_effect_digests=conflicting,
        stale_sources=sorted(set(stale)),
        invalid_sources=sorted(set(invalid)),
        observation_manifest_sha256=manifest_sha,
        validator_quorum_status=quorum_status,
        receipt_sha256=_hash(receipt_payload),
    )
    EFFECT_STORE_V15.persist(workspace_id, response, current_time)
    return response


@router.post("/verify", response_model=EffectVerificationResponse)
def verify(body: EffectVerificationRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> EffectVerificationResponse:
    try:
        result = verify_effect(principal.workspace_id, body)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "agent_action_not_found" else 400, detail=detail) from exc
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", result.verification_id),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action="effect_verification_v15",
        status=result.status,
        metadata={
            "verification_id": result.verification_id,
            "action_id": result.action_id,
            "receipt_sha256": result.receipt_sha256,
            "observation_manifest_sha256": result.observation_manifest_sha256,
            "validator_quorum_status": result.validator_quorum_status,
        },
    )
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "15.0",
        "workspace_id": principal.workspace_id,
        "intended_effect_commitment_binding": True,
        "independent_source_lineage_counting": True,
        "conflicting_lineage_rejection": True,
        "freshness_and_future_time_guards": True,
        "consensus_gate": True,
        "high_risk_validator_quorum_binding": True,
        "tamper_evident_receipt_hash": True,
        "external_observation_acquisition": False,
        "boundary": "The service verifies supplied observation evidence; it does not independently sense or query the external world.",
    }
