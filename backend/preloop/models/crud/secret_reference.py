"""CRUD operations for SecretReference."""

from typing import Optional

from sqlalchemy.orm import Session

from ..models.secret_reference import SecretReference
from .base import CRUDBase


class CRUDSecretReference(CRUDBase[SecretReference]):
    """CRUD class for SecretReference operations."""

    def get_for_account(
        self, db: Session, *, secret_id: str, account_id: str
    ) -> Optional[SecretReference]:
        """Get a secret reference scoped to an account."""
        return (
            db.query(self.model)
            .filter(self.model.id == secret_id, self.model.account_id == account_id)
            .first()
        )


crud_secret_reference = CRUDSecretReference(SecretReference)
