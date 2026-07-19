"""Server-to-server API for the ORTU AI chat assistant (webchat + WhatsApp).

The chat platform authenticates with ``X-Ortu-Agent-Key`` (env
``ORTU_FITNESS_AGENT_KEY``). Member identity is proven per channel before any
member data is returned:

- **WhatsApp** — the platform passes the sender's WhatsApp number to
  ``POST /api/agent/member/identify``; a member whose registered mobile matches
  is considered verified (the WhatsApp sender number is authenticated by the
  WhatsApp platform itself).
- **Webchat** — the visitor gives their member email; the assistant calls
  ``verify/start`` (emails the same 6-digit code used by website login) and
  ``verify/check`` with the code the visitor types back.

After identification the platform holds the ``member id`` for the conversation
and uses the member-scoped endpoints to read details and book / cancel / move
classes. These endpoints deliberately do NOT touch the website's
``membership_token`` (issuing one would rotate and invalidate the member's
browser session), and they enforce the exact same booking rules as the site.
"""

from __future__ import annotations

import hmac
import os
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import email_login, email_templates
from app.booking_rules import (
    FitnessRuleError,
    ensure_booking_window,
    ensure_cancellable,
    ensure_capacity,
    ensure_membership_can_book,
)
from app.db import get_db
from app.models import (
    FitnessClassBooking,
    FitnessClassSession,
    FitnessLoginCode,
    FitnessMember,
    FitnessMembership,
)
from app.routers.public_site import (
    BUSINESS_KEY,
    _confirmed_counts,
    _hash_token,
    _member_by_email,
    _member_by_phone,
    _new_token,
    _normalize_phone,
    _now,
    _rule_http_error,
    _session_dict,
)

router = APIRouter(prefix="/api/agent", tags=["ORTU Agent API"])

CANCEL_CUTOFF_MINUTES = 60


def require_agent_key(x_ortu_agent_key: Optional[str] = Header(default=None)) -> None:
    expected = str(os.getenv("ORTU_FITNESS_AGENT_KEY") or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="The chat assistant integration is not configured.")
    if not x_ortu_agent_key or not hmac.compare_digest(x_ortu_agent_key, expected):
        raise HTTPException(status_code=401, detail="Invalid agent key.")


class IdentifyByPhone(BaseModel):
    phone: str = Field(min_length=7, max_length=60)


class VerifyStart(BaseModel):
    email: EmailStr


class VerifyCheck(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class AgentBookingCreate(BaseModel):
    session_id: int


class AgentBookingMove(BaseModel):
    new_session_id: int


def _pick_membership(db: Session, member_id: int, *, lock: bool = False) -> Optional[FitnessMembership]:
    query = (
        db.query(FitnessMembership)
        .filter(FitnessMembership.business_key == BUSINESS_KEY, FitnessMembership.member_id == member_id)
        .order_by(FitnessMembership.created_at.desc())
    )
    if lock:
        query = query.with_for_update()
    rows = query.all()
    return next((row for row in rows if row.status == "active"), None) or (rows[0] if rows else None)


def _membership_dict(membership: Optional[FitnessMembership]) -> Optional[dict]:
    if membership is None:
        return None
    return {
        "id": int(membership.id),
        "plan_name": membership.plan_name,
        "status": membership.status,
        "billing_kind": membership.billing_kind,
        "remaining_classes": membership.remaining_classes,
        "unlimited": membership.remaining_classes is None,
        "starts_at": membership.starts_at.isoformat() if membership.starts_at else None,
        "ends_at": membership.ends_at.isoformat() if membership.ends_at else None,
    }


def _upcoming_bookings(db: Session, member_id: int) -> list[dict]:
    now = _now()
    rows = (
        db.query(FitnessClassBooking, FitnessClassSession)
        .join(FitnessClassSession, FitnessClassSession.id == FitnessClassBooking.session_id)
        .filter(
            FitnessClassBooking.business_key == BUSINESS_KEY,
            FitnessClassBooking.member_id == member_id,
            FitnessClassBooking.status == "confirmed",
            FitnessClassSession.start_at >= now,
        )
        .order_by(FitnessClassSession.start_at.asc())
        .all()
    )
    return [
        {
            "booking_id": int(booking.id),
            "class_name": session.name,
            "coach_name": session.coach_name or "ORTU Coach",
            "location": session.location or "ORTU Fitness Studio",
            "start_at": session.start_at.isoformat(),
            "end_at": session.end_at.isoformat(),
            "can_cancel": session.start_at - now >= timedelta(minutes=CANCEL_CUTOFF_MINUTES),
        }
        for booking, session in rows
    ]


def _member_context(db: Session, member: FitnessMember) -> dict:
    membership = _pick_membership(db, int(member.id))
    return {
        "member": {
            "id": int(member.id),
            "first_name": member.first_name,
            "last_name": member.last_name,
            "email": member.email,
            "phone": member.phone,
            "approval_status": member.approval_status,
        },
        "membership": _membership_dict(membership),
        "upcoming_bookings": _upcoming_bookings(db, int(member.id)),
    }


def _member_or_404(db: Session, member_id: int) -> FitnessMember:
    member = (
        db.query(FitnessMember)
        .filter(FitnessMember.business_key == BUSINESS_KEY, FitnessMember.id == int(member_id))
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    return member


@router.get("/classes", dependencies=[Depends(require_agent_key)])
def agent_classes(days: int = 14, db: Session = Depends(get_db)):
    now = _now()
    horizon = now + timedelta(days=max(1, min(int(days), 60)))
    sessions = (
        db.query(FitnessClassSession)
        .filter(
            FitnessClassSession.business_key == BUSINESS_KEY,
            FitnessClassSession.start_at >= now,
            FitnessClassSession.start_at <= horizon,
            FitnessClassSession.status == "scheduled",
        )
        .order_by(FitnessClassSession.start_at.asc())
        .limit(60)
        .all()
    )
    counts = _confirmed_counts(db, [int(row.id) for row in sessions])
    return {"sessions": [_session_dict(row, int(counts.get(row.id, 0))) for row in sessions]}


@router.post("/member/identify", dependencies=[Depends(require_agent_key)])
def agent_identify_by_phone(payload: IdentifyByPhone, db: Session = Depends(get_db)):
    phone = _normalize_phone(payload.phone)
    member = _member_by_phone(db, phone)
    if not member:
        raise HTTPException(
            status_code=404,
            detail="No member record matches this phone number. The member may have joined with a different number.",
        )
    return _member_context(db, member)


@router.post("/member/verify/start", status_code=202, dependencies=[Depends(require_agent_key)])
def agent_verify_start(payload: VerifyStart, db: Session = Depends(get_db)):
    if not email_login.is_configured():
        raise HTTPException(status_code=503, detail="Email verification is not configured yet.")
    email = str(payload.email).strip().lower()
    member = _member_by_email(db, email)
    if not member:
        raise HTTPException(status_code=404, detail="No member record was found for this email address.")
    now = _now()
    recent = (
        db.query(func.count(FitnessLoginCode.id))
        .filter(FitnessLoginCode.member_id == member.id, FitnessLoginCode.created_at >= now - timedelta(minutes=15))
        .scalar()
        or 0
    )
    if int(recent) >= 5:
        raise HTTPException(status_code=429, detail="Too many codes requested. Please wait a few minutes and try again.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        FitnessLoginCode(
            business_key=BUSINESS_KEY,
            member_id=int(member.id),
            code_hash=_hash_token(code),
            expires_at=now + timedelta(minutes=10),
        )
    )
    db.commit()
    subject, text, html = email_templates.sign_in_code(member.first_name, code)
    try:
        email_login.send(member.email, subject, text, html)
    except email_login.EmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent", "channel": "email"}


@router.post("/member/verify/check", dependencies=[Depends(require_agent_key)])
def agent_verify_check(payload: VerifyCheck, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    member = _member_by_email(db, email)
    if not member:
        raise HTTPException(status_code=404, detail="No member record was found for this email address.")
    now = _now()
    candidates = (
        db.query(FitnessLoginCode)
        .filter(
            FitnessLoginCode.member_id == member.id,
            FitnessLoginCode.consumed_at.is_(None),
            FitnessLoginCode.expires_at >= now,
            FitnessLoginCode.attempts < 5,
        )
        .order_by(FitnessLoginCode.created_at.desc())
        .all()
    )
    matched = None
    supplied_hash = _hash_token(payload.code.strip())
    for row in candidates:
        row.attempts = int(row.attempts) + 1
        if hmac.compare_digest(row.code_hash, supplied_hash):
            matched = row
            break
    if not matched:
        db.commit()
        raise HTTPException(status_code=401, detail="That code is not right or has expired. Please try again.")
    matched.consumed_at = now
    db.commit()
    return _member_context(db, member)


@router.get("/member/{member_id}", dependencies=[Depends(require_agent_key)])
def agent_member_detail(member_id: int, db: Session = Depends(get_db)):
    member = _member_or_404(db, member_id)
    return _member_context(db, member)


def _bookable_session(db: Session, session_id: int) -> FitnessClassSession:
    session = (
        db.query(FitnessClassSession)
        .filter(FitnessClassSession.id == int(session_id), FitnessClassSession.business_key == BUSINESS_KEY)
        .with_for_update()
        .first()
    )
    if not session or session.status != "scheduled":
        raise HTTPException(status_code=404, detail="Class session not found.")
    return session


def _confirmed_count(db: Session, session_id: int) -> int:
    return int(
        db.query(func.count(FitnessClassBooking.id))
        .filter(FitnessClassBooking.session_id == int(session_id), FitnessClassBooking.status == "confirmed")
        .scalar()
        or 0
    )


def _book_member_into_session(
    db: Session,
    *,
    member_id: int,
    membership: FitnessMembership,
    session: FitnessClassSession,
) -> FitnessClassBooking:
    """Apply the booking rules and create/reactivate the booking row.

    Caller is responsible for the transaction (commit/rollback).
    """
    ensure_booking_window(starts_at=session.start_at)
    ensure_membership_can_book(
        status=membership.status,
        starts_at=membership.starts_at,
        ends_at=membership.ends_at,
        remaining_classes=membership.remaining_classes,
        class_start=session.start_at,
    )
    ensure_capacity(capacity=int(session.capacity), confirmed_count=_confirmed_count(db, int(session.id)))
    existing = (
        db.query(FitnessClassBooking)
        .filter(FitnessClassBooking.session_id == session.id, FitnessClassBooking.member_id == member_id)
        .first()
    )
    if existing and existing.status == "confirmed":
        raise HTTPException(status_code=409, detail="This member is already booked into this class.")
    token = _new_token()
    if existing:
        existing.membership_id = membership.id
        existing.public_token_hash = _hash_token(token)
        existing.status = "confirmed"
        existing.booked_at = _now()
        existing.cancelled_at = None
        booking = existing
    else:
        booking = FitnessClassBooking(
            business_key=BUSINESS_KEY,
            session_id=session.id,
            member_id=member_id,
            membership_id=membership.id,
            public_token_hash=_hash_token(token),
            status="confirmed",
        )
        db.add(booking)
    if membership.remaining_classes is not None:
        membership.remaining_classes = int(membership.remaining_classes) - 1
    return booking


def _cancel_booking_row(
    db: Session,
    *,
    booking: FitnessClassBooking,
    session: FitnessClassSession,
) -> None:
    """Apply the cancellation cutoff and release the booking + credit."""
    ensure_cancellable(starts_at=session.start_at, cutoff_minutes=CANCEL_CUTOFF_MINUTES)
    booking.status = "cancelled"
    booking.cancelled_at = _now()
    membership = (
        db.query(FitnessMembership)
        .filter(FitnessMembership.id == booking.membership_id)
        .with_for_update()
        .first()
    )
    if membership is not None and membership.remaining_classes is not None:
        membership.remaining_classes = min(
            int(membership.included_classes or 0), int(membership.remaining_classes) + 1
        )


@router.post("/member/{member_id}/bookings", status_code=201, dependencies=[Depends(require_agent_key)])
def agent_create_booking(member_id: int, payload: AgentBookingCreate, db: Session = Depends(get_db)):
    member = _member_or_404(db, member_id)
    membership = _pick_membership(db, int(member.id), lock=True)
    if membership is None:
        raise HTTPException(status_code=409, detail="This member has no membership yet. They need to choose a plan on the website first.")
    session = _bookable_session(db, payload.session_id)
    try:
        booking = _book_member_into_session(db, member_id=int(member.id), membership=membership, session=session)
        db.commit()
    except FitnessRuleError as exc:
        db.rollback()
        raise _rule_http_error(exc) from exc
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This class was just filled. Please choose another session.") from exc
    return {
        "message": f"Booked into {session.name} on {session.start_at:%A %d %b at %H:%M}.",
        "booking_id": int(booking.id),
        "remaining_classes": membership.remaining_classes,
        "context": _member_context(db, member),
    }


@router.post("/member/{member_id}/bookings/{booking_id}/cancel", dependencies=[Depends(require_agent_key)])
def agent_cancel_booking(member_id: int, booking_id: int, db: Session = Depends(get_db)):
    member = _member_or_404(db, member_id)
    booking = (
        db.query(FitnessClassBooking)
        .filter(
            FitnessClassBooking.id == int(booking_id),
            FitnessClassBooking.member_id == int(member.id),
            FitnessClassBooking.status == "confirmed",
        )
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found for this member.")
    session = db.query(FitnessClassSession).filter(FitnessClassSession.id == booking.session_id).first()
    try:
        _cancel_booking_row(db, booking=booking, session=session)
        db.commit()
    except FitnessRuleError as exc:
        db.rollback()
        raise _rule_http_error(exc) from exc
    return {
        "message": "The booking has been cancelled and the class credit restored.",
        "context": _member_context(db, member),
    }


@router.post("/member/{member_id}/bookings/{booking_id}/move", dependencies=[Depends(require_agent_key)])
def agent_move_booking(member_id: int, booking_id: int, payload: AgentBookingMove, db: Session = Depends(get_db)):
    """Reschedule atomically: cancel the old booking and book the new session
    in one transaction, so the member never loses their place unless the new
    booking definitely succeeded."""
    member = _member_or_404(db, member_id)
    booking = (
        db.query(FitnessClassBooking)
        .filter(
            FitnessClassBooking.id == int(booking_id),
            FitnessClassBooking.member_id == int(member.id),
            FitnessClassBooking.status == "confirmed",
        )
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found for this member.")
    if int(payload.new_session_id) == int(booking.session_id):
        raise HTTPException(status_code=409, detail="The booking is already for this class session.")
    old_session = db.query(FitnessClassSession).filter(FitnessClassSession.id == booking.session_id).first()
    new_session = _bookable_session(db, payload.new_session_id)
    membership = _pick_membership(db, int(member.id), lock=True)
    if membership is None:
        raise HTTPException(status_code=409, detail="This member has no membership yet.")
    try:
        _cancel_booking_row(db, booking=booking, session=old_session)
        new_booking = _book_member_into_session(db, member_id=int(member.id), membership=membership, session=new_session)
        db.commit()
    except FitnessRuleError as exc:
        db.rollback()
        raise _rule_http_error(exc) from exc
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The new class was just filled. The original booking is unchanged.") from exc
    return {
        "message": f"Moved to {new_session.name} on {new_session.start_at:%A %d %b at %H:%M}.",
        "booking_id": int(new_booking.id),
        "context": _member_context(db, member),
    }
