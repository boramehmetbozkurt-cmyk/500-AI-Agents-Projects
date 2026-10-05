from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from app.crypto_core import commitment, dsel_decode, dsel_encode, normalize_wrapped_text, verify_effect_binding
from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "crypto-lab"}


def _seal_payload(algorithm: str = "aes256-gcm") -> dict:
    intent = {"action": "transfer", "asset": "USDC", "amount": "25", "recipient": "0xabc", "chain": "base", "fee": "0.01"}
    digest = commitment(intent, domain="intent")["sha256"]
    response = client.post("/v1/crypto/seal", json={"payload": {"message": "protected"}, "intent": intent, "effect": dict(intent), "approvals": [{"approver_id": "gesture-device-1", "intent_digest": digest, "proof_type": "gesture", "proof": "gesture-proof-opaque"}, {"approver_id": "second-party", "intent_digest": digest, "proof_type": "two_party", "proof": "second-proof-opaque"}], "min_approvals": 2, "domain": "transaction", "ttl_seconds": 600, "algorithm": algorithm}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def test_morseguard_wrappers_are_bounded_and_normalized():
    assert normalize_wrapped_text("hex:48656c6c6f") == "Hello"
    assert normalize_wrapped_text("base64:SGVsbG8=") == "Hello"
    assert normalize_wrapped_text("morse:.... . .-.. .-.. ---") == "HELLO"


def test_dsel_round_trip_is_key_derived():
    seed = b"s" * 32
    encoded = dsel_encode(b"orbythra", seed)
    assert encoded != b"b3JieXRockE"
    assert dsel_decode(encoded, seed) == b"orbythra"


def test_effectseal_blocks_recipient_substitution():
    intent = {"action": "transfer", "amount": "1", "recipient": "alice"}
    effect = {"action": "transfer", "amount": "1", "recipient": "mallory"}
    assert verify_effect_binding(intent, effect) == ["recipient"]


def test_crypto_status_reports_full_stack():
    response = client.get("/v1/crypto/status", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert "AES-256-GCM" in body["components"]
    assert "Ed25519 signed envelopes" in body["components"]


def test_aes_effectseal_round_trip_and_replay_rejection():
    sealed = _seal_payload("aes256-gcm")
    opened = client.post("/v1/crypto/open", json={"envelope": sealed["envelope"], "expected_intent_digest": sealed["intent_digest"], "enforce_replay_protection": True}, headers=HEADERS)
    assert opened.status_code == 200, opened.text
    assert opened.json()["payload"]["message"] == "protected"
    assert opened.json()["signer_verified"] is True
    replay = client.post("/v1/crypto/open", json={"envelope": sealed["envelope"], "expected_intent_digest": sealed["intent_digest"], "enforce_replay_protection": True}, headers=HEADERS)
    assert replay.status_code == 409
    assert replay.json()["detail"] == "replay_detected"


def test_chacha_effectseal_round_trip():
    sealed = _seal_payload("chacha20-poly1305")
    opened = client.post("/v1/crypto/open", json={"envelope": sealed["envelope"], "expected_intent_digest": sealed["intent_digest"], "enforce_replay_protection": False}, headers=HEADERS)
    assert opened.status_code == 200, opened.text
    assert opened.json()["payload"]["message"] == "protected"


def test_signature_or_ciphertext_tamper_fails_closed():
    sealed = _seal_payload()
    tampered = copy.deepcopy(sealed["envelope"])
    ciphertext = tampered["ciphertext_b64"]
    tampered["ciphertext_b64"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    response = client.post("/v1/crypto/open", json={"envelope": tampered, "enforce_replay_protection": False}, headers=HEADERS)
    assert response.status_code == 400
    assert response.json()["detail"] in {"invalid_signature", "authentication_failed"}


def test_gestureguard_rejects_approval_bound_to_wrong_intent():
    intent = {"action": "transfer", "asset": "USDC", "amount": "25", "recipient": "0xabc"}
    response = client.post("/v1/crypto/seal", json={"payload": {"message": "protected"}, "intent": intent, "effect": intent, "approvals": [{"approver_id": "gesture-device-1", "intent_digest": "0" * 64, "proof_type": "gesture", "proof": "opaque"}], "min_approvals": 1, "domain": "transaction"}, headers=HEADERS)
    assert response.status_code == 400
    assert response.json()["detail"] == "approval_not_bound_to_intent"


def test_at_rest_records_are_encrypted_in_database():
    from app.store import STORE
    result = STORE.create_evidence_snapshot(workspace_id="crypto-lab", principal_id="tester", label="encrypted", evidence=[{"source": "example", "claim": "hello"}])
    with STORE.engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT evidence_json FROM evidence_snapshots WHERE snapshot_id=?", (result["snapshot_id"],)).first()
    assert row is not None
    assert str(row[0]).startswith("orbenc1:")
    loaded = STORE.get_evidence_snapshot("crypto-lab", result["snapshot_id"])
    assert loaded is not None
    assert loaded["evidence"][0]["claim"] == "hello"
