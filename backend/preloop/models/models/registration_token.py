"""Registration token model for mobile device QR code registration."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class RegistrationToken(Base):
    """Registration token for mobile device registration via QR code.

    Attributes:
        id: The unique identifier for the token.
        token: The actual token value (random URL-safe string).
        user_id: The ID of the user this token is for.
        expires_at: When the token expires.
        used_at: When the token was used (None if not yet used).
        is_consumed: Whether the token has been consumed (one-time use).
        created_at: When the token was created.
    """

    __tablename__ = "registration_token"

    # Token details
    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # User relationship
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The user this token is for",
    )

    # Expiry and usage tracking
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="Token expiration time"
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the token was used (None if not yet used)",
    )
    is_consumed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Whether token has been used"
    )

    def __repr__(self) -> str:
        """Return a string representation of the token.

        Returns:
            String representation of the token.
        """
        return f"<RegistrationToken {self.token[:8]}... for user {self.user_id}>"

    @property
    def is_expired(self) -> bool:
        """Check if the token is expired.

        Returns:
            True if the token expiration time is in the past.
        """
        # Ensure expires_at is timezone-aware for comparison
        expires_at_aware = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=timezone.utc)
        )
        return expires_at_aware < datetime.now(timezone.utc)

    @property
    def is_valid(self) -> bool:
        """Check if the token is valid (not consumed and not expired).

        Returns:
            True if the token is valid and can be used.
        """
        return not self.is_consumed and not self.is_expired

    def consume(self) -> None:
        """Mark the token as consumed and set the used_at timestamp."""
        self.is_consumed = True
        self.used_at = datetime.now(timezone.utc)
