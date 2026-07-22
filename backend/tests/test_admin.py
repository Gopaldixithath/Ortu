"""Studio admin dashboard: auth, session CRUD, capacity guard, roster, members."""

from __future__ import annotations

from datetime import timedelta

from app.models import FitnessClassSession
from tests._harness import ADMIN_HEADERS, naive_utc_now


def test_admin_requires_key(client, monkeypatch):
    assert client.get("/api/admin/sessions").status_code == 401
    assert client.get("/api/admin/sessions", headers={"X-Ortu-Admin-Key": "wrong"}).status_code == 401
    monkeypatch.setenv("ORTU_FITNESS_ADMIN_KEY", "")
    assert client.get("/api/admin/sessions", headers=ADMIN_HEADERS).status_code == 503


def test_admin_lists_sessions_with_counts(client, make_session, make_member, make_membership, make_booking):
    session = make_session(name="Barbell", capacity=8)
    make_session(name="HIIT")
    member = make_member()
    membership, _ = make_membership(member)
    make_booking(membership, session)

    rows = client.get("/api/admin/sessions", headers=ADMIN_HEADERS).json()
    assert len(rows) == 2
    barbell = next(r for r in rows if r["name"] == "Barbell")
    assert barbell["booked"] == 1


def test_admin_create_session(client, db):
    start = (naive_utc_now() + timedelta(days=3)).replace(microsecond=0)
    payload = {
        "name": "Sunrise HIIT",
        "coach_name": "Coach Leo",
        "capacity": 14,
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=45)).isoformat(),
    }
    resp = client.post("/api/admin/sessions", json=payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 201
    assert resp.json()["name"] == "Sunrise HIIT"
    assert db.query(FitnessClassSession).count() == 1


def test_admin_create_session_rejects_bad_times(client):
    start = (naive_utc_now() + timedelta(days=3)).replace(microsecond=0)
    payload = {"name": "Bad", "capacity": 10, "start_at": start.isoformat(), "end_at": start.isoformat()}
    assert client.post("/api/admin/sessions", json=payload, headers=ADMIN_HEADERS).status_code == 422


def test_admin_capacity_cannot_drop_below_confirmed(client, make_session, make_member, make_membership, make_booking):
    session = make_session(capacity=5)
    for i in range(2):
        member = make_member(email=f"m{i}@example.com")
        membership, _ = make_membership(member)
        make_booking(membership, session)
    resp = client.patch(f"/api/admin/sessions/{session.id}", json={"capacity": 1}, headers=ADMIN_HEADERS)
    assert resp.status_code == 409


def test_admin_cancel_and_restore_session(client, db, make_session):
    session = make_session()
    assert client.patch(f"/api/admin/sessions/{session.id}", json={"status": "cancelled"}, headers=ADMIN_HEADERS).status_code == 200
    db.expire_all()
    assert db.get(FitnessClassSession, session.id).status == "cancelled"
    assert client.patch(f"/api/admin/sessions/{session.id}", json={"status": "scheduled"}, headers=ADMIN_HEADERS).status_code == 200


def test_admin_update_unknown_session_404(client):
    assert client.patch("/api/admin/sessions/999999", json={"capacity": 5}, headers=ADMIN_HEADERS).status_code == 404


def test_admin_session_roster(client, make_session, make_member, make_membership, make_booking):
    session = make_session()
    member = make_member(email="asha@example.com")
    membership, _ = make_membership(member)
    make_booking(membership, session)

    body = client.get(f"/api/admin/sessions/{session.id}/bookings", headers=ADMIN_HEADERS).json()
    assert body["session"]["id"] == session.id
    assert len(body["bookings"]) == 1
    assert body["bookings"][0]["member"]["email"] == "asha@example.com"


def test_admin_session_roster_unknown_404(client):
    assert client.get("/api/admin/sessions/999999/bookings", headers=ADMIN_HEADERS).status_code == 404


def test_admin_members_list(client, make_member, make_membership):
    member = make_member(email="asha@example.com")
    make_membership(member, status="active")
    make_member(email="ben@example.com", approval_status="pending")

    body = client.get("/api/admin/members", headers=ADMIN_HEADERS).json()
    assert len(body["members"]) == 2
    asha = next(m for m in body["members"] if m["email"] == "asha@example.com")
    assert asha["memberships"] and asha["memberships"][0]["status"] == "active"
