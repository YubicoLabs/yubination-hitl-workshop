"""Add runtime sessions and runtime session usage attribution.

Revision ID: 20260310_add_runtime_sessions
Revises: 20260309_gateway_search_docs
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260310_add_runtime_sessions"
down_revision: Union[str, None] = "20260309_gateway_search_docs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_session",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_source_type", sa.String(length=64), nullable=False),
        sa.Column("session_source_id", sa.String(length=255), nullable=False),
        sa.Column("session_reference", sa.String(length=255), nullable=True),
        sa.Column("runtime_principal_type", sa.String(length=64), nullable=True),
        sa.Column("runtime_principal_id", sa.String(length=255), nullable=True),
        sa.Column("runtime_principal_name", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_source_type",
            "session_source_id",
            name="uq_runtime_session_source",
        ),
    )
    op.create_index(
        op.f("ix_runtime_session_account_id"),
        "runtime_session",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_session_id"),
        "runtime_session",
        ["id"],
        unique=False,
    )

    op.add_column(
        "api_usage",
        sa.Column("runtime_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_api_usage_runtime_session_id"),
        "api_usage",
        ["runtime_session_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_api_usage_runtime_session_id_runtime_session",
        "api_usage",
        "runtime_session",
        ["runtime_session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_api_usage_runtime_session_id_runtime_session",
        "api_usage",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_api_usage_runtime_session_id"), table_name="api_usage")
    op.drop_column("api_usage", "runtime_session_id")

    op.drop_index(op.f("ix_runtime_session_id"), table_name="runtime_session")
    op.drop_index(op.f("ix_runtime_session_account_id"), table_name="runtime_session")
    op.drop_table("runtime_session")
