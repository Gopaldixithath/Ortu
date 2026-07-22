"""GoCardless webhook: signature verification, idempotency, status mapping."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta

import pytest

from app.models import FitnessMembership
from tests._harness import naive_utc_now

SECRET = "whsec_test_secret"


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setenv("GOCARDLESS_WEBHOOK_ENDPOINT_SECRET", SECRET)
    return SECRET


def _post(client, payload, *, secret=SECRET, signature=None):
    raw = json.dumps(payload).encode("utf-8")
    sig = signature or hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/gocardless/webhook",
        content=raw,
        headers={"Webhook-Signature": sig, "Content-Type": "application/json"},
    )


def _membership_with_ids(make_member, make_membership, db, **ids):
    member = make_member()
    membership, _ = make_membership(member, status="pending_payment")
    for key, value in ids.items():
        setattr(membership, key, value)
    db.commit()
    return membership


def test_webhook_requires_secret_configured(client):
    # secret unset by default -> 503
    assert _post(client, {"events": []}).status_code == 503


def test_webhook_rejects_bad_signature(client, webhook_secret):
    assert _post(client, {"events": []}, signature="deadbeef").status_code == 498


def test_webhook_confirmed_payment_activates(client, db, make_member, make_membership, webhook_secret):
    membership = _membership_with_ids(make_member, make_membership, db, gocardless_payment_id="PM0001")
    resp = _post(client, {"events": [
        {"id": "EV1", "resource_type": "payments", "action": "confirmed", "links": {"payment": "PM0001"}},
    ]})
    assert resp.status_code == 204
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).status == "active"


def test_webhook_failed_payment_marks_payment_failed(client, db, make_member, make_membership, webhook_secret):
    membership = _membership_with_ids(make_member, make_membership, db, gocardless_payment_id="PM0002")
    _post(client, {"events": [
        {"id": "EV2", "resource_type": "payments", "action": "failed", "links": {"payment": "PM0002"}},
    ]})
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).status == "payment_failed"


def test_webhook_cancelled_subscription_suspends(client, db, make_member, make_membership, webhook_secret):
    membership = _membership_with_ids(make_member, make_membership, db, gocardless_subscription_id="SB0002")
    _post(client, {"events": [
        {"id": "EV3", "resource_type": "subscriptions", "action": "cancelled", "links": {"subscription": "SB0002"}},
    ]})
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).status == "suspended"


def test_webhook_is_idempotent(client, db, make_member, make_membership, webhook_secret):
    membership = _membership_with_ids(make_member, make_membership, db, gocardless_payment_id="PM0003")
    event = {"id": "EV4", "resource_type": "payments", "action": "confirmed", "links": {"payment": "PM0003"}}
    assert _post(client, {"events": [event]}).status_code == 204
    # replay the SAME event id with a different action — must be ignored
    replay = {"id": "EV4", "resource_type": "payments", "action": "failed", "links": {"payment": "PM0003"}}
    assert _post(client, {"events": [replay]}).status_code == 204
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).status == "active"  # unchanged by replay


def test_webhook_renews_expired_period_on_payment(client, db, make_member, make_membership, webhook_secret):
    member = make_member()
    membership, _ = make_membership(
        member, status="active", included_classes=4, remaining_classes=0,
        ends_at=naive_utc_now() - timedelta(days=1),
    )
    membership.gocardless_subscription_id = "SB0003"
    db.commit()
    _post(client, {"events": [
        {"id": "EV5", "resource_type": "payments", "action": "confirmed", "links": {"subscription": "SB0003"}},
    ]})
    db.expire_all()
    row = db.get(FitnessMembership, membership.id)
    assert row.status == "active"
    assert row.remaining_classes == 4  # credits reset on renewal
    assert row.ends_at > naive_utc_now()
