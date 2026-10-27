"""CRUD operations for RegistrationToken model."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..models.registration_token import RegistrationToken
from .base import CRUDBase


class CRUDRegistrationToken(CRUDBase[RegistrationToken]):
    """CRUD operations for registration tokens."""

    def create_token(
        self,
        db: Session,
        *,
        user_id: UUID,
        expiry_minutes: int = 15,
    ) -> RegistrationToken:
        """Create a new registration token.

        Args:
            db: Database session
            user_id: ID of the user this token is for
            expiry_minutes: Token expiry time in minutes (default: 15)

        Returns:
            Created registration token
        """
        # Generate secure random token
        token_value = secrets.token_urlsafe(32)

        # Calculate expiry
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

        # Create token
        db_obj = RegistrationToken(
            token=token_value,
            user_id=user_id,
            expires_at=expires_at,
            is_consumed=False,
        )

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_token(self, db: Session, *, token: str) -> Optional[RegistrationToken]:
        """Get registration token by token value.

        Args:
            db: Database session
            token: Token value to search for

        Returns:
            RegistrationToken if found, None otherwise
        """
        return (
            db.query(RegistrationToken).filter(RegistrationToken.token == token).first()
        )

    def validate_and_consume(
        self, db: Session, *, token: str
    ) -> Optional[RegistrationToken]:
        """Validate a token and mark it as consumed if valid.

        Args:
            db: Database session
            token: Token value to validate

        Returns:
            RegistrationToken if valid and consumed, None if invalid or expired
        """
        token_obj = self.get_by_token(db, token=token)

        if not token_obj:
            return None

        # Check if valid (not consumed and not expired)
        if not token_obj.is_valid:
            return None

        # Mark as consumed
        token_obj.consume()
        db.add(token_obj)
        db.commit()
        db.refresh(token_obj)

        return token_obj

    def cleanup_expired(self, db: Session) -> int:
        """Clean up expired registration tokens.

        Args:
            db: Database session

        Returns:
            Number of tokens deleted
        """
        now = datetime.now(timezone.utc)

        # Delete expired tokens
        deleted_count = (
            db.query(RegistrationToken)
            .filter(RegistrationToken.expires_at < now)
            .delete()
        )

        db.commit()
        return deleted_count


# Create singleton instance
crud_registration_token = CRUDRegistrationToken(RegistrationToken)
