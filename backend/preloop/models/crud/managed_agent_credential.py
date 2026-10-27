"""CRUD operations for durable managed-agent credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.api_key import ApiKey
from ..models.managed_agent_credential import ManagedAgentCredential
from .base import CRUDBase


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CRUDManagedAgentCredential(CRUDBase[ManagedAgentCredential]):
    """CRUD helpers for durable managed-agent credentials."""

    def list_for_agent(
        self, db: Session, *, account_id: str, agent_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            db.query(self.model, ApiKey)
            .join(ApiKey, self.model.api_key_id == ApiKey.id)
            .filter(
                self.model.account_id == account_id,
                self.model.managed_agent_id == agent_id,
            )
            .order_by(self.model.created_at.desc())
            .all()
        )
        return [self._row_to_summary(row[0], row[1]) for row in rows]

    def get_for_agent(
        self, db: Session, *, account_id: str, agent_id: str, credential_id: str
    ) -> Optional[ManagedAgentCredential]:
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.managed_agent_id == agent_id,
                self.model.id == credential_id,
            )
            .first()
        )

    def create_for_agent(
        self,
        db: Session,
        *,
        account_id: Any,
        agent_id: Any,
        api_key_id: Any,
        created_by_user_id: Any,
        name: str,
        description: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        key_prefix: Optional[str] = None,
        credential_type: str = "durable_api_key",
        issued_at: Optional[datetime] = None,
        commit: bool = True,
    ) -> ManagedAgentCredential:
        db_obj = ManagedAgentCredential(
            account_id=account_id,
            managed_agent_id=agent_id,
            api_key_id=api_key_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            credential_type=credential_type,
            status="active",
            scopes=scopes or [],
            key_prefix=key_prefix,
            last_issued_at=issued_at or _utc_now(),
        )
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def revoke_for_agent(
        self,
        db: Session,
        *,
        account_id: str,
        agent_id: str,
        credential_id: str,
        reason: Optional[str] = None,
        commit: bool = True,
    ) -> Optional[ManagedAgentCredential]:
        db_obj = self.get_for_agent(
            db,
            account_id=account_id,
            agent_id=agent_id,
            credential_id=credential_id,
        )
        if db_obj is None:
            return None
        db_obj.status = "revoked"
        db_obj.revoked_at = _utc_now()
        db_obj.revoked_reason = reason
        if db_obj.api_key is not None:
            db_obj.api_key.is_active = False
            db.add(db_obj.api_key)
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    @staticmethod
    def _row_to_summary(
        credential: ManagedAgentCredential, api_key: Optional[ApiKey]
    ) -> dict[str, Any]:
        return {
            "id": str(credential.id),
            "api_key_id": str(credential.api_key_id),
            "created_by_user_id": (
                str(credential.created_by_user_id)
                if credential.created_by_user_id
                else None
            ),
            "name": credential.name,
            "description": credential.description,
            "credential_type": credential.credential_type,
            "status": credential.status,
            "scopes": list(credential.scopes or []),
            "key_prefix": credential.key_prefix,
            "created_at": credential.created_at,
            "updated_at": credential.updated_at,
            "last_issued_at": credential.last_issued_at,
            "last_used_at": api_key.last_used_at if api_key is not None else None,
            "expires_at": api_key.expires_at if api_key is not None else None,
            "revoked_at": credential.revoked_at,
            "revoked_reason": credential.revoked_reason,
        }


crud_managed_agent_credential = CRUDManagedAgentCredential(ManagedAgentCredential)
