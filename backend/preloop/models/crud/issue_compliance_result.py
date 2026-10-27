"""CRUD operations for IssueComplianceResult model."""

from .base import CRUDBase
from ..models.issue import Issue
from ..models.issue_compliance_result import IssueComplianceResult
from ..models.tracker import Tracker
from ..models.project import Project
from ..models.organization import Organization
from typing import List, Optional
from sqlalchemy.orm import Session


class CRUDIssueComplianceResult(CRUDBase[IssueComplianceResult]):
    """CRUD operations for IssueComplianceResult model."""

    def get_by_issue_id_and_prompt_id(
        self,
        db: Session,
        *,
        issue_id: str,
        prompt_id: str,
        account_id: Optional[str] = None,
    ) -> Optional[IssueComplianceResult]:
        """Get a compliance result by issue and prompt, checking account access."""
        query = db.query(self.model).filter(
            self.model.issue_id == issue_id, self.model.prompt_id == prompt_id
        )
        if account_id:
            query = (
                query.join(Issue, self.model.issue_id == Issue.id)
                .join(Tracker, Issue.tracker_id == Tracker.id)
                .filter(Tracker.account_id == account_id)
            )
        return query.first()

    def delete_by_issue_id(self, db: Session, *, issue_id: str) -> int:
        """Delete all compliance results for a given issue_id."""
        num_deleted = (
            db.query(self.model).filter(self.model.issue_id == issue_id).delete()
        )
        db.commit()
        return num_deleted

    def get_for_issue(
        self, db: Session, *, issue_id: str, account_id: Optional[str] = None
    ) -> List[IssueComplianceResult]:
        """Get all compliance results for an issue, checking account access."""
        query = db.query(self.model).filter(self.model.issue_id == issue_id)

        if account_id:
            query = (
                query.join(Issue, self.model.issue_id == Issue.id)
                .join(Project, Issue.project_id == Project.id)
                .join(Organization, Project.organization_id == Organization.id)
                .join(Tracker, Organization.tracker_id == Tracker.id)
                .filter(Tracker.account_id == account_id)
            )

        return query.all()


issue_compliance_result = CRUDIssueComplianceResult(IssueComplianceResult)
