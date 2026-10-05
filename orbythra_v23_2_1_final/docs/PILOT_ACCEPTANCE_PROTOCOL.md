# ORBYTHRA Pilot Acceptance Protocol

The purpose of this protocol is to prevent post-hoc success criteria.

## Before a pilot run

Each scenario must define:

- `scenario_id`
- user/engineering question
- claim set
- bound evidence IDs
- freshness requirement where relevant
- support and authority thresholds
- expected disposition (`ANSWER` or `ABSTAIN_OR_QUALIFY`)
- minimum evidence-gate pass rate
- maximum guarded-claim count
- whether the engineering envelope must be `READY_FOR_EVIDENCE`

## During execution

Use `POST /v1/pilot/run`. The service computes:

- adaptive plan
- evidence verdicts
- aggregate gate pass rate
- engineering envelope when supplied
- acceptance result and explicit failure reasons

The request and result are persisted together. Audit records include request ID, workspace, action and outcome.

## Negative controls

A credible evaluation must include cases that should fail or abstain:

- missing evidence
- stale evidence for time-sensitive claims
- low-authority evidence
- contradictory evidence
- incomplete engineering inputs
- unauthorized workspace access

Success means correct behavior against the pre-declared expectation, not simply returning `ANSWER`.

## Release acceptance

A release is pilot-ready only when:

1. CI is green.
2. Negative controls behave as expected.
3. No real credentials are committed to the repository.
4. The deployed release is tied to a commit SHA.
5. Pilot results are reproducible from stored inputs and evidence identifiers.
