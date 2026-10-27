"""add_event_tracking_and_superuser

Revision ID: a7421af76e5f
Revises: 15f8bd4254a2
Create Date: 2025-11-18 00:18:00.947994

Unified migration combining:
- Event tracking table (previously user_session_activity)
- is_superuser column on user table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7421af76e5f"
down_revision: Union[str, None] = "15f8bd4254a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create event table for tracking user sessions and activities
    # Tracks both user session events and system/async events
    op.create_table(
        "event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # Account and user identification
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Account this event belongs to",
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="WebSocket session ID (null for system events)",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who triggered event (null for system events)",
        ),
        sa.Column(
            "fingerprint",
            sa.String(length=128),
            nullable=True,
            comment="Browser fingerprint for anonymous users",
        ),
        # Event classification
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Connection metadata (for session_start/session_end events)
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        # Page view data (for page_view events)
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("referrer", sa.String(length=512), nullable=True),
        # Action data (for action events)
        sa.Column("action", sa.String(length=128), nullable=True),
        sa.Column("element", sa.String(length=128), nullable=True),
        sa.Column("element_text", sa.String(length=256), nullable=True),
        # Conversion tracking (for conversion events)
        sa.Column("conversion_event", sa.String(length=128), nullable=True),
        sa.Column("conversion_value", sa.Float(), nullable=True),
        # Flexible metadata
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Standard timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Foreign keys
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient querying
    op.create_index("ix_event_session_id", "event", ["session_id"])
    op.create_index("ix_event_user_id", "event", ["user_id"])
    op.create_index("ix_event_account_id", "event", ["account_id"])
    op.create_index("ix_event_fingerprint", "event", ["fingerprint"])
    op.create_index("ix_event_event_type", "event", ["event_type"])
    op.create_index("ix_event_timestamp", "event", ["timestamp"])
    op.create_index("ix_event_ip_address", "event", ["ip_address"])
    op.create_index("ix_event_path", "event", ["path"])
    op.create_index("ix_event_action", "event", ["action"])
    op.create_index("ix_event_conversion_event", "event", ["conversion_event"])

    # Add is_superuser column to user table
    op.add_column(
        "user",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Whether the user has superuser/admin privileges",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove is_superuser column from user table
    op.drop_column("user", "is_superuser")

    # Drop indexes for event table
    op.drop_index("ix_event_conversion_event", "event")
    op.drop_index("ix_event_action", "event")
    op.drop_index("ix_event_path", "event")
    op.drop_index("ix_event_ip_address", "event")
    op.drop_index("ix_event_timestamp", "event")
    op.drop_index("ix_event_event_type", "event")
    op.drop_index("ix_event_fingerprint", "event")
    op.drop_index("ix_event_account_id", "event")
    op.drop_index("ix_event_user_id", "event")
    op.drop_index("ix_event_session_id", "event")

    # Drop event table
    op.drop_table("event")
