"""Tool approval condition model for conditional approval based on tool arguments."""

import uuid
from typing import TYPE_CHECKING, Dict, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, JSON

from .base import Base

if TYPE_CHECKING:
    pass


class ToolApprovalCondition(Base):
    """Conditional approval rule for a tool based on arguments.

    Tool approval conditions allow fine-grained control over when tools require approval.
    Instead of always requiring approval, conditions can evaluate tool arguments
    using CEL (Common Expression Language) expressions.

    This model has a 1:1 relationship with ToolConfiguration. Each tool can have
    at most one condition. For complex logic, use CEL's AND/OR operators.

    Example CEL expressions:
        - "args.amount > 1000" - Require approval for transactions over $1000
        - "args.environment == 'production'" - Require approval for production deployments
        - "args.priority == 'critical' || args.priority == 'high'" - Require approval for high priority

    Attributes:
        id: Unique identifier for the condition (inherited from Base).
        account_id: The account this condition belongs to.
        tool_configuration_id: Reference to the tool configuration (unique, 1:1).
        name: Optional human-readable name for the condition.
        description: Optional description of what this condition does.
        is_enabled: Whether the condition is currently active.
        condition_type: Type of condition evaluator ('argument', 'state', 'risk').
        condition_expression: CEL expression for conditional approval (proprietary feature).
        condition_config: Additional configuration for the condition evaluator.
        created_at: When the condition was created (inherited from Base).
        updated_at: When the condition was last modified (inherited from Base).
    """

    __tablename__ = "tool_approval_conditions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The account this condition belongs to",
    )

    tool_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_configuration.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1:1 relationship
        index=True,
        comment="Reference to the tool configuration (1:1 relationship)",
    )

    # Condition identification (optional)
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional human-readable name for the condition",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of what this condition does",
    )

    # Condition status
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether the condition is currently active",
    )

    # Condition configuration
    condition_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="argument",
        index=True,
        comment="Type of condition evaluator: 'argument', 'state', 'risk'",
    )

    condition_expression: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="CEL expression for conditional approval (proprietary feature)",
    )

    condition_config: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional configuration for the condition evaluator",
    )

    # Note: created_at and updated_at are inherited from Base class

    # Relationships
    # NOTE: Relationships removed — the tool_approval_conditions table was dropped
    # by migration 20260201_policy_engine_enhancements and replaced by tool_access_rules.
    # This model is kept only for backward compatibility with existing CRUD/endpoint code.

    def __repr__(self) -> str:
        """String representation."""
        status = "enabled" if self.is_enabled else "disabled"
        expr = (
            f", expr='{self.condition_expression[:30]}...'"
            if self.condition_expression
            else ""
        )
        return f"<ToolApprovalCondition(name={self.name}, type={self.condition_type}{expr}, {status})>"
