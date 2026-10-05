# ORBYTHRA V23.2.2 Multilingual Final

This patch adds multilingual user experience and response-language routing without weakening the existing evidence gates.

## Interface languages
- English (default)
- Türkçe
- Deutsch
- Français
- Español
- Italiano
- العربية (RTL)

The interface language selector is persisted in local storage. Arabic enables RTL layout. User-generated content, evidence excerpts, source titles, code, URLs, and audit payloads are excluded from UI phrase translation.

## Answer language
The unified-answer backend detects the query language across the seven supported languages and instructs the configured LLM provider to reply in that language. URLs, code, identifiers, and quoted source names are preserved.

Examples:
- `What is Bitcoin?` -> English
- `BTC nedir?` -> Turkish
- `Was ist Bitcoin?` -> German
- `Qu'est-ce que Bitcoin ?` -> French
- `¿Qué es Bitcoin?` -> Spanish
- `Che cos'è Bitcoin?` -> Italian
- `ما هو البيتكوين؟` -> Arabic

## Validation
- Full backend regression: 892 passed, 3 skipped (with a nonzero test release SHA, matching a normal git checkout).
- Multilingual focused regression: 20 passed.
- `client/src/ui_i18n.js` passed Node syntax validation.
- Vite production build could not be completed in this sandbox because npm dependency installation timed out; GitHub/CI or a normal development machine should run `npm ci && npm run build` before deployment.