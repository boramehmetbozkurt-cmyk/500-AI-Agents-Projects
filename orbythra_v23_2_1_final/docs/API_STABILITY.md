# ORBYTHRA API Stability Policy

## Versioning

- `/v1/*` is the stable major API namespace.
- Additive response fields and new endpoints may be introduced without changing the major version.
- Removing or renaming fields, changing required semantics, or weakening security defaults requires a new major version unless a documented compatibility layer is retained.

## Deprecation

A deprecated v1 surface should provide:

1. replacement endpoint or field;
2. migration note;
3. explicit deprecation date;
4. telemetry/audit visibility where practical;
5. a compatibility period appropriate for enterprise integrations.

## Security compatibility

Security fixes may tighten validation without waiting for a new major version when preserving the old behavior would create material risk. Such changes must be documented in release notes.

## Stable behavior expectations

- workspace isolation is fail-closed;
- authorization failures do not fall back to weaker roles;
- policy `BLOCK` prevents provider invocation;
- policy `REVIEW` prevents provider invocation until approval state changes;
- evidence-gate guarded outcomes do not silently become unqualified `ANSWER`;
- replay protection remains fail-closed;
- production crypto does not silently start without configured key material;
- external-validation claims are never synthesized from internal tests.
