"""add_multi_trigger_support

Revision ID: 9a5b2c3d4e9m
Revises: 9a5b2c3d4e9n
Create Date: 2026-02-01

This migration:

1. Replaces single-value flow trigger fields with array-based fields:
   - trigger_event_type -> trigger_event_types (array)
   - trigger_project_id -> trigger_project_ids (array)

2. Removes deprecated notification_channels column from approval_policy table.
   Approvers now configure their own notification preferences in user settings.

Existing data is migrated from the old fields to the new array fields.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9m"
down_revision: Union[str, None] = "9a5b2c3d4e9n"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add multi-trigger support columns and migrate data."""
    # Add trigger_event_types array column
    op.add_column(
        "flow",
        sa.Column(
            "trigger_event_types",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="Array of event types that trigger this flow",
        ),
    )

    # Add trigger_project_ids array column
    op.add_column(
        "flow",
        sa.Column(
            "trigger_project_ids",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="Array of project IDs that can trigger this flow",
        ),
    )

    # Migrate existing data from single-value fields to array fields
    op.execute(
        """
        UPDATE flow
        SET trigger_event_types = ARRAY[trigger_event_type]
        WHERE trigger_event_type IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE flow
        SET trigger_project_ids = ARRAY[trigger_project_id]
        WHERE trigger_project_id IS NOT NULL
        """
    )

    # Create indexes for efficient array lookups
    op.create_index(
        "ix_flow_trigger_event_types",
        "flow",
        ["trigger_event_types"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_flow_trigger_project_ids",
        "flow",
        ["trigger_project_ids"],
        unique=False,
        postgresql_using="gin",
    )

    # Drop old single-value columns
    op.drop_column("flow", "trigger_event_type")
    op.drop_column("flow", "trigger_project_id")

    # Drop deprecated notification_channels column from approval_policy
    # Approvers now configure their own notification preferences in user settings
    op.drop_column("approval_policy", "notification_channels")


def downgrade() -> None:
    """Remove multi-trigger support and restore single-value fields."""
    # Re-add notification_channels column to approval_policy
    op.add_column(
        "approval_policy",
        sa.Column(
            "notification_channels",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute("UPDATE approval_policy SET notification_channels = ARRAY['email']")

    # Re-add single-value columns
    op.add_column(
        "flow",
        sa.Column("trigger_event_type", sa.String(), nullable=True),
    )
    op.add_column(
        "flow",
        sa.Column("trigger_project_id", sa.String(), nullable=True),
    )

    # Migrate data back (take first element from array)
    op.execute(
        """
        UPDATE flow
        SET trigger_event_type = trigger_event_types[1]
        WHERE trigger_event_types IS NOT NULL AND array_length(trigger_event_types, 1) > 0
        """
    )
    op.execute(
        """
        UPDATE flow
        SET trigger_project_id = trigger_project_ids[1]
        WHERE trigger_project_ids IS NOT NULL AND array_length(trigger_project_ids, 1) > 0
        """
    )

    # Drop indexes
    op.drop_index("ix_flow_trigger_project_ids", table_name="flow")
    op.drop_index("ix_flow_trigger_event_types", table_name="flow")

    # Drop array columns
    op.drop_column("flow", "trigger_project_ids")
    op.drop_column("flow", "trigger_event_types")
