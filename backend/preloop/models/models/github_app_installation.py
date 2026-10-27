"""OAuth App Installation model.

Generic model for OAuth App installations that can be used across different
providers (GitHub, GitLab, etc.).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import BigInteger, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, DateTime

from .base import Base

if TYPE_CHECKING:
    from .account import Account
    from .github_oauth_token import OAuthToken
    from .tracker import Tracker


class OAuthAppInstallation(Base):
    """OAuth App Installation model.

    Represents an OAuth App installation on an organization or user account.
    This generic model supports multiple providers (GitHub, GitLab, etc.).
    """

    __tablename__ = "oauth_app_installation"

    # Provider identification
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="OAuth provider: 'github', 'gitlab', etc.",
    )

    # Provider-specific installation details
    external_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Provider's installation/application ID",
    )
    target_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of target: 'Organization', 'User', 'Group', etc.",
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Provider's organization/user/group ID",
    )
    target_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Organization/user/group name or login",
    )

    # Permissions granted to the installation
    permissions: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Permissions/scopes granted to this installation",
    )

    # Resource access settings (e.g., repository selection for GitHub)
    resource_selection: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Resource selection mode: 'all', 'selected', etc.",
    )
    selected_resources: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="List of selected resource IDs if selection='selected'",
    )

    # Suspension status
    suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp when installation was suspended, if any",
    )
    suspended_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Username who suspended the installation",
    )

    # Provider-specific metadata
    provider_metadata: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Additional provider-specific metadata",
    )

    # Foreign keys
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account", back_populates="oauth_app_installations"
    )
    oauth_tokens: Mapped[List["OAuthToken"]] = relationship(
        "OAuthToken",
        back_populates="installation",
        cascade="all, delete-orphan",
    )
    trackers: Mapped[List["Tracker"]] = relationship(
        "Tracker",
        back_populates="oauth_installation",
        foreign_keys="Tracker.oauth_installation_id",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<OAuthAppInstallation(id={self.id}, provider={self.provider}, external_id={self.external_id}, target={self.target_name})>"

    @property
    def is_suspended(self) -> bool:
        """Check if the installation is currently suspended."""
        return self.suspended_at is not None

    # Backward compatibility aliases for GitHub-specific code
    @property
    def installation_id(self) -> int:
        """Alias for external_id (GitHub compatibility)."""
        return self.external_id

    @property
    def target_login(self) -> str:
        """Alias for target_name (GitHub compatibility)."""
        return self.target_name

    @property
    def repository_selection(self) -> Optional[str]:
        """Alias for resource_selection (GitHub compatibility)."""
        return self.resource_selection

    @property
    def selected_repositories(self) -> Optional[List]:
        """Alias for selected_resources (GitHub compatibility)."""
        return self.selected_resources


# Backward compatibility alias
GitHubAppInstallation = OAuthAppInstallation
