from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from seal import ReplayGuard, authorize_execution, seal_intent, sign_receipt, verify_receipt


def test_replay_guard_rejects_second_use(tmp_path):
    guard = ReplayGuard(str(tmp_path / "replay.sqlite3"))
    intent = seal_intent("deprem araştır", ["earthquakes"], ttl_seconds=60)
    authorize_execution(intent, ["earthquakes"], guard)
    with pytest.raises(PermissionError):
        authorize_execution(intent, ["earthquakes"], guard)


def test_unauthorized_tool_is_rejected(tmp_path):
    guard = ReplayGuard(str(tmp_path / "replay.sqlite3"))
    intent = seal_intent("deprem araştır", ["earthquakes"], ttl_seconds=60)
    with pytest.raises(PermissionError):
        authorize_execution(intent, ["cyber_attacks"], guard)


def test_signed_receipt_verifies(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    monkeypatch.setenv("SEAL_ED25519_PRIVATE_KEY_B64", base64.b64encode(raw).decode("ascii"))

    intent = seal_intent("deprem araştır", ["earthquakes"], ttl_seconds=60)
    receipt = sign_receipt(intent, ["earthquakes"], "kanıt bulundu", "abc123")
    assert receipt["signature_alg"] == "Ed25519"
    assert verify_receipt(receipt) is True

    receipt["actual_effect"]["evidence_digest"] = "tampered"
    assert verify_receipt(receipt) is False
