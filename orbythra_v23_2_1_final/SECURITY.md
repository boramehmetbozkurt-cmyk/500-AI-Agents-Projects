# ORBYTHRA Security Policy

ORBYTHRA V22 is a security-sensitive AI assurance, agent-governance, cryptographic-trust, continual-learning and model-adaptation platform.

Security controls are designed around **fail-closed verification, workspace isolation, bounded authority, cryptographic evidence, explicit risk ceilings and auditable state transitions**.

> **Important boundary:** passing ORBYTHRA internal CI, security scans, adversarial crypto tests or version gates does not constitute an independent penetration test, cryptographic audit, regulatory certification or proof of production security. External review remains a separate evidence gate.

## Supported security posture

The canonical production composition root is:

```text
app.api:app
```

Current V22 security controls include:

- API-key authentication;
- OIDC/JWT enterprise authentication;
- RBAC and workspace isolation;
- configurable rate limiting and request-size limits;
- encrypted persisted state;
- cryptographic intent/effect binding;
- nonce / TTL / replay protection, mandatory on production open routes;
- production rejection of opaque legacy approvals and zero-approval sealing at the external `/v1/crypto/seal` boundary;
- isolated encryption and signing root key rings;
- Ed25519 plus ML-DSA-65 hybrid approval/envelope signing;
- X25519 compatibility recipient envelopes;
- ML-KEM-768 + X25519 hybrid HPKE recipient envelopes;
- AES-256-GCM / ChaCha20-Poly1305 authenticated encryption;
- execution-time policy revalidation;
- agent/tool allowlists and risk ceilings;
- persistent failure memory;
- release-blocking behavior for unresolved high/critical failures;
- model-adaptation benchmark and canary gates;
- rollback controls;
- generated-skill tool/risk restrictions;
- training-provider isolation;
- skill-sandbox isolation;
- multimodal adapter allowlisting;
- cross-modal contradiction blocking;
- workspace-scoped V21 dataset, prompt, experiment and trace records;
- encrypted V21 dataset examples, prompt payloads, experiment results and trace attributes;
- immutable SHA-256 dataset/prompt manifests;
- frozen experiment-input binding and sealed experiment comparison;
- W3C trace-context propagation with opt-in OTLP/HTTP export;
- bounded OTLP exporter queue with telemetry failure isolated from request authorization;
- trace-to-evidence/policy/outcome-receipt hash lineage;
- repository secret scanning;
- static security scanning;
- dependency vulnerability auditing;
- SBOM generation;
- backup/restore and database-recovery tests.

## Security architecture

ORBYTHRA's high-level security path is:

```text
Identity
  -> Workspace Isolation
  -> RBAC
  -> Policy Evaluation
  -> Risk Ceiling
  -> Human / Cryptographic Approval when required
  -> Intent Commitment
  -> EffectSeal Authorization
  -> Execution-Time Revalidation
  -> Tool Allowlist
  -> Action Execution
  -> Actual-Effect Verification
  -> Signed / Hashed Outcome Evidence
  -> Failure Memory
  -> Versioned Evaluation / Experiment Evidence
  -> Trace / Evidence / Policy / Outcome-Receipt Lineage
  -> Release / Continuation Gate
```

Later learning and autonomy layers do not bypass these controls.

## V21 assurance and observability security

The V21 assurance lab is intentionally **non-authorizing**. Dataset records, prompt versions, evaluator scores, experiment results and trace spans cannot grant tool permissions, raise an agent risk ceiling, bypass human/cryptographic approval, activate a model candidate or modify an existing policy decision.

V21-specific controls include:

- evaluator/operator RBAC on assurance routes;
- workspace-scoped persistence and lookup;
- encrypted sensitive assurance payloads through the existing vault;
- immutable content hashes for dataset and prompt versions;
- experiment results restricted to indexes in the frozen dataset;
- incomplete datasets cannot be sealed as completed experiments;
- baseline/candidate comparison requires the same frozen dataset and prompt and sealed experiments;
- trace span conflicts fail closed when an existing trace/span identifier is reused with different lineage content;
- a trace lineage is complete only when every stored span in that lineage contains evidence, policy and outcome-receipt hash bindings;
- OTLP export is disabled unless explicitly configured;
- exporter network failure does not grant authority or alter assurance decisions.

OTLP collector endpoints and headers are deployment configuration. Production deployments should use TLS, keep collector credentials in a secret manager, restrict outbound destinations at the network layer and apply retention/privacy policies to exported telemetry.

## Authentication and authorization

### API keys

ORBYTHRA supports server-side API-key authentication.

Production API keys:

- must be long, random and unique;
- must not be committed to source control;
- must not be embedded in frontend source;
- must not be reused across unrelated tenants;
- must be rotated when compromise is suspected;
- should be replaced by stronger tenant-bound identity where appropriate.

Static API keys are deployment credentials. They should not be treated as equivalent to cryptographically tenant-bound enterprise identity.

### OIDC / JWT

Enterprise deployments may use OIDC/JWT authentication with configurable:

- issuer;
- audience;
- JWKS URL or JWKS JSON;
- workspace claim;
- role claim.

OIDC workspace identity should be preferred when multiple untrusted tenants share the same deployment.

### RBAC

Security-sensitive routes require explicit minimum roles such as:

- evaluator;
- operator;
- admin.

Role checks are enforced server-side.

## Workspace and tenant isolation

Workspace isolation is a core security invariant.

Security reports should prioritize any condition where one workspace can:

- read another workspace's evidence;
- read or mutate another workspace's agent state;
- access another workspace's model-adaptation state;
- access another workspace's learning history;
- reuse another workspace's validator identity;
- read another workspace's encrypted memory;
- route or execute actions using another workspace's authority.

Cross-workspace access is treated as a high-priority security defect.

## Cryptographic trust model

ORBYTHRA uses standard cryptographic primitives for confidentiality, integrity, signatures and key agreement.

Primary algorithms include:

- AES-256-GCM;
- ChaCha20-Poly1305;
- HKDF-SHA256;
- Ed25519;
- X25519;
- ML-DSA-65;
- ML-KEM-768 + X25519 hybrid HPKE;
- SHA-256;
- SHA3-256.

Additional controls include:

- deterministic canonicalization;
- domain-separated commitments;
- nonce reservation;
- TTL enforcement;
- replay rejection;
- semantic intent/effect comparison;
- approval binding;
- signed outcome receipts.

Project-specific controls such as MorseGuard, GestureGuard, DSEL / Project Adûnaic and EffectSeal are **defense-in-depth mechanisms** and do not replace established cryptographic primitives.

See `docs/CRYPTO_ARCHITECTURE.md`.

## Key management

Runtime key material must be supplied through deployment secrets or a KMS-compatible secret-management process.

Never commit:

- production master keys;
- API keys;
- provider tokens;
- OIDC private material;
- database passwords;
- trainer tokens;
- sandbox tokens;
- search-provider credentials.

ORBYTHRA supports ordered key rings for controlled key rotation. V22 separates `ORBYTHRA_MASTER_KEYS` (encryption/DEK wrapping) from `ORBYTHRA_SIGNING_KEYS` (envelope and outcome signing). Production readiness requires both roots, and they must be independently generated. New encryption/signing uses the active key in each ring while older key IDs may remain available during controlled migration.

Application support for `external_secret_manager` / `kms_envelope` deployment modes does not by itself prove a provider-specific KMS/HSM integration. The production deployment must independently validate secret injection, access policy, rotation, audit logging and recovery.

Key compromise should trigger:

1. immediate credential/key revocation where possible;
2. active-key rotation;
3. audit review;
4. scope assessment;
5. re-encryption/re-issuance where required;
6. independent incident review for material exposure.

## Agent security

ORBYTHRA agents operate under bounded authority.

Controls include:

- registered-agent identity;
- registered tools;
- tool allowlists;
- operation allowlists;
- maximum risk tier;
- human approval thresholds;
- signed approval options;
- execution-time policy revalidation;
- intended-vs-actual effect comparison;
- action and re-plan budgets;
- persistent action records;
- unsafe-action pause/block semantics.

A model proposal is not equivalent to permission to execute.

## Long-horizon autonomy security

V17 hierarchical programs include:

- maximum goal depth;
- maximum node count;
- maximum action count;
- maximum re-plan count;
- program risk budget;
- checkpoint persistence;
- resume state;
- unsafe-action pause behavior;
- failure-memory awareness.

These controls exist to prevent unbounded autonomous expansion.

ORBYTHRA does not claim unrestricted autonomous agency.

## Planner security — V19

The V19 structured planner is deliberately separated from tool authority.

The planner:

- proposes structured subgoals;
- cannot directly execute tools;
- cannot grant itself permissions;
- cannot override workspace policy;
- cannot exceed parent/program risk ceilings;
- cannot mark external work complete merely through model output;
- stores proposal integrity hashes.

Private semantic-memory contents and world-fact values are excluded from external planner prompts by default; bounded metadata is used instead.

## Continual learning and skill security — V16/V17/V20

Skill learning and skill invention are governed.

Promotion requires policy-controlled evidence such as:

- repeated trials;
- cross-domain performance;
- novelty performance;
- evidence coverage;
- confidence;
- regression safety.

V20 skill invention produces **declarative procedures and trial suites**, not arbitrary executable code inside the API process.

Generated skills:

- may use only explicitly allowed tool IDs;
- must respect the configured maximum risk tier;
- must pass their own trial set;
- cannot borrow unrelated historical evidence to bypass promotion;
- are protected against repeated trial replay/evidence inflation.

Optional executable evaluation must occur through an explicitly configured isolated skill-sandbox service.

Environment variables:

```text
ORBYTHRA_SKILL_SANDBOX_URL
ORBYTHRA_SKILL_SANDBOX_TOKEN
```

## Model adaptation and training security — V18/V20

### V18 adaptation controls

Model/adapter candidates are governed using:

- dataset manifests;
- train/validation/holdout hashes;
- provenance references;
- license references;
- PII-review status;
- locked holdout;
- baseline-vs-candidate benchmark comparison;
- regression ceilings;
- progressive canary rollout;
- automatic rollback;
- manual rollback.

### V20 training orchestration

V20 may prepare and submit adapter-training jobs to an explicitly configured trainer service.

Environment variables:

```text
ORBYTHRA_TRAINING_PROVIDER_URL
ORBYTHRA_TRAINING_PROVIDER_TOKEN
```

Training security requirements include:

- hash-bound training manifests;
- explicit base-model identity;
- dataset-manifest binding;
- training configuration fingerprinting;
- requested artifact identity;
- trainer attestation references;
- artifact SHA-256 verification;
- base-model fingerprint verification.

A successful trainer result is **not automatically promoted to production**. It must enter V18 candidate evaluation and pass benchmark/canary gates.

The ORBYTHRA API process does not execute arbitrary foundation-model training code.

## Multimodal security — V15/V20

V15 binds multimodal evidence to:

- artifact ID;
- modality;
- content SHA-256;
- metadata SHA-256;
- source identity;
- source lineage;
- capture/acquisition time.

V20 semantic fusion additionally binds:

- adapter ID;
- adapter version;
- adapter-output SHA-256;
- semantic claim identity.

Optional adapter allowlisting is configured using:

```text
ORBYTHRA_MULTIMODAL_ALLOWED_ADAPTERS
```

Security controls include:

- content-hash matching;
- modality matching;
- independent-lineage thresholds;
- minimum confidence thresholds;
- conflict detection;
- temporal-validity conflict blocking.

The core does not claim that arbitrary media adapters are trustworthy by default. Adapter security and semantic correctness require separate validation.

## Provider and gateway security

External model, evidence, search, trainer and sandbox providers are treated as external trust boundaries.

Priority risks include:

- SSRF;
- provider URL manipulation;
- token leakage;
- malicious provider responses;
- prompt/data exfiltration;
- poisoned training artifacts;
- malformed response objects;
- timeout/resource exhaustion.

Provider credentials must remain server-side.

## Frontend security

The React frontend must not contain production secrets.

Current CI includes a frontend credential-persistence guard and production build checks.

Do not:

- bake API secrets into the frontend bundle;
- persist sensitive credentials in browser storage;
- expose backend provider tokens to browser code;
- use demo credentials in public or shared production deployments.

Production frontend traffic is expected to reach the API through the configured reverse proxy.

## Database and persistence security

Production composition uses PostgreSQL.

Persistence controls include:

- encrypted application payloads for sensitive stored state;
- workspace-scoped queries;
- backup/restore integrity testing;
- database-corruption fault-injection recovery tests;
- restart/persistence regression tests.

Database credentials must be supplied through deployment secrets and must not be committed.

## Denial-of-service and resource controls

ORBYTHRA includes configurable:

- per-minute request limits;
- request-body size limits;
- bounded planner outputs;
- bounded skill trial counts;
- bounded hierarchical program depth/nodes/actions/replans;
- bounded training configuration ranges;
- provider timeouts;
- long-generation budgets.

Reports describing bypasses of these limits are in scope.

## Security-sensitive environment variables

Production deployments should treat the following as sensitive or security-relevant:

```text
ORBYTHRA_API_KEYS
ORBYTHRA_API_ROLES
ORBYTHRA_OIDC_ISSUER
ORBYTHRA_OIDC_AUDIENCE
ORBYTHRA_OIDC_JWKS_URL
ORBYTHRA_OIDC_JWKS_JSON
ORBYTHRA_OIDC_WORKSPACE_CLAIM
ORBYTHRA_OIDC_ROLE_CLAIM
ORBYTHRA_MASTER_KEYS
ORBYTHRA_SIGNING_KEYS
ORBYTHRA_PQC_MODE
ORBYTHRA_ALLOW_LEGACY_APPROVALS
ORBYTHRA_EVIDENCE_PROVIDER_TOKEN
ORBYTHRA_LLM_PROVIDER_TOKEN
ORBYTHRA_TRAINING_PROVIDER_TOKEN
ORBYTHRA_SKILL_SANDBOX_TOKEN
SERPAPI_API_KEY
SERPAPI_KEY
GOOGLE_SEARCH_API_KEY
POSTGRES_PASSWORD
```

## Vulnerability report scope

Reports should include:

- exact affected commit/release SHA;
- affected component or endpoint;
- authentication state and role used;
- workspace assumptions;
- reproducible steps;
- expected behavior;
- actual behavior;
- realistic security impact;
- safe proof-of-concept material;
- whether secrets/customer data were accessed;
- suggested mitigation if known.

High-priority categories include:

- authentication bypass;
- authorization/RBAC bypass;
- cross-workspace or cross-tenant access;
- cryptographic misuse;
- nonce/TTL/replay bypass;
- signature or approval bypass;
- key-handling failures;
- SSRF/provider-gateway bypass;
- policy or execution-check bypass;
- tool-allowlist bypass;
- risk-ceiling escalation;
- arbitrary code execution;
- sandbox escape;
- trainer poisoning / artifact substitution;
- multimodal adapter allowlist bypass;
- privacy isolation failures;
- secret exposure;
- injection or unsafe deserialization;
- audit-log integrity issues;
- rollback bypass;
- release-gate bypass;
- denial-of-service that bypasses configured controls.

## Safe reporting

Do not place live secrets, customer data or sensitive exploit details in public issues.

When demonstrating a vulnerability:

- use non-production test data;
- minimize accessed records;
- avoid persistence or destructive actions where possible;
- do not perform uncontrolled lateral movement;
- do not publish usable credentials;
- do not degrade production availability.

## Handling process

Material reports should follow this process:

1. Triage the report.
2. Reproduce against an isolated environment.
3. Determine severity and affected versions.
4. Identify whether data, keys, tenants, agent authority or model artifacts are affected.
5. Patch the root cause.
6. Add a regression test.
7. Re-run the relevant version gate.
8. Re-run the full FastAPI release gate where required.
9. Rotate/revoke affected credentials or keys.
10. Generate updated release evidence.
11. Request independent retest for material findings where appropriate.
12. Document remediation without prematurely exposing exploit details.

## Internal security gates

The current FastAPI CI includes security-oriented controls such as:

- production Compose validation;
- frontend/API/PostgreSQL runtime smoke;
- missing-credential authentication smoke;
- full Python test suite;
- one-million-case adversarial crypto regression gate;
- frozen assurance and generalist gates;
- semantic verifier hardening;
- external-validation protocol checks;
- deterministic performance smoke;
- Kubernetes deployment hardening gate;
- backup/restore integrity drill;
- database corruption fault-injection recovery gate;
- React credential-persistence guard;
- Bandit static security scan;
- Python dependency vulnerability audit;
- npm dependency audit;
- CycloneDX SBOM generation;
- repository secret scan;
- release evidence generation;
- external-validation handoff generation;
- production OpenAPI composition checks.

Dedicated V15, V16, V17, V18, V19, V20, V21 and V22 gates provide additional regression coverage for later layers.

## External validation boundary

The following are **not** claimed as completed merely because internal CI is green:

- independent penetration test;
- independent cryptographic audit;
- independent red-team assessment;
- SOC 2 certification;
- ISO 27001 certification;
- legal GDPR certification;
- production uptime history;
- customer security acceptance;
- independent AGI/general-intelligence validation.

For external evaluation, freeze an exact commit SHA and bind all reports, artifacts and conclusions to that tested release.

Relevant documents include:

- `docs/CRYPTO_ARCHITECTURE.md`
- `docs/V12_SECURITY_AUDIT_SCOPE.md`
- `docs/V12_INDEPENDENT_AUDIT_HANDOFF.md`
- `docs/SOC2_ISO27001_READINESS.md`
- `docs/PRODUCTION_RUNBOOK.md`
- `RADIANODE_READINESS.md`
- `docs/RADIANODE_EVALUATION_READINESS.md`

## Security claim boundary

ORBYTHRA V22 is designed to make unsafe state transitions harder, observable and reversible.

It does **not** claim:

- perfect security;
- unbreakable cryptography;
- safe arbitrary self-modification;
- safe arbitrary generated-code execution;
- automatic permission escalation;
- trusted arbitrary model/trainer/media providers;
- independent certification;
- unrestricted autonomous operation;
- AGI safety certification.

Security claims must remain tied to concrete code, exact release SHAs, retained CI evidence and independent external findings where applicable.
