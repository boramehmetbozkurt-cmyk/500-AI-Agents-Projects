# OSIRIS AI Fusion Security Policy

## Autonomous safety boundary

The autonomous registry is intentionally read-only. The product does not autonomously expose active
scanning, exploitation, credential access, intrusive surveillance, face-recognition tracking, or
destructive/mutating actions.

## SEAL v2

SEAL binds an investigation to a canonical CBOR intent, short-lived nonce, tool allow-list, scope and
read-only effect budget. Nonces are consumed before tool execution. Receipts bind the intent digest,
executed tool set, evidence bundle digest and analysis digest. Production deployments should require
Ed25519-signed receipts and protect signing keys with a managed KMS/HSM or equivalent secret boundary.

SEAL is an authorization and evidence-binding layer, not a replacement for TLS, disk encryption,
database encryption, WebAuthn, platform IAM, or audited cryptographic libraries.

## Prompt-injection boundary

All external OSINT content is treated as untrusted data. Evidence is delimited from instructions and
the analyst prompt explicitly forbids following commands embedded in source data. Tool selection is
performed before evidence is supplied to the model, and the SEAL allow-list prevents evidence from
expanding tool authority.

## Production controls

- Require `OSIRIS_FUSION_API_KEY`.
- Require signed receipts (`REQUIRE_SIGNED_RECEIPTS=true`).
- Store the Ed25519 private key outside the repository.
- Terminate TLS at a trusted reverse proxy or cloud load balancer.
- Enforce distributed rate limits at the gateway for multi-replica deployments.
- Centralize logs and alert on authorization failures, replay detections and dependency degradation.
- Run containers as non-root with a read-only filesystem where possible.
- Patch dependencies continuously and require CI before merge.
- Obtain an independent security review before handling sensitive customer data.
