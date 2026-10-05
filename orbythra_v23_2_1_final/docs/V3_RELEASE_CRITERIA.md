# ORBYTHRA v3.0 Release Criteria

## Release identity

Target: `3.0.0` — **Bounded Autonomous AI System Baseline**.

v3 extends the v1 evidence/enterprise/crypto baseline and v2 agent-action control plane with persistent encrypted memory, a registered skill layer, deterministic mission planning, criteria-based cycle evaluation and context-drift detection.

The release does **not** claim AGI, model-weight continual learning, independent autonomous-system safety certification or proven live enterprise autonomy.

## Compatibility

- `/v1` remains the stable assurance/enterprise surface.
- `/v2/agents` remains the governed action-authorization and outcome-assurance surface.
- `/v3/autonomy` adds bounded autonomy orchestration.
- `/v1/system/version` preserves historical `api_major=1`, exposes `latest_api_major=3` and `supported_api_majors=[1,2,3]`.

## Mandatory v3 internal capabilities

1. workspace- and agent-scoped persistent memory;
2. AES-backed encrypted memory payloads through the existing ORBYTHRA vault;
3. memory kinds: episodic, semantic, procedural and evidence;
4. memory confidence, provenance/source references, tags and optional expiry;
5. workspace-scoped skill registry;
6. skills bind capabilities to existing governed v2 tools;
7. skill risk tiers cannot exceed mission risk budgets during planning;
8. deterministic skill selection with stable lower-risk preference;
9. missing capabilities pause planning rather than inventing unavailable skills;
10. mission objects with explicit objective, constraints, success criteria and cycle budget;
11. deterministic revisioned mission plans;
12. plan context SHA-256 binding to agent, skills, tools, constraints and risk budget;
13. context-drift detection and fail-closed pause/replan behavior;
14. bounded criteria-based cycle evaluation;
15. v2 action states are incorporated when action IDs are supplied;
16. blocked/revoked/mismatched v2 actions pause v3 mission progression;
17. bounded evaluated observations can be persisted as episodic memory;
18. mission completion, pause and failure states are explicit;
19. frozen deterministic autonomy-planning benchmark requires 100% exact match;
20. readiness endpoint explicitly states that v3 is not an AGI claim.

## Mission lifecycle

`CREATE -> PLAN -> ACTIVE`

If required capabilities are unavailable:

`PLAN -> PAUSED`

During operation:

`ACTIVE -> DRIFT CHECK -> ACTIVE | PAUSED`

Cycle evaluation:

`ACTIVE/PAUSED -> EVALUATE -> ACTIVE | PAUSED | COMPLETED | FAILED`

A new plan revision can be created after drift or capability changes.

## Trust composition

v3 planning does not bypass v2 action controls. Any real consequential tool action remains subject to:

`Agent Intent -> v2 Policy -> Human/Ed25519 Approval -> EffectSeal Authorization -> Execution Check -> Tool Execution -> Outcome Verification -> Signed Receipt`

v3 adds the surrounding mission context:

`Memory -> Skill Selection -> Mission Plan -> Governed v2 Actions -> Criteria Evaluation -> Drift Check -> Bounded Memory Update`

## Mandatory CI gates

A final v3 release commit must pass:

- complete pytest suite;
- frozen assurance benchmark v2;
- expanded assurance benchmark v3;
- frozen agentic-policy benchmark;
- frozen autonomy-planning benchmark;
- external-validation protocol syntax gate;
- deterministic performance gate;
- hardened Kubernetes deployment gate;
- backup/restore integrity drill;
- Bandit static-security gate;
- dependency vulnerability audit;
- CycloneDX SBOM generation;
- repository secret scan;
- SHA-256 release-evidence manifest;
- external-validation handoff bundle generation;
- OpenAPI composition for mandatory v1/v2/v3 routes.

## Explicit boundaries

v3 memory is application memory, not model-weight training. The planner is deterministic registered-skill orchestration, not proof of human-level general reasoning. Criteria evaluation operates on declared criteria, submitted observations and recorded action states; independent validation is still required for real-world effectiveness.

## External evidence still required

- independent autonomy/agentic red-team evaluation;
- real MCP/tool interoperability tests;
- production execution history;
- measured mission-success/false-block/false-allow rates;
- external KMS/HSM custody evidence;
- independent pentest and crypto review;
- enterprise customer acceptance;
- paid conversion and recurring revenue;
- any AGI/general-intelligence claim would require separate broad independent capability testing.

## Approved claim

> ORBYTHRA v3.0 is an internally validated bounded autonomy orchestration baseline combining encrypted persistent memory, registered skills, deterministic mission planning, drift detection, criteria-based evaluation and the v2 cryptographic action-assurance layer. It is not an AGI claim and independent live-autonomy evidence remains an external gate.
