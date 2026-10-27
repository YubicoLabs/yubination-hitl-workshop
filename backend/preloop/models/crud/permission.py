"""CRUD operations for Permission and Role models."""

import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.permission import Permission, Role, RolePermission, UserRole, TeamRole
from .base import CRUDBase


class CRUDPermission(CRUDBase[Permission]):
    """CRUD operations for Permission model."""

    def get_by_name(self, db: Session, *, name: str) -> Optional[Permission]:
        """Get permission by name.

        Args:
            db: Database session.
            name: Permission name.

        Returns:
            Permission if found, None otherwise.
        """
        return db.query(Permission).filter(Permission.name == name).first()

    def get_by_category(
        self, db: Session, *, category: str, skip: int = 0, limit: int = 100
    ) -> List[Permission]:
        """Get permissions by category.

        Args:
            db: Database session.
            category: Permission category.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of permissions.
        """
        return (
            db.query(Permission)
            .filter(Permission.category == category, Permission.is_active)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active(
        self, db: Session, *, skip: int = 0, limit: int = 1000
    ) -> List[Permission]:
        """Get all active permissions.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of active permissions.
        """
        return (
            db.query(Permission)
            .filter(Permission.is_active)
            .offset(skip)
            .limit(limit)
            .all()
        )


class CRUDRole(CRUDBase[Role]):
    """CRUD operations for Role model."""

    def get_by_name(
        self, db: Session, *, name: str, account_id: Optional[str] = None
    ) -> Optional[Role]:
        """Get role by name.

        Args:
            db: Database session.
            name: Role name.
            account_id: Account ID for custom roles (None for system roles).

        Returns:
            Role if found, None otherwise.
        """
        query = db.query(Role).filter(Role.name == name)
        if account_id is not None:
            query = query.filter(Role.account_id == account_id)
        else:
            query = query.filter(Role.account_id.is_(None))
        return query.first()

    def get_system_roles(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[Role]:
        """Get all system roles.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of system roles.
        """
        return (
            db.query(Role).filter(Role.is_system_role).offset(skip).limit(limit).all()
        )

    def get_custom_roles(
        self, db: Session, *, account_id: str, skip: int = 0, limit: int = 100
    ) -> List[Role]:
        """Get custom roles for an account.

        Args:
            db: Database session.
            account_id: Account ID.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of custom roles.
        """
        return (
            db.query(Role)
            .filter(Role.account_id == account_id, not Role.is_system_role)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_all_for_account(
        self, db: Session, *, account_id: str, skip: int = 0, limit: int = 100
    ) -> List[Role]:
        """Get all roles available to an account (system + custom).

        Args:
            db: Database session.
            account_id: Account ID.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of roles (system + account's custom roles).
        """
        return (
            db.query(Role)
            .filter((Role.is_system_role) | (Role.account_id == account_id))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_permissions(self, db: Session, *, role_id: uuid.UUID) -> List[Permission]:
        """Get all permissions for a role.

        Args:
            db: Database session.
            role_id: Role ID.

        Returns:
            List of permissions.
        """
        return (
            db.query(Permission)
            .join(RolePermission)
            .filter(RolePermission.role_id == role_id)
            .all()
        )

    def assign_permission(
        self, db: Session, *, role_id: uuid.UUID, permission_id: uuid.UUID
    ) -> RolePermission:
        """Assign a permission to a role.

        Args:
            db: Database session.
            role_id: Role ID.
            permission_id: Permission ID.

        Returns:
            Created RolePermission.
        """
        role_perm = RolePermission(
            id=uuid.uuid4(), role_id=role_id, permission_id=permission_id
        )
        db.add(role_perm)
        db.commit()
        db.refresh(role_perm)
        return role_perm

    def remove_permission(
        self, db: Session, *, role_id: uuid.UUID, permission_id: uuid.UUID
    ) -> bool:
        """Remove a permission from a role.

        Args:
            db: Database session.
            role_id: Role ID.
            permission_id: Permission ID.

        Returns:
            True if removed, False if not found.
        """
        role_perm = (
            db.query(RolePermission)
            .filter(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
            .first()
        )
        if role_perm:
            db.delete(role_perm)
            db.commit()
            return True
        return False


class CRUDUserRole(CRUDBase[UserRole]):
    """CRUD operations for UserRole model."""

    def get_by_user(self, db: Session, *, user_id: uuid.UUID) -> List[UserRole]:
        """Get all user role assignments for a user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            List of UserRole objects.
        """
        return db.query(UserRole).filter(UserRole.user_id == user_id).all()

    def get_user_roles(self, db: Session, *, user_id: uuid.UUID) -> List[Role]:
        """Get all roles for a user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            List of roles.
        """
        return db.query(Role).join(UserRole).filter(UserRole.user_id == user_id).all()

    def assign_role(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        granted_by: Optional[uuid.UUID] = None,
    ) -> UserRole:
        """Assign a role to a user.

        Args:
            db: Database session.
            user_id: User ID.
            role_id: Role ID.
            granted_by: User who granted the role (optional).

        Returns:
            Created UserRole.
        """
        user_role = UserRole(
            id=uuid.uuid4(), user_id=user_id, role_id=role_id, granted_by=granted_by
        )
        db.add(user_role)
        db.commit()
        db.refresh(user_role)
        return user_role

    def remove_role(
        self, db: Session, *, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> bool:
        """Remove a role from a user.

        Args:
            db: Database session.
            user_id: User ID.
            role_id: Role ID.

        Returns:
            True if removed, False if not found.
        """
        user_role = (
            db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role_id == role_id)
            .first()
        )
        if user_role:
            db.delete(user_role)
            db.commit()
            return True
        return False


class CRUDTeamRole(CRUDBase[TeamRole]):
    """CRUD operations for TeamRole model."""

    def get_team_roles(self, db: Session, *, team_id: uuid.UUID) -> List[Role]:
        """Get all roles for a team.

        Args:
            db: Database session.
            team_id: Team ID.

        Returns:
            List of roles.
        """
        return db.query(Role).join(TeamRole).filter(TeamRole.team_id == team_id).all()

    def assign_role(
        self,
        db: Session,
        *,
        team_id: uuid.UUID,
        role_id: uuid.UUID,
        granted_by: Optional[uuid.UUID] = None,
    ) -> TeamRole:
        """Assign a role to a team.

        Args:
            db: Database session.
            team_id: Team ID.
            role_id: Role ID.
            granted_by: User who granted the role (optional).

        Returns:
            Created TeamRole.
        """
        team_role = TeamRole(
            id=uuid.uuid4(), team_id=team_id, role_id=role_id, granted_by=granted_by
        )
        db.add(team_role)
        db.commit()
        db.refresh(team_role)
        return team_role

    def remove_role(
        self, db: Session, *, team_id: uuid.UUID, role_id: uuid.UUID
    ) -> bool:
        """Remove a role from a team.

        Args:
            db: Database session.
            team_id: Team ID.
            role_id: Role ID.

        Returns:
            True if removed, False if not found.
        """
        team_role = (
            db.query(TeamRole)
            .filter(TeamRole.team_id == team_id, TeamRole.role_id == role_id)
            .first()
        )
        if team_role:
            db.delete(team_role)
            db.commit()
            return True
        return False


# Create instances
crud_permission = CRUDPermission(Permission)
crud_role = CRUDRole(Role)
crud_user_role = CRUDUserRole(UserRole)
crud_team_role = CRUDTeamRole(TeamRole)
