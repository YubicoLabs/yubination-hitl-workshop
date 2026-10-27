"""Add full-text index for gateway interaction search.

Revision ID: 20260310_gateway_search_fts
Revises: 20260310_global_secret_refs
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260310_gateway_search_fts"
down_revision: Union[str, None] = "20260310_global_secret_refs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_gateway_usage_search_document_search_vector",
        "gateway_usage_search_document",
        [sa.text("to_tsvector('simple', searchable_text)")],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gateway_usage_search_document_search_vector",
        table_name="gateway_usage_search_document",
    )
