"""Add participant feedback without changing existing tables or data."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261014_workshop_feedback"
down_revision = "20261005_workshop_signup_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workshop_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation", sa.Integer(), nullable=False),
        sa.Column("worked_well", sa.Text(), nullable=True),
        sa.Column("could_improve", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_workshop_feedback_user"),
        sa.CheckConstraint(
            "recommendation BETWEEN 1 AND 10", name="ck_workshop_feedback_rating"
        ),
        sa.CheckConstraint(
            "char_length(worked_well) <= 2000", name="ck_workshop_feedback_worked"
        ),
        sa.CheckConstraint(
            "char_length(could_improve) <= 2000", name="ck_workshop_feedback_improve"
        ),
    )
    op.create_index("ix_workshop_feedback_id", "workshop_feedback", ["id"])
    op.create_index(
        "ix_workshop_feedback_account_id", "workshop_feedback", ["account_id"]
    )


def downgrade() -> None:
    op.drop_table("workshop_feedback")
