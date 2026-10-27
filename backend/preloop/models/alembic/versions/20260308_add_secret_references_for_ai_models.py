"""Add secret references for AI model credentials.

Revision ID: 20260308_add_secret_refs
Revises: 20260307_add_hashed_api_keys
Create Date: 2026-03-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260308_add_secret_refs"
down_revision: Union[str, None] = "20260307_add_hashed_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "secret_reference",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("backend_type", sa.String(length=64), nullable=False),
        sa.Column("secret_kind", sa.String(length=64), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=True),
        sa.Column("external_ref", sa.String(length=512), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="active"
        ),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_secret_reference_account_id"),
        "secret_reference",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_secret_reference_id"),
        "secret_reference",
        ["id"],
        unique=False,
    )

    op.add_column(
        "ai_model",
        sa.Column(
            "credentials_secret_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_ai_model_credentials_secret_id"),
        "ai_model",
        ["credentials_secret_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_ai_model_credentials_secret_id_secret_reference",
        "ai_model",
        "secret_reference",
        ["credentials_secret_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_model_credentials_secret_id_secret_reference",
        "ai_model",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_ai_model_credentials_secret_id"), table_name="ai_model")
    op.drop_column("ai_model", "credentials_secret_id")

    op.drop_index(op.f("ix_secret_reference_id"), table_name="secret_reference")
    op.drop_index(op.f("ix_secret_reference_account_id"), table_name="secret_reference")
    op.drop_table("secret_reference")
