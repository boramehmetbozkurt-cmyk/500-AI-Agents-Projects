from __future__ import annotations

import hashlib
import time

from sqlalchemy.exc import SQLAlchemyError

from fastapi import APIRouter, Depends, HTTPException

from app.distributed_verification_v9 import TRUST_V9, QuorumRequest, Validator
from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v9/trust", tags=["v9-distributed-verification"])
_OP = require_minimum_role("operator")
_EV = require_minimum_role("evaluator")


@router.post("/validators")
def register(v: Validator, principal: Principal = Depends(_OP)) -> dict:
    try:
        return TRUST_V9.register(v, workspace_id=principal.workspace_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "validator_registry_unavailable") from exc
    except ValueError as exc:
        # Invalid cryptographic material is a caller validation error, not a
        # server failure. Keep the route fail-closed and never leak a 500 for
        # malformed Ed25519 public keys.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/quorum")
def quorum(r: QuorumRequest, principal: Principal = Depends(_EV)) -> dict:
    fingerprint = hashlib.sha256((r.payload_sha256 + "|" + r.nonce).encode()).hexdigest()
    reserved = STORE.reserve_crypto_nonce(
        workspace_id=principal.workspace_id,
        nonce_fingerprint="v9-attestation:" + fingerprint,
        expires_at=int(time.time()) + r.maximum_age_seconds,
    )
    if not reserved:
        raise HTTPException(status_code=409, detail="v9_attestation_replay_detected")
    try:
        return TRUST_V9.quorum(r, workspace_id=principal.workspace_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "validator_registry_unavailable") from exc


@router.get("/readiness")
def readiness(principal: Principal = Depends(_EV)) -> dict:
    return {
        "release": "9.0",
        "workspace_id": principal.workspace_id,
        "ed25519_attestations": True,
        "payload_nonce_binding": True,
        "freshness_gate": True,
        "duplicate_validator_rejection": True,
        "weighted_quorum": True,
        "byzantine_fail_closed": True,
        "persistent_validator_registry": True,
        "cross_organization_network_deployed": False,
        "independent_validation_claim": False,
    }
