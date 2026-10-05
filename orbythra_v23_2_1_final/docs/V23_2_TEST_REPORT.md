# ORBYTHRA V23.2 Test Report

Date: 2026-10-05

## Focused V23/V23.1/V23.2 regression

Command scope:
- `tests/test_v23_verifiable_general_agent.py`
- `tests/test_v23_1_search_and_attachments.py`
- `tests/test_v23_2_verifiable_agent.py`

Result: **18 passed, 1 skipped**.

The skipped case is the opt-in live keyless web-search smoke test, which requires `ORBYTHRA_LIVE_SEARCH_TEST=1` and live network access.

## Broader regression

All tests except `tests/test_v22_crypto_hardening.py` were executed.

Result: **869 passed, 1 skipped**.

## Environment limitation

The execution environment used for this package contains `cryptography 46.0.4`, while ORBYTHRA declares `cryptography>=50.0.0,<51.0` because V22 uses ML-DSA, ML-KEM and HPKE APIs introduced in the required dependency line. The V22 PQ-crypto hardening test therefore could not be executed in this environment. A test-only shim was used locally to make unavailable PQ symbols fail closed while exercising the non-PQ application paths; that shim is **not included in the project source**.

The V22 PQ cryptographic gate must be run in CI or another environment with the repository's declared dependency set before making a full-green release claim.

## Static checks

- `python -m compileall -q app scripts tests`: passed.
- release evidence manifest generation: passed with `PYTHONPATH=.`.
- Bandit was not installed in the execution environment, so the repository's GitHub V23.2 gate retains the Bandit security-scan step for CI.
