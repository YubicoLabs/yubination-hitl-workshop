"""CRUD operations for durable managed-agent enrollment state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.managed_agent_enrollment import ManagedAgentEnrollment
from .base import CRUDBase


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CRUDManagedAgentEnrollment(CRUDBase[ManagedAgentEnrollment]):
    """CRUD helpers for managed-agent enrollment records."""

    def get_latest_for_agent(
        self, db: Session, *, account_id: str, agent_id: str
    ) -> Optional[ManagedAgentEnrollment]:
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.managed_agent_id == agent_id,
            )
            .order_by(self.model.created_at.desc())
            .first()
        )

    def list_for_agent(
        self, db: Session, *, account_id: str, agent_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.managed_agent_id == agent_id,
            )
            .order_by(self.model.created_at.desc())
            .all()
        )
        return [self._to_summary(row) for row in rows]

    def create_for_agent(
        self,
        db: Session,
        *,
        account_id: Any,
        agent_id: Any,
        created_by_user_id: Any,
        enrollment_type: str,
        adapter_key: Optional[str] = None,
        status: str = "active",
        target_config_path: Optional[str] = None,
        discovered_config: Optional[dict[str, Any]] = None,
        managed_config: Optional[dict[str, Any]] = None,
        backup_metadata: Optional[dict[str, Any]] = None,
        validation_result: Optional[dict[str, Any]] = None,
        restore_available: bool = False,
        last_applied_at: Optional[datetime] = None,
        last_validated_at: Optional[datetime] = None,
        last_restored_at: Optional[datetime] = None,
        commit: bool = True,
    ) -> ManagedAgentEnrollment:
        db_obj = ManagedAgentEnrollment(
            account_id=account_id,
            managed_agent_id=agent_id,
            created_by_user_id=created_by_user_id,
            enrollment_type=enrollment_type,
            adapter_key=adapter_key,
            status=status,
            target_config_path=target_config_path,
            discovered_config=discovered_config or {},
            managed_config=managed_config or {},
            backup_metadata=backup_metadata or {},
            validation_result=validation_result or {},
            restore_available=restore_available,
            last_applied_at=last_applied_at,
            last_validated_at=last_validated_at,
            last_restored_at=last_restored_at,
        )
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def get_latest_for_agent_by_type(
        self,
        db: Session,
        *,
        account_id: str,
        agent_id: str,
        enrollment_type: str,
    ) -> Optional[ManagedAgentEnrollment]:
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.managed_agent_id == agent_id,
                self.model.enrollment_type == enrollment_type,
            )
            .order_by(self.model.created_at.desc())
            .first()
        )

    def get_for_agent(
        self,
        db: Session,
        *,
        account_id: str,
        agent_id: str,
        enrollment_id: str,
    ) -> Optional[ManagedAgentEnrollment]:
        return (
            db.query(self.model)
            .filter(
                self.model.account_id == account_id,
                self.model.managed_agent_id == agent_id,
                self.model.id == enrollment_id,
            )
            .first()
        )

    def upsert_runtime_bootstrap(
        self,
        db: Session,
        *,
        account_id: Any,
        agent_id: Any,
        created_by_user_id: Any,
        session_source_type: str,
        session_source_id: str,
        session_reference: Optional[str],
        display_name: str,
        managed_mcp_servers: list[str],
        runtime_session_id: Any,
        commit: bool = True,
    ) -> ManagedAgentEnrollment:
        db_obj = self.get_latest_for_agent_by_type(
            db,
            account_id=str(account_id),
            agent_id=str(agent_id),
            enrollment_type="runtime_session_bootstrap",
        )
        now = _utc_now()
        discovered_config = {
            "session_source_type": session_source_type,
            "session_source_id": session_source_id,
            "session_reference": session_reference,
            "display_name": display_name,
        }
        managed_config = {
            "managed_mcp_servers": managed_mcp_servers,
            "runtime_session_id": str(runtime_session_id),
        }
        if db_obj is None:
            return self.create_for_agent(
                db,
                account_id=account_id,
                agent_id=agent_id,
                created_by_user_id=created_by_user_id,
                enrollment_type="runtime_session_bootstrap",
                adapter_key=session_source_type,
                status="active",
                target_config_path=session_reference,
                discovered_config=discovered_config,
                managed_config=managed_config,
                validation_result={"bootstrap": True},
                restore_available=False,
                last_applied_at=now,
                last_validated_at=now,
                commit=commit,
            )

        db_obj.created_by_user_id = created_by_user_id
        db_obj.adapter_key = session_source_type
        db_obj.status = "active"
        db_obj.target_config_path = session_reference
        db_obj.discovered_config = discovered_config
        db_obj.managed_config = managed_config
        db_obj.validation_result = {"bootstrap": True}
        db_obj.last_applied_at = now
        db_obj.last_validated_at = now
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def mark_validated(
        self,
        db: Session,
        *,
        account_id: str,
        agent_id: str,
        enrollment_id: str,
        validation_result: Optional[dict[str, Any]] = None,
        status: str = "validated",
        commit: bool = True,
    ) -> Optional[ManagedAgentEnrollment]:
        db_obj = self.get_for_agent(
            db,
            account_id=account_id,
            agent_id=agent_id,
            enrollment_id=enrollment_id,
        )
        if db_obj is None:
            return None
        db_obj.status = status
        db_obj.validation_result = validation_result or {}
        db_obj.last_validated_at = _utc_now()
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def mark_restored(
        self,
        db: Session,
        *,
        account_id: str,
        agent_id: str,
        enrollment_id: str,
        backup_metadata: Optional[dict[str, Any]] = None,
        validation_result: Optional[dict[str, Any]] = None,
        status: str = "restored",
        commit: bool = True,
    ) -> Optional[ManagedAgentEnrollment]:
        db_obj = self.get_for_agent(
            db,
            account_id=account_id,
            agent_id=agent_id,
            enrollment_id=enrollment_id,
        )
        if db_obj is None:
            return None
        if backup_metadata:
            db_obj.backup_metadata = {
                **(db_obj.backup_metadata or {}),
                **backup_metadata,
            }
        if validation_result:
            db_obj.validation_result = {
                **(db_obj.validation_result or {}),
                **validation_result,
            }
        db_obj.status = status
        db_obj.restore_available = False
        db_obj.last_restored_at = _utc_now()
        db.add(db_obj)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    @staticmethod
    def _to_summary(enrollment: ManagedAgentEnrollment) -> dict[str, Any]:
        return {
            "id": str(enrollment.id),
            "created_by_user_id": (
                str(enrollment.created_by_user_id)
                if enrollment.created_by_user_id
                else None
            ),
            "enrollment_type": enrollment.enrollment_type,
            "adapter_key": enrollment.adapter_key,
            "status": enrollment.status,
            "target_config_path": enrollment.target_config_path,
            "discovered_config": enrollment.discovered_config or {},
            "managed_config": enrollment.managed_config or {},
            "backup_metadata": enrollment.backup_metadata or {},
            "validation_result": enrollment.validation_result or {},
            "restore_available": enrollment.restore_available,
            "last_applied_at": enrollment.last_applied_at,
            "last_validated_at": enrollment.last_validated_at,
            "last_restored_at": enrollment.last_restored_at,
            "created_at": enrollment.created_at,
            "updated_at": enrollment.updated_at,
        }


crud_managed_agent_enrollment = CRUDManagedAgentEnrollment(ManagedAgentEnrollment)
