# ORBYTHRA Unified Answer Console

The Unified Answer Console is the default browser experience for the local demo. A normal user writes one question and ORBYTHRA handles planning, provider routing, source collection, claim verification and output assurance.

## Local start

```bash
git checkout main
git pull
docker compose -f docker-compose.demo.yml down --remove-orphans
docker compose -f docker-compose.demo.yml up --build --force-recreate
```

Open `http://127.0.0.1:8080`.

The local demo API key is injected only into the demo frontend build. Google and model-provider secrets remain server-side and are never compiled into the browser bundle.

## Modes

- `AUTO`: chooses web research for current/factual questions when a search provider is available, otherwise uses the model provider.
- `WEB_RESEARCH`: requires Google Programmable Search or the configured ORBYTHRA evidence-provider search adapter.
- `AI_ANALYSIS`: uses the governed model provider. When search is configured it can also collect external evidence before assurance.

## Google search

Set these variables in the shell or `.env` used by Docker Compose:

```text
GOOGLE_SEARCH_API_KEY=...
GOOGLE_SEARCH_ENGINE_ID=...
```

The adapter uses Google Programmable Search for discovery. Search snippets are not treated as direct proof. ORBYTHRA attempts to fetch the underlying public HTTPS source through the hardened V5.1 web-evidence retrieval controls before a result can qualify as direct evidence.

## AI/model provider

ORBYTHRA keeps the existing governed HTTP model-provider contract. Configure:

```text
ORBYTHRA_LLM_PROVIDER_URL=https://your-provider.example
ORBYTHRA_LLM_PROVIDER_TOKEN=...
ORBYTHRA_DEFAULT_MODEL_ID=default
```

ORBYTHRA sends:

```http
POST /generate
Content-Type: application/json
Authorization: Bearer <token>   # when configured
```

```json
{
  "model_id": "default",
  "prompt": "..."
}
```

The provider must return:

```json
{
  "output": "model answer",
  "confidence": 0.91
}
```

`confidence` must be between 0 and 1. Invalid or missing provider output fails closed.

## Evidence provider fallback

When Google is not configured, an existing ORBYTHRA evidence provider may expose:

```http
POST /search
```

with:

```json
{
  "query": "...",
  "limit": 5
}
```

and a response shaped as:

```json
{
  "results": [
    {
      "source_id": "source-1",
      "title": "...",
      "url": "https://...",
      "publisher": "...",
      "snippet": "...",
      "full_text": "optional already-retrieved source text",
      "published_at": "optional timestamp",
      "source_type": "provider"
    }
  ]
}
```

## Verification statuses

- `PASS`: model-output assurance passes, the v1 evidence gate returns `ANSWER`, and direct source evidence is present.
- `REVIEW`: a review-only gate such as required human approval prevents release.
- `BLOCKED`: an answer draft exists but required evidence/assurance gates did not pass. The UI never labels it verified.
- `ERROR`: infrastructure/configuration/provider/authentication/release errors. These are not presented as evidence-gate failures.

The system never disables gates to make the demo appear successful.

## Automatic security metadata

The browser does not ask normal users for request IDs, nonces, release SHA or configuration hashes. The backend creates a new request ID and cryptographically strong nonce on every run, binds the assurance request to `ORBYTHRA_RELEASE_SHA`, and returns only the nonce hash in the receipt.

## Advanced API Explorer

The full OpenAPI endpoint console remains available at `Advanced / API Explorer`. It is intended for developers and evaluators; normal users do not need to construct endpoint payloads manually.
