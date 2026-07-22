"""Pytest fixtures shared by the backend suite.

``_harness`` is imported first (it pins env + builds the single SQLite engine
before the app is imported). Everything here builds on that: a fresh schema per
test, frozen naive-UTC time, small object factories, and stubs for the three
external integrations (GoCardless, SMTP email, Twilio).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests._harness import (  # noqa: F401 (re-exported for test modules)
    ADMIN_HEADERS,
    AGENT_HEADERS,
    BUSINESS_KEY,
    app,
    naive_utc_now,
    reset_db,
)
from tests._harness import SessionLocal

from app.models import (
    FitnessClassBooking,
    FitnessClassSession,
    FitnessMember,
    FitnessMembership,
)
from app.passwords import hash_password
from app.routers import agent_api, public_site
from app.routers.public_site import _hash_token, _new_token


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def db():
    """Fresh schema per test; yields a session for seeding/inspection."""
    reset_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    """Freeze every 'now' helper to naive UTC (SQLite stores naive datetimes)."""
    monkeypatch.setattr(public_site, "_now", naive_utc_now)
    monkeypatch.setattr(agent_api, "_now", naive_utc_now)
    import app.booking_rules as booking_rules

    monkeypatch.setattr(booking_rules, "utc_now", naive_utc_now)


# --- object factories --------------------------------------------------------

@pytest.fixture
def make_member(db):
    def _make(
        *,
        email="asha@example.com",
        first_name="Asha",
        last_name="Patel",
        phone="07700 900123",
        approval_status="approved",
        password=None,
    ):
        member = FitnessMember(
            business_key=BUSINESS_KEY,
            first_name=first_name,
            last_name=last_name,
            email=email.strip().lower(),
            phone=phone,
            access_token_hash=_hash_token(_new_token()),
            approval_status=approval_status,
            password_hash=hash_password(password) if password else None,
        )
        db.add(member)
        db.commit()
        return member

    return _make


@pytest.fixture
def make_membership(db):
    def _make(
        member,
        *,
        plan_slug="four-monthly",
        plan_name="4 classes monthly",
        billing_kind="recurring",
        amount_pence=2500,
        included_classes=4,
        remaining_classes=None,
        status="active",
        starts_at=None,
        ends_at=None,
        token=None,
    ):
        token = token or _new_token()
        remaining = included_classes if remaining_classes is None else remaining_classes
        membership = FitnessMembership(
            business_key=BUSINESS_KEY,
            member_id=member.id,
            public_token_hash=_hash_token(token),
            plan_slug=plan_slug,
            plan_name=plan_name,
            billing_kind=billing_kind,
            amount_pence=amount_pence,
            included_classes=included_classes,
            remaining_classes=remaining,
            status=status,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        db.add(membership)
        db.commit()
        return membership, token

    return _make


@pytest.fixture
def make_session(db):
    def _make(
        *,
        name="Sunday Reset",
        coach_name="Coach Sam",
        location="ORTU Fitness Studio",
        start_in=timedelta(days=1),
        duration=timedelta(hours=1),
        capacity=12,
        status="scheduled",
    ):
        start = naive_utc_now() + start_in
        session = FitnessClassSession(
            business_key=BUSINESS_KEY,
            name=name,
            coach_name=coach_name,
            location=location,
            start_at=start,
            end_at=start + duration,
            capacity=capacity,
            status=status,
        )
        db.add(session)
        db.commit()
        return session

    return _make


@pytest.fixture
def make_booking(db):
    def _make(membership, session, *, status="confirmed", token=None):
        booking = FitnessClassBooking(
            business_key=BUSINESS_KEY,
            session_id=session.id,
            member_id=membership.member_id,
            membership_id=membership.id,
            public_token_hash=_hash_token(token or _new_token()),
            status=status,
        )
        db.add(booking)
        db.commit()
        return booking

    return _make


# --- external-service stubs --------------------------------------------------

@pytest.fixture
def stub_gocardless(monkeypatch):
    """Make GoCardless 'configured' and return canned checkout/fulfil results."""
    calls = {}

    def _checkout(**kwargs):
        calls["checkout"] = kwargs
        return {
            "billing_request_id": "BRQ0001",
            "billing_flow_id": "BRF0001",
            "authorisation_url": "https://pay.gocardless.example/flow/BRF0001",
        }

    def _fulfil(*, billing_request_id, amount_pence, plan_name, billing_kind):
        calls["fulfil"] = {
            "billing_request_id": billing_request_id,
            "amount_pence": amount_pence,
            "plan_name": plan_name,
            "billing_kind": billing_kind,
        }
        if billing_kind == "recurring":
            return {"mandate_id": "MD0001", "subscription_id": "SB0001"}
        return {"mandate_id": "MD0001", "payment_id": "PM0001"}

    monkeypatch.setattr(public_site.gocardless, "create_mandate_checkout", _checkout)
    monkeypatch.setattr(public_site.gocardless, "fulfil_membership", _fulfil)
    monkeypatch.setattr(public_site.gocardless, "is_configured", lambda: True)
    monkeypatch.setattr(
        public_site.gocardless, "dashboard_base_url", lambda: "https://manage-sandbox.gocardless.com"
    )
    return calls


@pytest.fixture
def capture_email(monkeypatch):
    """Configure email + capture every send; force the OTP code to 123456."""
    sent = []

    def _send(to, subject, body, html=None):
        sent.append({"to": to, "subject": subject, "body": body, "html": html})

    monkeypatch.setattr(public_site.email_login, "is_configured", lambda: True)
    monkeypatch.setattr(public_site.email_login, "send", _send)
    monkeypatch.setattr(public_site.secrets, "randbelow", lambda _n: 123456)
    return sent


@pytest.fixture
def stub_twilio(monkeypatch):
    """Configure Twilio and approve only the code '123456'."""
    monkeypatch.setattr(public_site.twilio_verify, "is_configured", lambda: True)
    monkeypatch.setattr(public_site.twilio_verify, "start", lambda phone, channel: None)
    monkeypatch.setattr(public_site.twilio_verify, "check", lambda phone, code: code == "123456")
    return None
