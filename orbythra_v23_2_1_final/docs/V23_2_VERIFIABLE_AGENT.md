# ORBYTHRA V23.2 — Verifiable Agent Traceability

V23.2 strengthens the V23 Verifiable General Agent vertical slice without weakening the existing governance boundary.

## Added in V23.2

1. **Canonical release promotion** — `PLATFORM_RELEASE=23.2.0` and release metadata expose V23/V23.1/V23.2 capabilities.
2. **Agent context snapshots** — active/historical goals, recent encrypted episodic memories and referenced evidence are assembled into a deterministic SHA-256 context commitment.
3. **Goal lifecycle** — authenticated goal status changes (`ACTIVE`, `PAUSED`, `COMPLETED`, `CANCELLED`) are recorded as auditable status events; terminal states fail closed.
4. **Persistent cycle receipts** — each agent cycle stores goal, episode, context, evidence-manifest and simulation commitments.
5. **Tamper-evident workspace chain** — each receipt commits to the previous receipt hash, producing an append-oriented decision history.
6. **Receipt verification API** — stored payload integrity and previous-link integrity can be recomputed after the fact.
7. **V23.1 formalization** — workspace file evidence and keyless web discovery are explicitly included in the canonical capability map.

## V23.2 bounded cycle

```text
GOAL (ACTIVE)
  -> EPISODE
  -> CONTEXT SNAPSHOT
  -> CANDIDATE SIMULATION
  -> READY / REVIEW / BLOCK
  -> EVIDENCE MANIFEST HASH
  -> PERSISTENT RECEIPT
  -> PREVIOUS-RECEIPT HASH LINK
  -> VERIFY RECEIPT
```

The V23.2 cycle still stops before external execution. Existing ORBYTHRA authorization, approval, replay-protection and execution-control layers remain responsible for side effects.

## Primary endpoints

- `GET /v23.2/general-agent/context/{agent_id}`
- `GET /v23.2/general-agent/goals/{agent_id}`
- `PATCH /v23.2/general-agent/goals/{goal_id}/status`
- `GET /v23.2/general-agent/goals/{goal_id}/history`
- `POST /v23.2/general-agent/cycle`
- `GET /v23.2/general-agent/receipts/agent/{agent_id}`
- `GET /v23.2/general-agent/receipts/{cycle_id}`
- `GET /v23.2/general-agent/receipts/{cycle_id}/verify`

## Explicit non-claims

V23.2 is engineering evidence for a bounded, traceable agent layer. It is not evidence of AGI, unrestricted autonomy, independent certification, universal correctness, or production maturity.
