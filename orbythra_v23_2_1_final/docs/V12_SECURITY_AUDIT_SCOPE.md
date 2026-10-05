# ORBYTHRA V12 Independent Security & Cryptographic Audit Scope

Status: assessor-facing scope definition. This document does not represent an audit result.

## Security objective

Determine whether the frozen ORBYTHRA V12 candidate can resist unauthorized cross-workspace access, privilege escalation, replay, validator-authority spoofing, action-chain tampering, unsafe provider routing and material confidentiality/integrity failures within the agreed assessment environment.

## Systems in scope

- FastAPI production composition and OpenAPI-exposed control plane.
- API authentication and RBAC.
- Workspace/tenant isolation across persistent stores and control paths.
- V12 verification firewall.
- V12 validator registry and distributed quorum.
- V12 action-chain ledger.
- V12 temporal-reality store.
- Existing v1-v11 agent, autonomy, adaptive, provider, evidence, privacy, enterprise and cryptographic controls that are reachable by or materially influence the V12 candidate.
- PostgreSQL/SQLite behavior used by the assessed deployment, including application-layer encryption.
- Provider gateway and outbound URL validation.
- Runtime/container/Kubernetes configuration.
- Dependency, SBOM and software-supply-chain controls.
- Logging, audit records, observability and error handling.

## Required attack classes

### Authentication and authorization
- missing/invalid credential handling;
- role escalation attempts;
- confused-deputy paths;
- direct endpoint invocation at insufficient role;
- authorization-state changes between proposal and execution.

### Workspace isolation
- cross-workspace object-ID substitution;
- same validator ID in multiple workspaces;
- cross-workspace validator activation/rotation;
- cross-workspace temporal fact access;
- cross-workspace action-chain read/append;
- audit/evidence/privacy object leakage between workspaces.

Acceptance target: zero successful cross-workspace read/write escape in assessed scope.

### Validator authority and quorum
- malformed Ed25519 keys;
- invalid signatures;
- signature/key substitution;
- validator revocation bypass;
- old key use after rotation;
- stale registry revision;
- duplicate validator inflation;
- organization-diversity manipulation;
- weighted-quorum manipulation;
- future/stale attestations;
- nonce/payload/workspace binding failures.

Acceptance target: zero successful spoof/revoked/stale-authority bypass in assessed scope.

### Replay and state-machine integrity
- verification nonce replay;
- action stage replay;
- stage reordering;
- stale optimistic-concurrency head;
- duplicate completion/effect submission;
- concurrent append/race attempts;
- policy or authorization mutation between simulation and action.

### Action-chain integrity/confidentiality
- stored encrypted payload modification;
- payload substitution with unchanged digest metadata;
- digest/head modification;
- deletion or insertion of intermediate stages;
- ciphertext movement across workspaces;
- at-rest payload extraction without required keys.

Acceptance target: deterministic detection or fail-closed behavior for tampering and replay cases in scope.

### Verification firewall
- unsupported factual claim hidden beside supported content;
- contradictory evidence mixed with supporting evidence;
- caller-supplied claim list omitting output claims;
- duplicate/mirrored evidence inflation;
- declared digest mismatch;
- future and stale evidence timestamps;
- threshold/configuration manipulation;
- release-SHA mismatch;
- verifier-input denial-of-service boundaries.

### Temporal reality
- future observation/publication injection;
- invalid intervals;
- retirement/history rewriting attempts;
- snapshot known-time bypass;
- duplicate semantic assertion injection;
- source-lineage inflation;
- encrypted temporal-object substitution across workspaces.

### Provider gateway / SSRF
- localhost, loopback, private, link-local, multicast and reserved addresses;
- DNS rebinding/private resolution where practical;
- URL parser ambiguity;
- scheme downgrade;
- redirect behavior where applicable;
- oversized provider response;
- malformed provider response;
- secret/header leakage in errors and logs.

### Input and persistence attacks
- SQL injection/query manipulation;
- Unicode/normalization edge cases;
- non-finite numeric values;
- oversized request bodies;
- malformed JSON and nested structures;
- unsafe serialized payloads;
- audit/log injection;
- denial-of-service characteristics within agreed safe test limits.

### Secrets and cryptographic material
- repository secret scan verification;
- environment/config leakage;
- key material in responses, stack traces and logs;
- key rotation behavior;
- nonce uniqueness/replay handling;
- encryption domain/purpose separation;
- ciphertext tampering and wrong-workspace decryption.

## Cryptographic design review

The reviewer should explicitly assess:

- canonical JSON and normalization assumptions;
- domain separation for commitments, receipts, approvals and attestations;
- SHA-256/SHA3/HMAC use and boundaries;
- Ed25519 key parsing, identity/fingerprint derivation and verification;
- AEAD use, nonce handling and key derivation where applicable;
- workspace/purpose binding for encrypted records;
- replay-defense semantics;
- action intent/effect binding;
- release/configuration/policy/output/evidence receipt binding;
- validator key rotation/revocation semantics;
- threat assumptions not cryptographically enforced.

The final report must distinguish ordinary design review and implementation review from any formal proof or certification.

## Supply-chain and deployment review

- dependency audit and known vulnerabilities;
- pinned/reproducible dependency posture;
- SBOM completeness;
- GitHub Actions permission scope;
- secret exposure in CI;
- build artifact provenance;
- container user/privilege posture;
- network/service exposure;
- Kubernetes security context, secrets and ingress configuration;
- backup/restore and corruption-recovery controls.

## Severity gate

Final V12 external-security acceptance requires:

- zero unresolved Critical findings;
- zero unresolved High findings;
- independent retest of all remediated Critical/High findings;
- Medium/Low findings documented with owner, due date and residual-risk statement;
- exact tested release SHA and environment in the final report.

## Deliverables

1. Scope/methodology and dates.
2. Independence/conflict disclosure.
3. Tested release SHA and environment/configuration identity.
4. Findings with severity, reproduction steps and affected components.
5. Cryptographic review findings and assumptions.
6. Evidence for required negative controls.
7. Remediation verification/retest table.
8. Residual risks and exclusions.
9. Signed/final assessor report or verifiable equivalent.

Internal CI, static scanning and internal adversarial tests are supporting evidence only and do not replace this independent audit.
