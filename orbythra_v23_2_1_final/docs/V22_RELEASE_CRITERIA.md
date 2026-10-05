# ORBYTHRA V22 Release Criteria

V22 is a cryptographic-hardening release candidate only when the exact candidate commit satisfies all internal gates below.

## Required internal gates

- application and scripts compile successfully;
- the full Python regression suite passes;
- `tests/test_v22_crypto_hardening.py` passes;
- existing crypto trust, signed-approval and V13 recipient tests pass;
- the one-million-case adversarial crypto mutation gate passes;
- production Compose validates with separate encryption and signing key rings;
- production readiness fails if encryption/signing roots overlap;
- production readiness fails when `hybrid-required` is selected but the PQ backend is unavailable;
- production `/v1/crypto/seal` rejects zero-approval external sealing;
- production open routes reject replay-protection disable requests;
- system-generated at-rest/finalization seals remain able to use the explicit internal zero-approval path;
- EffectSeal v2 hybrid ML-DSA-65 signatures and ML-KEM-768 + X25519 recipient protection pass round-trip and tamper tests;
- release evidence fingerprints the V22 crypto implementation, tests and criteria.

## Required external gates before stronger claims

The following remain external evidence requirements:

- independent cryptographic design and implementation review;
- penetration testing;
- side-channel and fault-injection review appropriate to the deployment;
- provider-specific KMS/HSM integration validation;
- operational key-rotation/recovery exercise;
- production incident-response and key-compromise drill.

Passing the V22 internal gates is engineering evidence only. It does not establish perfect security, certification, or independent validation.
