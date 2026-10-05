from pathlib import Path

DEMO_KEY = "orbythra-demo-local-key-change-before-sharing"


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_demo_frontend_receives_local_auth_without_leaking_to_production() -> None:
    demo = _read("docker-compose.demo.yml")
    production = _read("docker-compose.production.yml")
    dockerfile = _read("client/Dockerfile")
    api_js = _read("client/src/api.js")
    nginx = _read("client/nginx.conf")

    assert f"ORBYTHRA_DEMO_PROXY_KEY: {DEMO_KEY}" in demo
    assert "${ORBYTHRA_DEMO_HOST:-127.0.0.1}" in demo
    assert "VITE_DEMO_API_KEY" not in dockerfile
    assert "/etc/nginx/templates/default.conf.template" in dockerfile
    assert "VITE_DEMO_API_KEY" not in api_js
    assert "DEMO_API_KEY" not in api_js
    assert DEMO_KEY not in api_js
    assert 'headers["X-API-Key"]=effectiveApiKey' in api_js
    assert 'headers["X-Workspace-ID"]=effectiveWorkspace' in api_js
    assert "proxy_set_header X-API-Key $orbythra_api_key;" in nginx
    assert "proxy_set_header X-Workspace-ID $http_x_workspace_id;" in nginx
    assert "VITE_DEMO_API_KEY" not in production
    assert DEMO_KEY not in production

    assert '"" "${ORBYTHRA_DEMO_PROXY_KEY}";' in nginx
    assert "ORBYTHRA_DEMO_PROXY_KEY" not in production


def test_production_compose_supports_oidc_without_forcing_static_api_keys() -> None:
    production = _read("docker-compose.production.yml")

    assert "ORBYTHRA_API_KEYS: ${ORBYTHRA_API_KEYS:-}" in production
    assert "ORBYTHRA_API_KEYS:?set ORBYTHRA_API_KEYS" not in production
    assert "ORBYTHRA_OIDC_ISSUER: ${ORBYTHRA_OIDC_ISSUER:-}" in production
    assert "ORBYTHRA_OIDC_AUDIENCE: ${ORBYTHRA_OIDC_AUDIENCE:-}" in production
    assert "ORBYTHRA_OIDC_JWKS_URL: ${ORBYTHRA_OIDC_JWKS_URL:-}" in production
    assert "ORBYTHRA_OIDC_JWKS_JSON: ${ORBYTHRA_OIDC_JWKS_JSON:-}" in production
    assert "ORBYTHRA_OIDC_WORKSPACE_CLAIM: ${ORBYTHRA_OIDC_WORKSPACE_CLAIM:-orbythra_workspace}" in production
    assert "ORBYTHRA_OIDC_ROLE_CLAIM: ${ORBYTHRA_OIDC_ROLE_CLAIM:-orbythra_role}" in production
