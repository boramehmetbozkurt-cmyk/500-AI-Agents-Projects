# ORBYTHRA V21 Release Criteria

V21 is a release candidate only when the following internal gates pass for the exact candidate commit.

## Required internal gates

- Python production composition compiles.
- All V21 focused regression tests pass.
- Existing observability-ledger regression tests pass.
- V21 OpenAPI routes are present.
- Dataset versions are immutable/hash-bound.
- Prompt versions are immutable/hash-bound.
- Experiment inputs bind the exact dataset version, prompt version and model.
- Baseline/candidate comparison produces deterministic hashes.
- Incoming W3C trace context is propagated with a fresh server span id.
- Trace spans can bind evidence, policy and outcome-receipt SHA-256 references.
- Sensitive V21 payloads use the existing encrypted vault path.
- V21 modules pass the configured high-severity Bandit gate.
- Claim-boundary assertions remain explicit.

## Required external gates before strong production/security claims

The following remain external evidence requirements and are not satisfied by CI:

- independent penetration test;
- independent cryptographic review;
- independent product/evaluation validation;
- production load/reliability evidence under the target deployment;
- customer acceptance evidence;
- legal/regulatory certification where required.

## Release position

Passing the V21 gate means the candidate has an internally reproducible assurance/observability baseline. It does not mean ORBYTHRA has surpassed competitors in deployment maturity, ecosystem breadth or independently verified safety.
