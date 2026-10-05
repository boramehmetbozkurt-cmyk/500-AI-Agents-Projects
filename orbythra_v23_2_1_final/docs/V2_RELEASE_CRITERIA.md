# ORBYTHRA v2.0 Release Criteria

## Release identity

Target: `2.0.0` — **Autonomous AI Assurance Baseline**.

ORBYTHRA v2 extends the stable v1 verification/governance/cryptographic-trust platform with an agent/tool control plane. The release number does not mean autonomous agents are independently certified safe or that live MCP/tool production execution has been externally validated.

## Compatibility boundary

- Existing `/v1` surfaces remain available.
- New autonomous-agent control surfaces live under `/v2/agents`.
- `/v1/system/version` preserves its historical `api_major=1` contract while exposing `latest_api_major=2` and `supported_api_majors=[1,2]`.
- v2 must not weaken the v1 evidence, privacy, enterprise policy, identity, crypto or release-evidence gates.

## Mandatory v2 internal capabilities

1. workspace-scoped agent registry;
2. workspace-scoped tool registry for MCP, HTTP and internal tools;
3. tool-operation allowlisting;
4. agent maximum-risk ceilings;
5. prohibited-data-category enforcement;
6. input-size enforcement;
7. idempotency-key enforcement for state-changing tools;
8. human approval from configured risk threshold;
9. Ed25519 intent-bound signed approval from configured risk threshold;
10. short-lived EffectSeal-backed action authorization;
11. policy-snapshot SHA-256 binding;
12. explicit policy revalidation immediately before execution;
13. server-side execution check that verifies authorization signature, TTL, intent digest, tool/operation binding and current policy snapshot;
14. policy drift/expiry revocation handling;
15. exact canonical intended-effect vs actual-effect digest comparison;
16. signed outcome receipt;
17. single recorded outcome per action;
18. encrypted action/outcome records at rest;
19. multi-agent run supervisor and participant binding;
20. fail-closed run halt on blocked, revoked or mismatched actions;
21. frozen deterministic agentic-policy benchmark at 100% required match.

## Mandatory CI gates

A v2 release commit must pass:

- the complete pytest suite;
- frozen assurance benchmark v2;
- expanded assurance benchmark v3;
- frozen agentic-policy challenge v1;
- external-validation protocol syntax gate;
- deterministic verification performance gate;
- hardened Kubernetes manifest gate;
- backup/restore integrity drill;
- Bandit static-security gate;
- dependency vulnerability audit;
- CycloneDX SBOM generation;
- repository secret scan;
- SHA-256 release-evidence manifest;
- external-validation handoff bundle generation;
- OpenAPI composition check including all mandatory `/v2/agents` routes.

## Agent action state model

`PROPOSE -> BLOCKED | REVIEW | AUTHORIZED`

A reviewed action can transition through:

`REVIEW -> AUTHORIZE -> AUTHORIZED`

Immediately before tool execution:

`AUTHORIZED -> REVALIDATE / EXECUTION-CHECK -> EXECUTABLE | POLICY_REVOKED`

The execution check opens the EffectSeal authorization and fails closed on expiry, signature failure, intent mismatch, policy drift or authorization payload mismatch.

After execution:

`AUTHORIZED -> OUTCOME_VERIFIED | OUTCOME_MISMATCH`

Multi-agent supervision halts a run when a material action becomes `BLOCKED`, `POLICY_REVOKED` or `OUTCOME_MISMATCH`.

## Cryptographic binding

The canonical agent intent includes workspace, run, agent, tool, operation, parameters, intended effect, risk tier, data categories and idempotency key. The intent object includes an explicit `kind=agent-action` field and is committed through the same EffectSeal intent domain used for Ed25519 approval verification.

Critical actions can therefore bind:

`Agent Intent -> Human Approval -> Ed25519 Proof -> EffectSeal Authorization -> Server-Side Execution Check -> Tool Execution -> Actual Effect -> Signed Outcome Receipt`

## MCP/tool boundary

v2.0 governs MCP/HTTP/internal tool registration and authorization. It deliberately does not claim that every external MCP implementation is interoperable or safe.

External tool endpoints are rejected when configured as literal local/private/loopback/link-local addresses. Production external endpoints must use HTTPS. Secrets are not fields in tool profiles.

## External evidence still required

- real MCP server interoperability testing;
- production execution history against real tools;
- independent agentic red-team / penetration test;
- independent review of authorization and outcome-verification semantics;
- measured stale-authorization/TOCTOU behavior with a real executor;
- customer acceptance on real enterprise agent workloads;
- measured incident, false-block and false-allow rates;
- formal certifications where buyer requirements justify them.

## Approved claim

> ORBYTHRA v2.0 is an internally validated autonomous AI assurance baseline that mediates agent/tool actions with risk policy, human and cryptographic approval, short-lived authorization, server-side execution authorization checks, intended-effect/outcome verification and multi-agent supervision. Independent agentic-security validation and live autonomous production evidence remain separate external gates.
