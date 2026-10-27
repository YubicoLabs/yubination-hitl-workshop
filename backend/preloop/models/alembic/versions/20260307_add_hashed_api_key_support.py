"""Add hashed API key support for runtime credentials.

Revision ID: 20260307_add_hashed_api_keys
Revises: 20260219_rename_approval_policy
Create Date: 2026-03-07
"""

from __future__ import annotations

import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260307_add_hashed_api_keys"
down_revision: Union[str, None] = "20260219_rename_approval_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _build_key_hash(key_value: str) -> str:
    return hashlib.sha256(key_value.encode("utf-8")).hexdigest()


def _build_key_prefix(key_value: str, prefix_len: int = 12) -> str:
    return key_value[:prefix_len]


def upgrade() -> None:
    op.add_column("api_key", sa.Column("key_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "api_key", sa.Column("key_prefix", sa.String(length=16), nullable=True)
    )
    op.alter_column(
        "api_key", "key", existing_type=sa.String(length=100), nullable=True
    )

    connection = op.get_bind()
    api_key_table = sa.table(
        "api_key",
        sa.column("id", sa.String()),
        sa.column("key", sa.String()),
        sa.column("key_hash", sa.String()),
        sa.column("key_prefix", sa.String()),
    )

    rows = connection.execute(
        sa.select(api_key_table.c.id, api_key_table.c.key).where(
            api_key_table.c.key.is_not(None)
        )
    ).fetchall()

    for row in rows:
        connection.execute(
            api_key_table.update()
            .where(api_key_table.c.id == row.id)
            .values(
                key_hash=_build_key_hash(row.key),
                key_prefix=_build_key_prefix(row.key),
            )
        )

    op.create_index("ix_api_key_key_prefix", "api_key", ["key_prefix"], unique=False)
    op.create_index("ix_api_key_key_hash", "api_key", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_key_key_hash", table_name="api_key")
    op.drop_index("ix_api_key_key_prefix", table_name="api_key")
    op.alter_column(
        "api_key", "key", existing_type=sa.String(length=100), nullable=False
    )
    op.drop_column("api_key", "key_prefix")
    op.drop_column("api_key", "key_hash")
