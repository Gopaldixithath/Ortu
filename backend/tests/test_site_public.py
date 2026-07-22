"""GET /api/site — public homepage payload, availability and feature flags."""

from __future__ import annotations

from datetime import timedelta


def test_site_returns_business_plans_and_default_flags(client):
    body = client.get("/api/site").json()
    assert body["business"]["name"] == "ORTU Fitness"
    assert body["business"]["cancellation_cutoff_minutes"] == 60
    assert len(body["plans"]) == 6
    # External integrations are unconfigured in tests.
    assert body["payments_ready"] is False
    assert body["member_login_channels"] == {"password": True, "email": False, "phone": False}


def test_site_lists_only_future_scheduled_sessions(client, make_session):
    make_session(name="Upcoming", start_in=timedelta(days=1))
    make_session(name="Already ran", start_in=timedelta(hours=-2))
    make_session(name="Cancelled one", start_in=timedelta(days=2), status="cancelled")

    names = [s["name"] for s in client.get("/api/site").json()["sessions"]]
    assert names == ["Upcoming"]


def test_site_reflects_live_availability(client, make_session, make_member, make_membership, make_booking):
    session = make_session(name="Core & Stability", capacity=12)
    member = make_member()
    membership, _ = make_membership(member)
    make_booking(membership, session)

    payload = next(s for s in client.get("/api/site").json()["sessions"] if s["name"] == "Core & Stability")
    assert payload["capacity"] == 12
    assert payload["booked"] == 1
    assert payload["remaining"] == 11
    assert payload["is_full"] is False


def test_site_marks_full_class(client, make_session, make_member, make_membership, make_booking):
    session = make_session(name="Small-Group Barbell", capacity=1)
    member = make_member()
    membership, _ = make_membership(member)
    make_booking(membership, session)

    payload = next(s for s in client.get("/api/site").json()["sessions"] if s["name"] == "Small-Group Barbell")
    assert payload["remaining"] == 0
    assert payload["is_full"] is True
