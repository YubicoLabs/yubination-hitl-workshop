"""CRUD operations for IssueRelationship model."""

from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.issue_relationship import IssueRelationship
from .base import CRUDBase


class CRUDIssueRelationship(CRUDBase[IssueRelationship]):
    """CRUD operations for IssueRelationship model."""

    def create(
        self,
        db: Session,
        *,
        source_issue_id: str,
        target_issue_id: str,
        type: str,
        reason: Optional[str] = None,
        confidence_score: Optional[float] = None,
        is_committed: Optional[bool] = False,
        comes_from_tracker: Optional[bool] = False,
    ) -> (IssueRelationship, bool):
        """Create a new issue relationship. Returns a tuple of (relationship, created)."""
        if type == "related" or type == "relates_to" or type == "relates to":
            # For undirected relationships, store with the smaller ID first to avoid duplicates
            if source_issue_id > target_issue_id:
                source_issue_id, target_issue_id = target_issue_id, source_issue_id
        elif type == "is_blocked_by" or type == "is blocked by":
            type = "blocks"
            source_issue_id, target_issue_id = target_issue_id, source_issue_id

        existing_relationship = self.get_by_source_target_type(
            db,
            source_issue_id=source_issue_id,
            target_issue_id=target_issue_id,
            type=type,
        )
        if existing_relationship:
            return existing_relationship, False

        new_relationship = super().create(
            db,
            obj_in={
                "source_issue_id": source_issue_id,
                "target_issue_id": target_issue_id,
                "type": type,
                "reason": reason,
                "confidence_score": confidence_score,
                "is_committed": is_committed,
                "comes_from_tracker": comes_from_tracker,
            },
        )
        return new_relationship, True

    def get_by_source_target_type(
        self, db: Session, *, source_issue_id: str, target_issue_id: str, type: str
    ) -> Optional[IssueRelationship]:
        """Get an issue relationship by source, target, and type."""
        return (
            db.query(self.model)
            .filter_by(
                source_issue_id=source_issue_id,
                target_issue_id=target_issue_id,
                type=type,
            )
            .first()
        )

    def get_for_issue(self, db: Session, *, issue_id: str) -> List[IssueRelationship]:
        """Get all relationships for a given issue."""
        return (
            db.query(self.model)
            .filter(
                or_(
                    self.model.source_issue_id == issue_id,
                    self.model.target_issue_id == issue_id,
                )
            )
            .all()
        )

    def get_relationships_for_issues(
        self, db: Session, *, issue_ids: List[str], any_in_list: bool = True
    ) -> List[IssueRelationship]:
        """Get all relationships for a given list of issues.

        Args:
            db: The database session.
            issue_ids: A list of issue IDs.
            any_in_list: If True, returns relationships where either the source or target
                         is in the list. If False, returns relationships where both must be
                         in the list. Defaults to True.
        """
        if any_in_list:
            return (
                db.query(self.model)
                .filter(
                    or_(
                        self.model.source_issue_id.in_(issue_ids),
                        self.model.target_issue_id.in_(issue_ids),
                    )
                )
                .all()
            )

        return (
            db.query(self.model)
            .filter(
                self.model.source_issue_id.in_(issue_ids),
                self.model.target_issue_id.in_(issue_ids),
            )
            .all()
        )

    def commit_relationships(
        self, db: Session, *, relationships: List[dict]
    ) -> List[IssueRelationship]:
        """Commit a list of issue relationships by setting is_committed to True."""
        updated_relationships = []
        for rel_data in relationships:
            source_id = rel_data.get("source_issue_id")
            target_id = rel_data.get("dependent_issue_id")

            relationship_obj = (
                db.query(IssueRelationship)
                .filter(
                    IssueRelationship.source_issue_id == source_id,
                    IssueRelationship.target_issue_id == target_id,
                )
                .first()
            )

            if relationship_obj:
                relationship_obj.is_committed = True
                db.add(relationship_obj)
                updated_relationships.append(relationship_obj)

        db.commit()
        for rel in updated_relationships:
            db.refresh(rel)

        return updated_relationships

    def remove(
        self, db: Session, *, source_issue_id: str, target_issue_id: str, type: str
    ) -> Optional[IssueRelationship]:
        """Remove an issue relationship."""
        if type == "related":
            if source_issue_id > target_issue_id:
                source_issue_id, target_issue_id = target_issue_id, source_issue_id

        obj = (
            db.query(self.model)
            .filter_by(
                source_issue_id=source_issue_id,
                target_issue_id=target_issue_id,
                type=type,
            )
            .first()
        )

        if obj:
            db.delete(obj)
            db.commit()
        return obj


issue_relationship = CRUDIssueRelationship(IssueRelationship)
