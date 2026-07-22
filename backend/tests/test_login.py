"""Member login: password, emailed one-time code, and Twilio phone code."""

from __future__ import annotations

from datetime import timedelta

from app.models import FitnessLoginCode
from app.routers.public_site import _hash_token
from tests._harness import BUSINESS_KEY, naive_utc_now


# --- password ----------------------------------------------------------------

def test_password_login_returns_token_when_member_has_plan(client, make_member, make_membership):
    member = make_member(email="asha@example.com", password="password123")
    make_membership(member, status="active")
    resp = client.post("/api/member/login/password", json={"email": "asha@example.com", "password": "password123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["membership_token"]
    assert body["needs_plan"] is False


def test_password_login_needs_plan_when_no_membership(client, make_member):
    make_member(email="asha@example.com", password="password123")
    resp = client.post("/api/member/login/password", json={"email": "asha@example.com", "password": "password123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["membership_token"] is None
    assert body["needs_plan"] is True


def test_password_login_wrong_password_and_unknown_email(client, make_member):
    make_member(email="asha@example.com", password="password123")
    assert client.post("/api/member/login/password", json={"email": "asha@example.com", "password": "nope"}).status_code == 401
    assert client.post("/api/member/login/password", json={"email": "ghost@example.com", "password": "password123"}).status_code == 401


def test_password_login_blocked_until_approved(client, make_member):
    make_member(email="pending@example.com", password="password123", approval_status="pending")
    make_member(email="declined@example.com", password="password123", approval_status="declined")
    assert client.post("/api/member/login/password", json={"email": "pending@example.com", "password": "password123"}).status_code == 403
    assert client.post("/api/member/login/password", json={"email": "declined@example.com", "password": "password123"}).status_code == 403


# --- emailed one-time code ---------------------------------------------------

def test_email_login_requires_email_configured(client, make_member):
    make_member(email="asha@example.com")
    # no capture_email fixture => email is not configured
    assert client.post("/api/member/login/email/start", json={"email": "asha@example.com"}).status_code == 503


def test_email_login_start_and_verify(client, make_member, make_membership, capture_email):
    member = make_member(email="asha@example.com")
    make_membership(member, status="active")

    start = client.post("/api/member/login/email/start", json={"email": "asha@example.com"})
    assert start.status_code == 202
    assert capture_email and "123456" in capture_email[-1]["body"]

    wrong = client.post("/api/member/login/email/verify", json={"email": "asha@example.com", "code": "000000"})
    assert wrong.status_code == 401

    ok = client.post("/api/member/login/email/verify", json={"email": "asha@example.com", "code": "123456"})
    assert ok.status_code == 200
    assert ok.json()["membership_token"]

    replay = client.post("/api/member/login/email/verify", json={"email": "asha@example.com", "code": "123456"})
    assert replay.status_code == 401  # code consumed


def test_email_login_unknown_email_404(client, capture_email):
    assert client.post("/api/member/login/email/start", json={"email": "ghost@example.com"}).status_code == 404


def test_email_login_rate_limited_after_five_codes(client, make_member, capture_email):
    make_member(email="asha@example.com")
    for _ in range(5):
        assert client.post("/api/member/login/email/start", json={"email": "asha@example.com"}).status_code == 202
    assert client.post("/api/member/login/email/start", json={"email": "asha@example.com"}).status_code == 429


def test_email_code_expired_is_rejected(client, db, make_member, make_membership, capture_email):
    member = make_member(email="asha@example.com")
    make_membership(member, status="active")
    db.add(FitnessLoginCode(
        business_key=BUSINESS_KEY, member_id=member.id, code_hash=_hash_token("123456"),
        expires_at=naive_utc_now() - timedelta(minutes=1),
    ))
    db.commit()
    assert client.post("/api/member/login/email/verify", json={"email": "asha@example.com", "code": "123456"}).status_code == 401


def test_email_code_locks_out_after_five_attempts(client, db, make_member, make_membership, capture_email):
    member = make_member(email="asha@example.com")
    make_membership(member, status="active")
    db.add(FitnessLoginCode(
        business_key=BUSINESS_KEY, member_id=member.id, code_hash=_hash_token("123456"),
        expires_at=naive_utc_now() + timedelta(minutes=10),
    ))
    db.commit()
    for _ in range(5):
        assert client.post("/api/member/login/email/verify", json={"email": "asha@example.com", "code": "000000"}).status_code == 401
    # correct code now rejected because the code row is locked (attempts >= 5)
    assert client.post("/api/member/login/email/verify", json={"email": "asha@example.com", "code": "123456"}).status_code == 401


# --- Twilio phone ------------------------------------------------------------

def test_phone_login_requires_twilio_configured(client, make_member):
    make_member(phone="07700 900123")
    assert client.post("/api/member/login/start", json={"phone": "07700 900123"}).status_code == 503


def test_phone_login_start_verify(client, make_member, make_membership, stub_twilio):
    member = make_member(phone="07700 900123")
    make_membership(member, status="active")
    assert client.post("/api/member/login/start", json={"phone": "07700 900123", "channel": "sms"}).status_code == 202
    ok = client.post("/api/member/login/verify", json={"phone": "07700 900123", "code": "123456"})
    assert ok.status_code == 200 and ok.json()["membership_token"]
    assert client.post("/api/member/login/verify", json={"phone": "07700 900123", "code": "999999"}).status_code == 401


def test_phone_login_unknown_number_404(client, stub_twilio):
    assert client.post("/api/member/login/start", json={"phone": "07700 999999"}).status_code == 404
