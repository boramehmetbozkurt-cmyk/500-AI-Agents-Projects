# ORBYTHRA

Private canonical repository for **ORBYTHRA V23.2** — an evidence-first enterprise AI assurance, verification, cryptographic-trust, governed-agent, bounded-autonomy, continual-learning, model-adaptation, multimodal world-model and verifiable-agent traceability platform.

ORBYTHRA is designed as a **verifiable AI / agent control and learning layer**. It combines evidence, policy, identity, cryptographic authorization, long-horizon execution, persistent memory, skill learning, model adaptation and world-state reasoning while keeping high-risk actions bounded and auditable.

> **Claim boundary:** ORBYTHRA is not represented as AGI, human-level general intelligence, consciousness, unrestricted self-improvement, independently certified safety, or proven live enterprise autonomy. Internal CI and regression gates are engineering evidence; they do not replace independent validation, penetration testing, cryptographic review, customer pilots or production history.

## Current canonical state — V23.2

The production composition root is:

```text
app.api:app
```

The current V23.2 stack preserves the V22 cryptographic-hardening baseline, promotes the V23 verifiable-agent vertical slice and V23.1 research/file evidence capabilities, and adds deterministic agent context snapshots, auditable goal lifecycle transitions, persistent chain-linked cycle receipts and receipt verification.

### V23.2 capability map

| Layer | Primary capability |
| --- | --- |
| V1 | Evidence, enterprise policy, privacy, cryptographic trust, provider governance |
| V2 | Governed agent actions, approvals, execution checks, signed outcome receipts |
| V3 | Bounded autonomy, encrypted memory, skills, missions, drift-aware re-planning |
| V4–V12 | Adaptive/generalist hardening, distributed verification, causal/temporal intelligence, audit/release hardening |
| V15 | Final hardening, persistent failure memory, multimodal provenance, long-generation controls |
| V16 | Continual skill learning, curriculum planning, temporal world model, semantic-memory consolidation |
| V17 | Hierarchical long-horizon programs, checkpoint/resume, re-plan, skill synthesis, causal impact analysis |
| V18 | Governed model/adapter adaptation, benchmark comparison, canary rollout and rollback |
| V19 | Structured model-generated planning and metacognitive CONTINUE/REPLAN/REVIEW/BLOCK control |
| V20 | Governed training orchestration, skill invention/sandbox evaluation, multimodal semantic fusion into the world model |
| V21 | Versioned datasets/prompts, reproducible experiments, W3C/OTLP tracing, and trace → evidence → policy → outcome-receipt lineage |
| V22 | Production crypto hardening, isolated signing roots, Ed25519 + ML-DSA-65 hybrid signatures, ML-KEM-768 + X25519 hybrid recipient protection, mandatory replay defense |
| V23 | Verifiable General Agent vertical slice: encrypted episodic memory, persistent goals, bounded action simulation and proof-oriented cycles |
| V23.1 | Workspace file evidence plus keyless DuckDuckGo/Bing research fallback integrated with the unified answer pipeline |
| V23.2 | Deterministic context snapshots, goal lifecycle audit trail, persistent chain-linked cycle receipts and post-hoc receipt verification |

## Evolution from PR #6 to V23.2

PR #6 was primarily the point where the V1–V5.1 API surface was connected to a live React/OpenAPI console, together with V5.1 output-assurance, NLI and web-evidence components.

Since that reference point, the canonical V23.2 codebase has added major new layers including distributed verification, causal/temporal intelligence, persistent failure memory, long-horizon hierarchical programs, continual learning, temporal world state, skill synthesis/invention, governed model adaptation, training orchestration, structured planning, metacognitive control, multimodal semantic fusion, verifiable-agent memory/goals, keyless research/file evidence and chain-linked agent-cycle receipts.

GitHub’s compare view between the PR #6 head and current main reports 138 changed files, including 48 added application modules, 39 added test modules and six added dedicated version-gate workflows. The histories are diverged, so these numbers describe the concrete diff rather than a strict linear commit count.

See [PR #6 → V20 evolution](docs/PR6_TO_V20_EVOLUTION.md) for the earlier baseline and [V21 assurance/observability](docs/V21_ASSURANCE_OBSERVABILITY.md) for the detailed capability-by-capability comparison.

---

## System architecture

The current high-level trust and learning path is:

```text
Evidence
  -> Engineering Intelligence
  -> Enterprise Policy / Identity
  -> Agent Governance
  -> Human / cryptographic Approval when required
  -> EffectSeal / Cryptographic Authorization
  -> Execution-Time Revalidation
  -> Tool Action
  -> Outcome Verification
  -> Persistent Memory
  -> Failure Memory
  -> Hierarchical Goal / Mission State
  -> Checkpoint / Resume / Re-plan
  -> Skill Experience
  -> Curriculum / Skill Candidate
  -> Skill Invention + Trial Evidence
  -> Governed Promotion
  -> Training Manifest
  -> External Isolated Trainer
  -> Candidate Artifact
  -> Frozen Benchmark Comparison
  -> Canary 5% -> 25% -> 50% -> 100%
  -> Automatic / Manual Rollback
  -> Multimodal Evidence Fusion
  -> Temporal World Model
  -> Structured Planner
  -> Metacognitive CONTINUE / REPLAN / REVIEW / BLOCK
  -> V23 Agent Goal + Episodic Context
  -> Bounded Action Simulation
  -> V23.2 Context Commitment
  -> Chain-linked Cycle Receipt
  -> Receipt Verification
```

No later layer bypasses the earlier governance controls.

---

## 1\. Evidence-first verification

ORBYTHRA records and evaluates claims against traceable evidence rather than treating model output as ground truth.

Core behavior includes:

* deterministic evidence states such as supported, contradicted, stale and insufficient-evidence outcomes;

* guarded abstention or qualification when evidence gates fail;

* evidence references and quantitative traceability;

* provider and policy registries;

* audit records and release evidence;

* internet/search-backed evidence providers when configured.

## 2\. Cryptographic trust chain

The trust layer includes:

* AES-256-GCM and ChaCha20-Poly1305 authenticated encryption;

* HKDF-SHA256 key separation;

* separate encryption and signing roots in production;

* Ed25519 signing plus ML-DSA-65 hybrid signatures in V22;

* X25519 compatibility recipient envelopes;

* ML-KEM-768 + X25519 hybrid HPKE recipient protection;

* production-mandatory nonce / TTL / replay protection;

* cryptographically verified production approvals;

* intent/effect binding;

* signed outcome receipts;

* encrypted persistent state;

* release fingerprints and evidence hashes.

The repository also contains the adversarial internal crypto regression gate. This is **not** a substitute for an independent cryptographic review.

## 3\. Enterprise identity and isolation

Supported controls include:

* API-key authentication;

* OIDC/JWT enterprise authentication;

* workspace identity claims;

* role claims and RBAC;

* workspace / tenant isolation;

* rate limiting;

* request body limits;

* audit projection;

* PostgreSQL production persistence.

API keys may be left empty in production when a valid OIDC deployment is configured.

## 4\. Governed agent control plane — V2

`/v2/agents` provides workspace-scoped:

* agent registry;

* tool registry;

* tool / operation allowlists;

* risk ceilings;

* human and Ed25519 approval thresholds;

* short-lived cryptographic authorization;

* execution-time policy revalidation;

* intended-vs-actual effect comparison;

* signed outcome receipts;

* encrypted action/run records;

* multi-agent supervision.

Agent action chain:

```text
Proposal
  -> Policy
  -> Approval
  -> Cryptographic Authorization
  -> Execution Check
  -> Tool Execution
  -> Actual Effect
  -> Signed Outcome Receipt
```

## 5\. Bounded autonomy and memory — V3

`/v3/autonomy` provides:

* encrypted episodic, semantic, procedural and evidence memory;

* confidence, source references, tags and optional expiry;

* versioned skills bound to governed tools;

* mission planning from explicit objective and success criteria;

* risk and cycle budgets;

* missing-capability pause instead of capability fabrication;

* context-drift detection;

* revisioned plans and re-planning;

* ACTIVE / PAUSED / COMPLETED / FAILED mission states.

V3 memory is application memory; it does not modify foundation-model weights.

## 6\. Persistent failure memory — V15

V15 adds release-aware failure persistence.

High- or critical-severity unresolved failures can block continuation or release decisions. Failure records survive process restart and remain available to later planning and metacognitive layers.

## 7\. Long-generation controls — V15

Long-running output generation is managed through persistent sessions and bounded output budgets.

The V15 implementation includes:

* resumable long-generation sessions;

* persistent session/request state;

* aggregate generation budgeting;

* per-provider-call output limits;

* recovery after process re-instantiation;

* explicit failure and abort semantics.

## 8\. Multimodal provenance — V15

V15 provides hash-bound multimodal evidence manifests for artifacts such as:

* image;

* audio;

* video;

* document;

* sensor data.

This layer proves artifact identity, lineage and structural provenance. Semantic interpretation is extended by V20.

## 9\. Continual learning — V16

`/v16/continual` adds governed application-level continual learning.

Capabilities include:

* persistent skill-experience memory;

* cross-domain transfer requirements;

* minimum observation thresholds;

* high-novelty success gates;

* evidence-coverage thresholds;

* regression-safe promotion;

* admin-governed skill activation;

* self-directed curriculum planning.

A skill is not promoted only because it succeeds once. Promotion requires repeated evidence under policy.

## 10\. Temporal world model — V16

The V16 world model stores workspace-isolated facts as:

```text
subject -> predicate -> value
```

Each fact can carry:

* confidence;

* evidence references;

* observed time;

* valid-from / valid-to interval;

* cryptographic value fingerprint.

The world model can detect conflicting values and can consolidate verified facts into agent semantic memory.

## 11\. Hierarchical long-horizon programs — V17

`/v17/generalist` adds persistent long-horizon orchestration.

Capabilities include:

* root objective -> subgoal trees;

* bounded depth and node count;

* action budgets;

* re-plan budgets;

* checkpoint persistence;

* restart-safe resume;

* leaf-goal scheduling;

* superseded branch history;

* unsafe-action pause semantics;

* completion criteria evaluation;

* failure-memory awareness.

This is bounded long-horizon orchestration, not unrestricted autonomous agency.

## 12\. Skill synthesis — V17

Successful traces can be transformed into reusable skill candidates.

A candidate still has to pass:

* its own trial history;

* cross-domain requirements;

* success thresholds;

* evidence thresholds;

* regression-safety requirements;

* novelty requirements;

* V16 promotion policy.

Historical evidence from unrelated candidates cannot be borrowed to bypass the gate.

## 13\. Causal and counterfactual analysis — V17

V17 can register evidence-gated causal graphs and perform bounded downstream reachability analysis.

Example question:

```text
If variable A changes, which downstream nodes may be affected?
```

This is structural causal-hypothesis analysis. It does not estimate real-world intervention magnitude and does not replace experimental validation.

## 14\. Governed model adaptation — V18

`/v18/adaptation` governs externally produced model / adapter candidates.

### Dataset controls

An adaptation plan records:

* dataset identity and purpose;

* sample count;

* train hash;

* validation hash;

* locked holdout hash;

* provenance references;

* license references;

* PII review state.

Train / validation / holdout fingerprints must remain distinct.

### Candidate comparison

Candidates are compared against a baseline using multiple metrics including:

* disposition accuracy;

* traceability rate;

* evidence pass rate;

* guarded-claim rate;

* latency.

A candidate must meet minimum improvement requirements without violating regression ceilings.

### Canary rollout

Eligible candidates progress through:

```text
5% -> 25% -> 50% -> 100%
```

Routing is deterministic by request key.

Error-rate, quality, latency or explicit regression failures trigger rollback.

## 15\. Structured model planner — V19

`/v19/planner` can request a model to propose bounded subgoal structures as strict JSON.

The planner:

* cannot grant permissions;

* cannot execute tools;

* cannot mark work complete by itself;

* must respect program and parent-goal risk budgets;

* rejects malformed, duplicate or circular/restated subgoals;

* stores proposal integrity hashes;

* separates proposal creation from application.

Private semantic-memory contents and world-fact values are excluded from provider prompts by default; the planner uses bounded metadata context.

## 16\. Metacognitive control — V19

`/v19/reflection` evaluates:

* confidence;

* evidence coverage;

* contradiction rate;

* recent failure rate;

* distribution shift;

* current hierarchical program state;

* persistent failure-memory release gate.

The result is one of:

```text
CONTINUE
REPLAN
REVIEW
BLOCK
COMPLETE
```

An unresolved high/critical failure can override apparent program completion and return `BLOCK`.

## 17\. Governed learning engine — V20

`/v20/learning` adds a controlled training-job lifecycle.

ORBYTHRA creates a training manifest containing:

* base model;

* adaptation type;

* dataset manifest;

* target capabilities;

* trainer profile;

* epochs;

* learning rate;

* batch size;

* gradient accumulation;

* seed;

* maximum training duration;

* requested artifact model ID.

The job can be submitted to an explicitly configured isolated trainer service.

Lifecycle:

```text
PREPARED
  -> SUBMITTED
  -> RUNNING
  -> SUCCEEDED / FAILED / CANCELLED
  -> CANDIDATE_REGISTERED
```

Successful artifacts must provide:

* artifact SHA-256;

* training-config SHA-256;

* size;

* trainer attestation references;

* base-model fingerprint.

A successful training result does **not** go directly to production. It is handed to V18 and must still pass benchmark and canary gates.

Actual GPU training is not executed as arbitrary code inside the ORBYTHRA API process.

## 18\. Skill invention — V20

`/v20/skills` can ask a configured model to invent a bounded reusable skill.

The model returns declarative structure, not executable arbitrary code:

* skill ID;

* description;

* procedure steps;

* capabilities;

* required governed tool IDs;

* risk tier;

* cross-domain trial scenarios;

* observable invariants;

* novelty scores.

Controls include:

* tool allowlist enforcement;

* maximum risk tier;

* minimum cross-domain trial count;

* high-novelty trial requirement;

* one-shot replay-resistant evidence recording;

* optional isolated sandbox evaluation;

* V16/V17 promotion-gate reuse.

Generated code is not executed inside the API process.

## 19\. Multimodal semantic world fusion — V20

`/v20/multimodal` extends V15 provenance into semantic fusion.

Semantic adapter outputs are bound to:

* artifact ID;

* modality;

* original content SHA-256;

* adapter ID/version;

* adapter-output SHA-256;

* claim identity.

Facts require configurable support thresholds such as:

* minimum modality count;

* minimum independent lineage count;

* minimum claim confidence;

* minimum mean confidence.

Supported cross-modal facts can be written into the V16 temporal world model.

Conflicting supported values are detected and can block world-model writes.

Incompatible temporal validity intervals also block fact creation.

ORBYTHRA does not claim that the core itself natively decodes pixels, audio or video. Semantic correctness depends on validated modality adapters.

---

## Current production API families

Major versioned surfaces include:

* `/v1/*` — evidence, enterprise, assurance, privacy, cryptographic foundation;

* `/v2/agents/*` — governed agent actions;

* `/v3/autonomy/*` — memory, missions and bounded autonomy;

* `/v4/adaptive/*` — adaptive/generalist baseline;

* later hardened V9–V15 validation, temporal, multimodal and release surfaces;

* `/v16/continual/*` — continual learning and temporal world model;

* `/v17/generalist/*` — hierarchical long-horizon generalist control;

* `/v18/adaptation/*` — model adaptation and canary routing;

* `/v19/planner/*` — structured planning;

* `/v19/reflection/*` — metacognitive program control;

* `/v20/learning/*` — governed training lifecycle;

* `/v20/skills/*` — skill invention and evaluation;

* `/v20/multimodal/*` — multimodal semantic fusion.

Use the generated OpenAPI document from the running API as the authoritative route contract.

## Quick start — secure demo

The repository provides a single-command demo composition:

```bash
docker compose -f docker-compose.demo.yml up --build
```

The demo composition includes the frontend, API, local persistence/services and health checks required by that profile.

Do not share demo credentials as production credentials.

## Production composition

Copy and configure the environment template:

```bash
cp .env.example .env
```

At minimum, configure production identity and secret material appropriately. Production supports API keys and/or OIDC depending on deployment policy.

Start the production composition:

```bash
docker compose -f docker-compose.production.yml up --build -d
```

Production composition includes:

* PostgreSQL;

* ORBYTHRA API;

* React frontend / nginx proxy;

* health checks;

* configurable external evidence/model providers;

* optional V20 trainer service endpoint;

* optional V20 isolated skill-sandbox endpoint;

* optional multimodal adapter allowlist.

Never commit real secrets to the repository.

## Important V20 environment integrations

Optional V20 integration variables:

```text
ORBYTHRA_TRAINING_PROVIDER_URL
ORBYTHRA_TRAINING_PROVIDER_TOKEN
ORBYTHRA_SKILL_SANDBOX_URL
ORBYTHRA_SKILL_SANDBOX_TOKEN
ORBYTHRA_MULTIMODAL_ALLOWED_ADAPTERS
```

Without a configured trainer provider, ORBYTHRA can prepare governed training manifests but cannot execute external GPU training.

Without a configured skill sandbox, declarative skill invention remains available but isolated executable evaluation is unavailable.

## Internal release gates

The current release path includes separate gates for the hardened V15–V20 layers plus the full FastAPI CI.

The exact main release is expected to pass:

1. production compose validation;

2. production frontend build;

3. frontend + API + PostgreSQL runtime smoke;

4. Python compilation;

5. full regression suite;

6. adversarial crypto regression gate;

7. frozen assurance / agent / autonomy / generalist regressions;

8. backup/restore integrity drill;

9. database corruption recovery gate;

10. frontend credential-persistence guard;

11. static security scan;

12. dependency vulnerability audit;

13. CycloneDX SBOM generation;

14. repository secret scan;

15. release evidence manifest;

16. external-validation handoff bundle;

17. production OpenAPI composition gates;

18. V15 Final Gate;

19. V16 Continual Generalist Gate;

20. V17 Hierarchical Generalist Gate;

21. V18 Governed Adaptation Gate;

22. V19 Structured Planner Gate;

23. V20 Learning and Multimodal Gate.

At the time of this README refresh, the V20 main release passed the current internal FastAPI CI and V15–V20 version gates.

Internal green status is not external certification.

## External validation still required

Production or commercial claims should remain gated on independent evidence.

Outstanding external assurance categories include:

* independent penetration testing;

* scoped independent cryptographic review;

* independent assessor-owned product/generalist validation;

* contamination-controlled unseen-task evaluation;

* real long-horizon operational testing;

* real customer pilot(s);

* production reliability / incident / recovery evidence;

* external compliance certification where applicable.

## AGI / general-intelligence boundary

ORBYTHRA V20 contains mechanisms commonly associated with more general agent systems:

* persistent memory;

* continual application-level learning;

* self-directed curriculum generation;

* cross-domain skill transfer;

* skill invention;

* hierarchical long-horizon planning;

* checkpoint / resume / re-plan;

* temporal world model;

* causal graph analysis;

* governed model adaptation;

* training orchestration;

* structured model planning;

* metacognitive control;

* multimodal semantic fusion.

These mechanisms do **not** establish AGI.

ORBYTHRA does not currently claim:

* human-level performance across arbitrary domains;

* independently demonstrated AGI;

* unrestricted recursive self-improvement;

* consciousness or sentience;

* autonomous permission escalation;

* arbitrary generated-code execution inside the API;

* embedded foundation-model training inside the API process;

* independently certified autonomous-system safety.

AGI-like capability claims require broad, contamination-controlled, assessor-owned unseen-task evidence and real-world generalization results.

## Security and operational documentation

Key repository documents include:

* `SECURITY.md`

* `docs/CRYPTO_ARCHITECTURE.md`

* `docs/PRODUCTION_RUNBOOK.md`

* `docs/API_STABILITY.md`

* `docs/SOC2_ISO27001_READINESS.md`

* `docs/SLA_SUPPORT_INCIDENT_POLICY.md`

* `docs/V15_FINAL_HARDENING.md`

* `docs/V15_RELEASE_CRITERIA.md`

* `docs/V15_LONG_GENERATION_2M.md`

* `RADIANODE_READINESS.md`

* `docs/RADIANODE_EVALUATION_READINESS.md`

Historical release-criteria documents remain in `docs/` for traceability.

## Repository status

This repository is private and is intended to remain the canonical technical source for controlled ORBYTHRA evaluation, development and external-validation handoff.

The canonical implementation is the code and tests on `main`. README language must not be treated as stronger evidence than executable release gates, retained artifacts or independent validation results.
### Unified Answer Excel export
The answer console includes an **Excel indir** action for completed results. It POSTs the already-rendered `UnifiedAnswerResponse` to `/v11/answer/export/xlsx` and downloads a real `.xlsx` workbook containing the summary, search/evidence sources, claims, verification fields, and pipeline trace. The export endpoint requires the same operator authentication as the answer route and sanitizes formula-like cell values before writing them.
