from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.crypto_core as crypto_core
from app.api import app
from app.config import SETTINGS
from app.crypto_core import CryptoValidationError, KeyRing, commitment, generate_x25519_keypair, seal
from app.crypto_recipient import open_recipient_envelope
from app.store import STORE

client = TestClient(app)
HEADERS = {"X-API-Key": "test-secret", "X-Workspace-ID": "v13-lab"}


def _recipient_seal(ttl_seconds: int = 600):
    pair = generate_x25519_keypair()
    intent = {"action": "approve", "asset": "record", "amount": "1", "recipient": "v13-lab"}
    digest = commitment(intent, domain="intent")["sha256"]
    envelope = seal(
        payload={"message": "recipient protected"},
        intent=intent,
        effect=dict(intent),
        approvals=[{"approver_id": "tester", "intent_digest": digest, "proof": "opaque"}],
        min_approvals=1,
        workspace_id="v13-lab",
        domain="validation",
        ttl_seconds=ttl_seconds,
        recipient_public_key_b64=pair["public_key_b64"],
    )
    return pair, digest, envelope


def test_recipient_only_open_without_master_key_path():
    pair, digest, envelope = _recipient_seal()
    opened = open_recipient_envelope(
        envelope,
        expected_workspace_id="v13-lab",
        recipient_private_key_b64=pair["private_key_b64"],
        expected_signing_public_key_b64=envelope["signing_public_key_b64"],
        expected_intent_digest=digest,
    )
    assert opened["recipient_verified"] is True
    assert opened["signer_verified"] is True
    assert opened["content"]["payload"]["message"] == "recipient protected"


def test_recipient_api_round_trip():
    pair, digest, envelope = _recipient_seal()
    response = client.post(
        "/v1/crypto/open-recipient",
        json={
            "envelope": envelope,
            "recipient_private_key_b64": pair["private_key_b64"],
            "expected_signing_public_key_b64": envelope["signing_public_key_b64"],
            "expected_intent_digest": digest,
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["recipient_verified"] is True


def test_recipient_open_rejects_wrong_private_key_and_signer_pin():
    pair, digest, envelope = _recipient_seal()
    wrong = generate_x25519_keypair()
    with pytest.raises(CryptoValidationError, match="recipient_authentication_failed"):
        open_recipient_envelope(
            envelope,
            expected_workspace_id="v13-lab",
            recipient_private_key_b64=wrong["private_key_b64"],
            expected_signing_public_key_b64=envelope["signing_public_key_b64"],
            expected_intent_digest=digest,
        )
    with pytest.raises(CryptoValidationError, match="unexpected_signer"):
        open_recipient_envelope(
            envelope,
            expected_workspace_id="v13-lab",
            recipient_private_key_b64=pair["private_key_b64"],
            expected_signing_public_key_b64="A" * len(envelope["signing_public_key_b64"]),
            expected_intent_digest=digest,
        )


def test_recipient_open_enforces_expiry_with_injected_clock():
    pair, digest, envelope = _recipient_seal(ttl_seconds=60)
    future = int(envelope["header"]["expires_at"]) + 1
    with pytest.raises(CryptoValidationError, match="envelope_expired"):
        open_recipient_envelope(
            envelope,
            expected_workspace_id="v13-lab",
            recipient_private_key_b64=pair["private_key_b64"],
            expected_signing_public_key_b64=envelope["signing_public_key_b64"],
            expected_intent_digest=digest,
            now=future,
        )


def test_recipient_wrap_and_ciphertext_mutations_fail_closed():
    pair, digest, envelope = _recipient_seal()
    for path in (("ciphertext_b64",), ("recipient_wrap", "wrapped_key_b64"), ("recipient_wrap", "ephemeral_public_key_b64")):
        tampered = copy.deepcopy(envelope)
        target = tampered
        for key in path[:-1]:
            target = target[key]
        value = target[path[-1]]
        target[path[-1]] = ("A" if value[0] != "A" else "B") + value[1:]
        with pytest.raises(CryptoValidationError):
            open_recipient_envelope(
                tampered,
                expected_workspace_id="v13-lab",
                recipient_private_key_b64=pair["private_key_b64"],
                expected_signing_public_key_b64=envelope["signing_public_key_b64"],
                expected_intent_digest=digest,
            )


def test_master_key_rotation_keeps_old_envelope_decryptable(monkeypatch):
    old_key = crypto_core._b64e(b"o" * 32)
    new_key = crypto_core._b64e(b"n" * 32)
    old_settings = replace(SETTINGS, master_keys=(("old", old_key),))
    rotated_settings = replace(SETTINGS, master_keys=(("new", new_key), ("old", old_key)))

    monkeypatch.setattr(crypto_core, "SETTINGS", old_settings)
    monkeypatch.setattr(crypto_core, "KEYRING", KeyRing())
    intent = {"action": "read", "asset": "document"}
    digest = commitment(intent, domain="intent")["sha256"]
    envelope = seal(
        payload={"value": 1}, intent=intent, effect=intent,
        approvals=[{"approver_id": "a", "intent_digest": digest, "proof": "p"}],
        min_approvals=1, workspace_id="v13-lab", domain="rotation", ttl_seconds=600,
    )
    assert envelope["header"]["key_id"] == "old"

    monkeypatch.setattr(crypto_core, "SETTINGS", rotated_settings)
    monkeypatch.setattr(crypto_core, "KEYRING", KeyRing())
    opened = crypto_core.open_envelope(envelope, expected_workspace_id="v13-lab", expected_intent_digest=digest)
    assert opened["content"]["payload"]["value"] == 1
    assert crypto_core.KEYRING.active.key_id == "new"


def test_replay_nonce_reservation_is_single_winner_under_concurrency():
    fingerprint = "v13-concurrent-replay-" + crypto_core._b64e(b"r" * 16)
    def reserve(_: int) -> bool:
        return STORE.reserve_crypto_nonce(workspace_id="v13-concurrency", nonce_fingerprint=fingerprint, expires_at=0)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(bool(item) for item in results) == 1


def test_validation_readiness_keeps_external_claims_pending():
    response = client.get("/v1/validation/readiness", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_status"] == "EXTERNAL_VALIDATION_CANDIDATE"
    assert body["external_gates"]["independent_penetration_test"] == "PENDING_EXTERNAL_PARTY"
    assert body["external_gates"]["independent_product_validation"] == "PENDING_EXTERNAL_PARTY"


def test_external_validation_protocol_is_fingerprinted_and_predeclared():
    response = client.get("/v1/validation/protocol", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["protocol_sha256"]) == 64
    assert body["protocol"]["minimum_total_cases"] >= 500
    assert body["protocol"]["validation_boundary"].startswith("Protocol only")
