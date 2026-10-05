from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.security import Principal, require_minimum_role
from app.store import STORE

router = APIRouter(prefix="/v12/trust", tags=["v12-distributed-verification"])
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")
_REQUIRE_ADMIN = require_minimum_role("admin")


def _b64d(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError("invalid_base64") from exc


def _canon(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class ValidatorV12(BaseModel):
    validator_id: str = Field(min_length=1, max_length=128)
    public_key_b64: str = Field(min_length=1, max_length=200)
    organization: str = Field(min_length=1, max_length=200)
    trust_weight: float = Field(default=1.0, gt=0, le=10)
    active: bool = True


class ValidatorRecordV12(ValidatorV12):
    workspace_id: str
    fingerprint: str
    revision: int
    updated_at: int


class AttestationV12(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    validator_id: str = Field(min_length=1, max_length=128)
    decision: Literal["PASS", "FAIL"]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str = Field(min_length=8, max_length=200)
    issued_at: int
    registry_revision: int = Field(ge=1)
    signature_b64: str = Field(min_length=1, max_length=512)


class QuorumRequestV12(BaseModel):
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str = Field(min_length=8, max_length=200)
    attestations: list[AttestationV12] = Field(min_length=1, max_length=1000)
    minimum_validators: int = Field(default=3, ge=1, le=1000)
    minimum_pass_fraction: float = Field(default=0.67, gt=0.5, le=1)
    maximum_age_seconds: int = Field(default=300, ge=1, le=86400)
    maximum_future_skew_seconds: int = Field(default=30, ge=0, le=300)
    minimum_organizations: int = Field(default=1, ge=1, le=1000)


class ActiveRequest(BaseModel):
    active: bool


class RotateRequest(BaseModel):
    public_key_b64: str = Field(min_length=1, max_length=200)


class WorkspaceValidatorRegistryV12:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS validators_v12(
                    workspace_id TEXT NOT NULL,
                    validator_id TEXT NOT NULL,
                    public_key_b64 TEXT NOT NULL,
                    organization TEXT NOT NULL,
                    trust_weight REAL NOT NULL,
                    active INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at BIGINT NOT NULL,
                    PRIMARY KEY(workspace_id, validator_id)
                    )"""
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_validators_v12_workspace_active ON validators_v12(workspace_id,active,organization)"))

    @staticmethod
    def _validated_key(public_key_b64: str) -> tuple[bytes, str]:
        raw = _b64d(public_key_b64)
        if len(raw) != 32:
            raise ValueError("invalid_ed25519_public_key")
        try:
            ed25519.Ed25519PublicKey.from_public_bytes(raw)
        except ValueError as exc:
            raise ValueError("invalid_ed25519_public_key") from exc
        return raw, hashlib.sha256(raw).hexdigest()

    def register(self, workspace_id: str, validator: ValidatorV12) -> ValidatorRecordV12:
        _, fingerprint = self._validated_key(validator.public_key_b64)
        now = int(time.time())
        try:
            with STORE.engine.begin() as connection:
                connection.execute(
                    text(
                        """INSERT INTO validators_v12(
                        workspace_id,validator_id,public_key_b64,organization,trust_weight,active,fingerprint,revision,updated_at
                        ) VALUES(:w,:i,:p,:o,:tw,:a,:f,1,:u)"""
                    ),
                    {
                        "w": workspace_id,
                        "i": validator.validator_id,
                        "p": validator.public_key_b64,
                        "o": validator.organization,
                        "tw": validator.trust_weight,
                        "a": 1 if validator.active else 0,
                        "f": fingerprint,
                        "u": now,
                    },
                )
        except IntegrityError as exc:
            raise ValueError("validator_already_exists") from exc
        record = self.get(workspace_id, validator.validator_id)
        if record is None:
            raise RuntimeError("validator_registration_not_persisted")
        return record

    def get(self, workspace_id: str, validator_id: str) -> ValidatorRecordV12 | None:
        with STORE.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM validators_v12 WHERE workspace_id=:w AND validator_id=:i"),
                {"w": workspace_id, "i": validator_id},
            ).mappings().first()
        if row is None:
            return None
        return ValidatorRecordV12(
            workspace_id=row["workspace_id"],
            validator_id=row["validator_id"],
            public_key_b64=row["public_key_b64"],
            organization=row["organization"],
            trust_weight=float(row["trust_weight"]),
            active=bool(row["active"]),
            fingerprint=row["fingerprint"],
            revision=int(row["revision"]),
            updated_at=int(row["updated_at"]),
        )

    def set_active(self, workspace_id: str, validator_id: str, active: bool) -> ValidatorRecordV12:
        with STORE.engine.begin() as connection:
            result = connection.execute(
                text("UPDATE validators_v12 SET active=:a,revision=revision+1,updated_at=:u WHERE workspace_id=:w AND validator_id=:i"),
                {"a": 1 if active else 0, "u": int(time.time()), "w": workspace_id, "i": validator_id},
            )
        if not result.rowcount:
            raise ValueError("validator_not_found")
        record = self.get(workspace_id, validator_id)
        if record is None:
            raise RuntimeError("validator_update_not_persisted")
        return record

    def rotate(self, workspace_id: str, validator_id: str, public_key_b64: str) -> ValidatorRecordV12:
        _, fingerprint = self._validated_key(public_key_b64)
        with STORE.engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE validators_v12
                    SET public_key_b64=:p,fingerprint=:f,revision=revision+1,updated_at=:u
                    WHERE workspace_id=:w AND validator_id=:i"""
                ),
                {"p": public_key_b64, "f": fingerprint, "u": int(time.time()), "w": workspace_id, "i": validator_id},
            )
        if not result.rowcount:
            raise ValueError("validator_not_found")
        record = self.get(workspace_id, validator_id)
        if record is None:
            raise RuntimeError("validator_rotation_not_persisted")
        return record


VALIDATORS_V12 = WorkspaceValidatorRegistryV12()


class WorkspaceTrustNetworkV12:
    def message(self, attestation: AttestationV12) -> bytes:
        return b"ORBYTHRA-V12-ATTESTATION\x00" + _canon(
            {
                "workspace_id": attestation.workspace_id,
                "validator_id": attestation.validator_id,
                "decision": attestation.decision,
                "payload_sha256": attestation.payload_sha256,
                "nonce": attestation.nonce,
                "issued_at": attestation.issued_at,
                "registry_revision": attestation.registry_revision,
            }
        )

    def verify(
        self,
        workspace_id: str,
        attestation: AttestationV12,
        expected_hash: str,
        nonce: str,
        max_age: int,
        max_future_skew: int,
        now: int | None = None,
    ) -> ValidatorRecordV12:
        if attestation.workspace_id != workspace_id:
            raise ValueError("attestation_workspace_mismatch")
        validator = VALIDATORS_V12.get(workspace_id, attestation.validator_id)
        if validator is None or not validator.active:
            raise ValueError("validator_unavailable")
        if validator.revision != attestation.registry_revision:
            raise ValueError("validator_revision_mismatch")
        if attestation.payload_sha256 != expected_hash or attestation.nonce != nonce:
            raise ValueError("attestation_binding_mismatch")
        current = int(time.time()) if now is None else int(now)
        if attestation.issued_at > current + max_future_skew:
            raise ValueError("future_attestation")
        if current - attestation.issued_at > max_age:
            raise ValueError("stale_attestation")
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(validator.public_key_b64))
            public_key.verify(_b64d(attestation.signature_b64), self.message(attestation))
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("invalid_attestation_signature") from exc
        return validator

    def quorum(self, workspace_id: str, request: QuorumRequestV12, now: int | None = None) -> dict[str, object]:
        seen: set[str] = set()
        valid: list[tuple[AttestationV12, ValidatorRecordV12]] = []
        invalid: list[dict[str, str]] = []
        for attestation in request.attestations:
            if attestation.validator_id in seen:
                invalid.append({"validator_id": attestation.validator_id, "reason": "duplicate_validator"})
                continue
            seen.add(attestation.validator_id)
            try:
                validator = self.verify(
                    workspace_id,
                    attestation,
                    request.payload_sha256,
                    request.nonce,
                    request.maximum_age_seconds,
                    request.maximum_future_skew_seconds,
                    now,
                )
                valid.append((attestation, validator))
            except ValueError as exc:
                invalid.append({"validator_id": attestation.validator_id, "reason": str(exc)})

        pass_weight = sum(validator.trust_weight for attestation, validator in valid if attestation.decision == "PASS")
        total_weight = sum(validator.trust_weight for _, validator in valid)
        fraction = pass_weight / total_weight if total_weight else 0.0
        organizations = len({validator.organization for _, validator in valid})
        passed = len(valid) >= request.minimum_validators and organizations >= request.minimum_organizations and fraction >= request.minimum_pass_fraction
        result = {
            "schema": "orbythra.distributed-verification.v12",
            "workspace_id": workspace_id,
            "status": "PASS" if passed else "FAIL",
            "valid_validators": len(valid),
            "valid_organizations": organizations,
            "pass_weight_fraction": round(fraction, 6),
            "invalid": invalid,
            "payload_sha256": request.payload_sha256,
            "nonce": request.nonce,
        }
        return {**result, "quorum_sha256": hashlib.sha256(_canon(result)).hexdigest()}


TRUST_V12 = WorkspaceTrustNetworkV12()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "v12-trust"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata=metadata,
    )


@router.post("/validators/register", response_model=ValidatorRecordV12)
def register_validator(body: ValidatorV12, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> ValidatorRecordV12:
    try:
        record = VALIDATORS_V12.register(principal.workspace_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc) == "validator_already_exists" else 400, detail=str(exc)) from exc
    _audit(request, principal, "validator_v12_register", "CREATED", {"validator_id": record.validator_id, "fingerprint": record.fingerprint, "revision": record.revision})
    return record


@router.post("/validators/{validator_id}/active", response_model=ValidatorRecordV12)
def set_validator_active(validator_id: str, body: ActiveRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> ValidatorRecordV12:
    try:
        record = VALIDATORS_V12.set_active(principal.workspace_id, validator_id, body.active)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(request, principal, "validator_v12_set_active", "UPDATED", {"validator_id": validator_id, "active": body.active, "revision": record.revision})
    return record


@router.post("/validators/{validator_id}/rotate", response_model=ValidatorRecordV12)
def rotate_validator(validator_id: str, body: RotateRequest, request: Request, principal: Principal = Depends(_REQUIRE_ADMIN)) -> ValidatorRecordV12:
    try:
        record = VALIDATORS_V12.rotate(principal.workspace_id, validator_id, body.public_key_b64)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "validator_not_found" else 400, detail=str(exc)) from exc
    _audit(request, principal, "validator_v12_rotate", "ROTATED", {"validator_id": validator_id, "fingerprint": record.fingerprint, "revision": record.revision})
    return record


@router.post("/quorum")
def evaluate_quorum(body: QuorumRequestV12, request: Request, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    result = TRUST_V12.quorum(principal.workspace_id, body)
    _audit(request, principal, "distributed_verification_v12", str(result["status"]), {"quorum_sha256": result["quorum_sha256"], "valid_validators": result["valid_validators"], "valid_organizations": result["valid_organizations"]})
    return result


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "12.0-p0",
        "workspace_id": principal.workspace_id,
        "workspace_isolated_validator_registry": True,
        "composite_workspace_validator_authority": True,
        "revision_bound_attestations": True,
        "rotation_invalidates_old_attestations": True,
        "revocation_invalidates_attestations": True,
        "future_attestation_rejection": True,
        "organization_diversity_gate": True,
        "weighted_quorum": True,
        "fail_closed_unknown_validator": True,
    }
