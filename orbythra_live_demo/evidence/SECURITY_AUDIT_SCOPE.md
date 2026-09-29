# ORBYTHRA Security Audit Scope

Date: 2026-09-29
Status: controlled scope proposal for an authorized third-party security assessment.

## Objective

Determine whether the evaluated ORBYTHRA release preserves confidentiality, integrity, authorization boundaries, tenant separation and safe tool/connector behavior under realistic web/API/LLM attack conditions.

## In-scope categories

1. Public web application and documented backend API routes.
2. Authentication and authorization when enabled in the evaluation environment.
3. Tenant/workspace isolation and object-level access controls.
4. Input validation and injection classes.
5. SSRF and unsafe outbound-request behavior.
6. Secret/token exposure in frontend bundles, logs, errors, repositories and responses.
7. Rate-limit, abuse and resource-exhaustion behavior.
8. Prompt injection and indirect prompt injection where retrieved content can influence an AI decision.
9. Data exfiltration and tool-boundary testing.
10. Approval-gated external side effects, when state-changing connectors are enabled.
11. Replay/duplicate-execution protections for state-changing operations.
12. Evidence/report integrity metadata and tamper-resistance claims, where implemented.
13. Dependency and supply-chain exposure relevant to the evaluated release.

## Out of scope without separate written authorization

- destructive production testing
- credential attacks against unrelated third parties
- denial-of-service beyond agreed load limits
- social engineering of employees/partners
- scanning infrastructure not explicitly listed in the scope
- irreversible state-changing transactions

## AI/agent-specific controls to verify

### Intent / approval binding
When a connector can create an external side effect, verify that approval is bound to the material action parameters rather than treated as a generic approval.

### Effect verification
Where technically available, compare intended recipient/resource/action with the actual connector/tool payload and resulting state.

### Fail-closed behavior
Missing authorization, stale approval, mismatched target, unbound connector, malformed tool output or uncertain execution state must not be silently reported as successful completion.

### Prompt-injection boundary
Retrieved content must not be allowed to silently override higher-level policy, authorization or evidence rules.

### Memory boundary
Tenant/user memory must not cross authorization boundaries. Historical memory must not be silently elevated into fresh evidence.

## Cryptographic review boundary

Where MorseGuard/GestureGuard/DSEL-derived mechanisms or equivalent controls are incorporated into ORBYTHRA, review should distinguish:

- standard cryptographic primitives and their correct use
- protocol composition and key/nonce lifecycle
- semantic intent canonicalization
- approval binding
- replay resistance
- effect verification
- non-cryptographic representation/obfuscation layers

No proprietary representation layer should be treated as a substitute for standard authenticated encryption or signatures.

## Required evidence per finding

- finding id
- affected exact release/snapshot/commit
- severity and impact rationale
- affected component/route
- prerequisites
- reproducible steps
- request/response or trace evidence
- expected vs actual behavior
- remediation recommendation
- retest status

## Required deliverables

1. Methodology and scope statement.
2. Finding register with reproducible evidence.
3. Severity/impact rationale.
4. Remediation guidance.
5. Retest/closure report for the same release lineage or an explicitly named successor.

A third-party report is independent evidence only for the exact scope and release it actually tested.
