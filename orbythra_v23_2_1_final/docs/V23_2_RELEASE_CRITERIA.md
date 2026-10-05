# ORBYTHRA V23.2 Release Criteria

V23.2 is a verifiable-agent traceability release candidate. It promotes the V23 general-agent vertical slice and V23.1 research/file capabilities into the canonical platform release while preserving the established execution boundaries.

## Required internal gates

- application modules and scripts compile successfully;
- the complete Python regression suite passes;
- existing V23 memory, goal, simulation and bounded-cycle tests remain green;
- V23.1 keyless web discovery and workspace attachment tests remain green;
- V23.2 context snapshots are workspace-scoped and deterministically SHA-256 bound;
- goal lifecycle transitions are authenticated, encrypted where sensitive, auditable and fail closed for terminal states;
- cycles refuse non-active goals;
- every V23.2 cycle persists a receipt containing goal, episode, context, evidence-manifest and simulation hashes;
- receipts are linked to the preceding workspace receipt through `previous_receipt_sha256`;
- stored receipt payloads can be recomputed and verified through the receipt verification endpoint;
- receipt and context APIs preserve workspace isolation;
- the canonical `platform_release` reports `23.2.0` while legacy v1-v4 API metadata remains stable for compatibility.

## Security and claim boundary

V23.2 does **not** execute unrestricted real-world actions and does not claim AGI, human-level intelligence, perfect factuality, independent safety certification, or completed external validation. Side effects remain subject to ORBYTHRA's existing authorization and execution-control layers.

## External gates before stronger claims

- independent penetration testing;
- independent cryptographic review, including receipt-chain and key-management review;
- independent product/agentic validation;
- adversarial evaluation of long-horizon goal persistence and context integrity;
- production reliability evidence from controlled pilots;
- infrastructure-specific KMS/HSM validation and operational recovery exercises.
