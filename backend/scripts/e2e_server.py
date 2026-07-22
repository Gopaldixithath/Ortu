"""Deterministic backend for Playwright E2E runs.

Boots the real FastAPI app against a throwaway SQLite database, seeds a fixed
timetable + one approved member (email/password + active membership + a
cancellable booking) + one pending member, then serves the built SPA so
Playwright can drive the whole thing at http://127.0.0.1:8000.

GoCardless/SMTP/Twilio are deliberately left unconfigured ("setup mode"): the
full payment + webhook paths are covered by the pytest suite, so the browser
tests exercise the UI up to the checkout boundary only.

Run (from anywhere):  python backend/scripts/e2e_server.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# --- environment: pin BEFORE importing the app -------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(BACKEND, "e2e.db").replace("\\", "/"))
os.environ.setdefault("ORTU_FITNESS_ADMIN_KEY", "e2e-admin-key")
os.environ.setdefault("ORTU_STATIC_DIR", os.path.join(REPO, "frontend", "dist"))
os.environ["GOCARDLESS_ENVIRONMENT"] = "sandbox"
for _var in (
    "GOCARDLESS_ACCESS_TOKEN", "GOCARDLESS_WEBHOOK_ENDPOINT_SECRET",
    "SMTP_HOST", "SMTP_FROM", "SMTP_USERNAME", "SMTP_PASSWORD",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID",
):
    os.environ[_var] = ""

from datetime import datetime, timedelta  # noqa: E402

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN201
    return "INTEGER"


import app.db as app_db  # noqa: E402
from app import booking_rules  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    FitnessClassBooking,
    FitnessClassSession,
    FitnessMember,
    FitnessMembership,
)
from app.passwords import hash_password  # noqa: E402
from app.routers import agent_api, public_site  # noqa: E402
from app.routers.public_site import _hash_token  # noqa: E402

# SQLite stores naive datetimes; freeze every 'now' helper to naive UTC so the
# app's timezone-aware comparisons behave on SQLite exactly as in the suite.
def _naive_now() -> datetime:
    return datetime.utcnow()


public_site._now = _naive_now
agent_api._now = _naive_now
booking_rules.utc_now = _naive_now

BUSINESS_KEY = "ortu-fitness"

# Fixtures the specs rely on (keep in sync with e2e/fixtures.js).
# NB: use example.com — pydantic EmailStr rejects reserved TLDs like .test.
MEMBER_EMAIL = "e2e@example.com"
MEMBER_PASSWORD = "e2ePassword123"
MEMBERSHIP_TOKEN = "e2e-membership-token-0000000000"  # 31 chars (>= 20 required)


def seed() -> None:
    Base.metadata.drop_all(app_db.engine)
    Base.metadata.create_all(app_db.engine)
    db = SessionLocal()
    now = _naive_now()

    classes = [
        ("Small-Group Barbell", "Coach Maya", timedelta(days=1, hours=6), 8),
        ("Saturday Sweat", "Coach Leo", timedelta(days=2, hours=3), 16),
        ("Core & Stability", "Coach Priya", timedelta(days=3, hours=4), 12),
        ("Sunday Reset", "Coach Sam", timedelta(days=4, hours=4), 12),
    ]
    sessions = []
    for name, coach, delta, capacity in classes:
        start = now + delta
        session = FitnessClassSession(
            business_key=BUSINESS_KEY, name=name, coach_name=coach, location="ORTU Fitness Studio",
            start_at=start, end_at=start + timedelta(hours=1), capacity=capacity, status="scheduled",
        )
        db.add(session)
        sessions.append(session)

    member = FitnessMember(
        business_key=BUSINESS_KEY, first_name="Ellie", last_name="Test", email=MEMBER_EMAIL,
        phone="07700 900555", access_token_hash=_hash_token("e2e-access-token"),
        approval_status="approved", password_hash=hash_password(MEMBER_PASSWORD),
    )
    db.add(member)
    db.flush()
    membership = FitnessMembership(
        business_key=BUSINESS_KEY, member_id=member.id, public_token_hash=_hash_token(MEMBERSHIP_TOKEN),
        plan_slug="unlimited-monthly", plan_name="Unlimited monthly", billing_kind="recurring",
        amount_pence=4000, included_classes=None, remaining_classes=None, status="active",
        starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30),
    )
    db.add(membership)
    db.flush()
    # A cancellable booking (>1h away) so the "My bookings" cancel path works.
    db.add(FitnessClassBooking(
        business_key=BUSINESS_KEY, session_id=sessions[-1].id, member_id=member.id,
        membership_id=membership.id, public_token_hash=_hash_token("e2e-booking-token"), status="confirmed",
    ))
    # A pending member for the admin approval spec.
    db.add(FitnessMember(
        business_key=BUSINESS_KEY, first_name="Pat", last_name="Waiting", email="pending@example.com",
        phone="07700 900666", access_token_hash=_hash_token("e2e-pending-access"),
        approval_status="pending", password_hash=hash_password("pendingPass123"),
    ))
    db.commit()
    db.close()


if __name__ == "__main__":
    from app.main import app  # noqa: E402  (import after ORTU_STATIC_DIR is set)

    if not (os.path.join(os.environ["ORTU_STATIC_DIR"], "index.html")) or not os.path.exists(
        os.path.join(os.environ["ORTU_STATIC_DIR"], "index.html")
    ):
        sys.stderr.write(
            f"\n[e2e_server] Built frontend not found at {os.environ['ORTU_STATIC_DIR']}.\n"
            "Run `npm --prefix frontend ci && npm --prefix frontend run build` first.\n\n"
        )
    seed()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
