# ORBYTHRA v4.0.0 Release Criteria

## Release identity

**ORBYTHRA v4.0.0 — Adaptive Generalist AI Baseline**

v4 extends the stable v1 assurance foundation, v2 governed agent-action plane and v3 bounded-autonomy layer with an application-level adaptive generalist plane under `/v4/adaptive`.

## Required implemented controls

A v4 release candidate must include all of the following:

- revisioned, SHA-256 hash-chained world-state records;
- evidence-referenced learning candidates;
- explicit baseline, candidate and minimum-improvement scores;
- fail-closed rejection when minimum measured improvement is not met;
- explicit human approval for high/critical-risk learning activation;
- derived skills bound to the existing v3 skill registry and governed v2 tools;
- rollback that disables the derived skill and appends a new learning revision;
- provenance-bound cross-domain transfer proposals that grant no tool authority;
- deterministic strategy routing constrained by domain, capability and maximum risk;
- workspace isolation and existing RBAC/audit controls;
- v3 memory/mission behavior and v2 execution gates preserved.

## Mandatory CI gates

Release is internally green only when the exact release head passes:

1. application compilation;
2. complete pytest suite across v1/v2/v3/v4;
3. frozen assurance benchmark v2;
4. expanded assurance benchmark v3;
5. frozen agentic-policy benchmark;
6. frozen autonomy-planning benchmark;
7. frozen adaptive-generalist benchmark;
8. external-validation protocol syntax gate;
9. deterministic performance smoke;
10. Kubernetes deployment hardening gate;
11. backup/restore integrity drill;
12. Bandit static-security scan;
13. dependency vulnerability audit;
14. CycloneDX SBOM generation;
15. repository secret scan;
16. SHA-256 release-evidence manifest;
17. external-validation handoff bundle;
18. production composition/OpenAPI gate including required v1-v4 routes.

## Release evidence

`GET /v1/system/assurance-manifest` must expose hash-addressed internal evidence for, at minimum:

- provider, policy and identity registries;
- agent and tool registries;
- v3 skill registry;
- v4 world-state revisions;
- v4 adaptive-learning revision history;
- v4 strategy registry;
- v4 transfer proposals.

The manifest must continue to state external gates explicitly rather than treating internal regression evidence as certification.

## Safety and claim boundary

v4.0.0 is an **application-level adaptive generalist baseline**. It does not:

- self-train or modify foundation-model weights;
- claim AGI or human-level general intelligence;
- grant tool authority from a cross-domain transfer proposal;
- allow high/critical-risk learning activation without explicit human approval;
- bypass v2 policy, cryptographic authorization, execution-check or outcome verification;
- constitute independent adaptive-system safety validation;
- constitute an independent penetration test or cryptographic review;
- prove live production reliability, customers, revenue, SOC 2/ISO certification or legal GDPR compliance.

## External completion gates

The following remain external until evidence from the relevant independent or operational party exists:

- independent adaptive-generalist evaluation;
- independent autonomy/agentic red-team validation;
- penetration testing and cryptographic review;
- real MCP/tool interoperability testing;
- production telemetry and reliability history;
- enterprise pilot acceptance and commercial evidence.

Internal CI success is necessary for release, but is not a substitute for these external gates.
