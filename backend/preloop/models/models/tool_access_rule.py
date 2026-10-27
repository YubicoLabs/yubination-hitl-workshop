"""Tool access rule model for flexible tool access control with multiple rules per tool."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Boolean

from .base import Base

if TYPE_CHECKING:
    from .account import Account
    from .tool_configuration import ApprovalWorkflow, ToolConfiguration


class ToolAccessRule(Base):
    """Access control rule for a tool with priority-based evaluation.

    Tool access rules allow fine-grained control over tool access and approval
    requirements. Unlike the previous 1:1 ToolApprovalCondition model, this supports
    multiple rules per tool with priority-based evaluation.

    Rules are evaluated in priority order (lower = first). The first matching rule
    determines the action. If no rules match, the tool's default behavior applies.

    Supported actions:
        - 'allow': Allow execution without approval
        - 'deny': Deny execution entirely
        - 'require_approval': Require approval before execution

    Condition types:
        - 'simple': Simple key-value matching (future)
        - 'cel': CEL (Common Expression Language) expressions

    Example CEL expressions:
        - "args.amount > 1000" - High-value transactions
        - "args.environment == 'production'" - Production deployments
        - "args.priority == 'critical' || args.priority == 'high'" - High priority

    Attributes:
        id: Unique identifier for the rule (inherited from Base).
        account_id: The account this rule belongs to.
        tool_configuration_id: Reference to the tool configuration (NOT unique - multiple rules allowed).
        condition_expression: Expression to evaluate (CEL or simple).
        condition_type: Type of expression ('simple' or 'cel').
        action: Action to take when condition matches ('allow', 'deny', 'require_approval').
        priority: Evaluation order (lower = first, default 0).
        description: Optional description of what this rule does.
        is_enabled: Whether the rule is currently active.
        created_at: When the rule was created (inherited from Base).
        updated_at: When the rule was last modified (inherited from Base).
    """

    __tablename__ = "tool_access_rules"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The account this rule belongs to",
    )

    tool_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_configuration.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # NOT unique - allows multiple rules per tool
        comment="Reference to the tool configuration",
    )

    condition_expression: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Expression to evaluate (CEL or simple format)",
    )

    condition_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="simple",
        comment="Type of condition: 'simple' or 'cel'",
    )

    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Action when condition matches: 'allow', 'deny', 'require_approval'",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
        comment="Evaluation order (lower = evaluated first)",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of what this rule does",
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether the rule is currently active",
    )

    # Approval workflow reference (only used when action='require_approval')
    approval_workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_workflow.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Approval workflow to use when action is 'require_approval'",
    )

    # Note: created_at and updated_at are inherited from Base class

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account", back_populates="tool_access_rules"
    )
    tool_configuration: Mapped["ToolConfiguration"] = relationship(
        "ToolConfiguration",
        back_populates="access_rules",
    )
    approval_workflow: Mapped[Optional["ApprovalWorkflow"]] = relationship(
        "ApprovalWorkflow",
        foreign_keys=[approval_workflow_id],
    )

    def __repr__(self) -> str:
        """String representation."""
        status = "enabled" if self.is_enabled else "disabled"
        expr = (
            f", expr='{self.condition_expression[:30]}...'"
            if self.condition_expression and len(self.condition_expression) > 30
            else f", expr='{self.condition_expression}'"
            if self.condition_expression
            else ""
        )
        return f"<ToolAccessRule(action={self.action}, priority={self.priority}, type={self.condition_type}{expr}, {status})>"
