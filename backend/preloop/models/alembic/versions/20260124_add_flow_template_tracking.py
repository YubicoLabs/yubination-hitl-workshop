"""add_flow_template_tracking

Revision ID: 9a5b2c3d4e9i
Revises: 9a5b2c3d4e8h
Create Date: 2026-01-24

Adds template tracking fields to the flow table for syncing flows
with their source presets:
- source_preset_id: Links to the preset this flow was cloned from
- source_prompt_hash: Hash of original prompt for detecting customization
- source_tools_hash: Hash of original allowed_mcp_tools
- prompt_customized: Flag indicating user customized the prompt
- tools_customized: Flag indicating user customized the tools
- preset_update_available: Flag for UI notifications about updates
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9i"
down_revision: Union[str, None] = "9a5b2c3d4e8h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add template tracking columns to flow table."""
    # Add source_preset_id with foreign key to flow.id
    op.add_column(
        "flow",
        sa.Column(
            "source_preset_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_flow_source_preset_id",
        "flow",
        "flow",
        ["source_preset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_flow_source_preset_id"),
        "flow",
        ["source_preset_id"],
        unique=False,
    )

    # Add hash columns for detecting customization
    op.add_column(
        "flow",
        sa.Column("source_prompt_hash", sa.String(32), nullable=True),
    )
    op.add_column(
        "flow",
        sa.Column("source_tools_hash", sa.String(32), nullable=True),
    )

    # Add customization flags
    op.add_column(
        "flow",
        sa.Column(
            "prompt_customized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "flow",
        sa.Column(
            "tools_customized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Add update notification flag
    op.add_column(
        "flow",
        sa.Column(
            "preset_update_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Remove template tracking columns from flow table."""
    op.drop_column("flow", "preset_update_available")
    op.drop_column("flow", "tools_customized")
    op.drop_column("flow", "prompt_customized")
    op.drop_column("flow", "source_tools_hash")
    op.drop_column("flow", "source_prompt_hash")
    op.drop_index(op.f("ix_flow_source_preset_id"), table_name="flow")
    op.drop_constraint("fk_flow_source_preset_id", "flow", type_="foreignkey")
    op.drop_column("flow", "source_preset_id")
