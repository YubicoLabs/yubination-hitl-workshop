"""Purpose-bound PQ confirmation and per-user authentication policy."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from preloop.api.auth import get_current_active_user
from preloop.models.crud import crud_audit_log
from preloop.models.crud.webauthn_credential import crud_webauthn_credential
from preloop.models.db.session import get_db_session
from preloop.models.models.user import User
from preloop.services.pq_authentication import policy_status
import uuid
from typing import Any, Literal
from fastapi import HTTPException
from pydantic import BaseModel
from fido2.webauthn import (
    AuthenticationResponse,
    AuthenticatorData,
    UserVerificationRequirement,
)
from preloop.api.endpoints._webauthn_utils import acd_from_stored, auth_options_to_dict
from preloop.api.endpoints.webauthn_registration import fido2_server
from preloop.services.webauthn_context import validate_ceremony_context
from preloop.services.pq_authentication import eligible

router = APIRouter(prefix="/webauthn/pq-policy", tags=["PQ authentication"])


@router.get("")
def get_policy(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> dict:
    return policy_status(
        current_user,
        crud_webauthn_credential.list_by_user(
            db, user_id=current_user.id, account_id=current_user.account_id
        ),
    )


class ConfirmationBegin(BaseModel):
    action: Literal["enable", "disable", "enroll", "remove", "test"]
    version: int
    credential_id: uuid.UUID | None = None
    emergency: bool = False
    consent: bool = False


class ConfirmationComplete(BaseModel):
    session_id: uuid.UUID
    response: dict[str, Any]


def _credentials(db: Session, user: User) -> list:
    return crud_webauthn_credential.list_by_user(
        db, user_id=user.id, account_id=user.account_id
    )


def _check_action(body: ConfirmationBegin, user: User, credentials: list) -> None:
    if body.version != user.pq_policy_version:
        raise HTTPException(409, "Passkey settings changed. Start again.")
    state = policy_status(user, credentials)
    if body.action == "enable":
        if not body.consent:
            raise HTTPException(
                422, "Confirm the PQ-only and no-recovery disclosure first."
            )
        if state["eligible_count"] < 2:
            raise HTTPException(409, "Add two eligible PQ passkeys first.")
    if body.action in ("remove", "test"):
        target = None
        if body.credential_id is not None:
            target = next((c for c in credentials if c.id == body.credential_id), None)
            if target is None:
                raise HTTPException(404, "Credential not found")
        if body.action == "remove" and target is None:
            raise HTTPException(422, "Choose the credential to remove.")
        if body.action == "remove" and user.pq_only and not body.emergency:
            remaining = [c for c in credentials if c.id != target.id]
            if not policy_status(user, remaining)["ready"]:
                raise HTTPException(
                    409,
                    "Routine removal requires two tested PQ passkeys to remain. For a compromised key, choose emergency revocation.",
                )


@router.post("/begin")
def begin_confirmation(
    body: ConfirmationBegin,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> dict:
    credentials = _credentials(db, current_user)
    _check_action(body, current_user, credentials)
    allowed = [
        c
        for c in credentials
        if (
            c.id == body.credential_id
            if body.action == "test" and body.credential_id is not None
            else eligible(c)
        )
    ]
    if not allowed:
        raise HTTPException(
            409, "No eligible passkey is available for this confirmation."
        )
    options, state = fido2_server.authenticate_begin(
        credentials=[
            acd_from_stored(c.credential_id, c.public_key_cbor, c.aaguid)
            for c in allowed
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    state = dict(state)
    state["pq_action"] = body.model_dump(mode="json")
    session_id = uuid.uuid4()
    crud_webauthn_credential.create_login_session(
        db,
        session_id=session_id,
        state_dict=state,
        challenge=bytes(options.public_key.challenge),
        kind="pq_confirm",
        user_id=current_user.id,
        account_id=current_user.account_id,
    )
    return dict(session_id=str(session_id), options=auth_options_to_dict(options))


@router.post("/complete")
def complete_confirmation(
    body: ConfirmationComplete,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> dict:
    session = crud_webauthn_credential.consume_login_session(
        db, session_id=body.session_id
    )
    if (
        session is None
        or session.kind != "pq_confirm"
        or session.user_id != current_user.id
        or session.account_id != current_user.account_id
    ):
        raise HTTPException(401, "Confirmation expired or invalid. Start again.")
    user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if user is None or not user.is_active:
        raise HTTPException(401, "Authentication failed")
    credentials = _credentials(db, user)
    action = ConfirmationBegin.model_validate(session.state_dict.pop("pq_action"))
    _check_action(action, user, credentials)
    try:
        assertion = AuthenticationResponse.from_dict(body.response)
        credential = next(c for c in credentials if c.credential_id == assertion.raw_id)
        if action.action == "test":
            if (
                (
                    action.credential_id is not None
                    and credential.id != action.credential_id
                )
                or (action.credential_id is None and not eligible(credential))
                or credential.uv_initialized is not True
            ):
                raise ValueError("Wrong credential")
        elif not eligible(credential):
            raise ValueError("PQ credential required")
        if (
            assertion.response.user_handle is not None
            and bytes(assertion.response.user_handle) != user.id.bytes
        ):
            raise ValueError("Wrong user")
        acd = acd_from_stored(
            credential.credential_id, credential.public_key_cbor, credential.aaguid
        )
        fido2_server.authenticate_complete(session.state_dict, [acd], assertion)
        validate_ceremony_context(
            assertion.response.client_data,
            assertion.response.authenticator_data,
            backup_eligible=credential.backup_eligible,
        )
        if not (
            assertion.response.authenticator_data.flags & AuthenticatorData.FLAG.UV
        ):
            raise ValueError("User verification required")
    except (ValueError, TypeError, KeyError, StopIteration):
        raise HTTPException(401, "Passkey confirmation failed. Start again.")
    data = assertion.response.authenticator_data
    # Only the explicit authentication test contributes readiness. An approval or
    # management confirmation is a different ceremony, never a readiness shortcut.
    if action.action == "test":
        crud_webauthn_credential.record_authentication(
            db,
            credential=credential,
            sign_count=data.counter,
            backup_state=bool(data.flags & AuthenticatorData.FLAG.BS),
        )
    elif action.action in ("enable", "disable"):
        crud_webauthn_credential.set_policy(
            db, user=user, enabled=action.action == "enable"
        )
    elif action.action == "remove":
        target = next(c for c in credentials if c.id == action.credential_id)
        crud_webauthn_credential.delete_owned(db, credential=target)
        crud_webauthn_credential.advance_policy_version(db, user=user)
        credentials = [c for c in credentials if c.id != target.id]
    result = policy_status(user, credentials)
    authorized_version = user.pq_policy_version
    db.commit()
    if action.action == "enroll":
        grant_id = uuid.uuid4()
        crud_webauthn_credential.create_login_session(
            db,
            session_id=grant_id,
            state_dict={"version": authorized_version},
            challenge=b"",
            kind="pq_enroll",
            user_id=user.id,
            account_id=user.account_id,
        )
        result["authorization_id"] = str(grant_id)
    try:
        crud_audit_log.log_action(
            db,
            account_id=user.account_id,
            user_id=user.id,
            action="pq_authentication_" + action.action,
            resource_type="user",
            resource_id=str(user.id),
            status="success",
            details={
                "policy_version": authorized_version,
                "emergency": action.emergency,
            },
        )
    except Exception:
        db.rollback()
    return result
