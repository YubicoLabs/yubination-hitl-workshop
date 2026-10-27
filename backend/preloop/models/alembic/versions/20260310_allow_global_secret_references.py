"""Allow global secret references without account ownership.

Revision ID: 20260310_global_secret_refs
Revises: 20260310_add_runtime_sessions
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260310_global_secret_refs"
down_revision: Union[str, None] = "20260310_add_runtime_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "secret_reference",
        "account_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "secret_reference",
        "account_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
