# Operations Runbook

## Readiness

- `/health` proves the API process is alive.
- `/ready` checks OSIRIS and Ollama dependencies.
- `/tools` exposes the current autonomous read-only registry.

A degraded `/ready` result should prevent new long-running investigations at the gateway while keeping
the process available for diagnostics.

## Incident priorities

1. Authorization/replay/signature failure: stop affected investigation and preserve logs/receipt.
2. Evidence integrity mismatch: mark case unverified; do not publish automated conclusions.
3. OSIRIS dependency outage: return degraded state; do not fabricate substitute data.
4. LLM outage: retain collected evidence and return model-unavailable status.
5. Rate-limit abuse: block at gateway and rotate exposed API credentials if necessary.

## Release gate

A production release is allowed only when:

- `ruff check .` passes.
- `pytest -q` passes.
- `python -m compileall -q .` passes.
- No secrets exist in repository history.
- Production config requires API auth and signed receipts.
- Dependency and container vulnerability scans have no unresolved critical findings.
- Backup/restore for case metadata and signing-key recovery procedures are documented and tested.
