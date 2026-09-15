# ORBYTHRA — One-Click Demo

This branch is the zero-secret, one-click public demo entrypoint for ORBYTHRA.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/boramehmetbozkurt-cmyk/500-AI-Agents-Projects/tree/orbythra-one-click-deploy)

## What this deploys

- ORBYTHRA Universal Search public interface
- AUTO / WEB / SCIENCE / WORLD / ENGINEERING modes
- source cards, confidence/routing, claims/findings and timeline signals
- backendless public-source fallback using the demo's supported public endpoints
- no API key or secret required for the initial demo deployment

This one-click branch intentionally deploys the buyer-safe/public demo surface rather than the full production backend. The full backend remains in `osiris_ai_fusion/` and can be attached later from the **Backend bağla** control in the UI.

## After clicking

1. Sign in to Render if prompted.
2. Review the single static service `orbythra-demo`.
3. Approve the Blueprint.
4. Open the generated `*.onrender.com` address.

No repository secret is required for this demo deployment.
