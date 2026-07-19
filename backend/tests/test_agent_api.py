"""End-to-end tests for the AI-assistant agent API (/api/agent/*).

Runs the real FastAPI app against a temporary sqlite database, so booking
rules, credit arithmetic, and transactional behaviour are exercised for real.
SQLite returns naive datetimes, so the "now" helpers are patched to naive UTC
for the duration of each test.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ORTU_FITNESS_AGENT_KEY"] = "test-agent-key"

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db as app_db
from app.db import Base, SessionLocal
from app.main import app
from app.models import FitnessClassBooking, FitnessClassSession, FitnessLoginCode, FitnessMember, FitnessMembership
from app.routers.public_site import _hash_token

# One shared in-memory database for every thread TestClient uses.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
app_db.engine = engine
SessionLocal.configure(bind=engine)

# SQLite only autoincrements INTEGER primary keys; render BigInteger as INTEGER.
from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(type_, compiler, **kw):
    return "INTEGER"

AGENT_HEADERS = {"X-Ortu-Agent-Key": "test-agent-key"}
BUSINESS_KEY = "ortu-fitness"


def _naive_utc_now():
    return datetime.utcnow()


class AgentApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self._patchers = [
            patch("app.booking_rules.utc_now", _naive_utc_now),
            patch("app.routers.agent_api._now", _naive_utc_now),
        ]
        for item in self._patchers:
            item.start()
        self.db = SessionLocal()
        self._seed()

    def tearDown(self):
        for item in self._patchers:
            item.stop()
        self.db.close()

    def _seed(self):
        db = self.db
        self.member = FitnessMember(
            business_key=BUSINESS_KEY,
            first_name="Asha",
            last_name="Patel",
            email="asha@example.com",
            phone="07700 900123",
            access_token_hash=_hash_token("member-1-access"),
            approval_status="approved",
        )
        self.other_member = FitnessMember(
            business_key=BUSINESS_KEY,
            first_name="Ben",
            last_name="Okafor",
            email="ben@example.com",
            phone="+447700900456",
            access_token_hash=_hash_token("member-2-access"),
            approval_status="approved",
        )
        db.add_all([self.member, self.other_member])
        db.flush()
        self.membership = FitnessMembership(
            business_key=BUSINESS_KEY,
            member_id=self.member.id,
            public_token_hash=_hash_token("member-1-site-token"),
            plan_slug="four-monthly",
            plan_name="4 classes monthly",
            billing_kind="subscription",
            amount_pence=2500,
            included_classes=4,
            remaining_classes=2,
            status="active",
        )
        self.other_membership = FitnessMembership(
            business_key=BUSINESS_KEY,
            member_id=self.other_member.id,
            public_token_hash=_hash_token("member-2-site-token"),
            plan_slug="unlimited-monthly",
            plan_name="Unlimited monthly",
            billing_kind="subscription",
            amount_pence=4000,
            included_classes=None,
            remaining_classes=None,
            status="active",
        )
        db.add_all([self.membership, self.other_membership])
        now = _naive_utc_now()
        self.session_tomorrow = FitnessClassSession(
            business_key=BUSINESS_KEY,
            name="Strength & Conditioning",
            coach_name="Coach Maya",
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=1, hours=1),
            capacity=12,
        )
        self.session_small = FitnessClassSession(
            business_key=BUSINESS_KEY,
            name="Small-Group Barbell",
            coach_name="Coach Maya",
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=1),
            capacity=1,
        )
        self.session_soon = FitnessClassSession(
            business_key=BUSINESS_KEY,
            name="Sunrise HIIT",
            coach_name="Coach Leo",
            start_at=now + timedelta(minutes=30),
            end_at=now + timedelta(minutes=75),
            capacity=14,
        )
        db.add_all([self.session_tomorrow, self.session_small, self.session_soon])
        db.commit()

    def _book_via_api(self, member_id, session_id):
        return self.client.post(
            f"/api/agent/member/{member_id}/bookings",
            json={"session_id": session_id},
            headers=AGENT_HEADERS,
        )

    def _refresh(self, instance):
        self.db.expire_all()
        return self.db.get(type(instance), instance.id)

    # ---- auth -----------------------------------------------------------

    def test_agent_key_required(self):
        response = self.client.get("/api/agent/classes")
        self.assertEqual(response.status_code, 401)
        response = self.client.get("/api/agent/classes", headers={"X-Ortu-Agent-Key": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_unconfigured_key_returns_503(self):
        with patch.dict(os.environ, {"ORTU_FITNESS_AGENT_KEY": ""}):
            response = self.client.get("/api/agent/classes", headers=AGENT_HEADERS)
        self.assertEqual(response.status_code, 503)

    # ---- identify / verify ---------------------------------------------

    def test_identify_by_whatsapp_phone_normalizes_uk_numbers(self):
        response = self.client.post(
            "/api/agent/member/identify", json={"phone": "+44 7700 900123"}, headers=AGENT_HEADERS
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["member"]["first_name"], "Asha")
        self.assertEqual(body["membership"]["plan_name"], "4 classes monthly")
        self.assertEqual(body["membership"]["remaining_classes"], 2)
        self.assertEqual(body["upcoming_bookings"], [])

    def test_identify_unknown_phone_404(self):
        response = self.client.post(
            "/api/agent/member/identify", json={"phone": "+447700999999"}, headers=AGENT_HEADERS
        )
        self.assertEqual(response.status_code, 404)

    def test_email_verify_flow(self):
        sent = {}

        def _capture(to, subject, body, html=None):
            sent["to"] = to
            sent["body"] = body

        with patch("app.routers.agent_api.email_login.is_configured", return_value=True), patch(
            "app.routers.agent_api.email_login.send", side_effect=_capture
        ), patch("app.routers.agent_api.secrets.randbelow", return_value=123456):
            start = self.client.post(
                "/api/agent/member/verify/start", json={"email": "asha@example.com"}, headers=AGENT_HEADERS
            )
        self.assertEqual(start.status_code, 202)
        self.assertEqual(sent["to"], "asha@example.com")
        self.assertIn("123456", sent["body"])

        wrong = self.client.post(
            "/api/agent/member/verify/check",
            json={"email": "asha@example.com", "code": "000000"},
            headers=AGENT_HEADERS,
        )
        self.assertEqual(wrong.status_code, 401)

        right = self.client.post(
            "/api/agent/member/verify/check",
            json={"email": "asha@example.com", "code": "123456"},
            headers=AGENT_HEADERS,
        )
        self.assertEqual(right.status_code, 200)
        self.assertEqual(right.json()["member"]["id"], self.member.id)

        replay = self.client.post(
            "/api/agent/member/verify/check",
            json={"email": "asha@example.com", "code": "123456"},
            headers=AGENT_HEADERS,
        )
        self.assertEqual(replay.status_code, 401)

    # ---- classes --------------------------------------------------------

    def test_classes_lists_upcoming_with_availability(self):
        response = self.client.get("/api/agent/classes", headers=AGENT_HEADERS)
        self.assertEqual(response.status_code, 200)
        sessions = response.json()["sessions"]
        names = [row["name"] for row in sessions]
        self.assertIn("Strength & Conditioning", names)
        first = next(row for row in sessions if row["name"] == "Strength & Conditioning")
        self.assertEqual(first["remaining"], 12)
        self.assertFalse(first["is_full"])

    # ---- booking --------------------------------------------------------

    def test_book_decrements_credits_and_returns_context(self):
        response = self._book_via_api(self.member.id, self.session_tomorrow.id)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["remaining_classes"], 1)
        self.assertEqual(len(body["context"]["upcoming_bookings"]), 1)
        self.assertEqual(body["context"]["upcoming_bookings"][0]["class_name"], "Strength & Conditioning")
        membership = self._refresh(self.membership)
        self.assertEqual(membership.remaining_classes, 1)

    def test_double_booking_same_class_rejected(self):
        self.assertEqual(self._book_via_api(self.member.id, self.session_tomorrow.id).status_code, 201)
        response = self._book_via_api(self.member.id, self.session_tomorrow.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("already booked", response.json()["detail"])

    def test_full_class_rejected(self):
        self.assertEqual(self._book_via_api(self.other_member.id, self.session_small.id).status_code, 201)
        response = self._book_via_api(self.member.id, self.session_small.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("full", response.json()["detail"])
        membership = self._refresh(self.membership)
        self.assertEqual(membership.remaining_classes, 2)

    def test_no_credits_rejected(self):
        self.membership.remaining_classes = 0
        self.db.commit()
        response = self._book_via_api(self.member.id, self.session_tomorrow.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("credits", response.json()["detail"])

    def test_inactive_membership_rejected(self):
        self.membership.status = "pending_payment"
        self.db.commit()
        response = self._book_via_api(self.member.id, self.session_tomorrow.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("not active", response.json()["detail"])

    def test_member_without_membership_gets_clear_error(self):
        lone = FitnessMember(
            business_key=BUSINESS_KEY,
            first_name="Cara",
            last_name="Singh",
            email="cara@example.com",
            access_token_hash=_hash_token("member-3-access"),
        )
        self.db.add(lone)
        self.db.commit()
        response = self._book_via_api(lone.id, self.session_tomorrow.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("no membership", response.json()["detail"])

    # ---- cancel ---------------------------------------------------------

    def test_cancel_restores_credit(self):
        booked = self._book_via_api(self.member.id, self.session_tomorrow.id).json()
        response = self.client.post(
            f"/api/agent/member/{self.member.id}/bookings/{booked['booking_id']}/cancel",
            headers=AGENT_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["context"]["membership"]["remaining_classes"], 2)
        self.assertEqual(response.json()["context"]["upcoming_bookings"], [])

    def test_cancel_inside_cutoff_rejected(self):
        booked = self._book_via_api(self.member.id, self.session_soon.id).json()
        response = self.client.post(
            f"/api/agent/member/{self.member.id}/bookings/{booked['booking_id']}/cancel",
            headers=AGENT_HEADERS,
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("1 hour", response.json()["detail"])

    def test_cannot_cancel_another_members_booking(self):
        booked = self._book_via_api(self.other_member.id, self.session_tomorrow.id).json()
        response = self.client.post(
            f"/api/agent/member/{self.member.id}/bookings/{booked['booking_id']}/cancel",
            headers=AGENT_HEADERS,
        )
        self.assertEqual(response.status_code, 404)

    # ---- move (update) --------------------------------------------------

    def test_move_swaps_sessions_with_no_net_credit_change(self):
        booked = self._book_via_api(self.member.id, self.session_tomorrow.id).json()
        self.assertEqual(booked["remaining_classes"], 1)
        response = self.client.post(
            f"/api/agent/member/{self.member.id}/bookings/{booked['booking_id']}/move",
            json={"new_session_id": self.session_small.id},
            headers=AGENT_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        context = response.json()["context"]
        self.assertEqual(context["membership"]["remaining_classes"], 1)
        self.assertEqual(len(context["upcoming_bookings"]), 1)
        self.assertEqual(context["upcoming_bookings"][0]["class_name"], "Small-Group Barbell")

    def test_move_to_full_class_keeps_original_booking(self):
        self.assertEqual(self._book_via_api(self.other_member.id, self.session_small.id).status_code, 201)
        booked = self._book_via_api(self.member.id, self.session_tomorrow.id).json()
        response = self.client.post(
            f"/api/agent/member/{self.member.id}/bookings/{booked['booking_id']}/move",
            json={"new_session_id": self.session_small.id},
            headers=AGENT_HEADERS,
        )
        self.assertEqual(response.status_code, 409)
        booking = self.db.get(FitnessClassBooking, booked["booking_id"])
        self.db.refresh(booking)
        self.assertEqual(booking.status, "confirmed")
        membership = self._refresh(self.membership)
        self.assertEqual(membership.remaining_classes, 1)

    def test_move_inside_cutoff_rejected(self):
        booked = self._book_via_api(self.member.id, self.session_soon.id).json()
        response = self.client.post(
            f"/api/agent/member/{self.member.id}/bookings/{booked['booking_id']}/move",
            json={"new_session_id": self.session_tomorrow.id},
            headers=AGENT_HEADERS,
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("1 hour", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
