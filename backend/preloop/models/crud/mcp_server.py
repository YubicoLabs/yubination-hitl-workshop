"""CRUD operations for MCPServer model."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models
from .base import CRUDBase


class CRUDMCPServer(CRUDBase[models.MCPServer]):
    """CRUD operations for MCPServer model."""

    def __init__(self):
        """Initialize with the MCPServer model."""
        super().__init__(model=models.MCPServer)

    def get(
        self, db: Session, id: UUID, account_id: Optional[str] = None
    ) -> Optional[models.MCPServer]:
        """Retrieve an MCP server by its ID.

        Args:
            db: The database session.
            id: The ID of the MCP server to retrieve.
            account_id: The ID of the account associated with the server. Optional.

        Returns:
            The MCP server object if found, otherwise None.
        """
        query = db.query(self.model).filter(self.model.id == id)

        if account_id:
            query = query.filter(self.model.account_id == account_id)

        return query.first()

    def get_by_name(
        self, db: Session, account_id: str, name: str
    ) -> Optional[models.MCPServer]:
        """Retrieve an MCP server by name and account.

        Args:
            db: The database session.
            name: The name of the MCP server.
            account_id: The ID of the account.

        Returns:
            The MCP server object if found, otherwise None.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.name == name,
            )
            .first()
        )

    def get_multi_by_account(
        self,
        db: Session,
        account_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[models.MCPServer]:
        """Retrieve MCP servers for a specific account.

        Args:
            db: The database session.
            account_id: The ID of the account.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of MCP server objects.
        """
        return (
            db.query(self.model)
            .filter(self.model.account_id == account_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_by_account(
        self,
        db: Session,
        account_id: str,
    ) -> List[models.MCPServer]:
        """Retrieve active MCP servers for a specific account.

        Args:
            db: The database session.
            account_id: The ID of the account.

        Returns:
            List of active MCP server objects.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.status == "active",
            )
            .all()
        )

    def remove(
        self, db: Session, *, id: UUID, account_id: str
    ) -> Optional[models.MCPServer]:
        """Remove an MCP server by its ID.

        Args:
            db: The database session.
            id: The ID of the MCP server to remove.
            account_id: The ID of the account.

        Returns:
            The removed MCP server object if found and deleted, otherwise None.
        """
        db_server = (
            db.query(self.model)
            .filter(
                self.model.id == id,
                self.model.account_id == account_id,
            )
            .first()
        )
        if db_server:
            db.delete(db_server)
            db.commit()
        return db_server
