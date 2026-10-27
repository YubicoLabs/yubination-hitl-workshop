"""add_instances_table

Revision ID: 8f4a1b2c3d5e
Revises: 3c2b9f2d0c4a
Create Date: 2026-01-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8f4a1b2c3d5e"
down_revision: Union[str, None] = "3c2b9f2d0c4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create instances table for tracking Preloop installations."""
    op.create_table(
        "instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instance_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column(
            "edition", sa.String(length=20), nullable=False, server_default="oss"
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "check_count", sa.String(length=20), nullable=False, server_default="1"
        ),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_uuid"),
    )
    op.create_index(
        op.f("ix_instances_instance_uuid"),
        "instances",
        ["instance_uuid"],
        unique=True,
    )
    op.create_index(
        op.f("ix_instances_last_seen"),
        "instances",
        ["last_seen"],
        unique=False,
    )
    op.create_index(
        op.f("ix_instances_is_active"),
        "instances",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop instances table."""
    op.drop_index(op.f("ix_instances_is_active"), table_name="instances")
    op.drop_index(op.f("ix_instances_last_seen"), table_name="instances")
    op.drop_index(op.f("ix_instances_instance_uuid"), table_name="instances")
    op.drop_table("instances")
