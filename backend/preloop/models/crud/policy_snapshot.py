"""CRUD operations for PolicySnapshot model."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, defer

from ..models.policy_snapshot import PolicySnapshot
from .base import CRUDBase


class CRUDPolicySnapshot(CRUDBase[PolicySnapshot]):
    """CRUD operations for PolicySnapshot model."""

    def __init__(self):
        """Initialize with the PolicySnapshot model."""
        super().__init__(model=PolicySnapshot)

    def get(
        self, db: Session, id: UUID, account_id: Optional[str] = None
    ) -> Optional[PolicySnapshot]:
        """Retrieve a policy snapshot by its ID.

        Args:
            db: The database session.
            id: The ID of the snapshot to retrieve.
            account_id: The ID of the account. Optional.

        Returns:
            The PolicySnapshot object if found, otherwise None.
        """
        query = db.query(self.model).filter(self.model.id == id)

        if account_id:
            query = query.filter(self.model.account_id == account_id)

        return query.first()

    def get_by_version_number(
        self, db: Session, account_id: str, version_number: int
    ) -> Optional[PolicySnapshot]:
        """Retrieve a snapshot by version number.

        Args:
            db: The database session.
            account_id: The ID of the account.
            version_number: The version number to find.

        Returns:
            The PolicySnapshot if found, otherwise None.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.version_number == version_number,
            )
            .first()
        )

    def get_by_tag(
        self, db: Session, account_id: str, tag: str
    ) -> Optional[PolicySnapshot]:
        """Retrieve a snapshot by tag.

        Args:
            db: The database session.
            account_id: The ID of the account.
            tag: The tag to search for.

        Returns:
            The PolicySnapshot if found, otherwise None.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.tag == tag,
            )
            .first()
        )

    def get_active(self, db: Session, account_id: str) -> Optional[PolicySnapshot]:
        """Retrieve the currently active snapshot for an account.

        Args:
            db: The database session.
            account_id: The ID of the account.

        Returns:
            The active PolicySnapshot if found, otherwise None.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.is_active == True,  # noqa: E712
            )
            .first()
        )

    def get_multi_by_account(
        self,
        db: Session,
        account_id: str,
        skip: int = 0,
        limit: int = 100,
        include_snapshots: bool = False,
    ) -> List[PolicySnapshot]:
        """Retrieve policy snapshots for a specific account.

        Args:
            db: The database session.
            account_id: The ID of the account.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            include_snapshots: Whether to include full snapshot data.
                When False (default), the snapshot_data column is deferred
                to avoid loading large JSONB data for metadata-only queries.

        Returns:
            List of PolicySnapshot objects.
        """
        query = db.query(self.model).filter(self.model.account_id == account_id)

        # Defer loading of snapshot_data when not needed (performance optimization)
        # This avoids loading potentially large JSONB data for list/metadata queries
        if not include_snapshots:
            query = query.options(defer(self.model.snapshot_data))

        query = (
            query.order_by(self.model.version_number.desc()).offset(skip).limit(limit)
        )

        return query.all()

    def get_next_version_number(self, db: Session, account_id: str) -> int:
        """Get the next version number for an account.

        Args:
            db: The database session.
            account_id: The ID of the account.

        Returns:
            The next version number (max + 1, or 1 if no versions exist).
        """
        result = (
            db.query(func.max(self.model.version_number))
            .filter(self.model.account_id == account_id)
            .scalar()
        )
        return (result or 0) + 1

    def set_active(
        self, db: Session, account_id: str, snapshot_id: UUID
    ) -> Optional[PolicySnapshot]:
        """Set a snapshot as the active version.

        Deactivates any previously active snapshot and activates the specified one.

        Args:
            db: The database session.
            account_id: The ID of the account.
            snapshot_id: The ID of the snapshot to activate.

        Returns:
            The activated PolicySnapshot if found, otherwise None.
        """
        # Deactivate all other snapshots for this account
        db.query(self.model).filter(
            self.model.account_id == account_id,
            self.model.is_active == True,  # noqa: E712
        ).update({"is_active": False})

        # Activate the specified snapshot
        snapshot = (
            db.query(self.model)
            .filter(
                self.model.id == snapshot_id,
                self.model.account_id == account_id,
            )
            .first()
        )

        if snapshot:
            snapshot.is_active = True

        return snapshot

    def clear_tag(
        self, db: Session, account_id: str, tag: str
    ) -> Optional[PolicySnapshot]:
        """Remove a tag from any snapshot that has it.

        Args:
            db: The database session.
            account_id: The ID of the account.
            tag: The tag to clear.

        Returns:
            The snapshot that had the tag, if any.
        """
        snapshot = (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.tag == tag,
            )
            .first()
        )

        if snapshot:
            snapshot.tag = None

        return snapshot

    def update_tag(
        self, db: Session, snapshot_id: UUID, account_id: str, tag: Optional[str]
    ) -> Optional[PolicySnapshot]:
        """Update the tag on a snapshot.

        If the tag is used elsewhere, it is cleared from the other snapshot first.

        Args:
            db: The database session.
            snapshot_id: The ID of the snapshot to update.
            account_id: The ID of the account.
            tag: The new tag value (or None to clear).

        Returns:
            The updated PolicySnapshot if found, otherwise None.
        """
        # Clear the tag from any other snapshot if it's being set
        if tag:
            self.clear_tag(db, account_id, tag)

        snapshot = (
            db.query(self.model)
            .filter(
                self.model.id == snapshot_id,
                self.model.account_id == account_id,
            )
            .first()
        )

        if snapshot:
            snapshot.tag = tag

        return snapshot

    def remove(
        self, db: Session, *, id: UUID, account_id: str
    ) -> Optional[PolicySnapshot]:
        """Remove a policy snapshot by its ID.

        Args:
            db: The database session.
            id: The ID of the snapshot to remove.
            account_id: The ID of the account.

        Returns:
            The removed PolicySnapshot object if found and deleted, otherwise None.
        """
        snapshot = (
            db.query(self.model)
            .filter(
                self.model.id == id,
                self.model.account_id == account_id,
            )
            .first()
        )
        if snapshot:
            db.delete(snapshot)
        return snapshot

    def prune_old_versions(
        self,
        db: Session,
        account_id: str,
        older_than_days: int = 90,
        keep_tagged: bool = True,
        keep_count: int = 10,
    ) -> int:
        """Delete old unused policy versions.

        Args:
            db: The database session.
            account_id: The ID of the account.
            older_than_days: Delete versions older than this many days.
            keep_tagged: If True, never delete tagged versions.
            keep_count: Always keep at least this many versions.

        Returns:
            The count of deleted versions.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        # Get IDs of versions to keep (most recent keep_count)
        keep_ids = (
            db.query(self.model.id)
            .filter(self.model.account_id == account_id)
            .order_by(self.model.version_number.desc())
            .limit(keep_count)
            .subquery()
        )

        # Build delete query
        delete_query = db.query(self.model).filter(
            and_(
                self.model.account_id == account_id,
                self.model.created_at < cutoff_date,
                self.model.is_active == False,  # noqa: E712
                ~self.model.id.in_(keep_ids),
            )
        )

        # Exclude tagged versions if requested
        if keep_tagged:
            delete_query = delete_query.filter(self.model.tag.is_(None))

        # Get count before deleting
        count = delete_query.count()

        # Delete
        delete_query.delete(synchronize_session=False)

        return count

    def count_by_account(self, db: Session, account_id: str) -> int:
        """Count the number of snapshots for an account.

        Args:
            db: The database session.
            account_id: The ID of the account.

        Returns:
            The count of snapshots.
        """
        return (
            db.query(func.count(self.model.id))
            .filter(self.model.account_id == account_id)
            .scalar()
        ) or 0


# Create singleton instance
crud_policy_snapshot = CRUDPolicySnapshot()
