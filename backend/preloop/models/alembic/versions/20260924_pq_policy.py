"""Per-user PQ policy and dedicated authentication readiness (no backfill)."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_pq_policy"
down_revision = "20260922_workshop_customer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("pq_only", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "user",
        sa.Column(
            "pq_policy_version", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column(
            "authentication_tested_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("authentication_key_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_webauthn_credential", "authentication_key_hash")
    op.drop_column("user_webauthn_credential", "authentication_tested_at")
    op.drop_column("user", "pq_policy_version")
    op.drop_column("user", "pq_only")
