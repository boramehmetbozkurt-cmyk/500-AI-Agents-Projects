# ORBYTHRA Final Web Evidence Patch — 2026-10-05

This patch hardens the unified answer pipeline so discovery results cannot be mistaken for verified evidence.

## Fixed

- Search snippets (Google / SerpAPI / DuckDuckGo / Bing / generic provider) are discovery metadata only.
- Provider-supplied `full_text` is no longer trusted as direct evidence for web results.
- A web result becomes direct evidence only after ORBYTHRA independently fetches the public HTTPS source through the web-evidence controls.
- Failed/unavailable direct fetches are marked `DISCOVERY_ONLY`; their snippets are not exposed as evidence.
- Discovery-only content is excluded from the model SOURCE PACK.
- WEB_RESEARCH fails closed when there is no directly fetched evidence: no LLM answer or claim text is released.
- If claim/evidence assurance does not PASS, web-derived answer text and claims are withheld from the API, UI and Excel export.
- Added explicit `evidence_status` (`DIRECT_EVIDENCE`, `DISCOVERY_ONLY`, `USER_FILE`) to source records.
- Split general factual routing from true time-sensitive verification, preventing every factual question from being treated as freshness-sensitive.
- Added regression tests covering LinkedIn-style snippet leakage and untrusted provider `full_text`.
- Added graceful fail-closed behavior when the installed `cryptography` package lacks optional PQC/HPKE primitives; classical cryptography remains importable while PQC operations report `pqc_backend_unavailable`.
- Fixed a version-policy bug so an older v2 envelope issued with PQC off remains readable after a later runtime PQC policy upgrade.

## Verification

Backend full test suite: **887 passed, 3 skipped**.

Targeted web/evidence/assurance/endpoint regression suite: **25 passed, 1 skipped**.

Python compile check (`app` + `tests`): PASS.

Frontend source was patched to label discovery-only records separately and to never render discovery snippets as evidence. A local production frontend build was not executed in this environment because `node_modules` is not present and external package installation is unavailable.
