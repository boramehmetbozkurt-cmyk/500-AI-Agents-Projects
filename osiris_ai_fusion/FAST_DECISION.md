# Fast Decision Layer

ORBYTHRA can use Jev, or another schema-compatible System-One service, as a fast
routing adviser before the slower planning model. It is deliberately not an
authorization service and never receives evidence, memory, tenant credentials,
wallet secrets, private keys, or tool results.

## Boundary

1. ORBYTHRA computes the deterministic read-only candidate set.
2. The fast service returns `allow`, `deny`, or `escalate`, confidence/risk scores,
   workload flags, and an optional subset of those candidates.
3. Unknown tools invalidate the response and trigger the deterministic fallback.
4. SEAL independently authorizes the final tool list immediately before execution.
5. Effect verification and signed receipts remain inside ORBYTHRA.

The invariant remains: **no SEAL authorization, no tool execution**.

## Endpoint contract

Set `FAST_DECISION_ENABLED=true`, `FAST_DECISION_BASE_URL`, and optionally the
remaining `FAST_DECISION_*` variables documented in `.env.example`. ORBYTHRA sends
a POST to `FAST_DECISION_PATH`. The response may be the decision object directly
or wrapped as `{ "decision": { ... } }`.

The adapter is vendor-neutral because a stable public Jev endpoint/package contract
has not been pinned in this repository. Production deployment must point it at a
verified vendor endpoint or an internal adapter and must keep the API key in the
hosting secret store.

## Failure behavior

Timeouts, invalid JSON/schema, redirects, HTTP errors, or any attempted capability
expansion fall back to deterministic read-only routing. A valid explicit `deny`
fails closed. The slow planner is used for escalation, low confidence, or tasks the
decision says require reasoning.
