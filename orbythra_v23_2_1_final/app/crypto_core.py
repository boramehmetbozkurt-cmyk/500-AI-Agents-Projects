from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidSignature, InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, x25519
try:
    from cryptography.hazmat.primitives.asymmetric import mldsa, mlkem
except ImportError:  # cryptography < 50: classical crypto remains usable; PQC fails closed when requested.
    mldsa = None  # type: ignore[assignment]
    mlkem = None  # type: ignore[assignment]
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
try:
    from cryptography.hazmat.primitives.hpke import (
        AEAD as HPKEAEAD,
        KDF as HPKEKDF,
        KEM as HPKEKEM,
        MLKEM768X25519PublicKey,
        Suite as HPKESuite,
    )
except ImportError:  # cryptography < 50
    HPKEAEAD = HPKEKDF = HPKEKEM = MLKEM768X25519PublicKey = HPKESuite = None  # type: ignore[assignment]
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import SETTINGS

_B64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_BIDI_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_MORSE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E",
    "..-.": "F", "--.": "G", "....": "H", "..": "I", ".---": "J",
    "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
    ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T",
    "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y",
    "--..": "Z", "-----": "0", ".----": "1", "..---": "2", "...--": "3",
    "....-": "4", ".....": "5", "-....": "6", "--...": "7", "---..": "8",
    "----.": "9",
}
_PROTECTED_EFFECT_FIELDS = (
    "action", "asset", "amount", "recipient", "chain", "fee", "expiry", "nonce"
)


class CryptoConfigurationError(RuntimeError):
    pass


class CryptoValidationError(ValueError):
    pass


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:
        raise CryptoValidationError("invalid_base64") from exc


def derive_argon2id_key(passphrase: str, salt: bytes, *, memory_cost_kib: int = 64 * 1024, time_cost: int = 3, parallelism: int = 2) -> bytes:
    if len(salt) < 16:
        raise CryptoValidationError("argon2_salt_too_short")
    return hash_secret_raw(secret=passphrase.encode("utf-8"), salt=salt, time_cost=time_cost, memory_cost=memory_cost_kib, parallelism=parallelism, hash_len=32, type=Type.ID)


def _decode_morse(value: str) -> str:
    words: list[str] = []
    for word in value.strip().split("/"):
        letters: list[str] = []
        for token in word.strip().split():
            if token not in _MORSE:
                raise CryptoValidationError("invalid_morse_token")
            letters.append(_MORSE[token])
        words.append("".join(letters))
    return " ".join(words)


def normalize_wrapped_text(value: str, max_depth: int = 3) -> str:
    current = unicodedata.normalize("NFKC", value)
    current = _ZERO_WIDTH_RE.sub("", current)
    if _BIDI_RE.search(current):
        raise CryptoValidationError("bidi_control_rejected")
    for _ in range(max_depth):
        lowered = current.lower()
        if lowered.startswith("base64:") or lowered.startswith("b64:"):
            _, encoded = current.split(":", 1)
            try:
                current = base64.b64decode(encoded, validate=True).decode("utf-8")
            except Exception as exc:
                raise CryptoValidationError("invalid_base64_wrapper") from exc
        elif lowered.startswith("hex:"):
            _, encoded = current.split(":", 1)
            encoded = encoded.strip()
            if len(encoded) % 2 or not _HEX_RE.fullmatch(encoded):
                raise CryptoValidationError("invalid_hex_wrapper")
            try:
                current = bytes.fromhex(encoded).decode("utf-8")
            except Exception as exc:
                raise CryptoValidationError("invalid_hex_wrapper") from exc
        elif lowered.startswith("morse:"):
            _, encoded = current.split(":", 1)
            current = _decode_morse(encoded)
        else:
            break
        current = unicodedata.normalize("NFKC", current)
        current = _ZERO_WIDTH_RE.sub("", current)
        if _BIDI_RE.search(current):
            raise CryptoValidationError("bidi_control_rejected")
    else:
        if current.lower().startswith(("base64:", "b64:", "hex:", "morse:")):
            raise CryptoValidationError("normalization_depth_exceeded")
    return current


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_wrapped_text(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = unicodedata.normalize("NFKC", str(key)).strip().lower()
            if not normalized_key:
                raise CryptoValidationError("empty_canonical_key")
            normalized[normalized_key] = normalize_value(item)
        return normalized
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise CryptoValidationError("non_finite_number")
        return value
    return normalize_wrapped_text(str(value))


def canonical_json(value: Any) -> bytes:
    normalized = normalize_value(value)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def commitment(value: Any, *, domain: str = "intent") -> dict[str, str]:
    payload = b"ORBYTHRA-" + domain.upper().encode("ascii") + b"-V1\x00" + canonical_json(value)
    return {"sha256": hashlib.sha256(payload).hexdigest(), "sha3_256": hashlib.sha3_256(payload).hexdigest()}


def verify_effect_binding(intent: dict[str, Any], effect: dict[str, Any] | None) -> list[str]:
    if effect is None:
        return []
    ni = normalize_value(intent)
    ne = normalize_value(effect)
    mismatches: list[str] = []
    for field in _PROTECTED_EFFECT_FIELDS:
        if field in ne and ni.get(field) != ne.get(field):
            mismatches.append(field)
    return mismatches


def approval_signature_message(approver_id: str, intent_digest: str) -> bytes:
    return b"ORBYTHRA-APPROVAL-V1\x00" + approver_id.encode("utf-8") + b"\x00" + intent_digest.lower().encode("ascii")


def approver_id_for_ed25519_public_key(public_key_b64: str) -> str:
    public_raw = _b64d(public_key_b64)
    if len(public_raw) != 32:
        raise CryptoValidationError("invalid_approval_public_key")
    return "ed25519:" + hashlib.sha256(public_raw).hexdigest()[:32]


def sign_approval(private_key_b64: str, intent_digest: str) -> dict[str, str]:
    private_raw = _b64d(private_key_b64)
    if len(private_raw) != 32:
        raise CryptoValidationError("invalid_approval_private_key")
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_raw)
    public_raw = private_key.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    public_b64 = _b64e(public_raw)
    approver_id = approver_id_for_ed25519_public_key(public_b64)
    signature = private_key.sign(approval_signature_message(approver_id, intent_digest))
    return {
        "approver_id": approver_id,
        "intent_digest": intent_digest,
        "proof_type": "signature",
        "proof": _b64e(signature),
        "public_key_b64": public_b64,
    }


def generate_ed25519_approval_keypair() -> dict[str, str]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption())
    public_raw = private_key.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    public_b64 = _b64e(public_raw)
    return {
        "private_key_b64": _b64e(private_raw),
        "public_key_b64": public_b64,
        "approver_id": approver_id_for_ed25519_public_key(public_b64),
    }


def hybrid_approver_id_for_public_keys(public_key_b64: str, pq_public_key_b64: str) -> str:
    ed_raw = _b64d(public_key_b64)
    pq_raw = _b64d(pq_public_key_b64)
    if len(ed_raw) != 32:
        raise CryptoValidationError("invalid_approval_public_key")
    material = b"ORBYTHRA-HYBRID-APPROVER-V1\x00" + ed_raw + pq_raw
    return "hybrid:" + hashlib.sha256(material).hexdigest()[:32]


def generate_hybrid_approval_keypair() -> dict[str, str]:
    if mldsa is None:
        raise CryptoConfigurationError("pqc_backend_unavailable")
    try:
        ed_private = ed25519.Ed25519PrivateKey.generate()
        pq_private = mldsa.MLDSA65PrivateKey.generate()
    except UnsupportedAlgorithm as exc:
        raise CryptoConfigurationError("pqc_backend_unavailable") from exc
    ed_private_raw = ed_private.private_bytes_raw()
    ed_public_raw = ed_private.public_key().public_bytes_raw()
    pq_private_raw = pq_private.private_bytes_raw()
    pq_public_raw = pq_private.public_key().public_bytes_raw()
    ed_public_b64 = _b64e(ed_public_raw)
    pq_public_b64 = _b64e(pq_public_raw)
    return {
        "private_key_b64": _b64e(ed_private_raw),
        "public_key_b64": ed_public_b64,
        "pq_private_key_b64": _b64e(pq_private_raw),
        "pq_public_key_b64": pq_public_b64,
        "approver_id": hybrid_approver_id_for_public_keys(ed_public_b64, pq_public_b64),
    }


def sign_hybrid_approval(private_key_b64: str, pq_private_key_b64: str, intent_digest: str) -> dict[str, str]:
    if mldsa is None:
        raise CryptoConfigurationError("pqc_backend_unavailable")
    try:
        ed_private = ed25519.Ed25519PrivateKey.from_private_bytes(_b64d(private_key_b64))
        pq_private = mldsa.MLDSA65PrivateKey.from_seed_bytes(_b64d(pq_private_key_b64))
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise CryptoConfigurationError("invalid_or_unsupported_hybrid_approval_key") from exc
    ed_public_b64 = _b64e(ed_private.public_key().public_bytes_raw())
    pq_public_b64 = _b64e(pq_private.public_key().public_bytes_raw())
    approver_id = hybrid_approver_id_for_public_keys(ed_public_b64, pq_public_b64)
    message = approval_signature_message(approver_id, intent_digest)
    return {
        "approver_id": approver_id,
        "intent_digest": intent_digest,
        "proof_type": "hybrid_signature",
        "proof": _b64e(ed_private.sign(message)),
        "public_key_b64": ed_public_b64,
        "pq_proof": _b64e(pq_private.sign(message, b"orbythra-approval-v1")),
        "pq_public_key_b64": pq_public_b64,
    }


def verify_approvals(approvals: list[dict[str, Any]], *, intent_digest: str, min_approvals: int) -> list[str]:
    unique: set[str] = set()
    accepted: list[str] = []
    for approval in approvals:
        approver = str(approval.get("approver_id", "")).strip()
        bound_digest = str(approval.get("intent_digest", "")).strip().lower()
        proof = str(approval.get("proof", "")).strip()
        proof_type = str(approval.get("proof_type", "gesture")).strip().lower()
        if not approver or not proof:
            continue
        if not hmac.compare_digest(bound_digest, intent_digest.lower()):
            raise CryptoValidationError("approval_not_bound_to_intent")
        if not SETTINGS.allow_legacy_approvals and proof_type not in {"signature", "hybrid_signature"}:
            raise CryptoValidationError("legacy_approval_not_allowed")
        if SETTINGS.pqc_mode == "hybrid-required" and proof_type != "hybrid_signature":
            raise CryptoValidationError("pqc_hybrid_approval_required")
        if proof_type == "signature":
            public_b64 = str(approval.get("public_key_b64", "")).strip()
            if not public_b64:
                raise CryptoValidationError("approval_public_key_required")
            expected_approver = approver_id_for_ed25519_public_key(public_b64)
            if not hmac.compare_digest(approver, expected_approver):
                raise CryptoValidationError("approval_signer_identity_mismatch")
            try:
                public_key = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(public_b64))
                public_key.verify(_b64d(proof), approval_signature_message(approver, bound_digest))
            except (ValueError, InvalidSignature) as exc:
                raise CryptoValidationError("invalid_approval_signature") from exc
        elif proof_type == "hybrid_signature":
            if mldsa is None:
                raise CryptoConfigurationError("pqc_backend_unavailable")
            public_b64 = str(approval.get("public_key_b64", "")).strip()
            pq_public_b64 = str(approval.get("pq_public_key_b64", "")).strip()
            pq_proof = str(approval.get("pq_proof", "")).strip()
            if not public_b64 or not pq_public_b64 or not pq_proof:
                raise CryptoValidationError("hybrid_approval_material_required")
            expected_approver = hybrid_approver_id_for_public_keys(public_b64, pq_public_b64)
            if not hmac.compare_digest(approver, expected_approver):
                raise CryptoValidationError("approval_signer_identity_mismatch")
            message = approval_signature_message(approver, bound_digest)
            try:
                ed25519.Ed25519PublicKey.from_public_bytes(_b64d(public_b64)).verify(_b64d(proof), message)
                mldsa.MLDSA65PublicKey.from_public_bytes(_b64d(pq_public_b64)).verify(
                    _b64d(pq_proof), message, b"orbythra-approval-v1"
                )
            except UnsupportedAlgorithm as exc:
                raise CryptoConfigurationError("pqc_backend_unavailable") from exc
            except (ValueError, InvalidSignature) as exc:
                raise CryptoValidationError("invalid_hybrid_approval_signature") from exc
        if approver in unique:
            continue
        unique.add(approver)
        accepted.append(approver)
    if len(accepted) < min_approvals:
        raise CryptoValidationError("approval_threshold_not_met")
    return accepted


def _hkdf(ikm: bytes, *, salt: bytes | None, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(ikm)


def _permuted_alphabet(seed: bytes) -> str:
    return "".join(sorted(_B64URL_ALPHABET, key=lambda ch: hmac.new(seed, ch.encode("ascii"), hashlib.sha256).digest()))


def dsel_encode(data: bytes, seed: bytes) -> bytes:
    encoded = _b64e(data)
    permuted = _permuted_alphabet(seed)
    return encoded.translate(str.maketrans(_B64URL_ALPHABET, permuted)).encode("ascii")


def dsel_decode(data: bytes, seed: bytes) -> bytes:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CryptoValidationError("invalid_dsel_payload") from exc
    permuted = _permuted_alphabet(seed)
    restored = text.translate(str.maketrans(permuted, _B64URL_ALPHABET))
    return _b64d(restored)


@dataclass(frozen=True)
class LoadedKey:
    key_id: str
    key: bytes


class KeyRing:
    def __init__(self, pairs: tuple[tuple[str, str], ...] | None = None, *, label: str = "master") -> None:
        loaded: list[LoadedKey] = []
        source = SETTINGS.master_keys if pairs is None else pairs
        for key_id, encoded in source:
            raw = _b64d(encoded)
            if len(raw) != 32:
                raise CryptoConfigurationError(f"{label} key {key_id!r} must decode to exactly 32 bytes")
            loaded.append(LoadedKey(key_id=key_id, key=raw))
        self._keys = tuple(loaded)

    @property
    def configured(self) -> bool:
        return bool(self._keys)

    @property
    def active(self) -> LoadedKey:
        if not self._keys:
            raise CryptoConfigurationError("crypto_master_key_not_configured")
        return self._keys[0]

    def get(self, key_id: str) -> LoadedKey:
        for item in self._keys:
            if hmac.compare_digest(item.key_id, key_id):
                return item
        raise CryptoValidationError("unknown_key_id")

    @property
    def key_ids(self) -> list[str]:
        return [item.key_id for item in self._keys]


KEYRING = KeyRing()


def _signing_ring() -> KeyRing:
    if SETTINGS.signing_keys:
        return KeyRing(SETTINGS.signing_keys, label="signing")
    if SETTINGS.environment == "production":
        raise CryptoConfigurationError("crypto_signing_key_not_configured")
    return KEYRING


def signing_key_ids() -> list[str]:
    return _signing_ring().key_ids


def pqc_backend_available() -> bool:
    if mldsa is None or mlkem is None or HPKESuite is None:
        return False
    try:
        mldsa.MLDSA65PrivateKey.generate()
        mlkem.MLKEM768PrivateKey.generate()
        return True
    except UnsupportedAlgorithm:
        return False


def _aead(algorithm: str, key: bytes):
    if algorithm == "aes256-gcm":
        return AESGCM(key)
    if algorithm == "chacha20-poly1305":
        return ChaCha20Poly1305(key)
    raise CryptoValidationError("unsupported_algorithm")


def _signing_private(master_key: bytes) -> ed25519.Ed25519PrivateKey:
    seed = _hkdf(master_key, salt=None, info=b"orbythra:ed25519-signing:v1")
    return ed25519.Ed25519PrivateKey.from_private_bytes(seed)


def _signing_public_b64(signing_root: bytes) -> str:
    public = _signing_private(signing_root).public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return _b64e(public)


def _pq_signing_private(signing_root: bytes):
    if mldsa is None:
        raise CryptoConfigurationError("pqc_backend_unavailable")
    seed = _hkdf(signing_root, salt=None, info=b"orbythra:mldsa65-signing:v1")
    try:
        return mldsa.MLDSA65PrivateKey.from_seed_bytes(seed)
    except UnsupportedAlgorithm as exc:
        raise CryptoConfigurationError("pqc_backend_unavailable") from exc


def _pq_signing_public_b64(signing_root: bytes) -> str:
    return _b64e(_pq_signing_private(signing_root).public_key().public_bytes_raw())


def _signature_input(envelope: dict[str, Any]) -> bytes:
    # V2 signatures bind both classical and PQ signer public keys into the signed
    # envelope. Only the signature byte strings themselves are excluded.
    excluded = {"signature_b64", "pq_signature_b64"}
    signable = {key: value for key, value in envelope.items() if key not in excluded}
    return b"ORBYTHRA-EFFECTSEAL-V2\x00" + canonical_json(signable)


def signature_input_for_envelope(envelope: dict[str, Any]) -> bytes:
    header = envelope.get("header") if isinstance(envelope, dict) else None
    version = str(header.get("version", "orbythra-effectseal-v1")) if isinstance(header, dict) else "orbythra-effectseal-v1"
    if version == "orbythra-effectseal-v2":
        return _signature_input(envelope)
    signable = {key: value for key, value in envelope.items() if key not in {"signature_b64", "signing_public_key_b64"}}
    return b"ORBYTHRA-EFFECTSEAL-V1\x00" + canonical_json(signable)


def seal(*, payload: dict[str, Any], intent: dict[str, Any], effect: dict[str, Any] | None, approvals: list[dict[str, Any]], min_approvals: int, workspace_id: str, domain: str, ttl_seconds: int, algorithm: str | None = None, recipient_public_key_b64: str | None = None, recipient_mlkem768_public_key_b64: str | None = None) -> dict[str, Any]:
    key_item = KEYRING.active
    signing_item = _signing_ring().active
    algorithm = algorithm or SETTINGS.crypto_algorithm
    if algorithm not in {"aes256-gcm", "chacha20-poly1305"}:
        raise CryptoValidationError("unsupported_algorithm")
    if ttl_seconds < 0 or ttl_seconds > SETTINGS.crypto_max_ttl_seconds:
        raise CryptoValidationError("invalid_ttl")
    if recipient_mlkem768_public_key_b64 and not recipient_public_key_b64:
        raise CryptoValidationError("hybrid_recipient_x25519_key_required")
    if SETTINGS.pqc_mode == "hybrid-required" and recipient_public_key_b64 and not recipient_mlkem768_public_key_b64:
        raise CryptoValidationError("pqc_hybrid_recipient_required")
    normalized_intent = normalize_value(intent)
    normalized_effect = normalize_value(effect) if effect is not None else None
    mismatches = verify_effect_binding(normalized_intent, normalized_effect)
    if mismatches:
        raise CryptoValidationError("intent_effect_mismatch:" + ",".join(mismatches))
    intent_commits = commitment(normalized_intent, domain="intent")
    effect_commits = commitment(normalized_effect, domain="effect") if normalized_effect is not None else None
    accepted_approvers = verify_approvals(approvals, intent_digest=intent_commits["sha256"], min_approvals=min_approvals)
    now = int(time.time())
    expires_at = now + ttl_seconds if ttl_seconds else 0
    nonce = secrets.token_bytes(12)
    wrap_nonce = secrets.token_bytes(12)
    dek = secrets.token_bytes(32)
    header = {"version": "orbythra-effectseal-v2", "key_id": key_item.key_id, "signing_key_id": signing_item.key_id, "algorithm": algorithm, "workspace_id": workspace_id, "domain": domain, "created_at": now, "expires_at": expires_at, "intent_sha256": intent_commits["sha256"], "intent_sha3_256": intent_commits["sha3_256"], "effect_sha256": effect_commits["sha256"] if effect_commits else None, "approval_count": len(accepted_approvers), "approval_threshold": min_approvals, "pqc_mode": SETTINGS.pqc_mode}
    aad = canonical_json(header)
    content = {"payload": normalize_value(payload), "intent": normalized_intent, "effect": normalized_effect, "approvers": accepted_approvers}
    plaintext = canonical_json(content)
    dsel_seed = _hkdf(dek, salt=nonce, info=b"orbythra:dsel-adunaic:v1")
    represented = dsel_encode(plaintext, dsel_seed)
    ciphertext = _aead(algorithm, dek).encrypt(nonce, represented, aad)
    kek_info = f"orbythra:kek:v1:{workspace_id}:{domain}".encode("utf-8")
    kek = _hkdf(key_item.key, salt=nonce, info=kek_info)
    wrapped_dek = AESGCM(kek).encrypt(wrap_nonce, dek, aad)
    envelope: dict[str, Any] = {"header": header, "nonce_b64": _b64e(nonce), "wrap_nonce_b64": _b64e(wrap_nonce), "wrapped_key_b64": _b64e(wrapped_dek), "ciphertext_b64": _b64e(ciphertext)}
    if recipient_public_key_b64 and recipient_mlkem768_public_key_b64:
        if mlkem is None or MLKEM768X25519PublicKey is None or HPKESuite is None or HPKEKEM is None or HPKEKDF is None or HPKEAEAD is None:
            raise CryptoConfigurationError("pqc_backend_unavailable")
        try:
            x_public = x25519.X25519PublicKey.from_public_bytes(_b64d(recipient_public_key_b64))
            pq_public = mlkem.MLKEM768PublicKey.from_public_bytes(_b64d(recipient_mlkem768_public_key_b64))
            hybrid_public = MLKEM768X25519PublicKey(pq_public, x_public)
            suite = HPKESuite(HPKEKEM.MLKEM768_X25519, HPKEKDF.HKDF_SHA256, HPKEAEAD.AES_256_GCM)
            hpke_info = b"ORBYTHRA-HYBRID-RECIPIENT-V1\x00" + hashlib.sha256(aad).digest()
            hybrid_wrapped = suite.encrypt(dek, hybrid_public, info=hpke_info)
            envelope["hybrid_recipient_wrap"] = {
                "scheme": "ML-KEM-768+X25519/HPKE-AES256GCM",
                "ciphertext_b64": _b64e(hybrid_wrapped),
            }
        except UnsupportedAlgorithm as exc:
            raise CryptoConfigurationError("pqc_backend_unavailable") from exc
        except ValueError as exc:
            raise CryptoValidationError("invalid_hybrid_recipient_public_key") from exc
    elif recipient_public_key_b64:
        recipient_raw = _b64d(recipient_public_key_b64)
        if len(recipient_raw) != 32:
            raise CryptoValidationError("invalid_x25519_public_key")
        recipient_public = x25519.X25519PublicKey.from_public_bytes(recipient_raw)
        ephemeral_private = x25519.X25519PrivateKey.generate()
        shared = ephemeral_private.exchange(recipient_public)
        recipient_kek = _hkdf(shared, salt=nonce, info=b"orbythra:x25519-recipient-wrap:v1")
        recipient_nonce = secrets.token_bytes(12)
        recipient_wrapped = AESGCM(recipient_kek).encrypt(recipient_nonce, dek, aad)
        envelope["recipient_wrap"] = {"ephemeral_public_key_b64": _b64e(ephemeral_private.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)), "nonce_b64": _b64e(recipient_nonce), "wrapped_key_b64": _b64e(recipient_wrapped)}
    use_pqc_signature = SETTINGS.pqc_mode != "off"
    if use_pqc_signature:
        try:
            envelope["pq_signing_algorithm"] = "ML-DSA-65"
            envelope["pq_signing_public_key_b64"] = _pq_signing_public_b64(signing_item.key)
        except CryptoConfigurationError:
            if SETTINGS.pqc_mode == "hybrid-required":
                raise
            use_pqc_signature = False
            envelope.pop("pq_signing_algorithm", None)
    signing_private = _signing_private(signing_item.key)
    envelope["signing_public_key_b64"] = _signing_public_b64(signing_item.key)
    signature_input = _signature_input(envelope)
    envelope["signature_b64"] = _b64e(signing_private.sign(signature_input))
    if use_pqc_signature:
        envelope["pq_signature_b64"] = _b64e(_pq_signing_private(signing_item.key).sign(signature_input, b"orbythra-effectseal-v2"))
    return envelope


def ciphertext_digest(envelope: dict[str, Any]) -> bytes:
    return hashlib.sha256(_b64d(str(envelope.get("ciphertext_b64", "")))).digest()


def open_envelope(envelope: dict[str, Any], *, expected_workspace_id: str, expected_intent_digest: str | None = None) -> dict[str, Any]:
    try:
        header = envelope["header"]
        key_id = str(header["key_id"])
        algorithm = str(header["algorithm"])
        workspace_id = str(header["workspace_id"])
        domain = str(header["domain"])
    except (KeyError, TypeError) as exc:
        raise CryptoValidationError("malformed_envelope") from exc
    if workspace_id != expected_workspace_id:
        raise CryptoValidationError("workspace_mismatch")
    expires_at = int(header.get("expires_at") or 0)
    if expires_at and int(time.time()) > expires_at:
        raise CryptoValidationError("envelope_expired")
    key_item = KEYRING.get(key_id)
    version = str(header.get("version", "orbythra-effectseal-v1"))
    signing_key_id = str(header.get("signing_key_id", key_id))
    signing_item = _signing_ring().get(signing_key_id) if "signing_key_id" in header else key_item
    expected_public = _signing_public_b64(signing_item.key)
    supplied_public = str(envelope.get("signing_public_key_b64", ""))
    if not hmac.compare_digest(expected_public, supplied_public):
        raise CryptoValidationError("unexpected_signer")
    signature = _b64d(str(envelope.get("signature_b64", "")))
    public_key = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(supplied_public))
    signature_input = signature_input_for_envelope(envelope)
    try:
        public_key.verify(signature, signature_input)
    except InvalidSignature as exc:
        raise CryptoValidationError("invalid_signature") from exc
    pq_signature = str(envelope.get("pq_signature_b64", "")).strip()
    pq_public = str(envelope.get("pq_signing_public_key_b64", "")).strip()
    if pq_signature or pq_public:
        if mldsa is None:
            raise CryptoConfigurationError("pqc_backend_unavailable")
        expected_pq_public = _pq_signing_public_b64(signing_item.key)
        if not pq_signature or not pq_public or not hmac.compare_digest(expected_pq_public, pq_public):
            raise CryptoValidationError("unexpected_pq_signer")
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
    if expected_intent_digest:
        actual = str(header.get("intent_sha256", "")).lower()
        if not hmac.compare_digest(actual, expected_intent_digest.lower()):
            raise CryptoValidationError("intent_commitment_mismatch")
    nonce = _b64d(str(envelope.get("nonce_b64", "")))
    wrap_nonce = _b64d(str(envelope.get("wrap_nonce_b64", "")))
    if len(nonce) != 12 or len(wrap_nonce) != 12:
        raise CryptoValidationError("invalid_nonce_length")
    aad = canonical_json(header)
    kek_info = f"orbythra:kek:v1:{workspace_id}:{domain}".encode("utf-8")
    kek = _hkdf(key_item.key, salt=nonce, info=kek_info)
    try:
        dek = AESGCM(kek).decrypt(wrap_nonce, _b64d(str(envelope.get("wrapped_key_b64", ""))), aad)
        represented = _aead(algorithm, dek).decrypt(nonce, _b64d(str(envelope.get("ciphertext_b64", ""))), aad)
    except InvalidTag as exc:
        raise CryptoValidationError("authentication_failed") from exc
    dsel_seed = _hkdf(dek, salt=nonce, info=b"orbythra:dsel-adunaic:v1")
    plaintext = dsel_decode(represented, dsel_seed)
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
    nonce_fingerprint = hashlib.sha256(key_id.encode("utf-8") + b":" + nonce + b":" + ciphertext_digest(envelope)).hexdigest()
    outcome = {"workspace_id": workspace_id, "domain": domain, "intent_sha256": str(header.get("intent_sha256", "")), "effect_sha256": header.get("effect_sha256"), "ciphertext_sha256": hashlib.sha256(_b64d(str(envelope.get("ciphertext_b64", "")))).hexdigest(), "opened_at": int(time.time())}
    receipt_payload = b"ORBYTHRA-OUTCOME-V1\x00" + canonical_json(outcome)
    receipt_signature = _signing_private(signing_item.key).sign(receipt_payload)
    outcome_receipt = {**outcome, "signature_b64": _b64e(receipt_signature), "signing_public_key_b64": expected_public}
    # Preserve the cryptographic policy embedded in the issued envelope.
    # A later runtime policy upgrade must not make an older, valid v2 envelope
    # unreadable or retroactively require a PQ outcome signature.
    envelope_pqc_mode = str(header.get("pqc_mode", "off"))
    if envelope_pqc_mode != "off" and version == "orbythra-effectseal-v2":
        try:
            outcome_receipt["pq_signature_b64"] = _b64e(_pq_signing_private(signing_item.key).sign(receipt_payload, b"orbythra-outcome-v2"))
            outcome_receipt["pq_signing_public_key_b64"] = _pq_signing_public_b64(signing_item.key)
            outcome_receipt["pq_signing_algorithm"] = "ML-DSA-65"
        except CryptoConfigurationError:
            if envelope_pqc_mode == "hybrid-required":
                raise
    return {"content": content, "header": header, "nonce_fingerprint": nonce_fingerprint, "signer_verified": True, "outcome_receipt": outcome_receipt}


def verify_legacy_secp256k1_signature(*, public_key_pem: bytes, signature_der: bytes, message: bytes) -> bool:
    try:
        public_key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            return False
        if not isinstance(public_key.curve, ec.SECP256K1):
            return False
        public_key.verify(signature_der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def generate_master_key_b64() -> str:
    return _b64e(secrets.token_bytes(32))


def generate_x25519_keypair() -> dict[str, str]:
    private = x25519.X25519PrivateKey.generate()
    return {"private_key_b64": _b64e(private.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption())), "public_key_b64": _b64e(private.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw))}


def generate_hybrid_recipient_keypair() -> dict[str, str]:
    if mlkem is None:
        raise CryptoConfigurationError("pqc_backend_unavailable")
    try:
        x_private = x25519.X25519PrivateKey.generate()
        pq_private = mlkem.MLKEM768PrivateKey.generate()
    except UnsupportedAlgorithm as exc:
        raise CryptoConfigurationError("pqc_backend_unavailable") from exc
    return {
        "x25519_private_key_b64": _b64e(x_private.private_bytes_raw()),
        "x25519_public_key_b64": _b64e(x_private.public_key().public_bytes_raw()),
        "mlkem768_private_key_b64": _b64e(pq_private.private_bytes_raw()),
        "mlkem768_public_key_b64": _b64e(pq_private.public_key().public_bytes_raw()),
    }
