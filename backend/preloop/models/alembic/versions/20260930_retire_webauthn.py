"""Retain replaced passkeys for historical receipt verification."""

from alembic import op
import sqlalchemy as sa

revision = "20260930_retire_webauthn"
down_revision = "20260924_pq_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_webauthn_credential",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    has_retired_credentials = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM user_webauthn_credential "
                "WHERE retired_at IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if has_retired_credentials:
        raise RuntimeError(
            "Cannot remove passkey retirement tracking while retired credentials exist. "
            "Use a compatible release or restore a verified pre-migration backup; "
            "dropping this column would reactivate retired credentials."
        )
    op.drop_column("user_webauthn_credential", "retired_at")
