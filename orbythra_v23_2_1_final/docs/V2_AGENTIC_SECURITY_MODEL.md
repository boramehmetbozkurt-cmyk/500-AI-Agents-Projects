# ORBYTHRA v2 Agentic Security Model

## Purpose

ORBYTHRA v2 treats model output and agent intent as untrusted until an action passes explicit governance and cryptographic authorization controls. Prompt content does not itself confer permission to execute a tool.

## Primary threats and controls

### Prompt injection / malicious instructions
Control: the agent can only use registered tools and allowlisted operations. Risk, data category and approval gates are evaluated outside the model response.

### Tool confusion or substitution
Control: authorization binds the exact `tool_id`, operation, parameters and intended effect into the canonical action intent.

### Privilege escalation
Control: each agent has a maximum risk tier and explicit allowed tools. Workspace/RBAC authentication remains enforced by the API layer.

### High-risk action without human approval
Control: configurable `human_approval_from_risk` threshold. Actions remain in `REVIEW` until approval requirements are satisfied.

### Forged critical approval
Control: configurable `signed_approval_from_risk` threshold. Ed25519 approval proofs are verified against the canonical intent digest and approver identity is derived from the signing public-key fingerprint.

### Stale authorization / TOCTOU policy change
Control: every authorization contains a SHA-256 policy snapshot. The action can be explicitly revalidated immediately before execution. Policy/tool/agent drift revokes a previously authorized action.

### Duplicate state mutation
Control: state-changing tools require an idempotency key. Outcomes are single-record per action. Existing nonce/replay controls continue to protect EffectSeal envelopes.

### Intent/effect divergence
Control: ORBYTHRA commits the intended effect before execution and compares it with the canonical actual-effect digest. Mismatch produces `OUTCOME_MISMATCH` and causes multi-agent supervision to halt the run.

### Outcome tampering
Control: outcome records are encrypted at rest and the outcome evidence is wrapped in a signed EffectSeal receipt.

### Supervisor bypass / rogue participant
Control: agent runs bind a supervisor and participant set. A participant with a configured supervisor must match the run supervisor.

### Excessive autonomous loops
Control: runs and individual agents have bounded action counts. A run cannot exceed its configured action budget.

### Tool endpoint SSRF
Control: literal localhost, private, loopback, link-local, multicast and unspecified external addresses are rejected. Production external tools require HTTPS. This is a registry/control-plane mitigation, not a full network egress sandbox.

### Oversized tool input
Control: each tool profile has a bounded maximum canonical input size.

### Cross-tenant access
Control: registries, runs, actions, outcomes and audit events are workspace scoped. Existing API-key/OIDC/RBAC controls remain in force.

## Authorization chain

`Untrusted Agent Proposal`

`-> Agent Registry`

`-> Tool/MCP Registry`

`-> Risk + Data + Operation Policy`

`-> Idempotency Gate`

`-> Human Review Gate`

`-> Ed25519 Intent-Bound Approval (when required)`

`-> Policy Snapshot SHA-256`

`-> Short-Lived EffectSeal Authorization`

`-> Revalidation Immediately Before Execution`

`-> External/Internal Tool Execution`

`-> Actual Effect Submission`

`-> Exact Effect Digest Comparison`

`-> Signed Outcome Receipt`

`-> Multi-Agent Supervision`

## Important limitations

ORBYTHRA v2.0 is a control plane, not a universal execution sandbox. The repository does not yet prove:

- compatibility with every MCP server/client implementation;
- isolation of arbitrary third-party tool code;
- semantic equivalence when an external system cannot report a precise canonical effect;
- protection from DNS rebinding or all network-layer SSRF without deployment egress controls;
- hardware-backed human identity or WebAuthn attestation for every approval;
- safety of the underlying model or agent planner;
- independent resistance to sophisticated agentic red-team attacks;
- production incident-rate reduction.

The external executor is responsible for enforcing the short authorization TTL, revalidating immediately before execution, using the authorized tool/operation/parameters, and returning a truthful actual-effect record.

## Validation strategy

Repository evidence includes unit/integration tests and a frozen agentic-policy corpus. Independent v2 validation should additionally exercise real MCP servers, hostile tool descriptions, prompt injection, confused-deputy cases, authorization expiry, policy changes between authorization and execution, concurrent state changes, false effect reports and multi-agent collusion attempts.
