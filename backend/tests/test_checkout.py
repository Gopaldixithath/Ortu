"""Plan checkout (GoCardless mandate) + the redirect-return completion."""

from __future__ import annotations

from app import gocardless
from app.models import FitnessMembership
from app.routers import public_site


def _checkout_body(**overrides):
    body = {
        "plan_slug": "four-monthly",
        "first_name": "Asha",
        "last_name": "Patel",
        "email": "asha@example.com",
        "phone": "07700 900123",
        "marketing_opt_in": True,
    }
    body.update(overrides)
    return body


def test_checkout_starts_mandate_for_approved_member(client, db, make_member, stub_gocardless):
    make_member(email="asha@example.com", approval_status="approved")
    resp = client.post("/api/memberships/checkout", json=_checkout_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["checkout_url"] == "https://pay.gocardless.example/flow/BRF0001"
    assert body["membership_token"] and body["member_access_token"]

    membership = db.query(FitnessMembership).one()
    assert membership.status == "pending_payment"
    assert membership.gocardless_billing_request_id == "BRQ0001"


def test_checkout_blocks_unapproved_and_unknown_members(client, make_member, stub_gocardless):
    # unknown email
    assert client.post("/api/memberships/checkout", json=_checkout_body(email="ghost@example.com")).status_code == 403
    make_member(email="pending@example.com", approval_status="pending")
    assert client.post("/api/memberships/checkout", json=_checkout_body(email="pending@example.com")).status_code == 403
    make_member(email="declined@example.com", approval_status="declined")
    assert client.post("/api/memberships/checkout", json=_checkout_body(email="declined@example.com")).status_code == 403


def test_checkout_unknown_plan_404(client, make_member, stub_gocardless):
    make_member(email="asha@example.com")
    assert client.post("/api/memberships/checkout", json=_checkout_body(plan_slug="does-not-exist")).status_code == 404


def test_checkout_gocardless_error_returns_503_and_rolls_back(client, db, make_member, monkeypatch):
    make_member(email="asha@example.com")

    def _boom(**kwargs):
        raise gocardless.GoCardlessError("Validation failed")

    monkeypatch.setattr(public_site.gocardless, "is_configured", lambda: True)
    monkeypatch.setattr(public_site.gocardless, "create_mandate_checkout", _boom)

    resp = client.post("/api/memberships/checkout", json=_checkout_body())
    assert resp.status_code == 503
    assert db.query(FitnessMembership).count() == 0  # rolled back


# --- completion (GoCardless redirect return) ---------------------------------

def _pending_membership(make_member, make_membership, db, *, plan_slug, billing_kind, included):
    member = make_member(email="asha@example.com")
    membership, token = make_membership(
        member, plan_slug=plan_slug, billing_kind=billing_kind, status="pending_payment",
        included_classes=included, remaining_classes=included,
    )
    membership.gocardless_billing_request_id = "BRQ0001"
    membership.gocardless_billing_flow_id = "BRF0001"
    db.commit()
    return membership, token


def test_complete_activates_recurring_membership(client, db, make_member, make_membership, stub_gocardless):
    membership, token = _pending_membership(make_member, make_membership, db, plan_slug="four-monthly", billing_kind="recurring", included=4)
    resp = client.get(f"/api/memberships/complete?membership_token={token}&id=BRF0001", follow_redirects=False)
    assert resp.status_code == 303
    assert "payment=success" in resp.headers["location"]
    db.expire_all()
    row = db.get(FitnessMembership, membership.id)
    assert row.status == "active"
    assert row.remaining_classes == 4
    assert row.starts_at is not None and row.ends_at is not None
    assert row.gocardless_subscription_id == "SB0001"


def test_complete_one_off_sets_payment_id(client, db, make_member, make_membership, stub_gocardless):
    membership, token = _pending_membership(make_member, make_membership, db, plan_slug="payg", billing_kind="one_off", included=1)
    resp = client.get(f"/api/memberships/complete?membership_token={token}", follow_redirects=False)
    assert resp.status_code == 303 and "payment=success" in resp.headers["location"]
    db.expire_all()
    row = db.get(FitnessMembership, membership.id)
    assert row.status == "active"
    assert row.gocardless_payment_id == "PM0001"
    assert row.gocardless_subscription_id is None


def test_complete_flow_id_mismatch_fails(client, db, make_member, make_membership, stub_gocardless):
    membership, token = _pending_membership(make_member, make_membership, db, plan_slug="four-monthly", billing_kind="recurring", included=4)
    resp = client.get(f"/api/memberships/complete?membership_token={token}&id=WRONG", follow_redirects=False)
    assert resp.status_code == 303 and "payment=failed" in resp.headers["location"]
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).status == "pending_payment"


def test_complete_fulfil_error_marks_payment_failed(client, db, make_member, make_membership, monkeypatch):
    membership, token = _pending_membership(make_member, make_membership, db, plan_slug="four-monthly", billing_kind="recurring", included=4)
    monkeypatch.setattr(public_site.gocardless, "is_configured", lambda: True)
    monkeypatch.setattr(public_site.gocardless, "fulfil_membership",
                        lambda **kw: (_ for _ in ()).throw(gocardless.GoCardlessError("not fulfilled")))
    resp = client.get(f"/api/memberships/complete?membership_token={token}&id=BRF0001", follow_redirects=False)
    assert resp.status_code == 303 and "payment=failed" in resp.headers["location"]
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).status == "payment_failed"


def test_complete_unknown_token_redirects_failed(client):
    resp = client.get("/api/memberships/complete?membership_token=" + "x" * 30, follow_redirects=False)
    assert resp.status_code == 303 and "payment=failed" in resp.headers["location"]
