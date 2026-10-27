"""User invitation model for inviting new users to accounts."""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Configurable invitation expiry (default: 7 days)
INVITATION_EXPIRY_DAYS = int(os.environ.get("INVITATION_EXPIRY_DAYS", "7"))

if TYPE_CHECKING:
    from .account import Account
    from .user import User


class UserInvitationStatus(str):
    """Status of a user invitation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class UserInvitation(Base):
    """User invitation for inviting new users to an account.

    When an admin invites a new user, an invitation is created with a
    unique token sent via email. The recipient can click the link to
    accept the invitation and create their account.

    Attributes:
        id: Unique identifier for the invitation.
        account_id: The account the user is being invited to.
        email: Email address of the invitee.
        invited_by: User who sent the invitation.
        token: Secure token for the invitation link.
        status: Current status ('pending', 'accepted', 'expired', 'cancelled').
        role_ids: List of role IDs to assign when invitation is accepted.
        team_ids: List of team IDs to assign when invitation is accepted.
        created_at: When the invitation was created.
        expires_at: When the invitation expires.
        accepted_at: When the invitation was accepted (if applicable).
        accepted_by: User created when invitation was accepted (if applicable).
    """

    __tablename__ = "user_invitation"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The account the user is being invited to",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address of the invitee",
    )

    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who sent the invitation",
    )

    token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
        comment="Secure token for the invitation link",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserInvitationStatus.PENDING,
        index=True,
        comment="Current status of the invitation",
    )

    # Role assignment (stored as comma-separated UUIDs for simplicity)
    role_ids: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Comma-separated role UUIDs to assign on acceptance",
    )

    # Team assignment (stored as comma-separated UUIDs for simplicity)
    team_ids: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Comma-separated team UUIDs to assign on acceptance",
    )

    # Timestamps

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: (
            datetime.now(timezone.utc) + timedelta(days=INVITATION_EXPIRY_DAYS)
        ),
        comment="When the invitation expires",
    )

    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the invitation was accepted",
    )

    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="User created when invitation was accepted",
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account")
    inviter: Mapped["User"] = relationship("User", foreign_keys=[invited_by])
    accepter: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[accepted_by]
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<UserInvitation(email={self.email}, status={self.status})>"

    @property
    def is_expired(self) -> bool:
        """Check if the invitation is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if the invitation is valid (pending and not expired)."""
        return self.status == UserInvitationStatus.PENDING and not self.is_expired
