"""Database operations for deployment-wide workshop signup codes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from preloop.models import models


def create(
    db: Session, *, code_digest: str, label: str | None
) -> models.WorkshopSignupCode:
    record = models.WorkshopSignupCode(code_digest=code_digest, label=label)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_by_digest(db: Session, *, code_digest: str) -> models.WorkshopSignupCode | None:
    return db.execute(
        select(models.WorkshopSignupCode).where(
            models.WorkshopSignupCode.code_digest == code_digest
        )
    ).scalar_one_or_none()


def list_all(db: Session) -> list[models.WorkshopSignupCode]:
    return list(
        db.execute(
            select(models.WorkshopSignupCode).order_by(
                models.WorkshopSignupCode.created_at,
                models.WorkshopSignupCode.id,
            )
        ).scalars()
    )


def delete(db: Session, *, code_id: UUID) -> None:
    record = db.get(models.WorkshopSignupCode, code_id)
    if record is not None:
        db.delete(record)
        db.commit()
