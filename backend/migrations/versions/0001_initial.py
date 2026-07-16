"""initial ORTU fitness schema (members, memberships, classes, bookings, webhooks)

Revision ID: 0001_initial
Revises:
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fitness_members",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_key", sa.String(length=80), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=60), nullable=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("business_key", "email", name="uq_fitness_member_business_email"),
    )
    op.create_index("ix_fitness_members_business_key", "fitness_members", ["business_key"])
    op.create_index("ix_fitness_members_email", "fitness_members", ["email"])
    op.create_index("ix_fitness_members_access_token_hash", "fitness_members", ["access_token_hash"], unique=True)

    op.create_table(
        "fitness_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_key", sa.String(length=80), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("fitness_members.id"), nullable=False),
        sa.Column("public_token_hash", sa.String(length=64), nullable=False),
        sa.Column("plan_slug", sa.String(length=80), nullable=False),
        sa.Column("plan_name", sa.String(length=180), nullable=False),
        sa.Column("billing_kind", sa.String(length=30), nullable=False),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("included_classes", sa.Integer(), nullable=True),
        sa.Column("remaining_classes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending_payment"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gocardless_billing_request_id", sa.String(length=80), nullable=True),
        sa.Column("gocardless_billing_flow_id", sa.String(length=80), nullable=True),
        sa.Column("gocardless_mandate_id", sa.String(length=80), nullable=True),
        sa.Column("gocardless_subscription_id", sa.String(length=80), nullable=True),
        sa.Column("gocardless_payment_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for name, columns, unique in (
        ("ix_fitness_memberships_business_key", ["business_key"], False),
        ("ix_fitness_memberships_member_id", ["member_id"], False),
        ("ix_fitness_memberships_public_token_hash", ["public_token_hash"], True),
        ("ix_fitness_memberships_plan_slug", ["plan_slug"], False),
        ("ix_fitness_memberships_status", ["status"], False),
        ("ix_fitness_memberships_gc_request", ["gocardless_billing_request_id"], False),
        ("ix_fitness_memberships_gc_mandate", ["gocardless_mandate_id"], False),
        ("ix_fitness_memberships_gc_subscription", ["gocardless_subscription_id"], False),
        ("ix_fitness_memberships_gc_payment", ["gocardless_payment_id"], False),
    ):
        op.create_index(name, "fitness_memberships", columns, unique=unique)

    op.create_table(
        "fitness_class_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("coach_name", sa.String(length=180), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fitness_class_sessions_business_key", "fitness_class_sessions", ["business_key"])
    op.create_index("ix_fitness_class_sessions_start_at", "fitness_class_sessions", ["start_at"])
    op.create_index("ix_fitness_class_sessions_status", "fitness_class_sessions", ["status"])

    op.create_table(
        "fitness_class_bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_key", sa.String(length=80), nullable=False),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("fitness_class_sessions.id"), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("fitness_members.id"), nullable=False),
        sa.Column("membership_id", sa.BigInteger(), sa.ForeignKey("fitness_memberships.id"), nullable=False),
        sa.Column("public_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="confirmed"),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "member_id", name="uq_fitness_booking_session_member"),
    )
    for name, columns, unique in (
        ("ix_fitness_class_bookings_business_key", ["business_key"], False),
        ("ix_fitness_class_bookings_session_id", ["session_id"], False),
        ("ix_fitness_class_bookings_member_id", ["member_id"], False),
        ("ix_fitness_class_bookings_membership_id", ["membership_id"], False),
        ("ix_fitness_class_bookings_public_token_hash", ["public_token_hash"], True),
        ("ix_fitness_class_bookings_status", ["status"], False),
    ):
        op.create_index(name, "fitness_class_bookings", columns, unique=unique)

    op.create_table(
        "fitness_webhook_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fitness_webhook_events_provider_event_id", "fitness_webhook_events", ["provider_event_id"], unique=True)


def downgrade() -> None:
    op.drop_table("fitness_webhook_events")
    op.drop_table("fitness_class_bookings")
    op.drop_table("fitness_class_sessions")
    op.drop_table("fitness_memberships")
    op.drop_table("fitness_members")
