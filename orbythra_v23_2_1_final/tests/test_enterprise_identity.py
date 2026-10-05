from __future__ import annotations

import base64
import json
import time
from dataclasses import replace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import app.security as security
from app.api import app
from app.config import SETTINGS
from app.identity import OIDCValidationError, verify_oidc_token

client = TestClient(app)


def _b64u_int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fixture():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_numbers()
    kid = "test-rsa-1"
    jwks = {"keys": [{"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": _b64u_int(public.n), "e": _b64u_int(public.e)}]}
    settings = replace(
        SETTINGS,
        oidc_issuer="https://idp.example.test/tenant",
        oidc_audience="orbythra-enterprise",
        oidc_jwks_url=None,
        oidc_jwks_json=json.dumps(jwks),
        oidc_workspace_claim="orbythra_workspace",
        oidc_role_claim="orbythra_role",
    )
    now = int(time.time())
    claims = {
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "sub": "user-123",
        "iat": now - 5,
        "exp": now + 300,
        "orbythra_workspace": "enterprise-sso",
        "orbythra_role": "evaluator",
    }
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": kid})
    return private, jwks, settings, token


def test_oidc_verifies_signed_enterprise_identity():
    _, jwks, settings, token = _fixture()
    identity = verify_oidc_token(token, settings, jwks_override=jwks)
    assert identity.subject == "user-123"
    assert identity.workspace_id == "enterprise-sso"
    assert identity.role == "evaluator"


def test_oidc_rejects_wrong_audience():
    private, jwks, settings, _ = _fixture()
    now = int(time.time())
    token = jwt.encode({"iss": settings.oidc_issuer, "aud": "wrong", "sub": "user-123", "iat": now, "exp": now + 300, "orbythra_workspace": "enterprise-sso", "orbythra_role": "viewer"}, private, algorithm="RS256", headers={"kid": "test-rsa-1"})
    try:
        verify_oidc_token(token, settings, jwks_override=jwks)
        assert False, "expected OIDCValidationError"
    except OIDCValidationError as exc:
        assert str(exc) == "oidc_token_invalid"


def test_oidc_rejects_missing_workspace_claim():
    private, jwks, settings, _ = _fixture()
    now = int(time.time())
    token = jwt.encode({"iss": settings.oidc_issuer, "aud": settings.oidc_audience, "sub": "user-123", "iat": now, "exp": now + 300, "orbythra_role": "viewer"}, private, algorithm="RS256", headers={"kid": "test-rsa-1"})
    try:
        verify_oidc_token(token, settings, jwks_override=jwks)
        assert False, "expected OIDCValidationError"
    except OIDCValidationError as exc:
        assert str(exc) == "oidc_workspace_claim_required"


def test_oidc_bearer_auth_drives_workspace_and_role(monkeypatch):
    _, _, settings, token = _fixture()
    monkeypatch.setattr(security, "SETTINGS", settings)
    response = client.get("/v1/metrics", headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": "must-not-override-claim"})
    assert response.status_code == 200, response.text
    assert response.json()["workspace_id"] == "enterprise-sso"


def test_oidc_viewer_cannot_access_evaluator_endpoint(monkeypatch):
    private, jwks, settings, _ = _fixture()
    now = int(time.time())
    viewer = jwt.encode({"iss": settings.oidc_issuer, "aud": settings.oidc_audience, "sub": "viewer-1", "iat": now, "exp": now + 300, "orbythra_workspace": "enterprise-sso", "orbythra_role": "viewer"}, private, algorithm="RS256", headers={"kid": jwks["keys"][0]["kid"]})
    monkeypatch.setattr(security, "SETTINGS", settings)
    response = client.get("/v1/metrics", headers={"Authorization": f"Bearer {viewer}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient_role"
