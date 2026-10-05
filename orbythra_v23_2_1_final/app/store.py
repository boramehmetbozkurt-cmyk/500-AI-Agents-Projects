from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import SETTINGS
from app.vault import VAULT


class DatabaseStore:
    def __init__(self, database_url: str | None, sqlite_path: str) -> None:
        if database_url:
            url = database_url
            connect_args: dict[str, Any] = {}
        else:
            path = str(Path(sqlite_path).expanduser().resolve())
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite+pysqlite:///{path}"
            connect_args = {"check_same_thread": False}
        self.url = url
        self.engine: Engine = create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)
        self._init_db()

    @property
    def backend(self) -> str:
        return self.engine.url.get_backend_name()

    def _init_db(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS audit_events (event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, principal_id TEXT NOT NULL, workspace_id TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_audit_workspace_created ON audit_events(workspace_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS evidence_snapshots (snapshot_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL, label TEXT, evidence_json TEXT NOT NULL, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_evidence_workspace_created ON evidence_snapshots(workspace_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS pilot_runs (run_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL, request_json TEXT NOT NULL, result_json TEXT NOT NULL, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_pilot_workspace_created ON pilot_runs(workspace_id, created_at DESC)",
            """CREATE TABLE IF NOT EXISTS crypto_nonces (nonce_fingerprint TEXT NOT NULL, workspace_id TEXT NOT NULL, expires_at BIGINT NOT NULL, created_at BIGINT NOT NULL, PRIMARY KEY (workspace_id, nonce_fingerprint))""",
            "CREATE INDEX IF NOT EXISTS idx_crypto_nonce_expiry ON crypto_nonces(expires_at)",
            """CREATE TABLE IF NOT EXISTS privacy_records (record_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, subject_token TEXT NOT NULL, subject_key_id TEXT NOT NULL, purpose TEXT NOT NULL, lawful_basis TEXT NOT NULL, encrypted_json TEXT NOT NULL, retention_until BIGINT NOT NULL, restricted INTEGER NOT NULL DEFAULT 0, consent_withdrawn INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_privacy_subject ON privacy_records(workspace_id, subject_token)",
            "CREATE INDEX IF NOT EXISTS idx_privacy_retention ON privacy_records(workspace_id, retention_until)",
            """CREATE TABLE IF NOT EXISTS privacy_breaches (breach_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, incident_reference TEXT NOT NULL, encrypted_json TEXT NOT NULL, detected_at BIGINT NOT NULL, notification_deadline_at BIGINT NOT NULL, authority_notified_at BIGINT, status TEXT NOT NULL, risk_assessment TEXT NOT NULL, created_at BIGINT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_privacy_breach_status ON privacy_breaches(workspace_id, status, detected_at DESC)",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text("SELECT 1")).scalar_one() == 1
        except Exception:
            return False

    def record_audit(self, *, request_id: str, principal_id: str, workspace_id: str, action: str, status: str, metadata: dict[str, Any] | None = None) -> str:
        event_id = "evt_" + uuid.uuid4().hex[:20]
        encrypted_metadata = VAULT.encrypt_json(metadata or {}, workspace_id=workspace_id, purpose="audit-metadata")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO audit_events(event_id, request_id, principal_id, workspace_id, action, status, metadata_json, created_at) VALUES (:event_id, :request_id, :principal_id, :workspace_id, :action, :status, :metadata_json, :created_at)"""), {"event_id": event_id, "request_id": request_id, "principal_id": principal_id, "workspace_id": workspace_id, "action": action, "status": status, "metadata_json": encrypted_metadata, "created_at": int(time.time())})
        return event_id

    def recent_audit(self, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self.engine.connect() as conn:
            rows = conn.execute(text("""SELECT event_id, request_id, principal_id, workspace_id, action, status, metadata_json, created_at FROM audit_events WHERE workspace_id=:workspace_id ORDER BY created_at DESC, event_id DESC LIMIT :limit"""), {"workspace_id": workspace_id, "limit": limit}).mappings().all()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = VAULT.decrypt_json(item.pop("metadata_json") or "{}", workspace_id=workspace_id, purpose="audit-metadata")
            result.append(item)
        return result

    def create_evidence_snapshot(self, *, workspace_id: str, principal_id: str, label: str | None, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        snapshot_id = "evs_" + uuid.uuid4().hex[:20]
        created_at = int(time.time())
        encrypted_evidence = VAULT.encrypt_json(evidence, workspace_id=workspace_id, purpose="evidence-snapshot")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO evidence_snapshots(snapshot_id, workspace_id, principal_id, label, evidence_json, created_at) VALUES (:snapshot_id, :workspace_id, :principal_id, :label, :evidence_json, :created_at)"""), {"snapshot_id": snapshot_id, "workspace_id": workspace_id, "principal_id": principal_id, "label": label, "evidence_json": encrypted_evidence, "created_at": created_at})
        return {"snapshot_id": snapshot_id, "workspace_id": workspace_id, "label": label, "evidence_count": len(evidence), "created_at": created_at}

    def get_evidence_snapshot(self, workspace_id: str, snapshot_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("""SELECT snapshot_id, workspace_id, label, evidence_json, created_at FROM evidence_snapshots WHERE workspace_id=:workspace_id AND snapshot_id=:snapshot_id"""), {"workspace_id": workspace_id, "snapshot_id": snapshot_id}).mappings().first()
        if row is None:
            return None
        item = dict(row)
        evidence = VAULT.decrypt_json(item.pop("evidence_json") or "[]", workspace_id=workspace_id, purpose="evidence-snapshot")
        item["evidence"] = evidence
        item["evidence_count"] = len(evidence)
        return item

    def save_pilot_run(self, *, run_id: str, scenario_id: str, workspace_id: str, principal_id: str, request_payload: dict[str, Any], result_payload: dict[str, Any]) -> None:
        encrypted_request = VAULT.encrypt_json(request_payload, workspace_id=workspace_id, purpose="pilot-request")
        encrypted_result = VAULT.encrypt_json(result_payload, workspace_id=workspace_id, purpose="pilot-result")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO pilot_runs(run_id, scenario_id, workspace_id, principal_id, request_json, result_json, created_at) VALUES (:run_id, :scenario_id, :workspace_id, :principal_id, :request_json, :result_json, :created_at)"""), {"run_id": run_id, "scenario_id": scenario_id, "workspace_id": workspace_id, "principal_id": principal_id, "request_json": encrypted_request, "result_json": encrypted_result, "created_at": int(time.time())})

    def get_pilot_run(self, workspace_id: str, run_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("""SELECT run_id, scenario_id, workspace_id, principal_id, request_json, result_json, created_at FROM pilot_runs WHERE workspace_id=:workspace_id AND run_id=:run_id"""), {"workspace_id": workspace_id, "run_id": run_id}).mappings().first()
        if row is None:
            return None
        item = dict(row)
        item["request"] = VAULT.decrypt_json(item.pop("request_json") or "{}", workspace_id=workspace_id, purpose="pilot-request")
        item["result"] = VAULT.decrypt_json(item.pop("result_json") or "{}", workspace_id=workspace_id, purpose="pilot-result")
        return item

    def reserve_crypto_nonce(self, *, workspace_id: str, nonce_fingerprint: str, expires_at: int) -> bool:
        now = int(time.time())
        cleanup_before = now - 86400
        effective_expiry = expires_at if expires_at > 0 else now + 86400
        try:
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM crypto_nonces WHERE expires_at < :cutoff"), {"cutoff": cleanup_before})
                conn.execute(text("""INSERT INTO crypto_nonces(nonce_fingerprint, workspace_id, expires_at, created_at) VALUES (:nonce_fingerprint, :workspace_id, :expires_at, :created_at)"""), {"nonce_fingerprint": nonce_fingerprint, "workspace_id": workspace_id, "expires_at": effective_expiry, "created_at": now})
            return True
        except Exception:
            return False

    def create_privacy_record(self, *, workspace_id: str, subject_token: str, subject_key_id: str, purpose: str, lawful_basis: str, record_data: dict[str, Any], retention_until: int) -> dict[str, Any]:
        now = int(time.time())
        record_id = "pvr_" + uuid.uuid4().hex[:20]
        encrypted = VAULT.encrypt_json(record_data, workspace_id=workspace_id, purpose="privacy-record")
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO privacy_records(record_id, workspace_id, subject_token, subject_key_id, purpose, lawful_basis, encrypted_json, retention_until, restricted, consent_withdrawn, created_at, updated_at) VALUES (:record_id, :workspace_id, :subject_token, :subject_key_id, :purpose, :lawful_basis, :encrypted_json, :retention_until, 0, 0, :created_at, :updated_at)"""), {"record_id": record_id, "workspace_id": workspace_id, "subject_token": subject_token, "subject_key_id": subject_key_id, "purpose": purpose, "lawful_basis": lawful_basis, "encrypted_json": encrypted, "retention_until": retention_until, "created_at": now, "updated_at": now})
        return {"record_id": record_id, "created_at": now, "updated_at": now}

    def _privacy_rows_for_tokens(self, workspace_id: str, tokens: list[str]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        rows_out: list[dict[str, Any]] = []
        with self.engine.connect() as conn:
            for token in tokens:
                rows = conn.execute(text("""SELECT record_id, workspace_id, subject_token, subject_key_id, purpose, lawful_basis, encrypted_json, retention_until, restricted, consent_withdrawn, created_at, updated_at FROM privacy_records WHERE workspace_id=:workspace_id AND subject_token=:subject_token ORDER BY created_at, record_id"""), {"workspace_id": workspace_id, "subject_token": token}).mappings().all()
                for row in rows:
                    if row["record_id"] in seen:
                        continue
                    seen.add(row["record_id"])
                    rows_out.append(dict(row))
        return rows_out

    def export_privacy_records(self, workspace_id: str, tokens: list[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in self._privacy_rows_for_tokens(workspace_id, tokens):
            protected = VAULT.decrypt_json(row.pop("encrypted_json"), workspace_id=workspace_id, purpose="privacy-record")
            row.pop("workspace_id", None)
            row.pop("subject_token", None)
            row.pop("subject_key_id", None)
            row.update(protected)
            row["restricted"] = bool(row["restricted"])
            row["consent_withdrawn"] = bool(row["consent_withdrawn"])
            result.append(row)
        return result

    def rectify_privacy_record(self, *, workspace_id: str, tokens: list[str], record_id: str, payload: dict[str, Any], declared_fields: list[str]) -> bool:
        rows = self._privacy_rows_for_tokens(workspace_id, tokens)
        target = next((row for row in rows if row["record_id"] == record_id), None)
        if target is None:
            return False
        protected = VAULT.decrypt_json(target["encrypted_json"], workspace_id=workspace_id, purpose="privacy-record")
        protected["payload"] = payload
        protected["declared_fields"] = sorted({item.strip() for item in declared_fields if item.strip()})
        encrypted = VAULT.encrypt_json(protected, workspace_id=workspace_id, purpose="privacy-record")
        now = int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("""UPDATE privacy_records SET encrypted_json=:encrypted_json, updated_at=:updated_at WHERE workspace_id=:workspace_id AND record_id=:record_id"""), {"encrypted_json": encrypted, "updated_at": now, "workspace_id": workspace_id, "record_id": record_id})
        return True

    def set_subject_restriction(self, *, workspace_id: str, tokens: list[str], restricted: bool) -> int:
        affected = 0
        with self.engine.begin() as conn:
            for token in tokens:
                result = conn.execute(text("""UPDATE privacy_records SET restricted=:restricted, updated_at=:updated_at WHERE workspace_id=:workspace_id AND subject_token=:subject_token"""), {"restricted": 1 if restricted else 0, "updated_at": int(time.time()), "workspace_id": workspace_id, "subject_token": token})
                affected += int(result.rowcount or 0)
        return affected

    def withdraw_subject_consent(self, *, workspace_id: str, tokens: list[str]) -> int:
        affected = 0
        with self.engine.begin() as conn:
            for token in tokens:
                result = conn.execute(text("""UPDATE privacy_records SET consent_withdrawn=1, restricted=1, updated_at=:updated_at WHERE workspace_id=:workspace_id AND subject_token=:subject_token AND lawful_basis='consent'"""), {"updated_at": int(time.time()), "workspace_id": workspace_id, "subject_token": token})
                affected += int(result.rowcount or 0)
        return affected

    def erase_subject_privacy_records(self, *, workspace_id: str, tokens: list[str]) -> int:
        affected = 0
        with self.engine.begin() as conn:
            for token in tokens:
                result = conn.execute(text("DELETE FROM privacy_records WHERE workspace_id=:workspace_id AND subject_token=:subject_token"), {"workspace_id": workspace_id, "subject_token": token})
                affected += int(result.rowcount or 0)
        return affected

    def purge_expired_privacy_records(self, *, workspace_id: str, now: int | None = None) -> int:
        cutoff = int(time.time()) if now is None else int(now)
        with self.engine.begin() as conn:
            result = conn.execute(text("DELETE FROM privacy_records WHERE workspace_id=:workspace_id AND retention_until <= :cutoff"), {"workspace_id": workspace_id, "cutoff": cutoff})
        return int(result.rowcount or 0)

    def privacy_inventory(self, workspace_id: str, now: int | None = None) -> dict[str, Any]:
        cutoff = int(time.time()) if now is None else int(now)
        with self.engine.connect() as conn:
            rows = conn.execute(text("""SELECT purpose, lawful_basis, restricted, retention_until FROM privacy_records WHERE workspace_id=:workspace_id"""), {"workspace_id": workspace_id}).mappings().all()
        purposes: dict[str, int] = {}
        lawful_bases: dict[str, int] = {}
        restricted = 0
        expired = 0
        active = 0
        for row in rows:
            purposes[row["purpose"]] = purposes.get(row["purpose"], 0) + 1
            lawful_bases[row["lawful_basis"]] = lawful_bases.get(row["lawful_basis"], 0) + 1
            restricted += 1 if row["restricted"] else 0
            if int(row["retention_until"]) <= cutoff:
                expired += 1
            else:
                active += 1
        return {"active_records": active, "restricted_records": restricted, "expired_records": expired, "purposes": purposes, "lawful_bases": lawful_bases}

    def record_privacy_breach(self, *, workspace_id: str, incident_reference: str, details: dict[str, Any], detected_at: int, risk_assessment: str) -> dict[str, Any]:
        breach_id = "pbr_" + uuid.uuid4().hex[:20]
        deadline = int(detected_at) + 72 * 3600
        encrypted = VAULT.encrypt_json(details, workspace_id=workspace_id, purpose="privacy-breach")
        status = "ASSESSMENT_REQUIRED" if risk_assessment == "unlikely" else "NOTIFICATION_REVIEW"
        created_at = int(time.time())
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO privacy_breaches(breach_id, workspace_id, incident_reference, encrypted_json, detected_at, notification_deadline_at, authority_notified_at, status, risk_assessment, created_at) VALUES (:breach_id, :workspace_id, :incident_reference, :encrypted_json, :detected_at, :deadline, NULL, :status, :risk_assessment, :created_at)"""), {"breach_id": breach_id, "workspace_id": workspace_id, "incident_reference": incident_reference, "encrypted_json": encrypted, "detected_at": int(detected_at), "deadline": deadline, "status": status, "risk_assessment": risk_assessment, "created_at": created_at})
        return {"breach_id": breach_id, "incident_reference": incident_reference, "detected_at": int(detected_at), "notification_deadline_at": deadline, "authority_notified_at": None, "status": status, "risk_assessment": risk_assessment}

    def open_privacy_breaches(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("""SELECT breach_id, incident_reference, detected_at, notification_deadline_at, authority_notified_at, status, risk_assessment FROM privacy_breaches WHERE workspace_id=:workspace_id AND status != 'CLOSED' ORDER BY detected_at DESC"""), {"workspace_id": workspace_id}).mappings().all()
        return [dict(row) for row in rows]


STORE = DatabaseStore(SETTINGS.database_url, SETTINGS.db_path)
