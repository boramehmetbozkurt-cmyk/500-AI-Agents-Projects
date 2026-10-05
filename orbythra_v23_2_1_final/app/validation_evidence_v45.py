from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from sqlalchemy import text

from app.store import STORE
from app.vault import VAULT


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False, default=str).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class ValidationEvidenceStore:
    """Append-only, workspace-scoped validation evidence ledger for v4.5."""

    def __init__(self) -> None:
        self.engine = STORE.engine
        with self.engine.begin() as conn:
            conn.execute(text("""CREATE TABLE IF NOT EXISTS validation_evidence_v45 (
                workspace_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                payload_json TEXT NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                previous_sha256 TEXT,
                created_at BIGINT NOT NULL,
                PRIMARY KEY(workspace_id,evidence_id),
                UNIQUE(workspace_id,sequence)
            )"""))

    def append(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self.engine.connect() as conn:
            previous = conn.execute(
                text("SELECT sequence,evidence_sha256 FROM validation_evidence_v45 WHERE workspace_id=:w ORDER BY sequence DESC LIMIT 1"),
                {"w": workspace_id},
            ).mappings().first()
        sequence = 1 if previous is None else int(previous["sequence"]) + 1
        previous_sha = None if previous is None else str(previous["evidence_sha256"])
        evidence_id = "val_" + uuid.uuid4().hex[:20]
        payload = {
            "evidence_id": evidence_id,
            "sequence": sequence,
            "suite": body["suite"],
            "commit_sha": body["commit_sha"],
            "configuration_sha256": body["configuration_sha256"],
            "result": body["result"],
            "total": int(body["total"]),
            "passed": int(body["passed"]),
            "failed": int(body["failed"]),
            "artifact_sha256": body.get("artifact_sha256"),
            "external_validator": body.get("external_validator"),
            "previous_sha256": previous_sha,
            "created_at": now,
        }
        digest = sha256({k: v for k, v in payload.items() if k != "created_at"})
        protected = VAULT.encrypt_json(payload, workspace_id=workspace_id, purpose="validation-evidence-v45")
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO validation_evidence_v45
                    (workspace_id,evidence_id,sequence,payload_json,evidence_sha256,previous_sha256,created_at)
                    VALUES (:w,:id,:seq,:p,:s,:prev,:t)"""),
                {"w": workspace_id, "id": evidence_id, "seq": sequence, "p": protected, "s": digest, "prev": previous_sha, "t": now},
            )
        return {**payload, "evidence_sha256": digest}

    def list(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT payload_json,evidence_sha256 FROM validation_evidence_v45 WHERE workspace_id=:w ORDER BY sequence"),
                {"w": workspace_id},
            ).mappings().all()
        return [
            {**VAULT.decrypt_json(row["payload_json"], workspace_id=workspace_id, purpose="validation-evidence-v45"), "evidence_sha256": row["evidence_sha256"]}
            for row in rows
        ]

    def verify(self, workspace_id: str) -> dict[str, Any]:
        rows = self.list(workspace_id)
        previous = None
        errors: list[str] = []
        for expected_sequence, item in enumerate(rows, start=1):
            if item["sequence"] != expected_sequence:
                errors.append(f"sequence:{item['evidence_id']}")
            if item.get("previous_sha256") != previous:
                errors.append(f"previous_sha256:{item['evidence_id']}")
            expected = sha256({k: v for k, v in item.items() if k not in {"created_at", "evidence_sha256"}})
            if item["evidence_sha256"] != expected:
                errors.append(f"digest:{item['evidence_id']}")
            if item["total"] != item["passed"] + item["failed"]:
                errors.append(f"counts:{item['evidence_id']}")
            if item["result"] == "PASS" and item["failed"] != 0:
                errors.append(f"pass_with_failures:{item['evidence_id']}")
            previous = item["evidence_sha256"]
        return {"valid": bool(rows) and not errors, "entries": len(rows), "head_sha256": previous, "errors": errors}

    def export(self, workspace_id: str) -> dict[str, Any]:
        entries = self.list(workspace_id)
        verification = self.verify(workspace_id)
        payload = {
            "schema": "orbythra.validation-evidence.v4.5",
            "workspace_scope": hashlib.sha256(workspace_id.encode()).hexdigest(),
            "entries": entries,
            "verification": verification,
        }
        return {**payload, "bundle_sha256": sha256(payload)}


VALIDATION_EVIDENCE = ValidationEvidenceStore()
