"""CRUD operations for OAuthAppInstallation model."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..models.github_app_installation import OAuthAppInstallation
from .base import CRUDBase


class CRUDOAuthAppInstallation(CRUDBase[OAuthAppInstallation]):
    """CRUD operations for OAuthAppInstallation model."""

    def get_by_provider_and_external_id(
        self,
        db: Session,
        *,
        provider: str,
        external_id: int,
        account_id: Optional[UUID] = None,
    ) -> Optional[OAuthAppInstallation]:
        """Get installation by provider and external ID.

        Args:
            db: Database session
            provider: OAuth provider (e.g., 'github')
            external_id: Provider's installation ID
            account_id: Optional account ID to filter by

        Returns:
            Installation if found, None otherwise
        """
        query = db.query(self.model).filter(
            self.model.provider == provider,
            self.model.external_id == external_id,
        )
        if account_id:
            query = query.filter(self.model.account_id == account_id)
        return query.first()

    def get_by_provider_and_account(
        self,
        db: Session,
        *,
        provider: str,
        account_id: UUID,
    ) -> List[OAuthAppInstallation]:
        """Get all installations for a provider and account.

        Args:
            db: Database session
            provider: OAuth provider (e.g., 'github')
            account_id: Account ID

        Returns:
            List of installations
        """
        return (
            db.query(self.model)
            .filter(
                self.model.provider == provider,
                self.model.account_id == account_id,
            )
            .all()
        )

    def get_by_id_provider_and_account(
        self,
        db: Session,
        *,
        id: UUID,
        provider: str,
        account_id: UUID,
    ) -> Optional[OAuthAppInstallation]:
        """Get installation by ID, provider, and account.

        Args:
            db: Database session
            id: Installation UUID
            provider: OAuth provider (e.g., 'github')
            account_id: Account ID

        Returns:
            Installation if found, None otherwise
        """
        return (
            db.query(self.model)
            .filter(
                self.model.id == id,
                self.model.provider == provider,
                self.model.account_id == account_id,
            )
            .first()
        )


crud_oauth_app_installation = CRUDOAuthAppInstallation(OAuthAppInstallation)
