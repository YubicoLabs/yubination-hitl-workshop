"""Fixed account-scoped database operations for workshop customers."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from preloop.models import models


def reconcile_bounded_schemas(
    db: Session,
    *,
    configuration_updates: Sequence[tuple[models.ToolConfiguration, dict[str, Any]]],
    cache_updates: Sequence[tuple[models.MCPTool, dict[str, Any]]],
) -> None:
    """Update reviewed managed schemas in one transaction."""
    originals: list[tuple[Any, str, Any]] = [
        (configuration, "tool_schema", configuration.tool_schema)
        for configuration, _ in configuration_updates
    ] + [
        (cached_tool, "input_schema", cached_tool.input_schema)
        for cached_tool, _ in cache_updates
    ]
    try:
        for configuration, schema in configuration_updates:
            configuration.tool_schema = schema
        for cached_tool, schema in cache_updates:
            cached_tool.input_schema = schema
        if originals:
            db.add_all([row for row, _, _ in originals])
            db.commit()
    except Exception:
        db.rollback()
        for row, attribute, value in originals:
            setattr(row, attribute, value)
        raise


def fixture_email(account_id: UUID) -> str:
    return f"customer-{account_id}@example.invalid"


def provision(db: Session, *, account_id: UUID) -> None:
    """Atomic insert only: retries preserve completed progress."""
    db.execute(
        insert(models.WorkshopCustomer)
        .values(
            account_id=account_id, email=fixture_email(account_id), status="standard"
        )
        .on_conflict_do_nothing(index_elements=["account_id"])
    )
    db.commit()


def get(db: Session, *, account_id: UUID) -> dict[str, str] | None:
    row = db.execute(
        select(models.WorkshopCustomer.email, models.WorkshopCustomer.status).where(
            models.WorkshopCustomer.account_id == account_id
        )
    ).first()
    return {"email": row.email, "status": row.status} if row else None


def transition(
    db: Session,
    *,
    account_id: UUID,
    email: str,
    expected_status: str,
    status: str,
    completion_request_id: UUID | None = None,
) -> dict[str, str]:
    allowed = {("standard", "vip"), ("vip", "standard")}
    if (expected_status, status) not in allowed:
        raise ValueError(
            "Only explicit standard to vip or vip to standard workshop transitions are supported."
        )
    try:
        row = db.execute(
            update(models.WorkshopCustomer)
            .where(
                models.WorkshopCustomer.account_id == account_id,
                models.WorkshopCustomer.email == email,
                models.WorkshopCustomer.status == expected_status,
            )
            .values(status=status)
            .returning(models.WorkshopCustomer.email, models.WorkshopCustomer.status)
        ).first()
        if row is None:
            db.rollback()
            raise ValueError(
                f"Workshop customer is unavailable or no longer {expected_status}; no transition occurred."
            )
        if completion_request_id is not None:
            db.add(
                models.ApprovalEvent(
                    account_id=account_id,
                    approval_request_id=completion_request_id,
                    event_type="workshop_execution_completed",
                    detail="Managed workshop transition committed.",
                )
            )
        db.commit()
        return {"email": row.email, "status": row.status}
    except Exception:
        db.rollback()
        raise


def has_completion(db: Session, *, account_id: UUID, approval_request_id: UUID) -> bool:
    """Read only: an exact request's managed transition committed successfully."""
    return bool(
        db.scalar(
            select(models.ApprovalEvent.id)
            .where(
                models.ApprovalEvent.account_id == account_id,
                models.ApprovalEvent.approval_request_id == approval_request_id,
                models.ApprovalEvent.event_type == "workshop_execution_completed",
            )
            .limit(1)
        )
    )
