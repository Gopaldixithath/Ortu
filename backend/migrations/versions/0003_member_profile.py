"""member record request profile: DOB, address, kin, medical, password, approval

Revision ID: 0003_member_profile
Revises: 0002_login_codes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_member_profile"
down_revision: Union[str, Sequence[str], None] = "0002_login_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    sa.Column("password_hash", sa.String(length=255), nullable=True),
    sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="approved"),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("date_of_birth", sa.Date(), nullable=True),
    sa.Column("phone_other", sa.String(length=60), nullable=True),
    sa.Column("address_house", sa.String(length=120), nullable=True),
    sa.Column("address_line1", sa.String(length=255), nullable=True),
    sa.Column("address_line2", sa.String(length=255), nullable=True),
    sa.Column("town", sa.String(length=120), nullable=True),
    sa.Column("county", sa.String(length=120), nullable=True),
    sa.Column("postcode", sa.String(length=20), nullable=True),
    sa.Column("kin_first_name", sa.String(length=120), nullable=True),
    sa.Column("kin_last_name", sa.String(length=120), nullable=True),
    sa.Column("kin_mobile", sa.String(length=60), nullable=True),
    sa.Column("kin_email", sa.String(length=320), nullable=True),
    sa.Column("kin_relationship", sa.String(length=120), nullable=True),
    sa.Column("kin_is_primary_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("contact2_name", sa.String(length=180), nullable=True),
    sa.Column("contact2_mobile", sa.String(length=60), nullable=True),
    sa.Column("contact2_email", sa.String(length=320), nullable=True),
    sa.Column("contact2_relationship", sa.String(length=120), nullable=True),
    sa.Column("health_notes", sa.Text(), nullable=True),
    sa.Column("no_health_issues", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("terms_agreed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("dp_legal", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("dp_services", sa.Boolean(), nullable=False, server_default=sa.false()),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("fitness_members", column)
    op.create_index("ix_fitness_members_approval_status", "fitness_members", ["approval_status"])


def downgrade() -> None:
    op.drop_index("ix_fitness_members_approval_status", table_name="fitness_members")
    for column in reversed(COLUMNS):
        op.drop_column("fitness_members", column.name)
