"""CRUD operations for Webhook model."""

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.webhook import Webhook
from ..models.project import Project
from ..models.organization import Organization
from ..models.tracker import Tracker
from .base import CRUDBase


class CRUDWebhook(CRUDBase[Webhook]):
    """CRUD operations for Webhook model."""

    def get_by_project_id(
        self, db: Session, *, project_id: str, account_id: Optional[str] = None
    ) -> Optional[Webhook]:
        """
        Get a webhook by project ID.
        """
        query = db.query(Webhook).filter(Webhook.project_id == project_id)
        if account_id:
            query = (
                query.join(Project)
                .join(Organization)
                .join(Tracker)
                .filter(Tracker.account_id == account_id)
            )
        return query.first()

    def get_all_by_project(
        self,
        db: Session,
        *,
        project_id: str,
        skip: int = 0,
        limit: int = 100,
        account_id: Optional[str] = None,
    ) -> List[Webhook]:
        """Get all webhooks for a project."""
        query = db.query(Webhook).join(Project).filter(Webhook.project_id == project_id)
        if account_id:
            query = query.join(Tracker).filter(Tracker.account_id == account_id)
        return query.offset(skip).limit(limit).all()

    def get_all_by_organization(
        self,
        db: Session,
        *,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        account_id: Optional[str] = None,
    ) -> List[Webhook]:
        """Get all webhooks for an organization."""
        query = (
            db.query(Webhook)
            .join(Organization)
            .filter(Organization.id == organization_id)
        )
        if account_id:
            query = query.join(Tracker).filter(Tracker.account_id == account_id)
        return query.offset(skip).limit(limit).all()

    def get_by_external_id(
        self,
        db: Session,
        *,
        external_id: str,
        tracker_id: str,
        account_id: Optional[str] = None,
    ) -> Optional[Webhook]:
        """
        Get a webhook by external ID and tracker ID.

        Args:
            db: Database session
            external_id: The external ID from the tracker (e.g., GitHub webhook ID)
            tracker_id: The tracker ID to scope the lookup
            account_id: Optional account ID to filter by

        Returns:
            The webhook if found, None otherwise
        """
        # Query webhooks by external_id
        query = db.query(Webhook).filter(Webhook.external_id == external_id)

        # Join through project to get to tracker, or through organization to get to tracker
        # We need to check both paths since webhooks can belong to either project or organization
        query = (
            query.outerjoin(Project, Webhook.project_id == Project.id)
            .outerjoin(
                Organization,
                (Webhook.organization_id == Organization.id)
                | (Project.organization_id == Organization.id),
            )
            .filter(Organization.tracker_id == tracker_id)
        )

        if account_id:
            query = query.join(Tracker).filter(Tracker.account_id == account_id)

        return query.first()

    def remove(self, db: Session, *, id: str) -> Optional[Webhook]:
        """Remove a webhook by ID."""
        return db.query(Webhook).filter(Webhook.id == id).delete()
