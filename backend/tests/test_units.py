"""Pure-logic unit tests: password hashing, booking rules, plans, phone norm."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app import passwords
from app.booking_rules import (
    FitnessRuleError,
    ensure_booking_window,
    ensure_cancellable,
    ensure_capacity,
    ensure_membership_can_book,
)
from app.membership_plans import ORTU_PLANS, PLAN_BY_SLUG
from app.routers.public_site import _normalize_phone

NOW = datetime(2026, 7, 22, 12, 0, 0)


# --- passwords ---------------------------------------------------------------

def test_password_hash_is_not_plaintext_and_round_trips():
    stored = passwords.hash_password("correct horse battery")
    assert stored != "correct horse battery"
    assert stored.startswith("pbkdf2_sha256$")
    assert passwords.verify_password("correct horse battery", stored) is True


def test_password_hash_is_salted_unique():
    assert passwords.hash_password("same") != passwords.hash_password("same")


def test_password_wrong_and_malformed_return_false():
    stored = passwords.hash_password("secret123")
    assert passwords.verify_password("nope", stored) is False
    assert passwords.verify_password("secret123", "not-a-valid-hash") is False
    assert passwords.verify_password("secret123", "") is False
    assert passwords.verify_password("secret123", None) is False


# --- capacity ----------------------------------------------------------------

def test_capacity_blocks_when_full_and_when_closed():
    with pytest.raises(FitnessRuleError):
        ensure_capacity(capacity=10, confirmed_count=10)  # full
    with pytest.raises(FitnessRuleError):
        ensure_capacity(capacity=0, confirmed_count=0)  # not open
    ensure_capacity(capacity=10, confirmed_count=9)  # ok, no raise


# --- booking window ----------------------------------------------------------

def test_booking_window_rejects_started_classes():
    with pytest.raises(FitnessRuleError):
        ensure_booking_window(starts_at=NOW - timedelta(minutes=1), now=NOW)
    ensure_booking_window(starts_at=NOW + timedelta(minutes=1), now=NOW)


# --- cancellation cutoff -----------------------------------------------------

def test_cancellable_enforces_one_hour_cutoff():
    with pytest.raises(FitnessRuleError):
        ensure_cancellable(starts_at=NOW + timedelta(minutes=59), now=NOW)
    ensure_cancellable(starts_at=NOW + timedelta(minutes=61), now=NOW)


# --- membership can book -----------------------------------------------------

def test_membership_can_book_branches():
    start = NOW + timedelta(days=1)
    # inactive
    with pytest.raises(FitnessRuleError):
        ensure_membership_can_book(status="pending_payment", starts_at=None, ends_at=None,
                                   remaining_classes=4, class_start=start)
    # class before membership begins
    with pytest.raises(FitnessRuleError):
        ensure_membership_can_book(status="active", starts_at=NOW + timedelta(days=2),
                                   ends_at=None, remaining_classes=4, class_start=start)
    # class outside (>= ends_at)
    with pytest.raises(FitnessRuleError):
        ensure_membership_can_book(status="active", starts_at=NOW, ends_at=NOW + timedelta(hours=1),
                                   remaining_classes=4, class_start=start)
    # no credits left
    with pytest.raises(FitnessRuleError):
        ensure_membership_can_book(status="active", starts_at=None, ends_at=None,
                                   remaining_classes=0, class_start=start)
    # unlimited (None) is never blocked on credits
    ensure_membership_can_book(status="active", starts_at=None, ends_at=None,
                               remaining_classes=None, class_start=start)
    # happy path
    ensure_membership_can_book(status="active", starts_at=NOW, ends_at=NOW + timedelta(days=30),
                               remaining_classes=1, class_start=start)


# --- membership plans --------------------------------------------------------

def test_plans_shape_and_pricing():
    assert len(ORTU_PLANS) == 6
    assert set(PLAN_BY_SLUG) == {
        "payg", "14-day-pass", "28-day-pass", "four-monthly", "eight-monthly", "unlimited-monthly",
    }
    assert PLAN_BY_SLUG["payg"].public_dict()["price"] == "£7"
    assert PLAN_BY_SLUG["unlimited-monthly"].public_dict()["price"] == "£40"
    # unlimited plans carry no credit cap
    assert PLAN_BY_SLUG["unlimited-monthly"].included_classes is None
    assert PLAN_BY_SLUG["four-monthly"].included_classes == 4
    # billing kinds
    assert PLAN_BY_SLUG["payg"].billing_kind == "one_off"
    assert PLAN_BY_SLUG["unlimited-monthly"].billing_kind == "recurring"


# --- phone normalisation -----------------------------------------------------

def test_normalize_phone_uk_and_intl():
    assert _normalize_phone("07700 900123") == "+447700900123"
    assert _normalize_phone("+44 7700 900123") == "+447700900123"
    assert _normalize_phone("0044 7700 900123") == "+447700900123"


def test_normalize_phone_rejects_bad_input():
    for bad in ["", "12345", "not a phone", "0770090012"]:
        with pytest.raises(HTTPException) as exc:
            _normalize_phone(bad)
        assert exc.value.status_code == 422
