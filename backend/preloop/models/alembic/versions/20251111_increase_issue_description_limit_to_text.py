"""increase_issue_description_limit_to_text

Revision ID: 42e000d008f4
Revises: 44bced548687
Create Date: 2025-11-11 07:39:37.618547

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "42e000d008f4"
down_revision: Union[str, None] = "44bced548687"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - change issue.description from VARCHAR(5000) to TEXT."""
    # Change the description column from VARCHAR(5000) to TEXT
    op.alter_column(
        "issue",
        "description",
        type_=sa.Text(),
        existing_type=sa.String(5000),
        existing_nullable=True,
    )

    # Upgrade schema - add context_data column to api_key table.
    op.add_column(
        "api_key",
        sa.Column(
            "context_data", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    """Downgrade schema - change issue.description from TEXT back to VARCHAR(5000)."""
    # Note: This will truncate any descriptions longer than 5000 characters
    op.alter_column(
        "issue",
        "description",
        type_=sa.String(5000),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    # Downgrade schema - remove context_data column from api_key table.
    op.drop_column("api_key", "context_data")
