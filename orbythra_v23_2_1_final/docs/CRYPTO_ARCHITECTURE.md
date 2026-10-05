# ORBYTHRA V22 Cryptographic Trust Architecture

## Purpose

ORBYTHRA uses standard cryptographic primitives for confidentiality, integrity, signatures and recipient key establishment. MorseGuard, GestureGuard, DSEL / Project Adûnaic and EffectSeal remain defense-in-depth and semantic-binding controls; they are not substitutes for reviewed cryptography.

## V22 security pipeline

1. MorseGuard normalization: Unicode NFKC, zero-width removal, bidi-control rejection, explicitly tagged Base64/Hex/Morse decoding and bounded recursion.
2. Canonical Intent: deterministic JSON serialization plus domain-separated SHA-256 and SHA3-256 commitments.
3. EffectSeal: protected effect fields are compared against the approved intent and substitutions fail closed.
4. Approval gate: production rejects opaque legacy approval types. V22 supports Ed25519 approvals and hybrid Ed25519 + ML-DSA-65 approvals. When `ORBYTHRA_PQC_MODE=hybrid-required`, hybrid approval is mandatory.
5. DSEL / Project Adûnaic: per-message key-derived representation permutation used only as defense in depth.
6. Envelope encryption: a random 256-bit DEK protects each payload using AES-256-GCM or ChaCha20-Poly1305.
7. Encryption-root separation: the DEK is wrapped from `ORBYTHRA_MASTER_KEYS` through HKDF-SHA256-derived KEKs.
8. Signing-root separation: new V22 envelopes use a different root from `ORBYTHRA_SIGNING_KEYS`. Production readiness requires both encryption and signing key rings.
9. Hybrid signatures: V22 envelopes can carry Ed25519 and ML-DSA-65 signatures over the same canonical envelope. Production defaults to `hybrid-required`.
10. Recipient envelope: V22 supports ML-KEM-768 + X25519 hybrid HPKE wrapping. A hybrid recipient envelope does not also emit a weaker standalone X25519 wrap for the same DEK.
11. Replay defense: nonce + TTL plus persistent receiver-side nonce reservation. Production API routes do not allow callers to disable replay protection.
12. Receiver verification: intent commitment and intent/effect binding are rechecked after decryption.

## Compatibility

Existing `orbythra-effectseal-v1` envelopes remain readable. New seals are emitted as `orbythra-effectseal-v2` and carry an explicit signing-key identifier.

Legacy X25519 recipient wrapping and non-cryptographic approval proofs remain available only for controlled development/test compatibility when production policy does not apply.

## Key management

Encryption and signing roots must be different in production:

```text
ORBYTHRA_MASTER_KEYS   -> encryption / DEK wrapping root
ORBYTHRA_SIGNING_KEYS  -> Ed25519 + ML-DSA signing root
```

Ordered key rings support rotation. The first key is active for new material and older key IDs may remain available for controlled migration.

Environment-backed keys are supported by the application, but production deployments should inject them through a secret manager or KMS/HSM-backed deployment path. Declaring a key-management mode is not itself proof that a cloud KMS/HSM integration has been independently validated.

## Algorithms

Primary symmetric and derivation primitives:

- AES-256-GCM
- ChaCha20-Poly1305
- HKDF-SHA256
- SHA-256
- SHA3-256

Classical asymmetric primitives:

- Ed25519
- X25519

Post-quantum / hybrid V22 primitives:

- ML-DSA-65
- ML-KEM-768 + X25519 hybrid HPKE

Compatibility:

- Argon2id for local/legacy passphrase-derived keys
- secp256k1 verification for earlier MorseGuard profiles

## Security boundary

Internal tests, the million-case adversarial mutation gate and V22 regression tests are engineering evidence. They do not constitute an independent cryptographic audit, penetration test, side-channel review, certification or proof of perfect security.
