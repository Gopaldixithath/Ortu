"""Website booking, dashboard and cancellation (POST /bookings, /member)."""

from __future__ import annotations

from datetime import timedelta

from app.models import FitnessMembership


def _book(client, token, session_id):
    return client.post("/api/bookings", json={"membership_token": token, "session_id": session_id})


def test_book_decrements_credit(client, db, make_member, make_membership, make_session):
    member = make_member()
    membership, token = make_membership(member, included_classes=4, remaining_classes=4, status="active")
    session = make_session(capacity=12)

    resp = _book(client, token, session.id)
    assert resp.status_code == 201
    assert resp.json()["remaining"] == 11
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).remaining_classes == 3


def test_unlimited_membership_does_not_decrement(client, db, make_member, make_membership, make_session):
    member = make_member()
    membership, token = make_membership(member, plan_slug="unlimited-monthly", included_classes=None, remaining_classes=None, status="active")
    session = make_session()
    assert _book(client, token, session.id).status_code == 201
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).remaining_classes is None


def test_full_class_is_rejected(client, make_member, make_membership, make_session, make_booking):
    other = make_member(email="ben@example.com")
    other_membership, _ = make_membership(other, status="active")
    session = make_session(capacity=1)
    make_booking(other_membership, session)  # fills the only seat

    member = make_member(email="asha@example.com")
    _, token = make_membership(member, status="active")
    assert _book(client, token, session.id).status_code == 409


def test_double_booking_is_rejected(client, make_member, make_membership, make_session):
    member = make_member()
    _, token = make_membership(member, status="active")
    session = make_session(capacity=12)
    assert _book(client, token, session.id).status_code == 201
    assert _book(client, token, session.id).status_code == 409


def test_cannot_book_started_class(client, make_member, make_membership, make_session):
    member = make_member()
    _, token = make_membership(member, status="active")
    session = make_session(start_in=timedelta(hours=-1))  # already started
    assert _book(client, token, session.id).status_code == 409


def test_cannot_book_without_credits_or_when_inactive(client, make_member, make_membership, make_session):
    session = make_session()
    m1 = make_member(email="a@example.com")
    _, no_credit = make_membership(m1, included_classes=4, remaining_classes=0, status="active")
    assert _book(client, no_credit, session.id).status_code == 409

    m2 = make_member(email="b@example.com")
    _, inactive = make_membership(m2, status="pending_payment")
    assert _book(client, inactive, session.id).status_code == 409


def test_cannot_book_outside_membership_period(client, make_member, make_membership, make_session):
    from tests._harness import naive_utc_now

    member = make_member()
    session = make_session(start_in=timedelta(days=5))
    # membership expires the day after 'now', i.e. before the class starts
    _, token = make_membership(member, status="active", ends_at=naive_utc_now() + timedelta(days=1))
    assert _book(client, token, session.id).status_code == 409


def test_invalid_token_and_missing_session(client, make_member, make_membership, make_session):
    member = make_member()
    _, token = make_membership(member, status="active")
    assert _book(client, "z" * 30, make_session().id).status_code == 401  # bad token
    assert _book(client, token, 999999).status_code == 404  # no session


# --- dashboard + cancel ------------------------------------------------------

def test_member_dashboard_lists_bookings_with_cancel_flag(client, make_member, make_membership, make_session, make_booking):
    member = make_member()
    membership, token = make_membership(member, status="active")
    soon = make_session(name="Soon", start_in=timedelta(minutes=30))
    later = make_session(name="Later", start_in=timedelta(days=1))
    make_booking(membership, soon)
    make_booking(membership, later)

    body = client.get(f"/api/member?membership_token={token}").json()
    assert body["member"]["email"] == member.email
    flags = {b["session"]["name"]: b["can_cancel"] for b in body["bookings"]}
    assert flags == {"Soon": False, "Later": True}


def test_cancel_restores_credit_capped_at_included(client, db, make_member, make_membership, make_session, make_booking):
    member = make_member()
    membership, token = make_membership(member, included_classes=4, remaining_classes=3, status="active")
    session = make_session(start_in=timedelta(days=1))
    booking = make_booking(membership, session)

    resp = client.post(f"/api/bookings/{booking.id}/cancel", json={"membership_token": token})
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).remaining_classes == 4  # 3 -> 4


def test_cancel_credit_never_exceeds_included(client, db, make_member, make_membership, make_session, make_booking):
    member = make_member()
    membership, token = make_membership(member, included_classes=4, remaining_classes=4, status="active")
    booking = make_booking(membership, make_session(start_in=timedelta(days=1)))
    client.post(f"/api/bookings/{booking.id}/cancel", json={"membership_token": token})
    db.expire_all()
    assert db.get(FitnessMembership, membership.id).remaining_classes == 4  # capped


def test_cancel_inside_cutoff_blocked(client, make_member, make_membership, make_session, make_booking):
    member = make_member()
    membership, token = make_membership(member, status="active")
    booking = make_booking(membership, make_session(start_in=timedelta(minutes=30)))
    assert client.post(f"/api/bookings/{booking.id}/cancel", json={"membership_token": token}).status_code == 409


def test_cancel_unknown_booking_404(client, make_member, make_membership):
    member = make_member()
    _, token = make_membership(member, status="active")
    assert client.post("/api/bookings/999999/cancel", json={"membership_token": token}).status_code == 404
