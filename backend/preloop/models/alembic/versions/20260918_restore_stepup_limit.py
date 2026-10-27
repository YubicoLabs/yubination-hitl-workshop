"""Restore the step-up limiter removed by the historical RDT migration.

Preserve counters on databases where an operator already repaired the table.
No approval, credential or account data is changed.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260918_restore_stepup_limit"
down_revision = "20260915_policy_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("webauthn_step_up_rate_limit"):
        return
    op.create_table(
        "webauthn_step_up_rate_limit",
        sa.Column("token_hash", sa.String(64), nullable=False, primary_key=True),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    # The previous application revision still needs this security table. Keep
    # counters across application rollback instead of reintroducing the outage.
    pass
