# ORBYTHRA Evolution — PR #6 to V20

Historical reference: PR #6 — “Connect full ORBYTHRA API surface to React”

PR #6 represented the point where the V1–V5.1 API surface was exposed through a live React/OpenAPI console and V5.1 output-assurance components were added. The current V20 main branch has evolved far beyond that baseline.

> Note: GitHub reports the PR #6 head and current main as diverged. Therefore commit counts are not a strict linear chronology. The file/module/function comparison below describes the concrete capability difference between the PR #6 head and the current canonical V20 main.

## Repository delta

| Metric | PR #6 head → current main |
|---|---:|
| Files changed | 138 |
| New application modules | 48 |
| New test modules | 39 |
| New dedicated release workflows | 6 |
| New technical docs in the compare set | 7 |

## What PR #6 contained

PR #6 primarily delivered:

- React/OpenAPI endpoint console for the V1–V5.1 surface;
- authenticated, workspace-scoped endpoint execution from the client;
- OpenAPI discovery, filtering, parameter editing and generated JSON request templates;
- V5.1 model-output assurance;
- NLI verification;
- web-evidence integration;
- React production build coverage in CI.

## Major capabilities added after PR #6

| Version / Layer | Added capability | What it changes |
|---|---|---|
| V6 | Verifiable Intelligence | Adds a dedicated verifiable-intelligence layer and API surface. |
| V7 | Governed Agents | Adds governed agent execution and policy-controlled agent behavior. |
| V8 | Temporal Reality | Adds time-validity and temporal-reality checks. |
| V9 | Distributed Verification | Adds workspace-aware distributed validators and quorum-style verification. |
| V10 | AI Operating Layer | Adds model-adapter and AI-operating abstractions. |
| V11 | Causal Intelligence | Adds evidence-gated cause/effect graph reasoning. |
| V11H | Metacognition | Adds confidence, uncertainty, contradiction, failure-rate and distribution-shift assessment. |
| V12 | Verification Firewall | Adds fail-closed verification and stronger action-chain enforcement. |
| V12 | Distributed / Temporal Hardening | Strengthens distributed verification and temporal semantics. |
| V12 | External Validation Package | Adds assessor-oriented handoff, release criteria and security-audit scope. |
| V15 | Failure Memory | Persists important failures across restarts and later decisions. |
| V15 | Release Blocking | Allows unresolved high/critical failures to block continuation or release. |
| V15 | Agent Control Plane | Adds a stronger agent-management and control-plane layer. |
| V15 | Effect Verification | Compares intended effects with actual effects. |
| V15 | Action-Chain Finalization | Finalizes governed action chains with retained evidence. |
| V15 | Calibration | Adds confidence/calibration controls. |
| V15 | Multimodal Evidence | Adds hash-bound provenance for image, audio, video, document and sensor artifacts. |
| V15 | Visual Identity Assurance | Adds identity-preservation and visual-assurance controls. |
| V15 | Long Generation | Adds persistent, resumable long-output sessions and aggregate output budgeting. |
| V16 | Continual Learning | Records skill experience and learns application-level capability performance over time. |
| V16 | Cross-Domain Transfer | Requires skill success across multiple domains rather than one narrow task family. |
| V16 | Novelty Gate | Requires success on sufficiently novel tasks. |
| V16 | Regression-Safe Learning | Blocks promotion when learning degrades prior capability safety. |
| V16 | Self-Directed Curriculum | Detects weak domains and proposes where more evidence/trials are required. |
| V16 | Temporal World Model | Stores subject/predicate/value facts with confidence, evidence and validity intervals. |
| V16 | Contradiction Detection | Detects incompatible world-model facts. |
| V16 | Semantic Memory Consolidation | Moves verified, non-conflicting world facts into agent semantic memory. |
| V17 | Hierarchical Programs | Adds root-goal → subgoal trees for long-horizon work. |
| V17 | Checkpoint / Resume | Persists long-running work and resumes after restart. |
| V17 | Replanning | Replaces failed or obsolete branches with bounded new plans. |
| V17 | Action / Replan / Risk Budgets | Prevents unlimited actions, unlimited replans and risk escalation. |
| V17 | Skill Synthesis | Converts successful traces into reusable skill candidates. |
| V17 | Counterfactual Reachability | Estimates which downstream causal nodes may be affected by a change. |
| V18 | Model Adaptation Governance | Registers and evaluates new model/adapter candidates. |
| V18 | Dataset Provenance | Adds train/validation/holdout hashes, provenance, licensing and PII-review state. |
| V18 | Locked Holdout | Keeps holdout evidence separated from training. |
| V18 | Baseline vs Candidate Benchmark | Requires measurable candidate improvement without unacceptable regression. |
| V18 | Progressive Canary | Adds deterministic 5% → 25% → 50% → 100% rollout. |
| V18 | Automatic / Manual Rollback | Reverts unsafe or degraded candidate models. |
| V19 | Structured Planner | Uses strict JSON subgoal proposals instead of unconstrained free-text planning. |
| V19 | Planner Risk Validation | Rejects plans that exceed program or parent-goal risk ceilings. |
| V19 | Planner Privacy Boundary | Excludes private semantic-memory contents and world-fact values from external planner prompts by default. |
| V19 | Proposal Integrity | Hash-binds stored plan proposals before application. |
| V19 | Metacognitive Control | Produces CONTINUE / REPLAN / REVIEW / BLOCK / COMPLETE decisions. |
| V20 | Learning Engine | Adds governed training-job lifecycle orchestration. |
| V20 | Training Manifest | Binds base model, dataset, learning parameters, seed and target artifact identity. |
| V20 | External Trainer Handoff | Sends bounded jobs to an explicitly configured isolated trainer service. |
| V20 | Training Artifact Verification | Verifies model/artifact identity, hashes, config fingerprints and trainer attestations. |
| V20 | V18 Handoff | Successful training becomes a V18 candidate and must still pass benchmark/canary gates. |
| V20 | Skill Invention | Generates declarative reusable skill procedures and trial suites. |
| V20 | Skill Sandbox | Supports isolated skill evaluation outside the API process. |
| V20 | Trial Replay Protection | Prevents repeated trial submissions from inflating evidence. |
| V20 | Multimodal Semantic Fusion | Fuses hash-bound semantic interpretations across modalities. |
| V20 | Cross-Modal Consensus | Requires configurable modality/lineage support before creating world facts. |
| V20 | Multimodal Conflict Blocking | Blocks unsupported or conflicting interpretations instead of silently writing them. |
| V20 | Multimodal → World Model | Writes sufficiently supported semantic facts into the V16 temporal world model. |

## Infrastructure and assurance added after PR #6

Beyond the intelligence layers, the project also gained:

- local LLM / Ollama integration and readiness checks;
- provider abstraction and external evidence/search integration;
- unified-answer API and console behavior;
- PostgreSQL-backed production persistence;
- restart-recovery coverage;
- backup/restore integrity testing;
- database-corruption fault-injection recovery;
- production Docker Compose with frontend, API and PostgreSQL;
- nginx frontend/API proxying and health checks;
- production runtime smoke tests;
- static security scanning;
- dependency vulnerability audit;
- repository secret scanning;
- CycloneDX SBOM generation;
- release-evidence manifests;
- external-validation handoff bundles;
- dedicated V15, V16, V17, V18, V19 and V20 release gates;
- adversarial one-million-case internal crypto regression gate.

## Architectural change in one line

PR #6:

AI output verification + web/NLI evidence + React access to the API surface

Current V20:

Evidence → Verification → Cryptographic Trust → Agent Governance → Persistent Memory → Failure Memory → Long-Horizon Planning → Replan → Continual Learning → Curriculum → Skill Synthesis → Skill Invention → Training → Benchmark → Canary → Rollback → Multimodal World Model → Structured Planning → Metacognition

## Practical interpretation

The most important change is not the number of endpoints. At PR #6, ORBYTHRA was primarily an AI-output verification and evidence system with a React control surface. V20 is a governed AI/agent operating and learning layer that can manage evidence, actions, long-horizon state, learning candidates, model adaptation and semantic world-state updates under explicit controls.

## Claim boundary

These additions do not establish AGI. Internal CI, regression gates, synthetic tests and internal crypto gates are engineering evidence, not independent certification. Broad contamination-controlled unseen-task evaluation, independent security/crypto review, real customer pilots and production reliability evidence are still required for stronger external claims.