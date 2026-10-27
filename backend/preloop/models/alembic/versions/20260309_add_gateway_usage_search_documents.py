"""Add gateway usage search document corpus table.

Revision ID: 20260309_gateway_search_docs
Revises: 20260309_add_gateway_usage
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "20260309_gateway_search_docs"
down_revision: Union[str, None] = "20260309_add_gateway_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gateway_usage_search_document",
        sa.Column("api_usage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("searchable_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["api_usage_id"],
            ["api_usage.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_usage_id"),
    )
    op.create_index(
        op.f("ix_gateway_usage_search_document_api_usage_id"),
        "gateway_usage_search_document",
        ["api_usage_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_gateway_usage_search_document_id"),
        "gateway_usage_search_document",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_gateway_usage_search_document_id"),
        table_name="gateway_usage_search_document",
    )
    op.drop_index(
        op.f("ix_gateway_usage_search_document_api_usage_id"),
        table_name="gateway_usage_search_document",
    )
    op.drop_table("gateway_usage_search_document")
