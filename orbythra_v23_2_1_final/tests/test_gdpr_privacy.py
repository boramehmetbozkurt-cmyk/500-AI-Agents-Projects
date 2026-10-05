from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.store import STORE

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "gdpr-lab"}
OTHER_WORKSPACE = {"X-API-Key": "test-secret", "X-Workspace-ID": "gdpr-other"}


def _subject() -> str:
    return f"person-{uuid.uuid4().hex}@example.test"


def _create(subject_id: str, *, lawful_basis: str = "contract") -> dict:
    payload = {
        "subject_id": subject_id,
        "purpose": "Provide contracted verification service",
        "lawful_basis": lawful_basis,
        "data_categories": ["contact", "service_usage"],
        "declared_fields": ["email", "usage_reference"],
        "payload": {"email": subject_id, "usage_reference": "case-42"},
        "retention_days": 30,
    }
    if lawful_basis == "consent":
        payload["consent_reference"] = "consent-2026-09"
    response = client.post("/v1/privacy/records", json=payload, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def test_gdpr_requires_consent_reference_when_consent_is_basis():
    response = client.post("/v1/privacy/records", json={"subject_id": _subject(), "purpose": "Optional product research", "lawful_basis": "consent", "data_categories": ["contact"], "declared_fields": ["email"], "payload": {"email": "a@example.test"}, "retention_days": 30}, headers=HEADERS)
    assert response.status_code == 422
    assert "consent_reference_required" in response.text


def test_gdpr_rejects_undeclared_fields_for_data_minimisation():
    response = client.post("/v1/privacy/records", json={"subject_id": _subject(), "purpose": "Support", "lawful_basis": "contract", "data_categories": ["contact"], "declared_fields": ["email"], "payload": {"email": "a@example.test", "unneeded_secret": "no"}, "retention_days": 30}, headers=HEADERS)
    assert response.status_code == 422
    assert "undeclared_payload_fields" in response.text


def test_special_category_requires_article9_condition():
    response = client.post("/v1/privacy/records", json={"subject_id": _subject(), "purpose": "High risk evaluation", "lawful_basis": "consent", "data_categories": ["health"], "declared_fields": ["health_note"], "payload": {"health_note": "sensitive"}, "retention_days": 10, "consent_reference": "consent-special", "special_category": True}, headers=HEADERS)
    assert response.status_code == 422
    assert "article9_condition_required" in response.text


def test_subject_identifier_is_pseudonymised_and_payload_encrypted_at_rest():
    subject = _subject()
    created = _create(subject)
    with STORE.engine.connect() as conn:
        row = conn.execute(text("SELECT subject_token, encrypted_json FROM privacy_records WHERE record_id=:record_id"), {"record_id": created["record_id"]}).first()
    assert row is not None
    assert row[0] != subject
    assert subject not in row[0]
    assert str(row[1]).startswith("orbenc1:")
    assert subject not in str(row[1])


def test_access_and_portability_export_returns_machine_readable_records():
    subject = _subject()
    created = _create(subject)
    response = client.post("/v1/privacy/subjects/export", json={"subject_id": subject}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "application/json"
    assert any(item["record_id"] == created["record_id"] for item in body["records"])
    assert body["records"][0]["payload"]["email"] == subject


def test_subject_export_is_workspace_isolated():
    subject = _subject()
    _create(subject)
    response = client.post("/v1/privacy/subjects/export", json={"subject_id": subject}, headers=OTHER_WORKSPACE)
    assert response.status_code == 200
    assert response.json()["records"] == []


def test_rectification_updates_personal_data():
    subject = _subject()
    created = _create(subject)
    updated_email = "corrected@example.test"
    response = client.post("/v1/privacy/records/rectify", json={"subject_id": subject, "record_id": created["record_id"], "declared_fields": ["email", "usage_reference"], "payload": {"email": updated_email, "usage_reference": "case-42"}}, headers=HEADERS)
    assert response.status_code == 200, response.text
    export = client.post("/v1/privacy/subjects/export", json={"subject_id": subject}, headers=HEADERS).json()
    assert export["records"][0]["payload"]["email"] == updated_email


def test_restriction_and_consent_withdrawal_are_enforced_as_state():
    subject = _subject()
    _create(subject, lawful_basis="consent")
    restricted = client.post("/v1/privacy/subjects/restrict", json={"subject_id": subject}, headers=HEADERS)
    assert restricted.status_code == 200
    assert restricted.json()["affected_records"] == 1
    withdrawn = client.post("/v1/privacy/subjects/withdraw-consent", json={"subject_id": subject}, headers=HEADERS)
    assert withdrawn.status_code == 200
    assert withdrawn.json()["affected_records"] == 1
    record = client.post("/v1/privacy/subjects/export", json={"subject_id": subject}, headers=HEADERS).json()["records"][0]
    assert record["restricted"] is True
    assert record["consent_withdrawn"] is True


def test_erasure_removes_registered_personal_data():
    subject = _subject()
    _create(subject)
    erased = client.post("/v1/privacy/subjects/erase", json={"subject_id": subject}, headers=HEADERS)
    assert erased.status_code == 200
    assert erased.json()["affected_records"] == 1
    exported = client.post("/v1/privacy/subjects/export", json={"subject_id": subject}, headers=HEADERS)
    assert exported.json()["records"] == []


def test_retention_purge_removes_expired_records():
    subject = _subject()
    created = _create(subject)
    with STORE.engine.begin() as conn:
        conn.execute(text("UPDATE privacy_records SET retention_until=1 WHERE record_id=:record_id"), {"record_id": created["record_id"]})
    response = client.post("/v1/privacy/retention/purge", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["purged_records"] >= 1


def test_processing_inventory_contains_no_raw_payloads():
    subject = _subject()
    _create(subject)
    response = client.get("/v1/privacy/inventory", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["active_records"] >= 1
    assert body["raw_subject_identifiers_stored"] is False
    assert body["encryption_at_rest"] is True
    assert subject not in response.text


def test_breach_register_calculates_72_hour_review_deadline():
    detected = int(time.time()) - 60
    response = client.post("/v1/privacy/breaches", json={"incident_reference": f"INC-{uuid.uuid4().hex[:8]}", "summary": "Potential unauthorised access under investigation", "detected_at": detected, "personal_data_categories": ["contact"], "estimated_subjects": 5, "risk_assessment": "possible"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notification_deadline_at"] == detected + 72 * 3600
    assert body["status"] == "NOTIFICATION_REVIEW"


def test_privacy_status_does_not_claim_legal_certification():
    response = client.get("/v1/privacy/status", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["legal_review_required"] is True
    assert "not a legal certification" in body["claim"]
