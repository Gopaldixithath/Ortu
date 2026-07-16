from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import gocardless
from app.booking_rules import (
    FitnessRuleError,
    ensure_booking_window,
    ensure_capacity,
    ensure_cancellable,
    ensure_membership_can_book,
)
from app.db import get_db
from app.membership_plans import ORTU_PLANS, PLAN_BY_SLUG
from app.models import (
    FitnessClassBooking,
    FitnessClassSession,
    FitnessMember,
    FitnessMembership,
    FitnessWebhookEvent,
)

router = APIRouter(prefix="/api", tags=["ORTU Fitness"])
BUSINESS_KEY = "ortu-fitness"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _public_url(request: Request) -> str:
    configured = str(os.getenv("ORTU_FITNESS_PUBLIC_URL") or "").strip().rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _rule_http_error(exc: FitnessRuleError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _require_admin(key: Optional[str]) -> None:
    expected = str(os.getenv("ORTU_FITNESS_ADMIN_KEY") or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Studio administration is not configured.")
    if not key or not hmac.compare_digest(key, expected):
        raise HTTPException(status_code=401, detail="Invalid studio administration key.")


def _session_dict(row: FitnessClassSession, booked: int) -> dict:
    remaining = max(0, int(row.capacity) - int(booked))
    return {
        "id": int(row.id),
        "name": row.name,
        "description": row.description or "",
        "coach_name": row.coach_name or "ORTU Coach",
        "location": row.location or "ORTU Fitness Studio",
        "start_at": row.start_at.isoformat(),
        "end_at": row.end_at.isoformat(),
        "capacity": int(row.capacity),
        "booked": int(booked),
        "remaining": remaining,
        "is_full": remaining < 1,
        "status": row.status,
    }


class MembershipCheckout(BaseModel):
    plan_slug: str
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=60)
    marketing_opt_in: bool = False


class BookingCreate(BaseModel):
    membership_token: str = Field(min_length=20)
    session_id: int


class BookingCancel(BaseModel):
    membership_token: str = Field(min_length=20)


class SessionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    description: Optional[str] = Field(default=None, max_length=2000)
    coach_name: Optional[str] = Field(default=None, max_length=180)
    location: Optional[str] = Field(default=None, max_length=255)
    start_at: datetime
    end_at: datetime
    capacity: int = Field(ge=1, le=500)


class SessionUpdate(BaseModel):
    capacity: Optional[int] = Field(default=None, ge=1, le=500)
    status: Optional[str] = Field(default=None, pattern="^(scheduled|cancelled)$")


@router.get("/site")
def site_data(db: Session = Depends(get_db)):
    sessions = (
        db.query(FitnessClassSession)
        .filter(
            FitnessClassSession.business_key == BUSINESS_KEY,
            FitnessClassSession.start_at >= _now(),
            FitnessClassSession.status == "scheduled",
        )
        .order_by(FitnessClassSession.start_at.asc())
        .limit(40)
        .all()
    )
    ids = [int(row.id) for row in sessions]
    counts = {}
    if ids:
        counts = dict(
            db.query(FitnessClassBooking.session_id, func.count(FitnessClassBooking.id))
            .filter(FitnessClassBooking.session_id.in_(ids), FitnessClassBooking.status == "confirmed")
            .group_by(FitnessClassBooking.session_id)
            .all()
        )
    return {
        "business": {
            "name": "ORTU Fitness",
            "tagline": "Stronger together. Healthier for life.",
            "cancellation_cutoff_minutes": 60,
            "currency": "GBP",
            "payments": "GoCardless Direct Debit",
        },
        "plans": [plan.public_dict() for plan in ORTU_PLANS],
        "sessions": [_session_dict(row, int(counts.get(row.id, 0))) for row in sessions],
        "payments_ready": gocardless.is_configured(),
    }


@router.post("/memberships/checkout", status_code=201)
def start_membership_checkout(payload: MembershipCheckout, request: Request, db: Session = Depends(get_db)):
    plan = PLAN_BY_SLUG.get(payload.plan_slug)
    if not plan:
        raise HTTPException(status_code=404, detail="Membership plan not found.")
    email = str(payload.email).strip().lower()
    member = (
        db.query(FitnessMember)
        .filter(FitnessMember.business_key == BUSINESS_KEY, func.lower(FitnessMember.email) == email)
        .first()
    )
    member_access_token = _new_token()
    if member is None:
        member = FitnessMember(
            business_key=BUSINESS_KEY,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=email,
            phone=(payload.phone or "").strip() or None,
            access_token_hash=_hash_token(member_access_token),
            marketing_opt_in=payload.marketing_opt_in,
        )
        db.add(member)
        db.flush()
    else:
        member.first_name = payload.first_name.strip()
        member.last_name = payload.last_name.strip()
        member.phone = (payload.phone or "").strip() or member.phone
        member.marketing_opt_in = bool(payload.marketing_opt_in)
        member.access_token_hash = _hash_token(member_access_token)

    membership_token = _new_token()
    membership = FitnessMembership(
        business_key=BUSINESS_KEY,
        member_id=int(member.id),
        public_token_hash=_hash_token(membership_token),
        plan_slug=plan.slug,
        plan_name=plan.name,
        billing_kind=plan.billing_kind,
        amount_pence=plan.price_pence,
        included_classes=plan.included_classes,
        remaining_classes=plan.included_classes,
        status="pending_payment",
    )
    db.add(membership)
    db.flush()
    public_url = _public_url(request)
    complete_uri = f"{str(request.base_url).rstrip('/')}/api/memberships/complete?membership_token={membership_token}"
    try:
        checkout = gocardless.create_mandate_checkout(
            first_name=member.first_name,
            last_name=member.last_name,
            email=member.email,
            redirect_uri=complete_uri,
            exit_uri=f"{public_url}?payment=cancelled",
        )
    except gocardless.GoCardlessError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    membership.gocardless_billing_request_id = checkout["billing_request_id"]
    membership.gocardless_billing_flow_id = checkout["billing_flow_id"]
    db.commit()
    return {
        "checkout_url": checkout["authorisation_url"],
        "member_access_token": member_access_token,
        "membership_token": membership_token,
    }


@router.get("/memberships/complete", include_in_schema=False)
def complete_membership(
    request: Request,
    membership_token: str = Query(...),
    id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(FitnessMembership)
        .filter(FitnessMembership.business_key == BUSINESS_KEY, FitnessMembership.public_token_hash == _hash_token(membership_token))
        .first()
    )
    public_url = _public_url(request)
    if not membership:
        return RedirectResponse(f"{public_url}?payment=failed", status_code=303)
    if membership.status == "active":
        return RedirectResponse(f"{public_url}?payment=success&membership_token={membership_token}", status_code=303)
    if id and membership.gocardless_billing_flow_id and not hmac.compare_digest(id, membership.gocardless_billing_flow_id):
        return RedirectResponse(f"{public_url}?payment=failed", status_code=303)
    try:
        provider = gocardless.fulfil_membership(
            billing_request_id=str(membership.gocardless_billing_request_id or ""),
            amount_pence=int(membership.amount_pence),
            plan_name=membership.plan_name,
            billing_kind=membership.billing_kind,
        )
    except gocardless.GoCardlessError:
        membership.status = "payment_failed"
        db.commit()
        return RedirectResponse(f"{public_url}?payment=failed", status_code=303)
    now = _now()
    plan = PLAN_BY_SLUG[membership.plan_slug]
    membership.status = "active"
    membership.starts_at = now
    membership.ends_at = now + timedelta(days=int(plan.duration_days or 31))
    membership.remaining_classes = plan.included_classes
    membership.gocardless_mandate_id = provider.get("mandate_id")
    membership.gocardless_subscription_id = provider.get("subscription_id")
    membership.gocardless_payment_id = provider.get("payment_id")
    db.commit()
    return RedirectResponse(f"{public_url}?payment=success&membership_token={membership_token}", status_code=303)


def _membership_from_token(db: Session, value: str, *, lock: bool = False) -> FitnessMembership:
    query = db.query(FitnessMembership).filter(
        FitnessMembership.business_key == BUSINESS_KEY,
        FitnessMembership.public_token_hash == _hash_token(value),
    )
    if lock:
        query = query.with_for_update()
    membership = query.first()
    if not membership:
        raise HTTPException(status_code=401, detail="Membership access link is invalid.")
    return membership


@router.get("/member")
def member_dashboard(membership_token: str = Query(..., min_length=20), db: Session = Depends(get_db)):
    membership = _membership_from_token(db, membership_token)
    member = db.query(FitnessMember).filter(FitnessMember.id == membership.member_id).first()
    bookings = (
        db.query(FitnessClassBooking, FitnessClassSession)
        .join(FitnessClassSession, FitnessClassSession.id == FitnessClassBooking.session_id)
        .filter(FitnessClassBooking.membership_id == membership.id, FitnessClassBooking.status == "confirmed")
        .order_by(FitnessClassSession.start_at.asc())
        .all()
    )
    return {
        "member": {"first_name": member.first_name, "last_name": member.last_name, "email": member.email},
        "membership": {
            "plan_name": membership.plan_name,
            "status": membership.status,
            "remaining_classes": membership.remaining_classes,
            "starts_at": membership.starts_at.isoformat() if membership.starts_at else None,
            "ends_at": membership.ends_at.isoformat() if membership.ends_at else None,
        },
        "bookings": [
            {
                "booking_id": int(row.id),
                "session": _session_dict(session, 0),
                "can_cancel": session.start_at - _now() >= timedelta(hours=1),
            }
            for row, session in bookings
        ],
    }


@router.post("/bookings", status_code=201)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    membership = _membership_from_token(db, payload.membership_token, lock=True)
    session = (
        db.query(FitnessClassSession)
        .filter(FitnessClassSession.id == payload.session_id, FitnessClassSession.business_key == BUSINESS_KEY)
        .with_for_update()
        .first()
    )
    if not session or session.status != "scheduled":
        raise HTTPException(status_code=404, detail="Class session not found.")
    try:
        ensure_booking_window(starts_at=session.start_at)
        ensure_membership_can_book(
            status=membership.status,
            starts_at=membership.starts_at,
            ends_at=membership.ends_at,
            remaining_classes=membership.remaining_classes,
            class_start=session.start_at,
        )
        confirmed_count = (
            db.query(func.count(FitnessClassBooking.id))
            .filter(FitnessClassBooking.session_id == session.id, FitnessClassBooking.status == "confirmed")
            .scalar()
            or 0
        )
        ensure_capacity(capacity=int(session.capacity), confirmed_count=int(confirmed_count))
    except FitnessRuleError as exc:
        raise _rule_http_error(exc) from exc
    existing = (
        db.query(FitnessClassBooking)
        .filter(FitnessClassBooking.session_id == session.id, FitnessClassBooking.member_id == membership.member_id)
        .first()
    )
    if existing and existing.status == "confirmed":
        raise HTTPException(status_code=409, detail="You are already booked into this class.")
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
            member_id=membership.member_id,
            membership_id=membership.id,
            public_token_hash=_hash_token(token),
            status="confirmed",
        )
        db.add(booking)
    if membership.remaining_classes is not None:
        membership.remaining_classes = int(membership.remaining_classes) - 1
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This class was just filled. Please choose another session.") from exc
    return {"message": "Your class is booked.", "booking_id": int(booking.id), "remaining": int(session.capacity) - int(confirmed_count) - 1}


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, payload: BookingCancel, db: Session = Depends(get_db)):
    membership = _membership_from_token(db, payload.membership_token, lock=True)
    booking = (
        db.query(FitnessClassBooking)
        .filter(
            FitnessClassBooking.id == booking_id,
            FitnessClassBooking.membership_id == membership.id,
            FitnessClassBooking.status == "confirmed",
        )
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found.")
    session = db.query(FitnessClassSession).filter(FitnessClassSession.id == booking.session_id).first()
    try:
        ensure_cancellable(starts_at=session.start_at)
    except FitnessRuleError as exc:
        raise _rule_http_error(exc) from exc
    booking.status = "cancelled"
    booking.cancelled_at = _now()
    if membership.remaining_classes is not None:
        membership.remaining_classes = min(int(membership.included_classes or 0), int(membership.remaining_classes) + 1)
    db.commit()
    return {"message": "Your booking has been cancelled and the class credit restored."}


@router.get("/admin/sessions")
def admin_sessions(x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    rows = db.query(FitnessClassSession).filter(FitnessClassSession.business_key == BUSINESS_KEY).order_by(FitnessClassSession.start_at.desc()).limit(100).all()
    return [_session_dict(row, 0) for row in rows]


@router.post("/admin/sessions", status_code=201)
def admin_create_session(payload: SessionCreate, x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="Class end time must be after the start time.")
    row = FitnessClassSession(business_key=BUSINESS_KEY, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _session_dict(row, 0)


@router.patch("/admin/sessions/{session_id}")
def admin_update_session(session_id: int, payload: SessionUpdate, x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    row = db.query(FitnessClassSession).filter(FitnessClassSession.id == session_id, FitnessClassSession.business_key == BUSINESS_KEY).first()
    if not row:
        raise HTTPException(status_code=404, detail="Class session not found.")
    if payload.capacity is not None:
        booked = db.query(func.count(FitnessClassBooking.id)).filter(FitnessClassBooking.session_id == row.id, FitnessClassBooking.status == "confirmed").scalar() or 0
        if payload.capacity < int(booked):
            raise HTTPException(status_code=409, detail=f"Capacity cannot be lower than the {booked} confirmed bookings.")
        row.capacity = payload.capacity
    if payload.status is not None:
        row.status = payload.status
    db.commit()
    return _session_dict(row, 0)


@router.post("/gocardless/webhook", status_code=204)
async def gocardless_webhook(request: Request, webhook_signature: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    raw = await request.body()
    secret = str(os.getenv("GOCARDLESS_WEBHOOK_ENDPOINT_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="GoCardless webhook verification is not configured.")
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not webhook_signature or not hmac.compare_digest(expected, webhook_signature):
        raise HTTPException(status_code=498, detail="Invalid webhook signature.")
    payload = await request.json()
    for event in payload.get("events") or []:
        event_id = str(event.get("id") or "")
        if not event_id or db.query(FitnessWebhookEvent.id).filter(FitnessWebhookEvent.provider_event_id == event_id).first():
            continue
        resource_type = str(event.get("resource_type") or "")
        action = str(event.get("action") or "")
        links = event.get("links") or {}
        membership = None
        if links.get("subscription"):
            membership = db.query(FitnessMembership).filter(FitnessMembership.gocardless_subscription_id == str(links["subscription"])).first()
        elif links.get("payment"):
            membership = db.query(FitnessMembership).filter(FitnessMembership.gocardless_payment_id == str(links["payment"])).first()
        elif links.get("mandate"):
            membership = db.query(FitnessMembership).filter(FitnessMembership.gocardless_mandate_id == str(links["mandate"])).first()
        if membership:
            if action in {"failed", "cancelled", "charged_back"}:
                membership.status = "payment_failed" if resource_type == "payments" else "suspended"
            elif resource_type == "payments" and action in {"confirmed", "paid_out"}:
                membership.status = "active"
                if membership.ends_at and membership.ends_at <= _now():
                    membership.starts_at = _now()
                    membership.ends_at = _now() + timedelta(days=31)
                    membership.remaining_classes = membership.included_classes
        db.add(FitnessWebhookEvent(provider="gocardless", provider_event_id=event_id, resource_type=resource_type, action=action))
    db.commit()
    return Response(status_code=204)
