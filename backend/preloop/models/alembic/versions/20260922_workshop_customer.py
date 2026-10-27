"""Add account-isolated workshop fixtures without changing legacy customers."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260922_workshop_customer"
down_revision = "20260918_restore_stepup_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workshop_customer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("account_id", name="uq_workshop_customer_account"),
        sa.UniqueConstraint("email", name="uq_workshop_customer_email"),
        sa.CheckConstraint(
            "status IN ('standard', 'vip')", name="ck_workshop_customer_status"
        ),
    )
    op.create_index("ix_workshop_customer_id", "workshop_customer", ["id"])


def downgrade() -> None:
    raise RuntimeError(
        "Workshop customer data must be preserved. Roll back the application only; "
        "schema downgrade requires an explicit data migration plan."
    )
