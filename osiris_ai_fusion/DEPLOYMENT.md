# OSIRIS FUSION v1 — Deployment Guide

This guide covers local development, Docker, Render and Railway deployment for the production-ready `osiris_ai_fusion` service.

## 1. Local setup

### Windows PowerShell

```powershell
cd osiris_ai_fusion
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Install Ollama separately, then pull the default local model:

```powershell
ollama pull qwen3:4b
```

Start the API and Command Center:

```powershell
uvicorn app:app --host 0.0.0.0 --port 8787
```

Open `http://localhost:8787/`.

### Linux / macOS

```bash
cd osiris_ai_fusion
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
ollama pull qwen3:4b
uvicorn app:app --host 0.0.0.0 --port 8787
```

## 2. Required production environment

At minimum, set:

```text
APP_ENV=production
OSIRIS_FUSION_API_KEY=<strong-random-secret>
UI_ENABLED=true
FUSION_STORE_PATH=<persistent-path>/fusion.sqlite3
SEAL_REPLAY_DB=<persistent-path>/seal-replay.sqlite3
```

Recommended production security:

```text
SEAL_ED25519_PRIVATE_KEY_B64=<32-byte-ed25519-private-key-base64>
REQUIRE_SIGNED_RECEIPTS=true
```

Never commit API keys, model-provider tokens, SEAL private keys, or production `.env` files to Git.

## 3. Model provider in production

The Docker image deliberately does **not** bundle Ollama or Qwen model weights. A hosted deployment must use one of these two patterns:

### External Ollama

```text
OLLAMA_BASE_URL=https://<trusted-ollama-host>
LLM_MODEL=qwen3:4b
AI_PLANNER_ENABLED=true
```

### OpenAI-compatible fallback

```text
LLM_FALLBACK_BASE_URL=https://<provider>/v1
LLM_FALLBACK_API_KEY=<secret>
LLM_FALLBACK_MODEL=<model-name>
AI_PLANNER_ENABLED=true
```

If no model endpoint is available, evidence collection can still run, but OSIRIS FUSION intentionally refuses to fabricate a synthesized factual conclusion.

## 4. Docker

From `osiris_ai_fusion/`:

```bash
docker build -t osiris-fusion:1.0.0 .
docker run --rm -p 8787:8787 \
  -e APP_ENV=production \
  -e OSIRIS_FUSION_API_KEY='replace-me' \
  -e UI_ENABLED=true \
  -v osiris-fusion-data:/data \
  -e FUSION_STORE_PATH=/data/fusion.sqlite3 \
  -e SEAL_REPLAY_DB=/data/seal-replay.sqlite3 \
  osiris-fusion:1.0.0
```

The container runs as non-root user UID `10001` and exposes `/health` for health checks.

## 5. Render

The repository root contains `render.yaml`.

Deployment flow:

1. Create a Render Blueprint from this repository.
2. `render.yaml` tracks `main`, which is where v1 now lives.
3. Keep the persistent disk enabled for the SQLite investigation store and replay database.
4. Set the model-provider secrets in Render; do not put them in Git.
5. Set `SEAL_ED25519_PRIVATE_KEY_B64` and switch `REQUIRE_SIGNED_RECEIPTS=true` when signed receipts are required.
6. After deployment, verify `/health`, `/ready`, `/tools`, `/providers`, and the Command Center root page.

The image reads `PORT` at start-up and falls back to `8787`, so Render, Railway, Fly
and Cloud Run all work from the same image with no start-command override. Set
`WEB_CONCURRENCY` to raise the uvicorn worker count; the replay guard and store are
SQLite, so see the scale-out note in `ARCHITECTURE.md` before going past one worker
per persistent disk.

## 6. Railway

`railway.json` and `Procfile` are included in `osiris_ai_fusion/`.

Recommended service configuration:

- service root: `osiris_ai_fusion`
- builder: Dockerfile
- health check: `/health`
- attach a persistent volume for `FUSION_STORE_PATH` and `SEAL_REPLAY_DB`
- configure all secrets as Railway variables
- connect an external Ollama endpoint or an OpenAI-compatible fallback

Example persistent variables:

```text
FUSION_STORE_PATH=/data/fusion.sqlite3
SEAL_REPLAY_DB=/data/seal-replay.sqlite3
```

## 6b. Continuous deployment

`.github/workflows/deploy.yml` redeploys on every push to `main` that touches
`osiris_ai_fusion/**` or `render.yaml`, and can also be run manually from the
Actions tab.

It is deliberately provider-agnostic: it POSTs to a deploy-hook URL rather than
holding a hosting API key, so this repository never stores provider credentials.

Configure two things in **Settings → Secrets and variables → Actions**:

| Name | Kind | Required | Value |
| --- | --- | --- | --- |
| `DEPLOY_HOOK_URL` | Secret | yes, to deploy at all | Render: *Service → Settings → Deploy Hook*. Railway: a deployment webhook URL. Any endpoint that redeploys on POST works. |
| `DEPLOY_HEALTH_URL` | Variable | optional | Public `/health` URL, e.g. `https://orbythra.onrender.com/health`. |

Behaviour worth knowing before you rely on it:

- With no `DEPLOY_HOOK_URL` the job explains what is missing and **succeeds**, so a
  fork is never blocked by a deployment it cannot perform.
- A hook that answers 4xx/5xx **fails the build**. A deploy that silently reports
  success is the worst failure mode here, so the check is explicit rather than
  relying on the runner's shell flags.
- A deploy hook returning 200 only means the build was *queued*. When
  `DEPLOY_HEALTH_URL` is set the workflow then polls `/health` for up to ten
  minutes and only reports success once the new revision actually serves traffic.

## 7. Commercial source policy

For a commercial deployment:

```text
COMMERCIAL_MODE=true
STRICT_COMMERCIAL_SOURCES=true
```

Providers that require a commercial license are blocked unless explicitly listed in:

```text
LICENSED_PROVIDERS=provider_a,provider_b
```

Do not disable the source-policy gate merely to make a provider available. Obtain the required data license first.

## 8. Production verification checklist

Before exposing the service publicly, confirm all of the following:

- GitHub CI passes: dependency install, `pip check`, Ruff, pytest, Python compile, browser JS syntax, FastAPI import.
- Security workflow passes: `pip-audit`, Docker build, non-root UID check.
- `APP_ENV=production` and a strong `OSIRIS_FUSION_API_KEY` are configured.
- Persistent storage is mounted.
- Secrets are stored only in the hosting provider's secret store.
- Active scanner/sweep routes remain excluded from autonomous execution.
- Commercial source policy is enabled for commercial deployments.
- Model endpoint health is verified through `/ready`.
- Signed SEAL receipts are enabled where auditability is required.
- TLS is terminated by the hosting provider or a trusted reverse proxy.

## 9. Smoke test

After deployment:

```bash
curl https://<host>/health
curl -H "X-API-Key: <key>" https://<host>/tools
curl -H "X-API-Key: <key>" https://<host>/providers
```

Then open the root Command Center in a browser, set the API key under **ACCESS**, and run a read-only investigation.
