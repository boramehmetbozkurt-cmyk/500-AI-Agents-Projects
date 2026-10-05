# ORBYTHRA V23.2 General Query Hotfix

Purpose: prevent ordinary static questions (for example `BTC nedir?` / `What is Bitcoin?`) from disappearing merely because auxiliary web evidence could not be directly fetched.

Behavior after this hotfix:

- AUTO + static/general question: AI answer remains visible. Web search may enrich evidence. If evidence is insufficient, status is `REVIEW`, not a blank/blocked answer.
- AUTO + person/profile lookup, current/time-sensitive data, live prices, or high-risk questions: strict external-evidence mode remains fail-closed.
- Explicit `WEB_RESEARCH`: remains fail-closed when direct evidence cannot be obtained.
- Search snippets, including LinkedIn/Google snippets, remain `DISCOVERY_ONLY` and are never promoted to evidence or injected into the answer-generation source pack.
- Contradiction, low-confidence, release-binding, replay, and other non-evidence security failures remain blocking failures.

This change separates **answer availability** from **verified release status** without weakening the evidence boundary.
