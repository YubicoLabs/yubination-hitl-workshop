"""CRUD operations for ApprovalWorkflow model."""

from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .. import models
from ..schemas.tool_configuration import ApprovalWorkflowCreate, ApprovalWorkflowUpdate
from .base import CRUDBase


class CRUDApprovalWorkflow(CRUDBase[models.ApprovalWorkflow]):
    """CRUD operations for ApprovalWorkflow model."""

    def __init__(self):
        """Initialize with the ApprovalWorkflow model."""
        super().__init__(model=models.ApprovalWorkflow)

    def get(
        self, db: Session, id: UUID, account_id: str
    ) -> Optional[models.ApprovalWorkflow]:
        """Retrieve an approval workflow by its ID.

        Args:
            db: The database session.
            id: The ID of the approval workflow to retrieve.
            account_id: The ID of the account associated with the workflow.

        Returns:
            The approval workflow object if found, otherwise None.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.id == id,
                self.model.account_id == account_id,
            )
            .first()
        )

    def get_by_name(
        self, db: Session, account_id: str, name: str
    ) -> Optional[models.ApprovalWorkflow]:
        """Retrieve an approval workflow by name and account.

        Args:
            db: The database session.
            account_id: The ID of the account.
            name: The name of the approval workflow.

        Returns:
            The approval workflow object if found, otherwise None.
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
    ) -> List[models.ApprovalWorkflow]:
        """Retrieve approval workflows for a specific account.

        Args:
            db: The database session.
            account_id: The ID of the account.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of approval workflow objects.
        """
        return (
            db.query(self.model)
            .filter(self.model.account_id == account_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_default(
        self, db: Session, account_id: str
    ) -> Optional[models.ApprovalWorkflow]:
        """Retrieve the default approval workflow for an account.

        Args:
            db: The database session.
            account_id: The ID of the account.

        Returns:
            The default approval workflow if found, otherwise None.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.is_default,
            )
            .first()
        )

    def is_user_authorized_approver(
        self,
        db: Session,
        *,
        workflow_id: UUID,
        account_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Return whether a user is an approver for an account-scoped workflow.

        Direct approvers and members of configured approver teams use the same
        workflow fields that notification delivery and quorum handling already
        consume.

        Args:
            db: Database session.
            workflow_id: Approval Workflow to authorize against.
            account_id: Account that owns the Approval Workflow.
            user_id: Candidate approver.

        Returns:
            True for a configured direct or team approver; otherwise False.
        """
        workflow = self.get(db, id=workflow_id, account_id=str(account_id))
        if workflow is None:
            return False

        if user_id in (workflow.approver_user_ids or []):
            return True

        from .team import crud_team

        for team_id in workflow.approver_team_ids or []:
            team = crud_team.get(db, id=team_id, account_id=str(account_id))
            if team is not None and crud_team.get_membership(
                db, team_id=team_id, user_id=user_id
            ):
                return True

        return False

    def find_legacy_default_workflows(self, db: Session) -> List[UUID]:
        """Return ``account_id``s whose default workflow needs repair.

        A default workflow is considered "legacy" / broken when it either:

        * was created with ``approval_type="manual"`` (the older synonym
          for the in-UI human-approval flow that the dialog dropdown can
          no longer render — the type field appears blank), or
        * has no ``approver_user_ids`` *and* no ``approver_team_ids`` —
          which makes any approval request routed through it impossible
          to act on.

        The startup repair pass uses this to find accounts that still
        carry pre-fix data and heal them on boot.
        """
        rows = (
            db.query(self.model.account_id)
            .filter(
                self.model.is_default.is_(True),
                (
                    (self.model.approval_type == "manual")
                    | (
                        (
                            (self.model.approver_user_ids.is_(None))
                            | (self.model.approver_user_ids == [])
                        )
                        & (
                            (self.model.approver_team_ids.is_(None))
                            | (self.model.approver_team_ids == [])
                        )
                    )
                ),
            )
            .all()
        )
        return [row[0] for row in rows]

    def create(
        self,
        db: Session,
        *,
        obj_in: Union[ApprovalWorkflowCreate, Dict[str, Any]],
        account_id: str,
    ) -> models.ApprovalWorkflow:
        """Create a new approval workflow.

        If this is the first workflow for the account, it will be marked as default.
        If is_default is explicitly set to True, any existing default will be unmarked.

        Args:
            db: The database session.
            obj_in: The approval workflow data.
            account_id: The ID of the account.

        Returns:
            The created approval workflow.
        """
        # Convert to dict if it's a Pydantic model
        if isinstance(obj_in, ApprovalWorkflowCreate):
            obj_data = obj_in.model_dump(exclude_unset=True)
        else:
            obj_data = obj_in.copy()

        # Ensure account_id is set
        obj_data["account_id"] = account_id

        # Check if this is the first workflow for the account
        existing_count = (
            db.query(self.model).filter(self.model.account_id == account_id).count()
        )

        # If no policies exist, make this one default
        if existing_count == 0:
            obj_data["is_default"] = True
        elif obj_data.get("is_default", False):
            # If explicitly setting as default, unmark existing default
            self._unmark_default(db, account_id)

        # Create the workflow
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: models.ApprovalWorkflow,
        obj_in: Union[ApprovalWorkflowUpdate, Dict[str, Any]],
    ) -> models.ApprovalWorkflow:
        """Update an approval workflow.

        If is_default is set to True, any existing default will be unmarked.

        Args:
            db: The database session.
            db_obj: The existing approval workflow object.
            obj_in: The update data.

        Returns:
            The updated approval workflow.
        """
        # Convert to dict if it's a Pydantic model
        if isinstance(obj_in, ApprovalWorkflowUpdate):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = obj_in.copy()

        # If setting as default, unmark existing default
        if update_data.get("is_default", False) and not db_obj.is_default:
            self._unmark_default(db, db_obj.account_id)

        # Update the object
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def _unmark_default(self, db: Session, account_id: str) -> None:
        """Unmark any existing default workflow for the account.

        Args:
            db: The database session.
            account_id: The ID of the account.
        """
        existing_default = self.get_default(db, account_id)
        if existing_default:
            existing_default.is_default = False
            db.add(existing_default)
            db.flush()  # Flush but don't commit yet

    def remove(
        self, db: Session, *, id: UUID, account_id: str
    ) -> Optional[models.ApprovalWorkflow]:
        """Remove an approval workflow by its ID.

        If removing the default workflow and other policies exist, the most recently
        created remaining workflow will be marked as default.

        Args:
            db: The database session.
            id: The ID of the approval workflow to remove.
            account_id: The ID of the account.

        Returns:
            The removed approval workflow object if found and deleted, otherwise None.
        """
        db_workflow = (
            db.query(self.model)
            .filter(
                self.model.id == id,
                self.model.account_id == account_id,
            )
            .order_by(self.model.created_at.desc())
            .first()
        )
        if db_workflow:
            was_default = db_workflow.is_default
            db.delete(db_workflow)
            db.flush()

            # If we deleted the default workflow, make another one default
            if was_default:
                replacement = (
                    db.query(self.model)
                    .filter(self.model.account_id == account_id)
                    .order_by(self.model.created_at.desc())
                    .first()
                )
                if replacement:
                    replacement.is_default = True
                    db.add(replacement)

            db.commit()
        return db_workflow


# Async helper functions
async def get_approval_workflow_async(
    db: Session, workflow_id: UUID
) -> Optional[models.ApprovalWorkflow]:
    """Async: Retrieve an approval workflow by its ID.

    Args:
        db: The async database session.
        workflow_id: The ID of the approval workflow.

    Returns:
        The approval workflow object if found, otherwise None.
    """
    result = await db.execute(
        select(models.ApprovalWorkflow).where(models.ApprovalWorkflow.id == workflow_id)
    )
    return result.scalar_one_or_none()


async def get_approval_workflow_for_account_async(
    db: AsyncSession, *, workflow_id: UUID, account_id: UUID
) -> Optional[models.ApprovalWorkflow]:
    """Retrieve an approval workflow only within its owning account."""
    result = await db.execute(
        select(models.ApprovalWorkflow).where(
            models.ApprovalWorkflow.id == workflow_id,
            models.ApprovalWorkflow.account_id == account_id,
        )
    )
    return result.scalar_one_or_none()


async def get_default_approval_workflow_async(
    db: Session, account_id: UUID
) -> Optional[models.ApprovalWorkflow]:
    """Async: Retrieve the default approval workflow for an account.

    Args:
        db: The async database session.
        account_id: The ID of the account.

    Returns:
        The default approval workflow if one is configured, otherwise None.
    """
    result = await db.execute(
        select(models.ApprovalWorkflow).where(
            models.ApprovalWorkflow.account_id == account_id,
            models.ApprovalWorkflow.is_default.is_(True),
        )
    )
    return result.scalars().first()


async def is_user_authorized_approver_async(
    db: AsyncSession,
    *,
    workflow_id: UUID,
    account_id: UUID,
    user_id: UUID,
) -> bool:
    """Return whether a user is a direct or team approver in an account."""
    workflow_result = await db.execute(
        select(models.ApprovalWorkflow).where(
            models.ApprovalWorkflow.id == workflow_id,
            models.ApprovalWorkflow.account_id == account_id,
        )
    )
    workflow = workflow_result.scalar_one_or_none()
    if workflow is None:
        return False
    if user_id in (workflow.approver_user_ids or []):
        return True
    if not workflow.approver_team_ids:
        return False

    membership_result = await db.execute(
        select(models.TeamMembership.id)
        .join(models.Team, models.Team.id == models.TeamMembership.team_id)
        .where(
            models.TeamMembership.user_id == user_id,
            models.TeamMembership.team_id.in_(workflow.approver_team_ids),
            models.Team.account_id == account_id,
        )
        .limit(1)
    )
    return membership_result.scalar_one_or_none() is not None
