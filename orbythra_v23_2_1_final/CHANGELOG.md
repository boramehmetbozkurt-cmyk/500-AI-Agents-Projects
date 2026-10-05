# Changelog

## 23.2.0 — 2026-10-05

Verifiable-agent traceability release candidate.

- promotes the V23 Verifiable General Agent vertical slice and V23.1 keyless-web/file-evidence capabilities into the canonical platform release;
- adds `/v23.2/general-agent/context/{agent_id}` for deterministic SHA-256-bound context snapshots assembled from workspace-scoped goals, encrypted episodic memory and evidence references;
- adds authenticated goal lifecycle transitions with encrypted reasons, append-oriented status history and fail-closed terminal states;
- adds persistent V23.2 cycle receipts binding goal, episode, context, evidence manifest and action-simulation hashes;
- chain-links each workspace receipt to the previous receipt through `previous_receipt_sha256`;
- adds receipt retrieval/listing and post-hoc integrity/link verification endpoints;
- cycles reject paused/completed/cancelled goals and preserve the no-unrestricted-execution boundary;
- release metadata now reports `platform_release=23.2.0` while established v1-v4 compatibility metadata remains unchanged.

V23.2 remains a bounded engineering release candidate. It does not claim AGI, unrestricted autonomy, independent certification, universal factual correctness or completed external product/security validation.

## 23.1.0 — 2026-10-05

Incremental research and file-evidence tranche.

- workspace-scoped TXT/Markdown/CSV/JSON/code/PDF/DOCX attachment ingestion for the unified answer console;
- attachment text becomes direct evidence with content hashes and workspace isolation;
- keyless DuckDuckGo HTML discovery with Bing HTML fallback when keyed search providers are unavailable;
- public-source fetching remains subject to the existing web-evidence controls before direct-evidence treatment.

## 23.0.0 — 2026-10-05

Verifiable General Agent development tranche.

- encrypted episodic memory;
- persistent long-horizon goals;
- bounded candidate-action simulation with low/moderate/high/critical risk handling;
- integrated agent cycle emitting a proof hash while stopping before real-world execution.

## 22.0.0 — 2026-10-04

Cryptographic hardening release candidate.

- production rejects opaque legacy approvals, while the external `/v1/crypto/seal` boundary rejects zero-approval sealing;
- hybrid Ed25519 + ML-DSA-65 intent-bound approvals are supported and required in `hybrid-required` mode;
- encryption and signing roots are separated through `ORBYTHRA_MASTER_KEYS` and `ORBYTHRA_SIGNING_KEYS`;
- new EffectSeal v2 envelopes carry explicit signing-key identity and optional/required ML-DSA-65 signatures;
- recipient protection supports ML-KEM-768 + X25519 hybrid HPKE without emitting a parallel weaker wrap;
- production API routes refuse replay-protection disable requests;
- V1 envelope compatibility is retained for controlled migration;
- dedicated V22 regression tests cover production approval policy, isolated signing roots, hybrid PQ signatures/recipient wrapping and replay enforcement.

V22 still requires independent cryptographic review, penetration testing, side-channel analysis and infrastructure-specific KMS/HSM validation before stronger external security claims.

## 21.0.0 — 2026-10-04

Assurance & Observability release candidate. V21 preserves the V20 governed-learning, multimodal, planner, cryptographic-trust and bounded-agent layers while adding reproducible AI evaluation and interoperable tracing under `/v21/assurance`.

### Evaluation and experiment layer

- workspace-scoped versioned datasets with encrypted examples and immutable SHA-256 manifests;
- append-only prompt versions with encrypted prompt bodies, model/parameter/tag binding and SHA-256 manifests;
- frozen experiment inputs bound to exact dataset version, prompt version and model;
- per-example evaluator scores plus latency, token and cost accounting;
- sealed experiment summaries and deterministic baseline/candidate comparison gates.

### Observability and assurance lineage

- W3C `traceparent` propagation for HTTP requests;
- optional OTLP/HTTP JSON trace export;
- OpenInference-compatible span-kind attributes;
- bounded exporter queue and fail-isolated telemetry delivery;
- trace spans bind evidence-manifest, policy-decision and outcome-receipt SHA-256 references;
- deterministic trace-lineage hashes connect observability to assurance evidence.

### Release evidence

- dedicated V21 regression/contract/security workflow;
- explicit V21 architecture and release criteria;
- V21 platform release metadata while preserving established legacy API version contracts.

### Explicit boundaries

V21 does not claim independent security/product validation, universal factual correctness, production reliability history, AGI, or certification. External penetration testing, cryptographic review and product validation remain separate gates.

## 4.0.0 — 2026-09-30

Adaptive Generalist AI Baseline. v4.0 preserves the v1 enterprise/evidence/privacy/crypto foundation, v2 governed agent-action control plane and v3 bounded-autonomy orchestration while adding an application-level adaptive plane under `/v4/adaptive`.

### Adaptive world state and learning

- revisioned, SHA-256 hash-chained world-state records;
- evidence-referenced learning candidates with baseline, candidate and minimum-improvement scores;
- fail-closed rejection when measured improvement is below the declared threshold;
- explicit human approval for high/critical-risk learning activation;
- derived skills materialized into the governed v3 skill registry;
- rollback appends a new learning revision and disables the derived skill;
- learning is application-level and does not modify foundation-model weights.

### Cross-domain transfer and meta-routing

- provenance-bound cross-domain transfer proposals;
- transfer proposals grant no tool authority and create no active skill by themselves;
- deterministic strategy routing constrained by domain, required capabilities and maximum risk;
- stable utility-based selection and tie-breaking;
- existing v2 action authorization and v3 mission/memory controls remain mandatory.

### Release evidence

- frozen `adaptive_generalist_challenge_v1` deterministic corpus and CI gate;
- v4 route composition added to the OpenAPI gate;
- system assurance manifest fingerprints world-state revisions, adaptive-learning history, strategy registry and transfer proposals;
- v4 artifacts included in SHA-256 release-evidence and external-validation handoff bundles;
- `/v1/system/version` preserves historical `api_major=1` while exposing `latest_api_major=4` and `supported_api_majors=[1,2,3,4]`.

### Explicit boundaries

v4.0.0 does not claim AGI, human-level general intelligence, foundation-model weight self-training, independent adaptive-system safety certification, completed independent penetration testing/crypto review, completed independent product/adaptive validation, universal MCP interoperability, live production reliability, paid customers, ARR or formal compliance certification.

## 3.0.0 — 2026-09-30

Bounded Autonomous AI System Baseline. v3.0 preserves the v1 enterprise/evidence/privacy/crypto foundation and v2 governed agent-action control plane while adding persistent encrypted memory, registered skills, deterministic mission planning, criteria-based cycle evaluation and context-drift detection under `/v3/autonomy`.

### Persistent memory

- workspace- and agent-scoped encrypted application memory;
- episodic, semantic, procedural and evidence memory classes;
- confidence, provenance/source references, tags and optional expiry;
- SHA-256 content fingerprints;
- bounded filtered retrieval;
- explicit boundary that memory does not modify model weights.

### Skill and mission orchestration

- workspace-scoped versioned skill registry;
- capability-to-v2-tool binding;
- skill risk tiers and active-tool validation;
- explicit mission objective, success criteria, constraints, capabilities, risk budget and cycle budget;
- deterministic skill selection with lower-risk preference and stable tie-breaking;
- missing capabilities pause the mission rather than inventing unavailable skills;
- revisioned plans with SHA-256 plan and context fingerprints.

### Continuous assurance

- plan context binds current agent, skills, tools, mission constraints and risk budget;
- context drift pauses a mission and requires re-planning;
- cycle evaluation records success-criterion coverage and referenced v2 action states;
- blocked, revoked or effect-mismatched referenced actions trigger review/pause;
- evaluated observations can be persisted as bounded episodic memory;
- explicit ACTIVE / PAUSED / COMPLETED / FAILED mission states.

### Release evidence

- frozen `autonomy_planning_challenge_v1` deterministic corpus;
- 100% required exact-match planning gate;
- v3 routes added to OpenAPI composition gate;
- v3 files added to SHA-256 release-evidence and external-validation handoff bundles;
- system assurance manifest now fingerprints the skill registry;
- `/v1/system/version` preserves `api_major=1` while exposing `latest_api_major=3` and `supported_api_majors=[1,2,3]`.

### Explicit boundaries

v3.0.0 does not claim AGI, human-level general intelligence, model-weight continual learning, independent autonomous-system safety certification, universal MCP interoperability, completed independent security/product validation, live autonomous production evidence, customers, ARR or formal compliance certification.

## 2.0.0 — 2026-09-30

Autonomous AI Assurance Baseline. v2.0 preserves the stable v1 verification, enterprise-governance, privacy and cryptographic-trust surfaces while adding a governed agent/tool action control plane under `/v2/agents`.

### Autonomous-agent governance

- workspace-scoped agent registry;
- MCP/HTTP/internal tool registry;
- agent tool allowlists and tool operation allowlists;
- per-agent maximum risk tiers and prohibited data-category controls;
- bounded canonical tool input;
- idempotency requirements for state-changing tools;
- bounded per-agent and per-run action budgets;
- supervisor/participant binding for multi-agent runs.

### Runtime authorization

- configurable human-approval threshold;
- configurable Ed25519 signed-approval threshold;
- critical approvals cryptographically bound to the canonical action intent;
- short-lived EffectSeal-backed action authorization envelopes;
- SHA-256 policy snapshots;
- explicit authorization revalidation before execution;
- server-side execution-check verifies authorization signature, TTL, intent digest, tool/operation binding and current policy snapshot;
- expired or drifted authorization fails closed into `POLICY_REVOKED`.

### Outcome assurance

- precommitted intended-effect digest;
- canonical actual-effect digest after execution;
- exact intended-effect vs actual-effect comparison;
- `OUTCOME_VERIFIED` / `OUTCOME_MISMATCH` states;
- signed EffectSeal outcome receipts;
- one recorded outcome per action;
- encrypted agent run/action/outcome records at rest;
- multi-agent supervision halts on blocked, revoked or mismatched actions.

### Agentic security evidence

- frozen `agentic_policy_challenge_v1` deterministic corpus;
- 100% required-match CI gate for the frozen corpus;
- regression coverage for low/high/critical-risk actions, idempotency, human approval, real Ed25519 approval, policy drift/revocation, execution authorization expiry, effect mismatch, supervisor halt, endpoint restrictions and encryption at rest;
- documented threat model for prompt injection, tool confusion, privilege escalation, stale authorization/TOCTOU, duplicate writes, effect divergence and supervisor bypass.

### Release evidence and compatibility

- existing `/v1` APIs remain supported;
- `/v1/system/version` preserves `api_major=1` and adds `latest_api_major=2` plus `supported_api_majors=[1,2]`;
- system assurance manifest includes agent/tool registry counts and SHA-256 fingerprints;
- v2 agentic-policy benchmark and v2 security/release documents are included in release evidence;
- external-validation handoff bundle includes v2 agentic-assurance artifacts.

### Explicitly pending external evidence

v2.0.0 does not claim universal MCP interoperability, independent agentic red-team approval, certified autonomous-agent safety, live autonomous production history, completed independent penetration testing/crypto review, completed Radianode validation, paid customers, ARR, SOC 2/ISO certification, GDPR legal certification or patent/FTO clearance.

## 1.3.0 — 2026-09-30

External Validation Candidate release.

- hardened Kubernetes baseline with 2+ replicas, rolling updates, HPA, PDB and NetworkPolicy;
- non-root/read-only/drop-capabilities container security context and health probes;
- external secret/KMS deployment mode requirement and CI deployment gate;
- X25519 recipient-only EffectSeal opening with signer pinning;
- real Ed25519 intent-bound approval proofs;
- expiry, mutation, signer substitution, key rotation and replay-concurrency regression coverage;
- minimum 500-case predeclared external A/B validation protocol;
- validation protocol/readiness APIs, SHA-256 fingerprints and reproducible evaluator handoff bundle.

External penetration testing, crypto review, independent product validation, live production reliability, customer traction and revenue remained external gates.

## 1.0.0 — 2026-09-30

First stable ORBYTHRA `/v1` enterprise technical baseline.

- deterministic evidence-state verification and guarded disposition;
- Engineering Intelligence and adaptive planning;
- enterprise provider/policy governance and governed multi-provider gateway;
- OIDC/JWT, RBAC and workspace isolation;
- MorseGuard / GestureGuard / DSEL-Project Adûnaic / EffectSeal composition;
- AES-256-GCM, ChaCha20-Poly1305, HKDF-SHA256, Ed25519 and X25519;
- GDPR-aligned privacy technical controls;
- immutable policy history, usage metering and benchmark scorecards;
- frozen assurance benchmark v2/v3, restore drill, Bandit, dependency audit, SBOM, secret scan, release manifest and OpenAPI gates.

v1.0.0 did not self-certify independent security/product validation, legal GDPR compliance, formal certifications, production uptime, paid customers, ARR or patent/FTO clearance.

## V23.2 unified answer Excel export
- Added authenticated POST /v11/answer/export/xlsx.
- Unified Answer UI now exposes an Excel indir button on answer cards.
- Export workbook includes Ozet, Arama Sonuclari, Claimler, Dogrulama, and Pipeline sheets.
- Added Excel formula-injection defense for external/user-controlled cell values.
- Added regression and frontend contract tests for the download flow.
