from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ops_attestation import DOMAIN, _canonical, build_attestation


def test_release_attestation_signs_and_verifies_when_key_is_configured(tmp_path, monkeypatch):
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"product":"ORBYTHRA"}\n', encoding="utf-8")
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes_raw()
    monkeypatch.setenv("SEAL_ED25519_PRIVATE_KEY_B64", base64.b64encode(raw).decode("ascii"))
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    result = build_attestation([artifact])

    assert result["subject"]["git_sha"] == "a" * 40
    assert result["signature"]["signed"] is True
    public = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(result["signature"]["public_key_b64"])
    )
    canonical = _canonical(result["subject"])
    framed = (
        len(DOMAIN).to_bytes(8, "big")
        + DOMAIN
        + len(canonical).to_bytes(8, "big")
        + canonical
    )
    public.verify(base64.b64decode(result["signature"]["signature_b64"]), framed)


def test_release_attestation_is_explicitly_unsigned_without_secret(tmp_path, monkeypatch):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("ORBYTHRA\n", encoding="utf-8")
    monkeypatch.delenv("SEAL_ED25519_PRIVATE_KEY_B64", raising=False)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)

    result = build_attestation([artifact])

    assert result["signature"]["signed"] is False
    assert "not configured" in result["signature"]["reason"]
