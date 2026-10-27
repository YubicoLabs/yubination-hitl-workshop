"""add_team_ids_to_user_invitation

Revision ID: 44bced548687
Revises: 20251105
Create Date: 2025-11-10 02:50:54.775841

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "44bced548687"
down_revision: Union[str, None] = "20251105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add team_ids column to user_invitation table
    op.add_column(
        "user_invitation",
        sa.Column(
            "team_ids",
            sa.String(length=500),
            nullable=True,
            comment="Comma-separated team UUIDs to assign on acceptance",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove team_ids column from user_invitation table
    op.drop_column("user_invitation", "team_ids")
