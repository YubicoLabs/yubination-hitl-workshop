"""add_account_id_to_api_key

Revision ID: 3c2b9f2d0c4a
Revises: 58e4ca3de37b
Create Date: 2025-12-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3c2b9f2d0c4a"
down_revision: Union[str, None] = "58e4ca3de37b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_key",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="The account this API key belongs to",
        ),
    )

    op.create_foreign_key(
        "fk_api_key_account_id_account",
        "api_key",
        "account",
        ["account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        sa.text(
            """
            UPDATE api_key
            SET account_id = \"user\".account_id
            FROM \"user\"
            WHERE api_key.user_id = \"user\".id
              AND api_key.account_id IS NULL
            """
        )
    )

    # If multiple keys within the same account share the same name (common for defaults
    # like "API Key"), the new unique constraint would fail. De-duplicate names by
    # appending a short suffix derived from the key UUID.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    account_id,
                    name,
                    ROW_NUMBER() OVER (
                        PARTITION BY account_id, name
                        ORDER BY created_at, id
                    ) AS rn
                FROM api_key
                WHERE account_id IS NOT NULL
            )
            UPDATE api_key
            SET name = LEFT(api_key.name, 80) || ' ' || LEFT(api_key.id::text, 8)
            FROM ranked r
            WHERE api_key.id = r.id
              AND r.rn > 1
            """
        )
    )

    op.alter_column("api_key", "account_id", nullable=False)

    op.create_index("ix_api_key_account_id", "api_key", ["account_id"])

    op.create_unique_constraint(
        "uix_api_key_account_id_name", "api_key", ["account_id", "name"]
    )


def downgrade() -> None:
    op.drop_constraint("uix_api_key_account_id_name", "api_key", type_="unique")
    op.drop_index("ix_api_key_account_id", table_name="api_key")
    op.drop_constraint("fk_api_key_account_id_account", "api_key", type_="foreignkey")
    op.drop_column("api_key", "account_id")
