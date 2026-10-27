"""policy_engine_enhancements

Revision ID: 9a5b2c3d4e9n
Revises: 9a5b2c3d4e9l
Create Date: 2026-02-01

This migration combines multiple enhancements to the policy engine:

1. Tool Access Rules (replacing tool_approval_conditions):
   - Creates new tool_access_rules table with support for multiple rules per tool
   - Supports allow/deny/require_approval actions with priority-based evaluation
   - Migrates existing data from tool_approval_conditions
   - Drops the old tool_approval_conditions table

2. Policy Versioning:
   - Creates policy_snapshot table for storing complete policy snapshots
   - Enables version tracking, tagging, and rollback capabilities

3. AI-Driven Approvals:
   - Adds AI approval fields to approval_policy table
   - Supports AI-based approval decisions with confidence thresholds and fallbacks
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9n"
down_revision: Union[str, None] = "9a5b2c3d4e9l"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply all policy engine enhancements."""
    # ==========================================================================
    # Part 1: Tool Access Rules
    # ==========================================================================

    # Create the new tool_access_rules table
    op.create_table(
        "tool_access_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tool_configuration_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("condition_expression", sa.Text(), nullable=True),
        sa.Column(
            "condition_type",
            sa.String(length=20),
            nullable=False,
            server_default="simple",
        ),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "approval_policy_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Approval policy to use when action is 'require_approval'",
        ),
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
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_tool_access_rules_account_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_configuration_id"],
            ["tool_configuration.id"],
            name="fk_tool_access_rules_tool_configuration_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approval_policy_id"],
            ["approval_policy.id"],
            name="fk_tool_access_rules_approval_policy_id",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for tool_access_rules
    op.create_index(
        op.f("ix_tool_access_rules_account_id"),
        "tool_access_rules",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_access_rules_tool_configuration_id"),
        "tool_access_rules",
        ["tool_configuration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_access_rules_priority"),
        "tool_access_rules",
        ["priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_access_rules_is_enabled"),
        "tool_access_rules",
        ["is_enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_access_rules_approval_policy_id"),
        "tool_access_rules",
        ["approval_policy_id"],
        unique=False,
    )

    # Migrate existing data from tool_approval_conditions
    # Each existing condition becomes a 'require_approval' rule with 'cel' type
    op.execute(
        """
        INSERT INTO tool_access_rules (
            id,
            account_id,
            tool_configuration_id,
            condition_expression,
            condition_type,
            action,
            priority,
            description,
            is_enabled,
            created_at,
            updated_at
        )
        SELECT
            id,
            account_id,
            tool_configuration_id,
            condition_expression,
            'cel',
            'require_approval',
            0,
            COALESCE(description, name),
            is_enabled,
            created_at,
            updated_at
        FROM tool_approval_conditions
        """
    )

    # Drop the old tool_approval_conditions table (with its indexes first)
    op.drop_index(
        op.f("ix_tool_approval_conditions_tool_configuration_id"),
        table_name="tool_approval_conditions",
    )
    op.drop_index(
        op.f("ix_tool_approval_conditions_is_enabled"),
        table_name="tool_approval_conditions",
    )
    op.drop_index(
        op.f("ix_tool_approval_conditions_condition_type"),
        table_name="tool_approval_conditions",
    )
    op.drop_index(
        op.f("ix_tool_approval_conditions_account_id"),
        table_name="tool_approval_conditions",
    )
    op.drop_table("tool_approval_conditions")

    # ==========================================================================
    # Part 2: Policy Snapshot Table
    # ==========================================================================

    op.create_table(
        "policy_snapshot",
        # Primary key
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # Account reference
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # Version info
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        # Complete snapshot as JSONB
        sa.Column(
            "snapshot_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        # Metadata
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Status
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        # Summary stats for quick reference
        sa.Column(
            "mcp_servers_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "policies_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "tools_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Timestamps
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
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_policy_snapshot_account_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
            name="fk_policy_snapshot_created_by_user_id",
            ondelete="SET NULL",
        ),
        # Unique constraint on (account_id, version_number)
        sa.UniqueConstraint(
            "account_id",
            "version_number",
            name="uq_policy_snapshot_account_version",
        ),
    )

    # Create indexes for policy_snapshot
    op.create_index(
        op.f("ix_policy_snapshot_account_id"),
        "policy_snapshot",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_snapshot_account_is_active",
        "policy_snapshot",
        ["account_id", "is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_policy_snapshot_version_number"),
        "policy_snapshot",
        ["version_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_policy_snapshot_tag"),
        "policy_snapshot",
        ["tag"],
        unique=False,
    )

    # ==========================================================================
    # Part 3: AI Approval Fields
    # ==========================================================================

    # Add approval_mode column
    op.add_column(
        "approval_policy",
        sa.Column(
            "approval_mode",
            sa.String(length=20),
            nullable=False,
            server_default="standard",
            comment="Approval mode: 'standard' (human) or 'ai_driven' (AI makes decision)",
        ),
    )

    # Add ai_model column
    op.add_column(
        "approval_policy",
        sa.Column(
            "ai_model",
            sa.String(length=100),
            nullable=True,
            comment="AI model for approval decisions (e.g., 'gpt-5.4', 'claude-sonnet-4.7')",
        ),
    )

    # Add ai_guidelines column
    op.add_column(
        "approval_policy",
        sa.Column(
            "ai_guidelines",
            sa.Text(),
            nullable=True,
            comment="User-defined guidelines for AI approval decisions",
        ),
    )

    # Add ai_context column (JSONB for structured data)
    op.add_column(
        "approval_policy",
        sa.Column(
            "ai_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Additional context for AI decisions (e.g., examples, constraints)",
        ),
    )

    # Add ai_confidence_threshold column
    op.add_column(
        "approval_policy",
        sa.Column(
            "ai_confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.8",
            comment="Minimum confidence score required for AI to make a decision",
        ),
    )

    # Add ai_fallback_behavior column
    op.add_column(
        "approval_policy",
        sa.Column(
            "ai_fallback_behavior",
            sa.String(length=20),
            nullable=False,
            server_default="escalate",
            comment="Behavior when AI confidence is below threshold: 'escalate', 'approve', 'deny'",
        ),
    )

    # Add escalation_policy_id column (self-referential foreign key)
    op.add_column(
        "approval_policy",
        sa.Column(
            "escalation_policy_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Policy to escalate to when fallback_behavior='escalate'",
        ),
    )

    # Add foreign key constraint for escalation_policy_id
    op.create_foreign_key(
        "fk_approval_policy_escalation_policy_id",
        "approval_policy",
        "approval_policy",
        ["escalation_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add index for approval_mode for efficient filtering
    op.create_index(
        "ix_approval_policy_approval_mode",
        "approval_policy",
        ["approval_mode"],
        unique=False,
    )

    # Add index for escalation_policy_id for efficient lookups
    op.create_index(
        "ix_approval_policy_escalation_policy_id",
        "approval_policy",
        ["escalation_policy_id"],
        unique=False,
    )

    # ── AI decision tracking on approval_request ──
    op.add_column(
        "approval_request",
        sa.Column(
            "decided_by_ai",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this request was decided by AI",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "ai_model",
            sa.String(length=100),
            nullable=True,
            comment="AI model that made the decision (if decided_by_ai=True)",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "ai_confidence",
            sa.Float(),
            nullable=True,
            comment="AI confidence score for the decision (0.0-1.0)",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "ai_reasoning",
            sa.Text(),
            nullable=True,
            comment="AI's reasoning for the approval/denial decision",
        ),
    )


def downgrade() -> None:
    """Revert all policy engine enhancements."""
    # ==========================================================================
    # Part 3a: Remove AI decision tracking from approval_request
    # ==========================================================================
    op.drop_column("approval_request", "ai_reasoning")
    op.drop_column("approval_request", "ai_confidence")
    op.drop_column("approval_request", "ai_model")
    op.drop_column("approval_request", "decided_by_ai")

    # ==========================================================================
    # Part 3b: Remove AI Approval Fields from approval_policy
    # ==========================================================================

    # Drop indexes
    op.drop_index(
        "ix_approval_policy_escalation_policy_id",
        table_name="approval_policy",
    )
    op.drop_index(
        "ix_approval_policy_approval_mode",
        table_name="approval_policy",
    )

    # Drop foreign key constraint
    op.drop_constraint(
        "fk_approval_policy_escalation_policy_id",
        "approval_policy",
        type_="foreignkey",
    )

    # Drop columns in reverse order
    op.drop_column("approval_policy", "escalation_policy_id")
    op.drop_column("approval_policy", "ai_fallback_behavior")
    op.drop_column("approval_policy", "ai_confidence_threshold")
    op.drop_column("approval_policy", "ai_context")
    op.drop_column("approval_policy", "ai_guidelines")
    op.drop_column("approval_policy", "ai_model")
    op.drop_column("approval_policy", "approval_mode")

    # ==========================================================================
    # Part 2: Drop Policy Snapshot Table
    # ==========================================================================

    op.drop_index(
        op.f("ix_policy_snapshot_tag"),
        table_name="policy_snapshot",
    )
    op.drop_index(
        op.f("ix_policy_snapshot_version_number"),
        table_name="policy_snapshot",
    )
    op.drop_index(
        "ix_policy_snapshot_account_is_active",
        table_name="policy_snapshot",
    )
    op.drop_index(
        op.f("ix_policy_snapshot_account_id"),
        table_name="policy_snapshot",
    )
    op.drop_table("policy_snapshot")

    # ==========================================================================
    # Part 1: Recreate tool_approval_conditions, migrate data, drop tool_access_rules
    # ==========================================================================

    # Recreate the old tool_approval_conditions table
    op.create_table(
        "tool_approval_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tool_configuration_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "condition_type",
            sa.String(length=50),
            nullable=False,
            server_default="argument",
        ),
        sa.Column("condition_expression", sa.Text(), nullable=True),
        sa.Column(
            "condition_config", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
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
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_configuration_id"],
            ["tool_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tool_configuration_id"),
    )

    # Recreate indexes
    op.create_index(
        op.f("ix_tool_approval_conditions_account_id"),
        "tool_approval_conditions",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_approval_conditions_condition_type"),
        "tool_approval_conditions",
        ["condition_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_approval_conditions_is_enabled"),
        "tool_approval_conditions",
        ["is_enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_approval_conditions_tool_configuration_id"),
        "tool_approval_conditions",
        ["tool_configuration_id"],
        unique=True,
    )

    # Migrate data back (only 'require_approval' rules with unique tool_configuration_id)
    # Note: Rules with allow/deny actions or multiple rules per tool will be lost
    op.execute(
        """
        INSERT INTO tool_approval_conditions (
            id,
            account_id,
            tool_configuration_id,
            name,
            description,
            is_enabled,
            condition_type,
            condition_expression,
            condition_config,
            created_at,
            updated_at
        )
        SELECT
            id,
            account_id,
            tool_configuration_id,
            NULL,
            description,
            is_enabled,
            'argument',
            condition_expression,
            NULL,
            created_at,
            updated_at
        FROM tool_access_rules
        WHERE action = 'require_approval'
        AND tool_configuration_id IN (
            SELECT tool_configuration_id
            FROM tool_access_rules
            WHERE action = 'require_approval'
            GROUP BY tool_configuration_id
            HAVING COUNT(*) = 1
        )
        """
    )

    # Drop the tool_access_rules table
    op.drop_index(
        op.f("ix_tool_access_rules_approval_policy_id"),
        table_name="tool_access_rules",
    )
    op.drop_index(
        op.f("ix_tool_access_rules_is_enabled"),
        table_name="tool_access_rules",
    )
    op.drop_index(
        op.f("ix_tool_access_rules_priority"),
        table_name="tool_access_rules",
    )
    op.drop_index(
        op.f("ix_tool_access_rules_tool_configuration_id"),
        table_name="tool_access_rules",
    )
    op.drop_index(
        op.f("ix_tool_access_rules_account_id"),
        table_name="tool_access_rules",
    )
    op.drop_table("tool_access_rules")
