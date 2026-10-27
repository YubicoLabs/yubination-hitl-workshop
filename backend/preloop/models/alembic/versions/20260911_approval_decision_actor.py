"""Add canonical final decision actor and time to approval requests.

Revision ID: 20260911_approval_decision_actor
Revises: 20260910_iv_workflow_cfg
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_approval_decision_actor"
down_revision: Union[str, Sequence[str], None] = "20260910_iv_workflow_cfg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "approval_request",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_approval_request_decided_by_user_id_user",
        "approval_request",
        "user",
        ["decided_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_approval_request_decided_by_user_id",
        "approval_request",
        ["decided_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_approval_request_decided_by_user_id", table_name="approval_request"
    )
    op.drop_constraint(
        "fk_approval_request_decided_by_user_id_user",
        "approval_request",
        type_="foreignkey",
    )
    op.drop_column("approval_request", "decided_at")
    op.drop_column("approval_request", "decided_by_user_id")
