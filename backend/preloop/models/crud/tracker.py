"""CRUD operations for Tracker model."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.tracker import Tracker, TrackerType
from .base import CRUDBase


class CRUDTracker(CRUDBase[Tracker]):
    """CRUD operations for Tracker model."""

    def create(self, db: Session, *, obj_in: Dict[str, Any]) -> Tracker:
        """Create new tracker with initialized timestamp fields."""
        obj_data = dict(obj_in)

        # Initialize timestamp fields
        current_time = datetime.now(timezone.utc)
        obj_data.setdefault("created", current_time)
        obj_data.setdefault("last_updated", current_time)

        return super().create(db=db, obj_in=obj_data)

    def update(
        self, db: Session, *, db_obj: Tracker, obj_in: Dict[str, Any]
    ) -> Tracker:
        """Update tracker and its last_updated timestamp."""
        # Update last_updated field
        obj_in["last_updated"] = datetime.now(timezone.utc)

        return super().update(db=db, db_obj=db_obj, obj_in=obj_in)

    def get_for_account(
        self, db: Session, *, account_id: str, skip: int = 0, limit: int = 100
    ) -> List[Tracker]:
        """Get trackers for an account."""
        return (
            db.query(Tracker)
            .filter(Tracker.account_id == str(account_id))
            .filter(Tracker.is_deleted.is_(False))  # Exclude soft-deleted trackers
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active(
        self,
        db: Session,
        *,
        account_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Tracker]:
        """Get active trackers, optionally filtered by account."""
        query = db.query(Tracker).filter(Tracker.is_active.is_(True))
        if account_id:
            query = query.filter(Tracker.account_id == account_id)
        return query.offset(skip).limit(limit).all()

    def get_by_type(
        self,
        db: Session,
        *,
        tracker_type: TrackerType,
        account_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Tracker]:
        """Get trackers by type, optionally filtered by account."""
        query = db.query(Tracker).filter(Tracker.tracker_type == tracker_type.value)
        if account_id:
            query = query.filter(Tracker.account_id == account_id)
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, db: Session, *, id: str) -> Optional[Tracker]:
        """Get tracker by ID."""
        return db.query(Tracker).filter(Tracker.id == id).first()

    def validate(
        self, db: Session, *, id: str, is_valid: bool, message: Optional[str] = None
    ) -> Optional[Tracker]:
        """Update tracker validation status."""
        tracker = self.get(db, id=id)
        if tracker:
            tracker.is_valid = is_valid
            current_time = datetime.now(timezone.utc)
            tracker.last_validation = current_time
            tracker.last_updated = current_time
            tracker.validation_message = message
            db.add(tracker)
            db.commit()
            db.refresh(tracker)
        return tracker

    def deactivate(self, db: Session, *, id: str) -> Optional[Tracker]:
        """Deactivate a tracker."""
        tracker = self.get(db, id=id)
        if tracker:
            tracker.is_active = False
            tracker.last_updated = datetime.now(timezone.utc)
            db.add(tracker)
            db.commit()
            db.refresh(tracker)
        return tracker

    def get_by_name(
        self,
        db: Session,
        *,
        name: str,
        account_id: str,
        include_deleted: bool = False,
    ) -> Optional[Tracker]:
        """Get tracker by name for a specific account."""
        query = db.query(Tracker).filter(
            Tracker.name == name, Tracker.account_id == account_id
        )
        if not include_deleted:
            query = query.filter(Tracker.is_deleted.is_(False))
        return query.first()

    def get_by_id_and_account(
        self,
        db: Session,
        *,
        id: str,
        account_id: str,
        include_deleted: bool = False,
    ) -> Optional[Tracker]:
        """Get tracker by ID for a specific account."""
        query = db.query(Tracker).filter(
            Tracker.id == str(id), Tracker.account_id == account_id
        )
        if not include_deleted:
            query = query.filter(Tracker.is_deleted.is_(False))
        return query.first()

    def delete_scope_rules(self, db: Session, *, tracker_id: str) -> None:
        """Delete all scope rules for a tracker."""
        from ..models.tracker_scope_rule import TrackerScopeRule

        db.query(TrackerScopeRule).filter(
            TrackerScopeRule.tracker_id == tracker_id
        ).delete(synchronize_session=False)

    def has_tracker(self, db: Session, *, account_id: str) -> bool:
        """Check if an account has at least one tracker.

        Args:
            db: Database session
            account_id: Account ID

        Returns:
            True if account has at least one tracker, False otherwise
        """
        return (
            db.query(Tracker)
            .filter(Tracker.account_id == str(account_id))
            .filter(Tracker.is_deleted.is_(False))
            .limit(1)
            .first()
        ) is not None

    def count_by_oauth_installation(
        self, db: Session, *, oauth_installation_id: Any
    ) -> int:
        """Count trackers using a specific OAuth installation.

        Args:
            db: Database session
            oauth_installation_id: OAuth installation ID

        Returns:
            Number of trackers using this installation
        """
        return (
            db.query(Tracker)
            .filter(Tracker.oauth_installation_id == oauth_installation_id)
            .count()
        )

    def get_by_oauth_installation(
        self,
        db: Session,
        *,
        oauth_installation_id: Any,
        active_only: bool = True,
    ) -> List[Tracker]:
        """Get trackers using a specific OAuth installation.

        Args:
            db: Database session
            oauth_installation_id: OAuth installation ID
            active_only: Only return active, non-deleted trackers

        Returns:
            List of trackers using this installation
        """
        query = db.query(Tracker).filter(
            Tracker.oauth_installation_id == oauth_installation_id
        )
        if active_only:
            query = query.filter(
                Tracker.is_active.is_(True),
                Tracker.is_deleted.is_(False),
            )
        return query.all()


# Create instance
crud_tracker = CRUDTracker(Tracker)
