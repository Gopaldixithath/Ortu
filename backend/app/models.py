from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db import Base


class FitnessMember(Base):
    __tablename__ = "fitness_members"
    __table_args__ = (UniqueConstraint("business_key", "email", name="uq_fitness_member_business_email"),)

    id = Column(BigInteger, primary_key=True)
    business_key = Column(String(80), nullable=False, index=True)
    first_name = Column(String(120), nullable=False)
    last_name = Column(String(120), nullable=False)
    email = Column(String(320), nullable=False, index=True)
    phone = Column(String(60), nullable=True)
    access_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    marketing_opt_in = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FitnessMembership(Base):
    __tablename__ = "fitness_memberships"

    id = Column(BigInteger, primary_key=True)
    business_key = Column(String(80), nullable=False, index=True)
    member_id = Column(BigInteger, ForeignKey("fitness_members.id"), nullable=False, index=True)
    public_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    plan_slug = Column(String(80), nullable=False, index=True)
    plan_name = Column(String(180), nullable=False)
    billing_kind = Column(String(30), nullable=False)
    amount_pence = Column(Integer, nullable=False)
    included_classes = Column(Integer, nullable=True)
    remaining_classes = Column(Integer, nullable=True)
    status = Column(String(40), nullable=False, server_default="pending_payment", index=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    gocardless_billing_request_id = Column(String(80), nullable=True, index=True)
    gocardless_billing_flow_id = Column(String(80), nullable=True)
    gocardless_mandate_id = Column(String(80), nullable=True, index=True)
    gocardless_subscription_id = Column(String(80), nullable=True, index=True)
    gocardless_payment_id = Column(String(80), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FitnessClassSession(Base):
    __tablename__ = "fitness_class_sessions"

    id = Column(BigInteger, primary_key=True)
    business_key = Column(String(80), nullable=False, index=True)
    name = Column(String(180), nullable=False)
    description = Column(Text, nullable=True)
    coach_name = Column(String(180), nullable=True)
    location = Column(String(255), nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False)
    capacity = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, server_default="scheduled", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FitnessClassBooking(Base):
    __tablename__ = "fitness_class_bookings"
    __table_args__ = (
        UniqueConstraint("session_id", "member_id", name="uq_fitness_booking_session_member"),
    )

    id = Column(BigInteger, primary_key=True)
    business_key = Column(String(80), nullable=False, index=True)
    session_id = Column(BigInteger, ForeignKey("fitness_class_sessions.id"), nullable=False, index=True)
    member_id = Column(BigInteger, ForeignKey("fitness_members.id"), nullable=False, index=True)
    membership_id = Column(BigInteger, ForeignKey("fitness_memberships.id"), nullable=False, index=True)
    public_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(30), nullable=False, server_default="confirmed", index=True)
    booked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FitnessWebhookEvent(Base):
    __tablename__ = "fitness_webhook_events"

    id = Column(BigInteger, primary_key=True)
    provider = Column(String(40), nullable=False)
    provider_event_id = Column(String(100), nullable=False, unique=True, index=True)
    resource_type = Column(String(60), nullable=False)
    action = Column(String(60), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
