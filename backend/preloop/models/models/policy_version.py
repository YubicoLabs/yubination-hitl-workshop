"""Policy version model for storing complete policy snapshots."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Boolean

from .base import Base

if TYPE_CHECKING:
    from .account import Account
    from .user import User


class PolicyVersion(Base):
    """Policy version model for storing complete policy snapshots.

    This table stores versioned snapshots of all policy-related configurations
    for an account. Each version captures the complete state of MCP servers,
    tools, approval workflows, access rules, and defaults at a point in time.

    Versions are auto-incrementing per account and can be optionally tagged
    for easy reference (e.g., "v1.0", "production", "before-migration").

    Attributes:
        id: Unique identifier for the version (inherited from Base).
        account_id: The account this version belongs to.
        version_number: Auto-incrementing version number per account.
        tag: Optional tag like "v1.0", "production", "before-migration".
        description: Optional description of the changes in this version.
        snapshot: Complete JSONB snapshot containing all policy configurations.
        created_at: When the version was created (inherited from Base).
        created_by_id: Optional reference to the user who created this version.
        is_active: Whether this is the currently active version.
        applied_at: When this version was last applied/activated.
        last_used_at: When this version was last accessed (for pruning).
        updated_at: When the version was last updated (inherited from Base).
    """

    __tablename__ = "policy_version"

    # Account reference
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The account this version belongs to",
    )

    # Version info
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Auto-incrementing version number per account",
    )

    tag: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Optional tag like 'v1.0', 'production', 'before-migration'",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of changes in this version",
    )

    # Complete snapshot as JSONB
    # Contains: mcp_servers, tools, approval_workflows, access_rules, defaults
    snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete JSONB snapshot of all policy configurations",
    )

    # Metadata
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this version",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this is the currently active version",
    )

    applied_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When this version was last applied/activated",
    )

    # For pruning
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When this version was last accessed",
    )

    # Table constraints
    __table_args__ = (
        # Unique constraint on (account_id, version_number)
        UniqueConstraint(
            "account_id",
            "version_number",
            name="uq_policy_version_account_version",
        ),
        # Partial unique constraint on (account_id, tag) where tag is not null
        # This is implemented as a unique index with a WHERE clause
        Index(
            "ix_policy_version_account_tag_unique",
            "account_id",
            "tag",
            unique=True,
            postgresql_where=(tag.isnot(None)),
        ),
        # Composite index on (account_id, is_active) for efficient lookups
        Index(
            "ix_policy_version_account_is_active",
            "account_id",
            "is_active",
        ),
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="policy_versions",
    )

    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
    )

    def __repr__(self) -> str:
        """String representation."""
        tag_str = f", tag='{self.tag}'" if self.tag else ""
        active_str = " (active)" if self.is_active else ""
        return (
            f"<PolicyVersion(account_id={self.account_id}, "
            f"version={self.version_number}{tag_str}{active_str})>"
        )
