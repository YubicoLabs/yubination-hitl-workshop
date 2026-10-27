"""add model price overrides

Revision ID: 20260407_model_price_overrides
Revises: 20260406_agent_model_bindings
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260407_model_price_overrides"
down_revision: Union[str, None] = "20260406_agent_model_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create account-scoped model price override table."""
    op.create_table(
        "model_price_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("model_alias", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("input_price_per_1k", sa.Float(), nullable=True),
        sa.Column("output_price_per_1k", sa.Float(), nullable=True),
        sa.Column("cache_read_input_price_per_1k", sa.Float(), nullable=True),
        sa.Column("cache_creation_input_price_per_1k", sa.Float(), nullable=True),
        sa.Column("price_per_1k", sa.Float(), nullable=True),
        sa.Column("request_price", sa.Float(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_model_id"], ["ai_model.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_model_price_overrides_id"),
        "model_price_overrides",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_price_overrides_account_id"),
        "model_price_overrides",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_price_overrides_ai_model_id"),
        "model_price_overrides",
        ["ai_model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_price_overrides_model_alias"),
        "model_price_overrides",
        ["model_alias"],
        unique=False,
    )
    op.create_index(
        "ix_model_price_overrides_lookup",
        "model_price_overrides",
        ["account_id", "model_alias", "provider_name", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop account-scoped model price override table."""
    op.drop_index("ix_model_price_overrides_lookup", table_name="model_price_overrides")
    op.drop_index(
        op.f("ix_model_price_overrides_model_alias"),
        table_name="model_price_overrides",
    )
    op.drop_index(
        op.f("ix_model_price_overrides_ai_model_id"),
        table_name="model_price_overrides",
    )
    op.drop_index(
        op.f("ix_model_price_overrides_account_id"),
        table_name="model_price_overrides",
    )
    op.drop_index(
        op.f("ix_model_price_overrides_id"), table_name="model_price_overrides"
    )
    op.drop_table("model_price_overrides")
