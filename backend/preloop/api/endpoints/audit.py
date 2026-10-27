"""Audit endpoints for forensic review of resolved approval decisions."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from preloop.api.auth import get_current_active_user
from preloop.models.crud import crud_approval_request
from preloop.models.db.session import get_db_session
from preloop.models.models.user import User
from preloop.models.schemas.audit import AuditDecisionList, AuditDecisionRecord

from preloop.services.approval_verification import (
    resolve_credential,
    verify_stored_binding,
)

router = APIRouter(prefix="/audit", tags=["Audit"])


# ---------------------------------------------------------------------------
# Verify schemas
# ---------------------------------------------------------------------------


class AuditVerifyResult(BaseModel):
    request_id: str
    signature_valid: bool
    challenge_bound: bool
    intent_intact: bool


@router.get("/decisions/{request_id}/verify", response_model=AuditVerifyResult)
def verify_audit_decision(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> AuditVerifyResult:
    """Re-run stored assertion checks without asserting hardware provenance."""
    req = crud_approval_request.get(
        db, id=str(request_id), account_id=current_user.account_id
    )
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if not req.step_up_verified:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="step_up_verified is False — no hardware ceremony was completed",
        )

    nonce: Optional[bytes] = getattr(req, "step_up_challenge_nonce", None)
    client_data_json: Optional[bytes] = getattr(req, "step_up_client_data_json", None)
    auth_data: Optional[bytes] = getattr(req, "step_up_authenticator_data", None)
    sig: Optional[bytes] = getattr(req, "step_up_signature", None)

    if not all([nonce, client_data_json, auth_data, sig]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="not verifiable — assertion bytes were not stored for this record",
        )

    credential = resolve_credential(db, current_user.account_id, req)
    return AuditVerifyResult(
        request_id=str(request_id), **verify_stored_binding(req, credential)
    )


@router.get("/decisions", response_model=AuditDecisionList)
def list_audit_decisions(
    step_up_verified: Optional[bool] = Query(None),
    tool_name: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> AuditDecisionList:
    """Forensic audit log of resolved approval decisions for the account."""
    items, total = crud_approval_request.get_audit_decisions(
        db,
        account_id=current_user.account_id,
        statuses=["approved", "declined"],
        step_up_verified=step_up_verified,
        tool_name=tool_name,
        since=since,
        until=until,
        skip=skip,
        limit=limit,
    )
    return AuditDecisionList(
        items=[AuditDecisionRecord.from_orm(r) for r in items],
        total=total,
        skip=skip,
        limit=limit,
    )
