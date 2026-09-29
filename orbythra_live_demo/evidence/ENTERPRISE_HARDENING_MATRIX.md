# ORBYTHRA Enterprise Hardening Matrix

Date: 2026-09-29
Status: owner-side readiness matrix; completion requires evidence attached to an exact release.

| Domain | Minimum control | Evidence required | Gate |
|---|---|---|---|
| Release control | Immutable release/snapshot + commit mapping | release manifest, commit, deployment id | Required |
| Configuration | Declared enabled providers/tools/features | config inventory without secrets | Required |
| Secrets | No secrets in client/logs/repo; backend-only secret handling | secret scan + runtime inspection | Required |
| Authentication | Identity established for protected areas | auth test evidence | If enabled |
| Authorization | Object/tenant/resource checks on every protected action | positive/negative authorization tests | Required where protected state exists |
| Tenant isolation | No cross-tenant read/write/memory leakage | isolation test suite | Required where multi-tenant |
| Input validation | Structured validation at trust boundaries | negative tests | Required |
| Outbound requests | SSRF/allowlist/scheme protections where applicable | controlled SSRF tests | Required where outbound fetch exists |
| Prompt injection | Retrieved content cannot override policy/authorization | injection challenge set | Required for AI retrieval flows |
| Tool/connector safety | Explicit approval for state-changing effects | approval/effect mismatch tests | Required where connectors exist |
| Replay protection | Duplicate/stale actions rejected | replay test evidence | Required where state changes exist |
| Evidence integrity | Claim/source lineage and integrity metadata retained | trace artifacts | Required |
| Uncertainty | Missing/conflicting/stale evidence surfaced | abstention/escalation tests | Required |
| Observability | Request/run ids, failure classes, provider/runtime events | logs/telemetry sample | Required |
| Failure taxonomy | Capability vs provider/runtime/load/harness separated | classified benchmark report | Required |
| Reliability | timeout, retry/fail-soft, 429/quota behavior defined | fault-injection evidence | Required |
| Load/performance | Load tests separated from capability scoring | load report | Before scale claims |
| Dependency risk | Dependency audit/SBOM or equivalent inventory | audit artifact | Required for external review |
| Backup/recovery | Recovery objectives defined for persisted critical state | recovery test or documented N/A | If persistent critical state |
| Privacy/data lifecycle | Retention/deletion/logging boundaries defined | data-flow/lifecycle record | Required for enterprise data |
| Change control | Later releases do not inherit validation silently | retest/change-control procedure | Required |
| Incident handling | Severity, owner, containment and closure path | incident playbook | Required before enterprise pilot |
| External validation | Independent report tied to exact release | evaluator report | External gate |

## Readiness labels

- **EVIDENCED** — control exists and objective evidence is attached to the exact release.
- **IMPLEMENTED / UNVERIFIED** — control is represented but independent or complete evidence is missing.
- **PLANNED** — target-state control only.
- **N/A** — not applicable to the frozen evaluation scope, with rationale.

No control should be marked EVIDENCED solely because it is described in documentation.

## Release decision rule

An enterprise pilot release should not be described as enterprise-ready while a Critical security/authorization/tenant-isolation finding is open, or while a material engineering output cannot meet the agreed evidence/traceability gate.
