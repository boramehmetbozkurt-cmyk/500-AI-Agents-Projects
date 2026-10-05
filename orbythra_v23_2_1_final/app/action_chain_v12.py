from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.crypto_core import canonical_json
from app.security import Principal, require_minimum_role
from app.store import STORE
from app.vault import VAULT

router = APIRouter(prefix="/v12/action-chain", tags=["v12-action-chain"])
_REQUIRE_OPERATOR = require_minimum_role("operator")
_REQUIRE_EVALUATOR = require_minimum_role("evaluator")

Stage = Literal["INTENT", "PLAN", "CANDIDATE", "SIMULATION", "APPROVAL", "ACTION", "EFFECT"]
_STAGES: tuple[str, ...] = ("INTENT", "PLAN", "CANDIDATE", "SIMULATION", "APPROVAL", "ACTION", "EFFECT")
_GENESIS = "0" * 64


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _entry_hash(*, workspace_id: str, chain_id: str, sequence: int, stage: str, payload_sha256: str, previous_entry_sha256: str, created_at: int) -> str:
    return _hash(
        {
            "domain": "ORBYTHRA-V12-ACTION-CHAIN",
            "workspace_id": workspace_id,
            "chain_id": chain_id,
            "sequence": sequence,
            "stage": stage,
            "payload_sha256": payload_sha256,
            "previous_entry_sha256": previous_entry_sha256,
            "created_at": created_at,
        }
    )


class ChainCreateRequest(BaseModel):
    intent: dict[str, Any] = Field(min_length=1)
    external_reference: str | None = Field(default=None, max_length=200)


class ChainAppendRequest(BaseModel):
    stage: Literal["PLAN", "CANDIDATE", "SIMULATION", "APPROVAL", "ACTION", "EFFECT"]
    payload: dict[str, Any] = Field(min_length=1)
    expected_previous_entry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChainEntry(BaseModel):
    sequence: int
    stage: Stage
    payload: dict[str, Any]
    payload_sha256: str
    previous_entry_sha256: str
    entry_sha256: str
    created_at: int


class ChainResponse(BaseModel):
    chain_id: str
    workspace_id: str
    status: Literal["OPEN", "COMPLETE"]
    external_reference: str | None
    head_sha256: str
    next_stage: str | None
    entries: list[ChainEntry]
    chain_receipt_sha256: str
    integrity_verified: bool


class ActionChainLedgerV12:
    def __init__(self) -> None:
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS action_chains_v12(
                    workspace_id TEXT NOT NULL,
                    chain_id TEXT NOT NULL,
                    external_reference TEXT,
                    status TEXT NOT NULL,
                    head_sha256 TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    PRIMARY KEY(workspace_id, chain_id)
                    )"""
                )
            )
            connection.execute(
                text(
                    """CREATE TABLE IF NOT EXISTS action_chain_entries_v12(
                    workspace_id TEXT NOT NULL,
                    chain_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    previous_entry_sha256 TEXT NOT NULL,
                    entry_sha256 TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    PRIMARY KEY(workspace_id, chain_id, sequence),
                    UNIQUE(workspace_id, chain_id, stage)
                    )"""
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_action_chain_v12_head ON action_chain_entries_v12(workspace_id,chain_id,sequence)"))

    def _encrypt_payload(self, workspace_id: str, payload: dict[str, Any]) -> str:
        return VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="action-chain-v12")

    def _decrypt_payload(self, workspace_id: str, stored: str) -> dict[str, Any]:
        value = VAULT.decrypt_json(stored, workspace_id=workspace_id, purpose="action-chain-v12")
        if not isinstance(value, dict) or not value:
            raise ValueError("action_chain_payload_invalid")
        return value

    def create(self, workspace_id: str, intent: dict[str, Any], external_reference: str | None = None, *, now: int | None = None) -> ChainResponse:
        created_at = int(time.time()) if now is None else int(now)
        chain_id = "ac12_" + uuid.uuid4().hex[:24]
        payload_sha = _hash(intent)
        entry_sha = _entry_hash(
            workspace_id=workspace_id,
            chain_id=chain_id,
            sequence=0,
            stage="INTENT",
            payload_sha256=payload_sha,
            previous_entry_sha256=_GENESIS,
            created_at=created_at,
        )
        encrypted_intent = self._encrypt_payload(workspace_id, intent)
        with STORE.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO action_chains_v12(workspace_id,chain_id,external_reference,status,head_sha256,created_at,updated_at)
                    VALUES(:w,:c,:r,'OPEN',:h,:t,:t)"""
                ),
                {"w": workspace_id, "c": chain_id, "r": external_reference, "h": entry_sha, "t": created_at},
            )
            connection.execute(
                text(
                    """INSERT INTO action_chain_entries_v12(workspace_id,chain_id,sequence,stage,payload_json,payload_sha256,previous_entry_sha256,entry_sha256,created_at)
                    VALUES(:w,:c,0,'INTENT',:p,:ph,:prev,:eh,:t)"""
                ),
                {
                    "w": workspace_id,
                    "c": chain_id,
                    "p": encrypted_intent,
                    "ph": payload_sha,
                    "prev": _GENESIS,
                    "eh": entry_sha,
                    "t": created_at,
                },
            )
        return self.get(workspace_id, chain_id)

    def append(self, workspace_id: str, chain_id: str, body: ChainAppendRequest, *, now: int | None = None) -> ChainResponse:
        current = self.get(workspace_id, chain_id)
        if current.status == "COMPLETE":
            raise ValueError("action_chain_already_complete")
        expected_stage = current.next_stage
        if body.stage != expected_stage:
            raise ValueError(f"action_chain_stage_out_of_order:expected_{expected_stage}")
        if body.expected_previous_entry_sha256 != current.head_sha256:
            raise ValueError("action_chain_head_mismatch")

        created_at = int(time.time()) if now is None else int(now)
        sequence = len(current.entries)
        payload_sha = _hash(body.payload)
        entry_sha = _entry_hash(
            workspace_id=workspace_id,
            chain_id=chain_id,
            sequence=sequence,
            stage=body.stage,
            payload_sha256=payload_sha,
            previous_entry_sha256=current.head_sha256,
            created_at=created_at,
        )
        encrypted_payload = self._encrypt_payload(workspace_id, body.payload)
        status = "COMPLETE" if body.stage == "EFFECT" else "OPEN"
        with STORE.engine.begin() as connection:
            latest = connection.execute(
                text("SELECT head_sha256,status FROM action_chains_v12 WHERE workspace_id=:w AND chain_id=:c"),
                {"w": workspace_id, "c": chain_id},
            ).mappings().first()
            if latest is None:
                raise ValueError("action_chain_not_found")
            if latest["status"] == "COMPLETE":
                raise ValueError("action_chain_already_complete")
            if latest["head_sha256"] != body.expected_previous_entry_sha256:
                raise ValueError("action_chain_concurrent_head_changed")
            connection.execute(
                text(
                    """INSERT INTO action_chain_entries_v12(workspace_id,chain_id,sequence,stage,payload_json,payload_sha256,previous_entry_sha256,entry_sha256,created_at)
                    VALUES(:w,:c,:s,:stage,:p,:ph,:prev,:eh,:t)"""
                ),
                {
                    "w": workspace_id,
                    "c": chain_id,
                    "s": sequence,
                    "stage": body.stage,
                    "p": encrypted_payload,
                    "ph": payload_sha,
                    "prev": current.head_sha256,
                    "eh": entry_sha,
                    "t": created_at,
                },
            )
            updated = connection.execute(
                text(
                    """UPDATE action_chains_v12 SET head_sha256=:new,status=:status,updated_at=:t
                    WHERE workspace_id=:w AND chain_id=:c AND head_sha256=:old"""
                ),
                {"new": entry_sha, "status": status, "t": created_at, "w": workspace_id, "c": chain_id, "old": current.head_sha256},
            )
            if updated.rowcount != 1:
                raise ValueError("action_chain_concurrent_head_changed")
        return self.get(workspace_id, chain_id)

    def _rows(self, workspace_id: str, chain_id: str):
        with STORE.engine.connect() as connection:
            chain = connection.execute(
                text("SELECT * FROM action_chains_v12 WHERE workspace_id=:w AND chain_id=:c"),
                {"w": workspace_id, "c": chain_id},
            ).mappings().first()
            if chain is None:
                raise ValueError("action_chain_not_found")
            entries = connection.execute(
                text("SELECT * FROM action_chain_entries_v12 WHERE workspace_id=:w AND chain_id=:c ORDER BY sequence ASC"),
                {"w": workspace_id, "c": chain_id},
            ).mappings().all()
        return chain, entries

    def get(self, workspace_id: str, chain_id: str) -> ChainResponse:
        chain, rows = self._rows(workspace_id, chain_id)
        entries: list[ChainEntry] = []
        integrity = True
        previous = _GENESIS
        for expected_sequence, row in enumerate(rows):
            try:
                payload = self._decrypt_payload(workspace_id, row["payload_json"])
            except Exception:
                payload = {}
                integrity = False
            payload_sha = _hash(payload) if payload else ""
            recalculated = _entry_hash(
                workspace_id=workspace_id,
                chain_id=chain_id,
                sequence=expected_sequence,
                stage=row["stage"],
                payload_sha256=row["payload_sha256"],
                previous_entry_sha256=row["previous_entry_sha256"],
                created_at=int(row["created_at"]),
            )
            expected_stage = _STAGES[expected_sequence] if expected_sequence < len(_STAGES) else None
            if int(row["sequence"]) != expected_sequence or row["stage"] != expected_stage:
                integrity = False
            if payload_sha != row["payload_sha256"] or row["previous_entry_sha256"] != previous or recalculated != row["entry_sha256"]:
                integrity = False
            previous = row["entry_sha256"]
            entries.append(
                ChainEntry(
                    sequence=int(row["sequence"]),
                    stage=row["stage"],
                    payload=payload,
                    payload_sha256=row["payload_sha256"],
                    previous_entry_sha256=row["previous_entry_sha256"],
                    entry_sha256=row["entry_sha256"],
                    created_at=int(row["created_at"]),
                )
            )

        if not entries or chain["head_sha256"] != entries[-1].entry_sha256:
            integrity = False
        expected_status = "COMPLETE" if entries and entries[-1].stage == "EFFECT" else "OPEN"
        if chain["status"] != expected_status:
            integrity = False
        next_stage = None if expected_status == "COMPLETE" else _STAGES[len(entries)] if len(entries) < len(_STAGES) else None
        receipt_sha = _hash(
            {
                "domain": "ORBYTHRA-V12-ACTION-CHAIN-RECEIPT",
                "workspace_id": workspace_id,
                "chain_id": chain_id,
                "status": chain["status"],
                "head_sha256": chain["head_sha256"],
                "entry_sha256s": [entry.entry_sha256 for entry in entries],
            }
        )
        return ChainResponse(
            chain_id=chain_id,
            workspace_id=workspace_id,
            status=chain["status"],
            external_reference=chain["external_reference"],
            head_sha256=chain["head_sha256"],
            next_stage=next_stage,
            entries=entries,
            chain_receipt_sha256=receipt_sha,
            integrity_verified=integrity,
        )


ACTION_CHAIN_V12 = ActionChainLedgerV12()


def _audit(request: Request, principal: Principal, action: str, status: str, metadata: dict[str, object]) -> None:
    STORE.record_audit(
        request_id=getattr(request.state, "request_id", "action-chain-v12"),
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        action=action,
        status=status,
        metadata=metadata,
    )


@router.post("/chains", response_model=ChainResponse)
def create_chain(body: ChainCreateRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> ChainResponse:
    result = ACTION_CHAIN_V12.create(principal.workspace_id, body.intent, body.external_reference)
    _audit(request, principal, "action_chain_v12_create", "OPEN", {"chain_id": result.chain_id, "head_sha256": result.head_sha256})
    return result


@router.post("/chains/{chain_id}/append", response_model=ChainResponse)
def append_chain(chain_id: str, body: ChainAppendRequest, request: Request, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> ChainResponse:
    try:
        result = ACTION_CHAIN_V12.append(principal.workspace_id, chain_id, body)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "action_chain_not_found" else 409, detail=detail) from exc
    _audit(request, principal, "action_chain_v12_append", result.status, {"chain_id": chain_id, "stage": body.stage, "head_sha256": result.head_sha256, "receipt_sha256": result.chain_receipt_sha256})
    return result


@router.get("/chains/{chain_id}", response_model=ChainResponse)
def get_chain(chain_id: str, principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> ChainResponse:
    try:
        return ACTION_CHAIN_V12.get(principal.workspace_id, chain_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/readiness")
def readiness(principal: Principal = Depends(_REQUIRE_EVALUATOR)) -> dict[str, object]:
    return {
        "release": "12.0-p0",
        "workspace_id": principal.workspace_id,
        "ordered_binding": list(_STAGES),
        "domain_separated_hash_chain": True,
        "payload_integrity_recomputation": True,
        "optimistic_concurrency_head_binding": True,
        "stage_replay_prevention": True,
        "workspace_isolation": True,
        "encrypted_payloads_at_rest": True,
        "complete_chain_receipt": True,
        "tamper_detection_on_read": True,
        "digital_signature_of_chain_receipt": False,
        "external_effect_observation": False,
    }
