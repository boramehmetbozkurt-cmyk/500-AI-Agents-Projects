# ORBYTHRA Production Evidence

## Live deployment

- Public buyer demo: https://orbythra-buyer-demo-pns9l3.v2.appdeploy.ai/
- AppDeploy app id: `orbythra-buyer-demo-pns9l3`
- Production release: `v2`
- AppDeploy snapshot/version: `1789502718462`
- Production timestamp: 2026-09-15 23:05:18 Europe/Istanbul
- Architecture: frontend + backend
- Deployment state at release: `ready`
- QA snapshot at release: frontend errors `0`, backend errors `0`, network errors `0`

## Release capabilities

1. Turkish and English questions use the same search interface.
2. Public evidence retrieval remains available through Wikipedia TR/EN, OpenAlex and GDELT routing.
3. A backend AI synthesis layer produces a non-empty same-language answer when public evidence is sparse.
4. The answer engine is instructed to distinguish current/source-backed facts from general model knowledge when freshness or precision matters.
5. Automotive and engineering questions account for model-year, market and trim variability rather than assuming one configuration.
6. Technical visual search is included through Wikimedia Commons and can show photographs, components, schematics or cutaway-style technical imagery when available.
7. AI synthesis failure degrades to the public-source fallback instead of leaving the user with a blank result.
8. The UI exposes confidence, routing, sources, claims/findings, timeline signals and technical visuals.

## Acceptance benchmark

The public benchmark suite is stored at `evidence/benchmark_cases.json` and includes Turkish/English automotive, engineering, science, history, world, current-information, medical-information, software/API, ambiguity and no-source fallback cases.

Benchmark SHA-256: `b09e23504123ee2fb1ae10c958a2afe0896458989aea4a44279560c4c8e84b24`

The first regression case is the previously failing query:

`Cupra Formentor motoru nedir?`

Expected behavior: non-empty Turkish answer, explicit model-year/market/trim variability where relevant, and a completed technical-visual state.

## External validation handoff

For Radianode, InterClin AI and Synack, the reference deployment is AppDeploy `v2` / snapshot `1789502718462`. Controlled evaluation should follow NDA -> scoped evaluation package -> written findings/report -> remediation -> retest. Source code, secrets and sensitive implementation details should not be sent in open email.

## Evidence limitations

This file records deployment and release evidence available from the production deployment tooling. It does not claim that Radianode, InterClin AI or Synack have completed validation yet, and it does not represent a cryptographic code-signing signature. Their independent reports remain separate evidence once issued.
