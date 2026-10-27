"""Add gateway usage fields to api_usage.

Revision ID: 20260309_add_gateway_usage
Revises: 20260308_add_secret_refs
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260309_add_gateway_usage"
down_revision: Union[str, None] = "20260308_add_secret_refs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_usage",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("auth_subject_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("ai_model_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("flow_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("flow_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "api_usage", sa.Column("model_alias", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "api_usage", sa.Column("provider_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "api_usage",
        sa.Column("upstream_request_id", sa.String(length=255), nullable=True),
    )
    op.add_column("api_usage", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "api_usage", sa.Column("completion_tokens", sa.Integer(), nullable=True)
    )
    op.add_column("api_usage", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("api_usage", sa.Column("estimated_cost", sa.Float(), nullable=True))
    op.add_column(
        "api_usage",
        sa.Column("runtime_principal_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("runtime_principal_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("runtime_principal_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "api_usage",
        sa.Column("meta_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    for column in (
        "account_id",
        "api_key_id",
        "ai_model_id",
        "flow_id",
        "flow_execution_id",
    ):
        op.create_index(
            op.f(f"ix_api_usage_{column}"), "api_usage", [column], unique=False
        )

    op.create_foreign_key(
        "fk_api_usage_account_id_account",
        "api_usage",
        "account",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_api_usage_api_key_id_api_key",
        "api_usage",
        "api_key",
        ["api_key_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_api_usage_ai_model_id_ai_model",
        "api_usage",
        "ai_model",
        ["ai_model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_api_usage_flow_id_flow",
        "api_usage",
        "flow",
        ["flow_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_api_usage_flow_execution_id_flow_execution",
        "api_usage",
        "flow_execution",
        ["flow_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_api_usage_flow_execution_id_flow_execution",
        "api_usage",
        type_="foreignkey",
    )
    op.drop_constraint("fk_api_usage_flow_id_flow", "api_usage", type_="foreignkey")
    op.drop_constraint(
        "fk_api_usage_ai_model_id_ai_model", "api_usage", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_api_usage_api_key_id_api_key", "api_usage", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_api_usage_account_id_account", "api_usage", type_="foreignkey"
    )

    for column in (
        "flow_execution_id",
        "flow_id",
        "ai_model_id",
        "api_key_id",
        "account_id",
    ):
        op.drop_index(op.f(f"ix_api_usage_{column}"), table_name="api_usage")

    for column in (
        "meta_data",
        "runtime_principal_name",
        "runtime_principal_id",
        "runtime_principal_type",
        "estimated_cost",
        "total_tokens",
        "completion_tokens",
        "prompt_tokens",
        "upstream_request_id",
        "provider_name",
        "model_alias",
        "flow_execution_id",
        "flow_id",
        "ai_model_id",
        "auth_subject_type",
        "api_key_id",
        "account_id",
    ):
        op.drop_column("api_usage", column)
