"""Member signup (record request) validation + studio approve/decline."""

from __future__ import annotations

from app.models import FitnessMember
from tests._harness import ADMIN_HEADERS, BUSINESS_KEY


def _signup_payload(**overrides):
    payload = {
        "first_name": "New",
        "last_name": "Member",
        "date_of_birth": "1990-05-01",
        "email": "new@example.com",
        "phone": "07700 900999",
        "kin_first_name": "Kin",
        "kin_last_name": "Person",
        "kin_mobile": "07700 900000",
        "kin_email": "kin@example.com",
        "no_health_issues": True,
        "password": "password123",
        "agree_terms": True,
        "dp_legal": True,
        "dp_services": True,
    }
    payload.update(overrides)
    return payload


def test_signup_creates_pending_member_and_emails_confirmation(client, db, capture_email):
    resp = client.post("/api/member/signup", json=_signup_payload())
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"

    member = db.query(FitnessMember).filter(FitnessMember.email == "new@example.com").one()
    assert member.approval_status == "pending"
    assert member.business_key == BUSINESS_KEY
    assert member.password_hash and member.password_hash != "password123"

    assert len(capture_email) == 1
    assert capture_email[0]["to"] == "new@example.com"


def test_signup_succeeds_without_email_configured(client, db):
    resp = client.post("/api/member/signup", json=_signup_payload())
    assert resp.status_code == 201
    assert db.query(FitnessMember).count() == 1


def test_signup_duplicate_email_conflicts(client, make_member):
    make_member(email="new@example.com")
    resp = client.post("/api/member/signup", json=_signup_payload())
    assert resp.status_code == 409


def test_signup_validation_branches(client):
    assert client.post("/api/member/signup", json=_signup_payload(agree_terms=False)).status_code == 422
    assert client.post("/api/member/signup", json=_signup_payload(dp_legal=False)).status_code == 422
    # health notes required unless "no health issues" ticked
    assert client.post(
        "/api/member/signup", json=_signup_payload(no_health_issues=False, health_notes=None)
    ).status_code == 422
    # date of birth must be in the past
    assert client.post("/api/member/signup", json=_signup_payload(date_of_birth="2099-01-01")).status_code == 422


# --- approval ----------------------------------------------------------------

def test_admin_approve_sets_status_and_emails(client, db, make_member, capture_email):
    member = make_member(email="pending@example.com", approval_status="pending")
    resp = client.post(
        f"/api/admin/members/{member.id}/approval", json={"action": "approve"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json() == {"approval_status": "approved", "notification_email": "sent"}
    db.expire_all()
    assert db.get(FitnessMember, member.id).approval_status == "approved"
    assert len(capture_email) == 1


def test_admin_decline_sets_status(client, db, make_member):
    member = make_member(approval_status="pending")
    resp = client.post(
        f"/api/admin/members/{member.id}/approval", json={"action": "decline"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "declined"
    # email unconfigured in this test
    assert resp.json()["notification_email"] == "not_configured"


def test_approval_requires_valid_admin_key(client, make_member):
    member = make_member(approval_status="pending")
    assert client.post(f"/api/admin/members/{member.id}/approval", json={"action": "approve"}).status_code == 401
    assert client.post(
        f"/api/admin/members/{member.id}/approval", json={"action": "approve"},
        headers={"X-Ortu-Admin-Key": "wrong"},
    ).status_code == 401


def test_approval_unknown_member_404(client):
    assert client.post(
        "/api/admin/members/999999/approval", json={"action": "approve"}, headers=ADMIN_HEADERS
    ).status_code == 404
