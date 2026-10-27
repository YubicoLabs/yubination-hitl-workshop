"""Permission enforcement for protected endpoints.

This module provides decorators and helpers for enforcing role-based permissions
across all protected API endpoints.
"""

import functools
import logging
from typing import Callable, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from preloop.models.models.user import User
from preloop.models.crud import crud_user_role, crud_role

logger = logging.getLogger(__name__)


def has_permission(user: User, permission_name: str, db: Session) -> bool:
    """Check if a user has a specific permission.

    This function checks if the user has been assigned a role that grants
    the specified permission. Permissions are aggregated from all roles
    assigned to the user.

    Args:
        user: The user to check permissions for.
        permission_name: The name of the permission to check (e.g., "create_issue").
        db: Database session for querying roles and permissions.

    Returns:
        True if the user has the permission, False otherwise.

    Note:
        - Users with the "owner" role have all permissions automatically
        - Inactive users have no permissions
        - Permissions are cached per request for performance
    """
    if not user.is_active:
        return False

    # Get all roles assigned to the user
    user_roles = crud_user_role.get_by_user(db, user_id=user.id)

    if not user_roles:
        return False

    # Check each role for the permission
    for user_role in user_roles:
        role = crud_role.get(db, id=user_role.role_id)
        if not role:
            continue

        # Owner role has all permissions
        if role.name == "owner":
            return True

        # Check if this role has the specific permission
        for role_perm in role.permissions:
            if role_perm.permission.name == permission_name:
                return True

    return False


def get_user_permissions(user: User, db: Session) -> List[str]:
    """Get all permissions for a user.

    Args:
        user: The user to get permissions for.
        db: Database session.

    Returns:
        List of permission names the user has.
    """
    if not user.is_active:
        return []

    permissions = set()
    user_roles = crud_user_role.get_by_user(db, user_id=user.id)

    for user_role in user_roles:
        role = crud_role.get(db, id=user_role.role_id)
        if not role:
            continue

        # Owner role has all permissions
        if role.name == "owner":
            # Get all permissions from the database
            from preloop.models.models.permission import Permission

            all_perms = db.query(Permission).all()
            return [p.name for p in all_perms]

        # Add this role's permissions
        for role_perm in role.permissions:
            permissions.add(role_perm.permission.name)

    return list(permissions)


def require_permission(permission_name: str):
    """Decorator to require a specific permission for endpoint access.

    This decorator should be applied to FastAPI endpoint functions to enforce
    permission checks. It must be used after the `Depends(get_current_active_user)`
    dependency.

    Args:
        permission_name: The name of the permission required (e.g., "create_issue").

    Returns:
        Decorator function.

    Example:
        @router.post("/issues")
        @require_permission("create_issue")
        async def create_issue(
            issue_data: IssueCreate,
            current_user: User = Depends(get_current_active_user),
            db: Session = Depends(get_db_session),
        ):
            # Implementation here
            pass

    Raises:
        HTTPException: 403 Forbidden if the user doesn't have the required permission.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user and db from kwargs
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Permission check requires current_user and db dependencies",
                )

            # Check if user has the required permission
            if not has_permission(current_user, permission_name, db):
                logger.warning(
                    f"Permission denied: User {current_user.username} "
                    f"(ID: {current_user.id}) attempted to access endpoint requiring "
                    f"'{permission_name}' permission"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {permission_name}",
                )

            # Permission check passed, call the original function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(*permission_names: str):
    """Decorator to require any one of multiple permissions.

    This is useful for endpoints that can be accessed by users with different roles.

    Args:
        *permission_names: Variable number of permission names.

    Returns:
        Decorator function.

    Example:
        @require_any_permission("manage_users", "view_users")
        async def list_users(...):
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Permission check requires current_user and db dependencies",
                )

            # Check if user has any of the required permissions
            for perm in permission_names:
                if has_permission(current_user, perm, db):
                    return await func(*args, **kwargs)

            logger.warning(
                f"Permission denied: User {current_user.username} "
                f"attempted to access endpoint requiring one of: {permission_names}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required one of: {', '.join(permission_names)}",
            )

        return wrapper

    return decorator


def require_all_permissions(*permission_names: str):
    """Decorator to require all specified permissions.

    This is useful for endpoints that require multiple permissions simultaneously.

    Args:
        *permission_names: Variable number of permission names.

    Returns:
        Decorator function.

    Example:
        @require_all_permissions("manage_flows", "execute_flows")
        async def execute_and_modify_flow(...):
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Permission check requires current_user and db dependencies",
                )

            # Check if user has all required permissions
            missing_perms = []
            for perm in permission_names:
                if not has_permission(current_user, perm, db):
                    missing_perms.append(perm)

            if missing_perms:
                logger.warning(
                    f"Permission denied: User {current_user.username} "
                    f"missing permissions: {missing_perms}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Missing: {', '.join(missing_perms)}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
