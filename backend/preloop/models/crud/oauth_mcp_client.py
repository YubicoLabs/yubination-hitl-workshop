"""CRUD operations for OAuthMCPClient model."""

import hashlib
import secrets
import time
from typing import Optional

from sqlalchemy.orm import Session

from ..models.oauth_mcp_client import OAuthMCPClient
from .base import CRUDBase


class CRUDOAuthMCPClient(CRUDBase[OAuthMCPClient]):
    """CRUD operations for OAuth MCP clients (Dynamic Client Registration)."""

    @staticmethod
    def generate_client_id() -> str:
        """Generate a unique client ID."""
        return f"preloop_{secrets.token_urlsafe(24)}"

    @staticmethod
    def generate_client_secret() -> str:
        """Generate a client secret."""
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_secret(secret: str) -> str:
        """Hash a client secret using SHA-256."""
        return hashlib.sha256(secret.encode()).hexdigest()

    def get_by_client_id(
        self, db: Session, *, client_id: str
    ) -> Optional[OAuthMCPClient]:
        """Get a client by its OAuth client_id."""
        return db.query(self.model).filter(self.model.client_id == client_id).first()

    def verify_client_secret(
        self, db_client: OAuthMCPClient, client_secret: str
    ) -> bool:
        """Verify a client secret against the stored hash."""
        if not db_client.client_secret_hash:
            return False
        return db_client.client_secret_hash == self.hash_secret(client_secret)

    def delete_by_client_id(
        self, db: Session, *, client_id: str
    ) -> Optional[OAuthMCPClient]:
        """Delete a client by its OAuth client_id."""
        obj = self.get_by_client_id(db, client_id=client_id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def cleanup_expired(self, db: Session) -> int:
        """Delete clients whose secrets have expired. Returns count deleted."""
        now = int(time.time())
        expired = (
            db.query(self.model)
            .filter(
                self.model.client_secret_expires_at.isnot(None),
                self.model.client_secret_expires_at > 0,
                self.model.client_secret_expires_at < now,
            )
            .all()
        )
        count = len(expired)
        for client in expired:
            db.delete(client)
        if count:
            db.commit()
        return count


crud_oauth_mcp_client = CRUDOAuthMCPClient(OAuthMCPClient)
