"""member sign-in one-time codes (email login)

Revision ID: 0002_login_codes
Revises: 0001_initial
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_login_codes"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fitness_login_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_key", sa.String(length=80), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("fitness_members.id"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fitness_login_codes_member_id", "fitness_login_codes", ["member_id"])


def downgrade() -> None:
    op.drop_index("ix_fitness_login_codes_member_id", table_name="fitness_login_codes")
    op.drop_table("fitness_login_codes")
