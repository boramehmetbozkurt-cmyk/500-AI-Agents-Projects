from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
try:
    from cryptography.hazmat.primitives.asymmetric import mldsa, mlkem
except ImportError:
    mldsa = None  # type: ignore[assignment]
    mlkem = None  # type: ignore[assignment]
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
try:
    from cryptography.hazmat.primitives.hpke import (
        AEAD as HPKEAEAD,
        KDF as HPKEKDF,
        KEM as HPKEKEM,
        MLKEM768X25519PrivateKey,
        Suite as HPKESuite,
    )
except ImportError:
    HPKEAEAD = HPKEKDF = HPKEKEM = MLKEM768X25519PrivateKey = HPKESuite = None  # type: ignore[assignment]

from app.config import SETTINGS
from app.crypto_core import (
    CryptoConfigurationError,
    CryptoValidationError,
    _aead,
    _b64d,
    _hkdf,
    canonical_json,
    ciphertext_digest,
    commitment,
    dsel_decode,
    signature_input_for_envelope,
    verify_effect_binding,
)


def _verify_envelope_signatures(
    envelope: dict[str, Any],
    *,
    expected_signing_public_key_b64: str,
    expected_pq_signing_public_key_b64: str | None,
) -> None:
    supplied_public = str(envelope.get("signing_public_key_b64", ""))
    if not supplied_public or not hmac.compare_digest(supplied_public, expected_signing_public_key_b64):
        raise CryptoValidationError("unexpected_signer")
    signature_input = signature_input_for_envelope(envelope)
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(supplied_public))
        public_key.verify(_b64d(str(envelope.get("signature_b64", ""))), signature_input)
    except (ValueError, InvalidSignature) as exc:
        raise CryptoValidationError("invalid_signature") from exc

    header = envelope.get("header") or {}
    version = str(header.get("version", "orbythra-effectseal-v1"))
    pq_public = str(envelope.get("pq_signing_public_key_b64", "")).strip()
    pq_signature = str(envelope.get("pq_signature_b64", "")).strip()
    if pq_public or pq_signature:
        if mldsa is None:
            raise CryptoConfigurationError("pqc_backend_unavailable")
        if not pq_public or not pq_signature:
            raise CryptoValidationError("incomplete_pq_signature")
        if expected_pq_signing_public_key_b64:
            if not hmac.compare_digest(pq_public, expected_pq_signing_public_key_b64):
                raise CryptoValidationError("unexpected_pq_signer")
        elif SETTINGS.pqc_mode == "hybrid-required":
            raise CryptoValidationError("expected_pq_signer_required")
        try:
            mldsa.MLDSA65PublicKey.from_public_bytes(_b64d(pq_public)).verify(
                _b64d(pq_signature), signature_input, b"orbythra-effectseal-v2"
            )
        except UnsupportedAlgorithm as exc:
            raise CryptoConfigurationError("pqc_backend_unavailable") from exc
        except (ValueError, InvalidSignature) as exc:
            raise CryptoValidationError("invalid_pq_signature") from exc
    elif version == "orbythra-effectseal-v2" and str(header.get("pqc_mode", "off")) == "hybrid-required":
        raise CryptoValidationError("pqc_signature_required")



def _validate_plaintext(plaintext: bytes, header: dict[str, Any]) -> dict[str, Any]:
    try:
        content = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise CryptoValidationError("invalid_plaintext") from exc
    recomputed_intent = commitment(content.get("intent"), domain="intent")["sha256"]
    if not hmac.compare_digest(recomputed_intent, str(header.get("intent_sha256", "")).lower()):
        raise CryptoValidationError("intent_commitment_corrupted")
    effect = content.get("effect")
    if effect is not None:
        mismatches = verify_effect_binding(content.get("intent") or {}, effect)
        if mismatches:
            raise CryptoValidationError("intent_effect_mismatch:" + ",".join(mismatches))
    return content


def _result(envelope: dict[str, Any], header: dict[str, Any], content: dict[str, Any], current_time: int, nonce: bytes) -> dict[str, Any]:
    key_id = str(header.get("key_id", ""))
    nonce_fingerprint = hashlib.sha256(
        key_id.encode("utf-8") + b":" + nonce + b":" + ciphertext_digest(envelope)
    ).hexdigest()
    return {
        "content": content,
        "header": header,
        "nonce_fingerprint": nonce_fingerprint,
        "signer_verified": True,
        "recipient_verified": True,
        "ciphertext_sha256": hashlib.sha256(_b64d(str(envelope.get("ciphertext_b64", "")))).hexdigest(),
        "opened_at": current_time,
    }


def open_recipient_envelope(
    envelope: dict[str, Any],
    *,
    expected_workspace_id: str,
    recipient_private_key_b64: str,
    expected_signing_public_key_b64: str,
    expected_pq_signing_public_key_b64: str | None = None,
    expected_intent_digest: str | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        header = envelope["header"]
        workspace_id = str(header["workspace_id"])
        algorithm = str(header["algorithm"])
        recipient_wrap = envelope["recipient_wrap"]
    except (KeyError, TypeError) as exc:
        raise CryptoValidationError("recipient_wrap_missing_or_malformed") from exc

    if workspace_id != expected_workspace_id:
        raise CryptoValidationError("workspace_mismatch")
    current_time = int(time.time()) if now is None else int(now)
    expires_at = int(header.get("expires_at") or 0)
    if expires_at and current_time > expires_at:
        raise CryptoValidationError("envelope_expired")

    _verify_envelope_signatures(
        envelope,
        expected_signing_public_key_b64=expected_signing_public_key_b64,
        expected_pq_signing_public_key_b64=expected_pq_signing_public_key_b64,
    )

    if expected_intent_digest:
        actual = str(header.get("intent_sha256", "")).lower()
        if not hmac.compare_digest(actual, expected_intent_digest.lower()):
            raise CryptoValidationError("intent_commitment_mismatch")

    nonce = _b64d(str(envelope.get("nonce_b64", "")))
    if len(nonce) != 12:
        raise CryptoValidationError("invalid_nonce_length")
    aad = canonical_json(header)

    private_raw = _b64d(recipient_private_key_b64)
    ephemeral_raw = _b64d(str(recipient_wrap.get("ephemeral_public_key_b64", "")))
    recipient_nonce = _b64d(str(recipient_wrap.get("nonce_b64", "")))
    if len(private_raw) != 32 or len(ephemeral_raw) != 32 or len(recipient_nonce) != 12:
        raise CryptoValidationError("invalid_x25519_recipient_material")

    try:
        recipient_private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
        ephemeral_public = x25519.X25519PublicKey.from_public_bytes(ephemeral_raw)
        shared = recipient_private.exchange(ephemeral_public)
        recipient_kek = _hkdf(shared, salt=nonce, info=b"orbythra:x25519-recipient-wrap:v1")
        dek = AESGCM(recipient_kek).decrypt(
            recipient_nonce,
            _b64d(str(recipient_wrap.get("wrapped_key_b64", ""))),
            aad,
        )
        represented = _aead(algorithm, dek).decrypt(
            nonce,
            _b64d(str(envelope.get("ciphertext_b64", ""))),
            aad,
        )
    except (ValueError, InvalidTag) as exc:
        raise CryptoValidationError("recipient_authentication_failed") from exc

    dsel_seed = _hkdf(dek, salt=nonce, info=b"orbythra:dsel-adunaic:v1")
    plaintext = dsel_decode(represented, dsel_seed)
    content = _validate_plaintext(plaintext, header)
    return _result(envelope, header, content, current_time, nonce)


def open_hybrid_recipient_envelope(
    envelope: dict[str, Any],
    *,
    expected_workspace_id: str,
    recipient_x25519_private_key_b64: str,
    recipient_mlkem768_private_key_b64: str,
    expected_signing_public_key_b64: str,
    expected_pq_signing_public_key_b64: str | None = None,
    expected_intent_digest: str | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    if mlkem is None or MLKEM768X25519PrivateKey is None or HPKESuite is None or HPKEKEM is None or HPKEKDF is None or HPKEAEAD is None:
        raise CryptoConfigurationError("pqc_backend_unavailable")
    try:
        header = envelope["header"]
        workspace_id = str(header["workspace_id"])
        algorithm = str(header["algorithm"])
        hybrid_wrap = envelope["hybrid_recipient_wrap"]
    except (KeyError, TypeError) as exc:
        raise CryptoValidationError("hybrid_recipient_wrap_missing_or_malformed") from exc

    if str(hybrid_wrap.get("scheme", "")) != "ML-KEM-768+X25519/HPKE-AES256GCM":
        raise CryptoValidationError("unsupported_hybrid_recipient_scheme")
    if workspace_id != expected_workspace_id:
        raise CryptoValidationError("workspace_mismatch")
    current_time = int(time.time()) if now is None else int(now)
    expires_at = int(header.get("expires_at") or 0)
    if expires_at and current_time > expires_at:
        raise CryptoValidationError("envelope_expired")

    _verify_envelope_signatures(
        envelope,
        expected_signing_public_key_b64=expected_signing_public_key_b64,
        expected_pq_signing_public_key_b64=expected_pq_signing_public_key_b64,
    )
    if expected_intent_digest:
        actual = str(header.get("intent_sha256", "")).lower()
        if not hmac.compare_digest(actual, expected_intent_digest.lower()):
            raise CryptoValidationError("intent_commitment_mismatch")

    nonce = _b64d(str(envelope.get("nonce_b64", "")))
    if len(nonce) != 12:
        raise CryptoValidationError("invalid_nonce_length")
    aad = canonical_json(header)

    try:
        x_private = x25519.X25519PrivateKey.from_private_bytes(_b64d(recipient_x25519_private_key_b64))
        pq_private = mlkem.MLKEM768PrivateKey.from_seed_bytes(_b64d(recipient_mlkem768_private_key_b64))
        hybrid_private = MLKEM768X25519PrivateKey(pq_private, x_private)
        suite = HPKESuite(HPKEKEM.MLKEM768_X25519, HPKEKDF.HKDF_SHA256, HPKEAEAD.AES_256_GCM)
        hpke_info = b"ORBYTHRA-HYBRID-RECIPIENT-V1\x00" + hashlib.sha256(aad).digest()
        dek = suite.decrypt(_b64d(str(hybrid_wrap.get("ciphertext_b64", ""))), hybrid_private, info=hpke_info)
        represented = _aead(algorithm, dek).decrypt(
            nonce,
            _b64d(str(envelope.get("ciphertext_b64", ""))),
            aad,
        )
    except UnsupportedAlgorithm as exc:
        raise CryptoConfigurationError("pqc_backend_unavailable") from exc
    except (ValueError, InvalidTag) as exc:
        raise CryptoValidationError("hybrid_recipient_authentication_failed") from exc

    dsel_seed = _hkdf(dek, salt=nonce, info=b"orbythra:dsel-adunaic:v1")
    plaintext = dsel_decode(represented, dsel_seed)
    content = _validate_plaintext(plaintext, header)
    return _result(envelope, header, content, current_time, nonce)
