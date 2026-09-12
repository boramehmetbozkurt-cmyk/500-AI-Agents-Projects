# OSIRIS Fusion Public SaaS

Version 1.3 adds a self-service multi-tenant SaaS layer in front of the existing passive/read-only research engine.

## What is public

`/` is the public landing, signup, login, plan and account surface. `/app` is the authenticated research command center. API documentation remains available at `/docs`.

The SaaS layer adds:

- self-service email/password signup and login
- tenant/workspace isolation enforced by authenticated identity, never by caller-supplied `workspace_id`
- bearer sessions stored as SHA-256 digests with expiration
- tenant API keys stored only as hashes; the raw key is shown once
- Free, Pro and Team usage plans with server-enforced investigation, watchlist and API-key limits
- usage reporting per billing month
- Stripe Checkout and signed webhook support without storing Stripe secrets in the repository
- administrator/bootstrap API-key compatibility for operations and migrations

## Default plan limits

| Plan | Investigations / month | Watchlists | API keys | UI reference price |
| --- | ---: | ---: | ---: | ---: |
| Free | 50 | 3 | 2 | $0 |
| Pro | 2,000 | 50 | 10 | $29 / month |
| Team | 20,000 | 250 | 50 | $99 / month |

Prices in the UI are product defaults, not a Stripe charge until matching Stripe Price IDs are configured.

## Authentication

Browser account sessions use:

```text
Authorization: Bearer <session-token>
```

API clients and the command center use:

```text
X-API-Key: osf_live_...
```

Passwords use `hashlib.scrypt` with a random per-user salt. Raw session tokens and tenant API keys are never persisted. Only SHA-256 token/key digests are stored.

## Tenant isolation

Existing case, investigation, watchlist and alert storage already carries a `workspace_id`. SaaS routes ignore any caller-provided workspace and replace it with the authenticated tenant ID before reading or writing data.

An API key from tenant A cannot select tenant B by sending a different workspace ID.

## Stripe billing

Set all of the following together:

```text
SAAS_BASE_URL=https://your-public-domain.example
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_TEAM=price_...
```

Configure the Stripe webhook endpoint as:

```text
POST https://your-public-domain.example/saas/billing/webhook
```

The backend validates the `Stripe-Signature` timestamp and HMAC before applying plan changes.

## Production persistence

The current application and SaaS metadata share the existing SQLite database. This is suitable for a single application instance when `FUSION_STORE_PATH` is placed on persistent storage and backups are enabled.

Before horizontal multi-instance scaling, migrate persistence to a managed transactional database or add a dedicated database adapter. Do not run multiple independent containers with ephemeral SQLite volumes and call that durable multi-tenant storage.

## Safety boundary

Public SaaS does not expand the autonomous tool boundary. Active scanning, exploitation, credential access, intrusive surveillance and facial tracking remain excluded. External research stays passive/read-only and evidence-bound through the existing provider federation and SEAL effect-verification flow.
