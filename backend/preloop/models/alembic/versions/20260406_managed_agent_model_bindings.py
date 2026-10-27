"""Add managed-agent kind and explicit AI model bindings.

Revision ID: 20260406_agent_model_bindings
Revises: 147510708aac
Create Date: 2026-04-06
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260406_agent_model_bindings"
down_revision: Union[str, None] = "147510708aac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "managed_agent", sa.Column("agent_kind", sa.String(length=64), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE managed_agent "
            "SET agent_kind = lower(replace(session_source_type, ' ', '_')) "
            "WHERE agent_kind IS NULL"
        )
    )
    op.alter_column("managed_agent", "agent_kind", nullable=False)

    op.create_table(
        "managed_agent_ai_model_binding",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("managed_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_type", sa.String(length=32), nullable=False),
        sa.Column("config_key", sa.String(length=255), nullable=False),
        sa.Column("gateway_alias", sa.String(length=255), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["managed_agent_id"], ["managed_agent.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ai_model_id"], ["ai_model.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "managed_agent_id",
            "config_key",
            "gateway_alias",
            name="uq_managed_agent_ai_model_binding_slot",
        ),
    )
    op.create_index(
        op.f("ix_managed_agent_ai_model_binding_account_id"),
        "managed_agent_ai_model_binding",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_ai_model_binding_managed_agent_id"),
        "managed_agent_ai_model_binding",
        ["managed_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_ai_model_binding_ai_model_id"),
        "managed_agent_ai_model_binding",
        ["ai_model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_ai_model_binding_id"),
        "managed_agent_ai_model_binding",
        ["id"],
        unique=False,
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                ai_model.id AS ai_model_id,
                ai_model.account_id AS account_id,
                ai_model.meta_data AS meta_data,
                ai_model.updated_at AS updated_at,
                ai_model.created_at AS created_at
            FROM ai_model
            WHERE ai_model.account_id IS NOT NULL
              AND ai_model.meta_data IS NOT NULL
              AND ai_model.meta_data ? 'managed_agent_id'
            """
        )
    ).mappings()

    valid_agents_res = bind.execute(sa.text("SELECT id FROM managed_agent")).mappings()
    valid_agents = {str(r["id"]) for r in valid_agents_res}

    now = datetime.now(timezone.utc)
    first_primary_by_agent: dict[str, bool] = {}
    for row in rows:
        meta_data = row["meta_data"] or {}
        managed_agent_id = str(meta_data.get("managed_agent_id") or "").strip()
        if not managed_agent_id or managed_agent_id not in valid_agents:
            continue
        gateway_meta = (
            meta_data.get("gateway")
            if isinstance(meta_data.get("gateway"), dict)
            else {}
        )
        gateway_alias = str(gateway_meta.get("model_alias") or "").strip()
        if not gateway_alias:
            continue

        is_primary = managed_agent_id not in first_primary_by_agent
        first_primary_by_agent[managed_agent_id] = True
        status = (
            "gateway_ready"
            if bool(gateway_meta.get("enabled", False))
            else "unresolved_credentials"
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO managed_agent_ai_model_binding (
                    id,
                    account_id,
                    managed_agent_id,
                    ai_model_id,
                    binding_type,
                    config_key,
                    gateway_alias,
                    is_primary,
                    status,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :account_id,
                    :managed_agent_id,
                    :ai_model_id,
                    :binding_type,
                    :config_key,
                    :gateway_alias,
                    :is_primary,
                    :status,
                    :first_seen_at,
                    :last_seen_at,
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (account_id, managed_agent_id, config_key, gateway_alias)
                DO NOTHING
                """
            ),
            {
                "id": uuid.uuid4(),
                "account_id": row["account_id"],
                "managed_agent_id": uuid.UUID(managed_agent_id),
                "ai_model_id": row["ai_model_id"],
                "binding_type": "configured",
                "config_key": "legacy.configured_model",
                "gateway_alias": gateway_alias,
                "is_primary": is_primary,
                "status": status,
                "first_seen_at": row["created_at"] or now,
                "last_seen_at": row["updated_at"] or now,
                "created_at": row["created_at"] or now,
                "updated_at": row["updated_at"] or now,
            },
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_managed_agent_ai_model_binding_id"),
        table_name="managed_agent_ai_model_binding",
    )
    op.drop_index(
        op.f("ix_managed_agent_ai_model_binding_ai_model_id"),
        table_name="managed_agent_ai_model_binding",
    )
    op.drop_index(
        op.f("ix_managed_agent_ai_model_binding_managed_agent_id"),
        table_name="managed_agent_ai_model_binding",
    )
    op.drop_index(
        op.f("ix_managed_agent_ai_model_binding_account_id"),
        table_name="managed_agent_ai_model_binding",
    )
    op.drop_table("managed_agent_ai_model_binding")
    op.drop_column("managed_agent", "agent_kind")
