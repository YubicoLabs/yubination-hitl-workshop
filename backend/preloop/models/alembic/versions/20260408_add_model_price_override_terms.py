"""add model price override adjustment terms

Revision ID: 20260408_price_override_terms
Revises: 20260407_model_price_overrides
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260408_price_override_terms"
down_revision: Union[str, None] = "20260407_model_price_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add negotiated pricing adjustment fields."""
    op.add_column(
        "model_price_overrides",
        sa.Column("discount_percent", sa.Float(), nullable=True),
    )
    op.add_column(
        "model_price_overrides",
        sa.Column("prepaid_token_balance", sa.Float(), nullable=True),
    )
    op.add_column(
        "model_price_overrides",
        sa.Column("prepaid_credit_balance_usd", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Remove negotiated pricing adjustment fields."""
    op.drop_column("model_price_overrides", "prepaid_credit_balance_usd")
    op.drop_column("model_price_overrides", "prepaid_token_balance")
    op.drop_column("model_price_overrides", "discount_percent")
