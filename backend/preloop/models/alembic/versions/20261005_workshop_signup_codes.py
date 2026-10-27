"""Add reusable deployment-wide workshop signup codes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261005_workshop_signup_codes"
down_revision = "20261001_registration_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workshop_signup_code",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("code_digest", name="uq_workshop_signup_code_digest"),
    )


def downgrade() -> None:
    op.drop_table("workshop_signup_code")
