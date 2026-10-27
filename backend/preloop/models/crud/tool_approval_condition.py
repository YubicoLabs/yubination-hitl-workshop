"""CRUD operations for tool approval conditions."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from ..models.tool_approval_condition import ToolApprovalCondition


def get_by_id(
    db: Session, condition_id: uuid.UUID, account_id: uuid.UUID
) -> Optional[ToolApprovalCondition]:
    """Get tool approval condition by ID.

    Args:
        db: Database session.
        condition_id: Condition ID.
        account_id: Account ID for scoping.

    Returns:
        ToolApprovalCondition if found, None otherwise.
    """
    return (
        db.query(ToolApprovalCondition)
        .filter(
            ToolApprovalCondition.id == condition_id,
            ToolApprovalCondition.account_id == account_id,
        )
        .first()
    )


def get_by_tool_configuration(
    db: Session, tool_configuration_id: uuid.UUID, account_id: uuid.UUID
) -> Optional[ToolApprovalCondition]:
    """Get tool approval condition by tool configuration ID.

    Args:
        db: Database session.
        tool_configuration_id: Tool configuration ID.
        account_id: Account ID for scoping.

    Returns:
        ToolApprovalCondition if found, None otherwise.
    """
    return (
        db.query(ToolApprovalCondition)
        .filter(
            ToolApprovalCondition.tool_configuration_id == tool_configuration_id,
            ToolApprovalCondition.account_id == account_id,
        )
        .first()
    )


def create(
    db: Session,
    tool_configuration_id: uuid.UUID,
    account_id: uuid.UUID,
    condition_type: str = "argument",
    condition_expression: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_enabled: bool = True,
    condition_config: Optional[dict] = None,
) -> ToolApprovalCondition:
    """Create a new tool approval condition.

    Args:
        db: Database session.
        tool_configuration_id: Tool configuration ID.
        account_id: Account ID.
        condition_type: Type of condition evaluator.
        condition_expression: CEL expression for conditional approval.
        name: Optional human-readable name.
        description: Optional description.
        is_enabled: Whether the condition is enabled.
        condition_config: Additional configuration.

    Returns:
        Created ToolApprovalCondition.
    """
    condition = ToolApprovalCondition(
        tool_configuration_id=tool_configuration_id,
        account_id=account_id,
        condition_type=condition_type,
        condition_expression=condition_expression,
        name=name,
        description=description,
        is_enabled=is_enabled,
        condition_config=condition_config or {},
    )
    db.add(condition)
    db.flush()
    return condition


def update(
    db: Session,
    condition: ToolApprovalCondition,
    condition_type: Optional[str] = None,
    condition_expression: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    condition_config: Optional[dict] = None,
) -> ToolApprovalCondition:
    """Update a tool approval condition.

    Args:
        db: Database session.
        condition: Condition to update.
        condition_type: Type of condition evaluator.
        condition_expression: CEL expression.
        name: Human-readable name.
        description: Description.
        is_enabled: Whether enabled.
        condition_config: Additional configuration.

    Returns:
        Updated ToolApprovalCondition.
    """
    if condition_type is not None:
        condition.condition_type = condition_type
    if condition_expression is not None:
        condition.condition_expression = condition_expression
    if name is not None:
        condition.name = name
    if description is not None:
        condition.description = description
    if is_enabled is not None:
        condition.is_enabled = is_enabled
    if condition_config is not None:
        condition.condition_config = condition_config

    db.flush()
    return condition


def create_or_update(
    db: Session,
    tool_configuration_id: uuid.UUID,
    account_id: uuid.UUID,
    condition_type: str = "argument",
    condition_expression: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_enabled: bool = True,
    condition_config: Optional[dict] = None,
) -> ToolApprovalCondition:
    """Create or update a tool approval condition.

    Since tool configurations have a 1:1 relationship with conditions,
    this method will update an existing condition if one exists, or create
    a new one if it doesn't.

    Args:
        db: Database session.
        tool_configuration_id: Tool configuration ID.
        account_id: Account ID.
        condition_type: Type of condition evaluator.
        condition_expression: CEL expression.
        name: Optional human-readable name.
        description: Optional description.
        is_enabled: Whether enabled.
        condition_config: Additional configuration.

    Returns:
        Created or updated ToolApprovalCondition.
    """
    condition = get_by_tool_configuration(db, tool_configuration_id, account_id)

    if condition:
        return update(
            db,
            condition,
            condition_type=condition_type,
            condition_expression=condition_expression,
            name=name,
            description=description,
            is_enabled=is_enabled,
            condition_config=condition_config,
        )
    else:
        return create(
            db,
            tool_configuration_id=tool_configuration_id,
            account_id=account_id,
            condition_type=condition_type,
            condition_expression=condition_expression,
            name=name,
            description=description,
            is_enabled=is_enabled,
            condition_config=condition_config,
        )


def delete(db: Session, condition: ToolApprovalCondition) -> None:
    """Delete a tool approval condition.

    Args:
        db: Database session.
        condition: Condition to delete.
    """
    db.delete(condition)
    db.flush()
