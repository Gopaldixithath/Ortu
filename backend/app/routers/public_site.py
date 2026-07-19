from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import email_login, email_templates, gocardless, passwords, twilio_verify
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
    FitnessLoginCode,
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


def _normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    plus = raw.startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
        plus = True
    if not plus and digits.startswith("07") and len(digits) == 11:
        digits = f"44{digits[1:]}"
        plus = True
    if not plus or not 8 <= len(digits) <= 15:
        raise HTTPException(status_code=422, detail="Enter the mobile number with its country code, e.g. +44 7700 900123.")
    return f"+{digits}"


def _member_by_phone(db: Session, phone_e164: str) -> Optional[FitnessMember]:
    rows = (
        db.query(FitnessMember)
        .filter(FitnessMember.business_key == BUSINESS_KEY, FitnessMember.phone.isnot(None), FitnessMember.phone != "")
        .all()
    )
    for member in rows:
        try:
            if _normalize_phone(member.phone) == phone_e164:
                return member
        except HTTPException:
            continue
    return None


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
        "member_login_enabled": email_login.is_configured() or twilio_verify.is_configured(),
        "member_login_channels": {"password": True, "email": email_login.is_configured(), "phone": twilio_verify.is_configured()},
    }


def _issue_membership_token(db: Session, member: FitnessMember) -> str:
    memberships = (
        db.query(FitnessMembership)
        .filter(FitnessMembership.business_key == BUSINESS_KEY, FitnessMembership.member_id == member.id)
        .order_by(FitnessMembership.created_at.desc())
        .all()
    )
    membership = next((row for row in memberships if row.status == "active"), None) or (memberships[0] if memberships else None)
    if not membership:
        raise HTTPException(status_code=404, detail="This member has no membership records yet.")
    token = _new_token()
    membership.public_token_hash = _hash_token(token)
    db.commit()
    return token


class EmailLoginStart(BaseModel):
    email: EmailStr


class EmailLoginVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


def _member_by_email(db: Session, email: str) -> Optional[FitnessMember]:
    return (
        db.query(FitnessMember)
        .filter(FitnessMember.business_key == BUSINESS_KEY, func.lower(FitnessMember.email) == email)
        .first()
    )


@router.post("/member/login/email/start", status_code=202)
def member_email_login_start(payload: EmailLoginStart, db: Session = Depends(get_db)):
    if not email_login.is_configured():
        raise HTTPException(status_code=503, detail="Member login by email is not configured yet.")
    email = str(payload.email).strip().lower()
    member = _member_by_email(db, email)
    if not member:
        raise HTTPException(status_code=404, detail="No membership was found for this email address. Use the address you gave when joining.")
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
    db.add(FitnessLoginCode(business_key=BUSINESS_KEY, member_id=int(member.id), code_hash=_hash_token(code), expires_at=now + timedelta(minutes=10)))
    db.commit()
    subject, text, html = email_templates.sign_in_code(member.first_name, code)
    try:
        email_login.send(member.email, subject, text, html)
    except email_login.EmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent", "channel": "email"}


@router.post("/member/login/email/verify")
def member_email_login_verify(payload: EmailLoginVerify, db: Session = Depends(get_db)):
    if not email_login.is_configured():
        raise HTTPException(status_code=503, detail="Member login by email is not configured yet.")
    email = str(payload.email).strip().lower()
    member = _member_by_email(db, email)
    if not member:
        raise HTTPException(status_code=404, detail="No membership was found for this email address.")
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
    return {"membership_token": _issue_membership_token(db, member)}


class MemberSignup(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=60)
    phone_other: Optional[str] = Field(default=None, max_length=60)
    address_house: Optional[str] = Field(default=None, max_length=120)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    town: Optional[str] = Field(default=None, max_length=120)
    county: Optional[str] = Field(default=None, max_length=120)
    postcode: Optional[str] = Field(default=None, max_length=20)
    kin_first_name: str = Field(min_length=1, max_length=120)
    kin_last_name: str = Field(min_length=1, max_length=120)
    kin_mobile: str = Field(min_length=7, max_length=60)
    kin_email: EmailStr
    kin_relationship: Optional[str] = Field(default=None, max_length=120)
    kin_is_primary_contact: bool = False
    contact2_name: Optional[str] = Field(default=None, max_length=180)
    contact2_mobile: Optional[str] = Field(default=None, max_length=60)
    contact2_email: Optional[str] = Field(default=None, max_length=320)
    contact2_relationship: Optional[str] = Field(default=None, max_length=120)
    health_notes: Optional[str] = Field(default=None, max_length=4000)
    no_health_issues: bool = False
    password: str = Field(min_length=8, max_length=128)
    agree_terms: bool
    dp_legal: bool
    dp_services: bool
    dp_marketing: bool = False


class MemberPasswordLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@router.post("/member/signup", status_code=201)
def member_signup(payload: MemberSignup, db: Session = Depends(get_db)):
    if not payload.agree_terms:
        raise HTTPException(status_code=422, detail="Please agree to the terms and conditions.")
    if not (payload.dp_legal and payload.dp_services):
        raise HTTPException(status_code=422, detail="The first two data protection options are required to create your member record.")
    if not payload.no_health_issues and not (payload.health_notes or "").strip():
        raise HTTPException(status_code=422, detail="Add your health notes, or tick that you have no health issues.")
    if payload.date_of_birth >= _now().date():
        raise HTTPException(status_code=422, detail="Please check the date of birth.")
    email = str(payload.email).strip().lower()
    if _member_by_email(db, email):
        raise HTTPException(status_code=409, detail="A member record with this email already exists. Try logging in instead, or contact the studio.")
    now = _now()
    member = FitnessMember(
        business_key=BUSINESS_KEY,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        email=email,
        phone=(payload.phone or "").strip() or None,
        access_token_hash=_hash_token(_new_token()),
        marketing_opt_in=bool(payload.dp_marketing),
        password_hash=passwords.hash_password(payload.password),
        approval_status="pending",
        date_of_birth=payload.date_of_birth,
        phone_other=(payload.phone_other or "").strip() or None,
        address_house=(payload.address_house or "").strip() or None,
        address_line1=(payload.address_line1 or "").strip() or None,
        address_line2=(payload.address_line2 or "").strip() or None,
        town=(payload.town or "").strip() or None,
        county=(payload.county or "").strip() or None,
        postcode=(payload.postcode or "").strip() or None,
        kin_first_name=payload.kin_first_name.strip(),
        kin_last_name=payload.kin_last_name.strip(),
        kin_mobile=payload.kin_mobile.strip(),
        kin_email=str(payload.kin_email).strip().lower(),
        kin_relationship=(payload.kin_relationship or "").strip() or None,
        kin_is_primary_contact=bool(payload.kin_is_primary_contact),
        contact2_name=(payload.contact2_name or "").strip() or None,
        contact2_mobile=(payload.contact2_mobile or "").strip() or None,
        contact2_email=(payload.contact2_email or "").strip() or None,
        contact2_relationship=(payload.contact2_relationship or "").strip() or None,
        health_notes=(payload.health_notes or "").strip() or None,
        no_health_issues=bool(payload.no_health_issues),
        terms_agreed_at=now,
        dp_legal=True,
        dp_services=True,
    )
    db.add(member)
    db.commit()
    if email_login.is_configured():
        subject, text, html = email_templates.signup_received(member.first_name)
        try:
            email_login.send(member.email, subject, text, html)
        except email_login.EmailError:
            pass
    return {"status": "pending", "detail": "Your member record request has been sent to the club."}


@router.post("/member/login/password")
def member_password_login(payload: MemberPasswordLogin, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    member = _member_by_email(db, email)
    if not member or not member.password_hash:
        raise HTTPException(status_code=401, detail="Email or password is not right. Members who joined before passwords existed can use the emailed sign-in code instead.")
    if not passwords.verify_password(payload.password, member.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is not right.")
    if member.approval_status == "pending":
        raise HTTPException(status_code=403, detail="The club has not accepted your sign-up yet. You will receive an email when your member record is approved.")
    if member.approval_status == "declined":
        raise HTTPException(status_code=403, detail="This member record request was not accepted. Please contact the studio.")
    membership_token = None
    try:
        membership_token = _issue_membership_token(db, member)
    except HTTPException:
        pass
    return {
        "membership_token": membership_token,
        "needs_plan": membership_token is None,
        "member": {"first_name": member.first_name, "last_name": member.last_name, "email": member.email, "phone": member.phone},
    }


class MemberLoginStart(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    channel: str = Field(default="whatsapp", pattern="^(whatsapp|sms)$")


class MemberLoginVerify(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    code: str = Field(min_length=4, max_length=10)


@router.post("/member/login/start", status_code=202)
def member_login_start(payload: MemberLoginStart, db: Session = Depends(get_db)):
    if not twilio_verify.is_configured():
        raise HTTPException(status_code=503, detail="Member login by mobile is not configured yet.")
    phone = _normalize_phone(payload.phone)
    if not _member_by_phone(db, phone):
        raise HTTPException(status_code=404, detail="No membership was found for this mobile number. Use the number you gave when joining, including the country code.")
    try:
        twilio_verify.start(phone, payload.channel)
    except twilio_verify.VerifyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent", "channel": payload.channel}


@router.post("/member/login/verify")
def member_login_verify(payload: MemberLoginVerify, db: Session = Depends(get_db)):
    if not twilio_verify.is_configured():
        raise HTTPException(status_code=503, detail="Member login by mobile is not configured yet.")
    phone = _normalize_phone(payload.phone)
    member = _member_by_phone(db, phone)
    if not member:
        raise HTTPException(status_code=404, detail="No membership was found for this mobile number.")
    try:
        approved = twilio_verify.check(phone, payload.code)
    except twilio_verify.VerifyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not approved:
        raise HTTPException(status_code=401, detail="That code is not right or has expired. Please try again.")
    return {"membership_token": _issue_membership_token(db, member)}


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
    if member is None:
        raise HTTPException(status_code=403, detail="Please become a member first — send a member record request and wait for the club to accept it.")
    if member.approval_status == "pending":
        raise HTTPException(status_code=403, detail="Your member record request is still awaiting the club's approval. You will receive an email once it is accepted.")
    if member.approval_status == "declined":
        raise HTTPException(status_code=403, detail="This member record was not accepted. Please contact the studio.")
    member_access_token = _new_token()
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
            exit_uri=f"{public_url}/?payment=cancelled",
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
        return RedirectResponse(f"{public_url}/?payment=failed", status_code=303)
    if membership.status == "active":
        return RedirectResponse(f"{public_url}/?payment=success&membership_token={membership_token}", status_code=303)
    if id and membership.gocardless_billing_flow_id and not hmac.compare_digest(id, membership.gocardless_billing_flow_id):
        return RedirectResponse(f"{public_url}/?payment=failed", status_code=303)
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
        return RedirectResponse(f"{public_url}/?payment=failed", status_code=303)
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
    if email_login.is_configured():
        member = db.query(FitnessMember).filter(FitnessMember.id == membership.member_id).first()
        if member:
            price = f"£{membership.amount_pence / 100:.2f}" + ("/month" if membership.billing_kind == "recurring" else "")
            if membership.remaining_classes is None:
                credits_line = "Your plan includes unlimited classes."
            else:
                credits_line = f"Your plan includes {membership.remaining_classes} class credit{'s' if membership.remaining_classes != 1 else ''}"
                credits_line += f", valid until {membership.ends_at:%d %b %Y}." if membership.ends_at else "."
            subject, text, html = email_templates.membership_active(member.first_name, membership.plan_name, price, credits_line, public_url)
            try:
                email_login.send(member.email, subject, text, html)
            except email_login.EmailError:
                pass
    return RedirectResponse(f"{public_url}/?payment=success&membership_token={membership_token}", status_code=303)


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
        "member": {"first_name": member.first_name, "last_name": member.last_name, "email": member.email, "phone": member.phone},
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


def _confirmed_counts(db: Session, session_ids: list[int]) -> dict[int, int]:
    if not session_ids:
        return {}
    return dict(
        db.query(FitnessClassBooking.session_id, func.count(FitnessClassBooking.id))
        .filter(FitnessClassBooking.session_id.in_(session_ids), FitnessClassBooking.status == "confirmed")
        .group_by(FitnessClassBooking.session_id)
        .all()
    )


@router.get("/admin/sessions")
def admin_sessions(x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    rows = db.query(FitnessClassSession).filter(FitnessClassSession.business_key == BUSINESS_KEY).order_by(FitnessClassSession.start_at.desc()).limit(100).all()
    counts = _confirmed_counts(db, [int(row.id) for row in rows])
    return [_session_dict(row, int(counts.get(row.id, 0))) for row in rows]


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
    counts = _confirmed_counts(db, [int(row.id)])
    return _session_dict(row, int(counts.get(row.id, 0)))


@router.get("/admin/sessions/{session_id}/bookings")
def admin_session_bookings(session_id: int, x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    session_row = db.query(FitnessClassSession).filter(FitnessClassSession.id == session_id, FitnessClassSession.business_key == BUSINESS_KEY).first()
    if not session_row:
        raise HTTPException(status_code=404, detail="Class session not found.")
    rows = (
        db.query(FitnessClassBooking, FitnessMember, FitnessMembership)
        .join(FitnessMember, FitnessMember.id == FitnessClassBooking.member_id)
        .join(FitnessMembership, FitnessMembership.id == FitnessClassBooking.membership_id)
        .filter(FitnessClassBooking.session_id == session_row.id)
        .order_by(FitnessClassBooking.booked_at.asc())
        .all()
    )
    confirmed = sum(1 for booking, _, _ in rows if booking.status == "confirmed")
    return {
        "session": _session_dict(session_row, confirmed),
        "bookings": [
            {
                "booking_id": int(booking.id),
                "status": booking.status,
                "booked_at": booking.booked_at,
                "cancelled_at": booking.cancelled_at,
                "plan_name": membership.plan_name,
                "member": {
                    "id": int(member.id),
                    "first_name": member.first_name,
                    "last_name": member.last_name,
                    "email": member.email,
                    "phone": member.phone,
                },
            }
            for booking, member, membership in rows
        ],
    }


@router.get("/admin/members")
def admin_members(x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    members = db.query(FitnessMember).filter(FitnessMember.business_key == BUSINESS_KEY).order_by(FitnessMember.created_at.desc()).limit(500).all()
    member_ids = [int(member.id) for member in members]
    memberships_by_member: dict[int, list[FitnessMembership]] = {}
    booking_counts: dict[int, int] = {}
    if member_ids:
        for row in (
            db.query(FitnessMembership)
            .filter(FitnessMembership.member_id.in_(member_ids))
            .order_by(FitnessMembership.created_at.desc())
            .all()
        ):
            memberships_by_member.setdefault(int(row.member_id), []).append(row)
        booking_counts = dict(
            db.query(FitnessClassBooking.member_id, func.count(FitnessClassBooking.id))
            .filter(FitnessClassBooking.member_id.in_(member_ids), FitnessClassBooking.status == "confirmed")
            .group_by(FitnessClassBooking.member_id)
            .all()
        )
    return {
        "gocardless_dashboard_url": gocardless.dashboard_base_url(),
        "members": [
            {
                "id": int(member.id),
                "first_name": member.first_name,
                "last_name": member.last_name,
                "email": member.email,
                "phone": member.phone,
                "marketing_opt_in": bool(member.marketing_opt_in),
                "joined_at": member.created_at,
                "confirmed_bookings": int(booking_counts.get(int(member.id), 0)),
                "approval_status": member.approval_status,
                "approved_at": member.approved_at,
                "date_of_birth": member.date_of_birth.isoformat() if member.date_of_birth else None,
                "phone_other": member.phone_other,
                "address": ", ".join(part for part in [member.address_house, member.address_line1, member.address_line2, member.town, member.county, member.postcode] if part) or None,
                "kin": {
                    "name": " ".join(part for part in [member.kin_first_name, member.kin_last_name] if part) or None,
                    "mobile": member.kin_mobile,
                    "email": member.kin_email,
                    "relationship": member.kin_relationship,
                    "is_primary_contact": bool(member.kin_is_primary_contact),
                },
                "contact2": {
                    "name": member.contact2_name,
                    "mobile": member.contact2_mobile,
                    "email": member.contact2_email,
                    "relationship": member.contact2_relationship,
                },
                "health_notes": member.health_notes,
                "no_health_issues": bool(member.no_health_issues),
                "has_password": bool(member.password_hash),
                "memberships": [
                    {
                        "id": int(row.id),
                        "plan_name": row.plan_name,
                        "billing_kind": row.billing_kind,
                        "amount_pence": int(row.amount_pence),
                        "status": row.status,
                        "remaining_classes": row.remaining_classes,
                        "starts_at": row.starts_at,
                        "ends_at": row.ends_at,
                        "gocardless_mandate_id": row.gocardless_mandate_id,
                        "gocardless_subscription_id": row.gocardless_subscription_id,
                        "gocardless_payment_id": row.gocardless_payment_id,
                    }
                    for row in memberships_by_member.get(int(member.id), [])
                ],
            }
            for member in members
        ],
    }


class MemberApproval(BaseModel):
    action: str = Field(pattern="^(approve|decline)$")


@router.post("/admin/members/{member_id}/approval")
def admin_member_approval(member_id: int, payload: MemberApproval, request: Request, x_ortu_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    _require_admin(x_ortu_admin_key)
    member = db.query(FitnessMember).filter(FitnessMember.id == member_id, FitnessMember.business_key == BUSINESS_KEY).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    if payload.action == "approve":
        member.approval_status = "approved"
        member.approved_at = _now()
    else:
        member.approval_status = "declined"
        member.approved_at = None
    db.commit()
    email_result = "not_configured"
    if email_login.is_configured():
        if payload.action == "approve":
            subject, text, html = email_templates.signup_approved(member.first_name, _public_url(request))
        else:
            subject, text, html = email_templates.signup_declined(member.first_name)
        try:
            email_login.send(member.email, subject, text, html)
            email_result = "sent"
        except email_login.EmailError:
            email_result = "failed"
    return {"approval_status": member.approval_status, "notification_email": email_result}


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
