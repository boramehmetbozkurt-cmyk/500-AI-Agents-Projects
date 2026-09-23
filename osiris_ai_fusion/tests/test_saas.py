from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from dataclasses import replace

import pytest

from saas import AuthContext, SaaSManager


def _stripe_event(manager, event_id, tenant_id, customer, *, paid="paid", kind="checkout.session.completed", status=None):
    obj = {
        "client_reference_id": tenant_id,
        "metadata": {"tenant_id": tenant_id, "plan": "pro"},
        "customer": customer,
        "mode": "subscription",
        "status": status or ("complete" if kind.startswith("checkout.") else "active"),
        "payment_status": paid,
    }
    payload = json.dumps({"id": event_id, "type": kind, "data": {"object": obj}}).encode()
    timestamp = int(time.time())
    signed = f"{timestamp}.".encode() + payload
    signature = hmac.new(b"test-webhook-secret", signed, hashlib.sha256).hexdigest()
    return manager.process_stripe_webhook(payload, f"t={timestamp},v1={signature}")


def test_stripe_checkout_entitlement_requires_payment_and_customer_binding(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    manager.settings = replace(manager.settings, stripe_webhook_secret="test-webhook-secret")
    one = manager.signup("one@example.com", "long-secure-password", "One", "One Inc")
    two = manager.signup("two@example.com", "long-secure-password", "Two", "Two Inc")
    first, second = one["tenant"]["id"], two["tenant"]["id"]

    assert _stripe_event(manager, "evt_unpaid", first, "cus_one", paid="unpaid")["updated"] is False
    assert manager.account(manager.authenticate(f"Bearer {one['token']}", None))["tenant"]["plan"] == "free"
    assert _stripe_event(manager, "evt_paid", first, "cus_one")["updated"] is True
    assert _stripe_event(manager, "evt_paid", first, "cus_one")["updated"] is False
    assert _stripe_event(manager, "evt_collision", second, "cus_one")["updated"] is False
    assert _stripe_event(manager, "evt_rebind", first, "cus_other")["updated"] is False
    assert manager.account(manager.authenticate(f"Bearer {two['token']}", None))["tenant"]["plan"] == "free"


def test_subscription_event_cannot_bind_customer_before_checkout(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    manager.settings = replace(manager.settings, stripe_webhook_secret="test-webhook-secret")
    created = manager.signup("owner@example.com", "long-secure-password", "Owner", "Acme")
    tenant = created["tenant"]["id"]
    assert _stripe_event(manager, "evt_sub", tenant, "cus_one", kind="customer.subscription.created")["updated"] is False
    assert _stripe_event(manager, "evt_checkout", tenant, "cus_one")["updated"] is True
    assert _stripe_event(manager, "evt_sub", tenant, "cus_one", kind="customer.subscription.created")["updated"] is True


def test_inactive_subscription_downgrades_entitlement(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    manager.settings = replace(manager.settings, stripe_webhook_secret="test-webhook-secret")
    created = manager.signup("owner@example.com", "long-secure-password", "Owner", "Acme")
    tenant = created["tenant"]["id"]
    _stripe_event(manager, "evt_checkout", tenant, "cus_one")
    _stripe_event(manager, "evt_past_due", tenant, "cus_one", kind="customer.subscription.updated", status="past_due")
    auth = manager.authenticate(f"Bearer {created['token']}", None)
    assert manager.account(auth)["tenant"]["plan"] == "free"


def test_signup_login_and_password_not_stored(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    created = manager.signup("Owner@Example.com", "long-secure-password", "Owner", "Acme")
    assert created["tenant"]["plan"] == "free"
    auth = manager.authenticate(f"Bearer {created['token']}", None)
    assert auth.tenant_id == created["tenant"]["id"]
    logged = manager.login("owner@example.com", "long-secure-password")
    assert logged["user"]["email"] == "owner@example.com"
    with sqlite3.connect(manager.path) as conn:
        row = conn.execute("SELECT password_hash, password_salt FROM saas_users").fetchone()
    assert row[0] != "long-secure-password"
    assert len(row[0]) == 64
    assert len(row[1]) == 32


def test_wrong_password_is_rejected(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    manager.signup("owner@example.com", "long-secure-password", "Owner", "Acme")
    with pytest.raises(PermissionError):
        manager.login("owner@example.com", "definitely-wrong-password")


def test_api_key_is_hashed_and_revocable(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    created = manager.signup("owner@example.com", "long-secure-password", "Owner", "Acme")
    auth = manager.authenticate(f"Bearer {created['token']}", None)
    api_key = manager.create_api_key(auth, "CLI")
    assert api_key["api_key"].startswith("orb_live_")
    via_key = manager.authenticate(None, api_key["api_key"])
    assert via_key.tenant_id == auth.tenant_id
    with sqlite3.connect(manager.path) as conn:
        stored = conn.execute(
            "SELECT key_hash FROM saas_api_keys WHERE id=?", (api_key["id"],)
        ).fetchone()[0]
    assert stored != api_key["api_key"]
    assert manager.revoke_api_key(auth, api_key["id"])
    with pytest.raises(PermissionError):
        manager.authenticate(None, api_key["api_key"])


def test_tenants_are_isolated_by_identity(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    one = manager.signup("one@example.com", "long-secure-password", "One", "One Inc")
    two = manager.signup("two@example.com", "long-secure-password", "Two", "Two Inc")
    a = manager.authenticate(f"Bearer {one['token']}", None)
    b = manager.authenticate(f"Bearer {two['token']}", None)
    assert a.tenant_id != b.tenant_id
    key = manager.create_api_key(a, "One")
    assert manager.authenticate(None, key["api_key"]).tenant_id == a.tenant_id


def test_free_monthly_quota_is_enforced(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    created = manager.signup("owner@example.com", "long-secure-password", "Owner", "Acme")
    auth = manager.authenticate(f"Bearer {created['token']}", None)
    for _ in range(50):
        manager.reserve_investigation(auth)
    with pytest.raises(PermissionError):
        manager.reserve_investigation(auth)
    report = manager.usage(auth)
    assert report["usage"]["investigations"] == 50


def test_admin_context_is_unlimited(tmp_path):
    manager = SaaSManager(str(tmp_path / "saas.sqlite3"))
    auth = AuthContext("default", "system", "admin@local", "admin", "test", True)
    for _ in range(60):
        manager.reserve_investigation(auth)
