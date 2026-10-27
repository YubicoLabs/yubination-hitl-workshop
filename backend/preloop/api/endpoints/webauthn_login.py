"""WebAuthn passwordless login and 2FA login endpoints.

POST /webauthn/login/begin   — return challenge for navigator.credentials.get()
POST /webauthn/login/complete — verify assertion, return JWT

These endpoints are unauthenticated. They share the fido2_server singleton from
webauthn_registration so all ceremonies use the same RP configuration.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fido2.webauthn import (
    AuthenticationResponse,
    AuthenticatorData,
    UserVerificationRequirement,
)

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from preloop.api.auth.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)
from preloop.api.endpoints._webauthn_utils import (
    acd_from_stored,
    auth_options_to_dict,
    b64url_decode as _from_b64url,
)
from preloop.api.endpoints.webauthn_registration import fido2_server
from preloop.services.webauthn_context import validate_ceremony_context
from preloop.services.pq_authentication import eligible
from preloop.services.browser_migration import validate_binding
from preloop.config import settings
from preloop.models.crud import crud_audit_log
from preloop.models.crud.webauthn_credential import crud_webauthn_credential
from preloop.models.db.session import get_db_session
from preloop.utils import get_client_ip

_FLAG = AuthenticatorData.FLAG

router = APIRouter(prefix="/webauthn", tags=["WebAuthn Login"])

# ---------------------------------------------------------------------------
# Rate limiting — separate IP and user namespaces, 20 attempts / 60 s
# ---------------------------------------------------------------------------

_RATE_WINDOW = 60
_RATE_MAX_IP = 20
_RATE_MAX_USER = 10

_MAX_CREDENTIAL_ID_BYTES = 1023


def _check_login_rate_limit(
    namespace: str, key: str, db: Session, max_hits: int
) -> None:
    """DB-backed fixed-window rate limiter for login endpoints."""
    key_hash = hashlib.sha256(f"{namespace}:{key}".encode()).hexdigest()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=_RATE_WINDOW)

    result = db.execute(
        text(
            """
            INSERT INTO webauthn_login_rate_limit (namespace, key_hash, hit_count, window_start)
            VALUES (:namespace, :key_hash, 1, :now)
            ON CONFLICT (namespace, key_hash) DO UPDATE
            SET
                hit_count = CASE
                    WHEN webauthn_login_rate_limit.window_start < :window_start
                    THEN 1
                    ELSE webauthn_login_rate_limit.hit_count + 1
                END,
                window_start = CASE
                    WHEN webauthn_login_rate_limit.window_start < :window_start
                    THEN :now
                    ELSE webauthn_login_rate_limit.window_start
                END
            RETURNING hit_count
            """
        ),
        {
            "namespace": namespace,
            "key_hash": key_hash,
            "now": now,
            "window_start": window_start,
        },
    )
    hit_count = result.scalar()
    db.commit()

    if hit_count > max_hits:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in 1 minute.",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginBeginRequest(BaseModel):
    # Optional: specify a username to start a targeted 2FA ceremony.
    # Omit for discoverable (passkey) flow.
    username: Optional[str] = None


class LoginBeginResponse(BaseModel):
    session_id: str
    options: Dict[str, Any]


class LoginCompleteRequest(BaseModel):
    session_id: str
    response: Dict[str, Any]


class LoginCompleteResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/login/begin",
    response_model=LoginBeginResponse,
    status_code=status.HTTP_200_OK,
)
def login_begin(
    body: LoginBeginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> LoginBeginResponse:
    """Start a WebAuthn login ceremony.

    Returns a challenge and session_id. The client passes the challenge to
    navigator.credentials.get(), then calls /login/complete with the assertion.
    """
    if not settings.webauthn_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WebAuthn login is not enabled on this server.",
        )

    client_ip = get_client_ip(request)
    _check_login_rate_limit("ip", client_ip, db, _RATE_MAX_IP)

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

    allow_creds = None
    kind = "passwordless"
    user_id: Optional[uuid.UUID] = None
    account_id: Optional[uuid.UUID] = None

    if body.username:
        # Targeted 2FA begin: look up the user and build allowCredentials.
        from preloop.models.crud import crud_user

        user = crud_user.get_by_username(db, username=body.username)
        if user is not None:
            creds = crud_webauthn_credential.list_by_user(
                db, user_id=user.id, account_id=user.account_id
            )
            if creds:
                allow_creds = [
                    crud_webauthn_credential.get_by_credential_id(
                        db, credential_id=c.credential_id
                    )
                    for c in creds
                ]
                # Filter out None in case any lookup fails
                allow_creds = [c for c in allow_creds if c is not None]
                kind = "2fa"
                user_id = user.id
                account_id = user.account_id

    # Build fido2 AttestedCredentialData list for authenticate_begin
    acd_list = []
    if allow_creds:
        for c in allow_creds:
            try:
                acd = acd_from_stored(c.credential_id, c.public_key_cbor, c.aaguid)
                acd_list.append(acd)
            except Exception:
                pass

    options, state = fido2_server.authenticate_begin(
        credentials=acd_list if acd_list else None,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    challenge_bytes = bytes(options.public_key.challenge)
    session_id = uuid.uuid4()
    crud_webauthn_credential.create_login_session(
        db,
        session_id=session_id,
        state_dict=dict(state),
        challenge=challenge_bytes,
        kind=kind,
        user_id=user_id,
        account_id=account_id,
    )

    return LoginBeginResponse(
        session_id=str(session_id),
        options=auth_options_to_dict(options),
    )


@router.post(
    "/login/complete",
    response_model=LoginCompleteResponse,
    status_code=status.HTTP_200_OK,
)
def login_complete(
    body: LoginCompleteRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> LoginCompleteResponse:
    """Complete a WebAuthn login ceremony.

    Verifies the assertion against the stored public key and issues a JWT pair
    on success. All failure paths return a uniform 401 to prevent user enumeration
    (AP-03).
    """
    if not settings.webauthn_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WebAuthn login is not enabled on this server.",
        )

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

    auth_failed = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication failed",
    )

    # Rate-limit by IP on the complete path too.
    client_ip = get_client_ip(request)
    _check_login_rate_limit("ip", client_ip, db, _RATE_MAX_IP)

    try:
        session_uuid = uuid.UUID(body.session_id)
    except (ValueError, AttributeError):
        raise auth_failed

    # Atomic consume — prevents TOCTOU replay
    consumed = crud_webauthn_credential.consume_login_session(
        db, session_id=session_uuid
    )
    if consumed is None or consumed.kind not in ("passwordless", "2fa"):
        raise auth_failed

    # Parse the credential ID from the response to look up the stored credential
    raw_response = body.response
    raw_id_b64 = raw_response.get("rawId") or raw_response.get("id")
    if not raw_id_b64:
        raise auth_failed

    try:
        credential_id_bytes = _from_b64url(raw_id_b64)
    except Exception:
        raise auth_failed

    # Guard against oversized credential IDs (spec §6.1.1)
    if len(credential_id_bytes) > _MAX_CREDENTIAL_ID_BYTES:
        raise auth_failed

    stored_cred = crud_webauthn_credential.get_by_credential_id(
        db, credential_id=credential_id_bytes
    )
    if stored_cred is None:
        raise auth_failed
    migration_context = consumed.state_dict.get("_migration_binding")
    if migration_context is not None:
        if str(stored_cred.id) != migration_context.get("source"):
            raise auth_failed

    # Credentials that were registered without UV must not be used for login.
    if stored_cred.uv_initialized is False:
        raise auth_failed

    verified_key = bytes(stored_cred.public_key_cbor)

    # Reconstruct AttestedCredentialData and verify the assertion.
    try:
        acd = acd_from_stored(
            stored_cred.credential_id,
            stored_cred.public_key_cbor,
            stored_cred.aaguid,
        )
        auth_response = AuthenticationResponse.from_dict(raw_response)
        fido2_server.authenticate_complete(
            consumed.state_dict,
            [acd],
            auth_response,
        )
        # AuthenticatorData carries the flags and sign counter we need below.
        auth_data = auth_response.response.authenticator_data
        validate_ceremony_context(
            auth_response.response.client_data,
            auth_data,
            backup_eligible=stored_cred.backup_eligible,
        )
    except Exception:
        raise auth_failed

    # UV flag must be set in the assertion (not just at registration)
    if not (auth_data.flags & _FLAG.UV):
        raise auth_failed

    # Bind to the expected user when the session was targeted (2FA path).
    if consumed.user_id is not None:
        if (
            stored_cred.user_id != consumed.user_id
            or stored_cred.account_id != consumed.account_id
        ):
            raise auth_failed

    # Resolve user via userHandle from the authenticator response.
    # For discoverable credentials, user_handle identifies who authenticated.
    user_handle = auth_response.response.user_handle
    if user_handle is not None:
        try:
            resolved_user_id = uuid.UUID(bytes=bytes(user_handle))
        except (ValueError, TypeError):
            raise auth_failed
        if stored_cred.user_id != resolved_user_id:
            raise auth_failed
    if (
        migration_context is not None
        and user_handle is not None
        and user_handle != stored_cred.user_id.bytes
    ):
        raise auth_failed

    # All checks pass — fetch the user record
    from preloop.models.crud import crud_user
    from preloop.models.models.user import User as UserModel

    user: Optional[UserModel] = crud_user.get(db, id=stored_cred.user_id)
    if user is None or not user.is_active:
        raise auth_failed

    # Rate-limit by user after we know who they are.
    _check_login_rate_limit("user", str(user.id), db, _RATE_MAX_USER)

    # Serialize the current policy decision with enrollment/removal/activation.
    user = crud_webauthn_credential.lock_user(
        db, user_id=user.id, account_id=user.account_id
    )
    if user is None or not user.is_active:
        raise auth_failed
    current = crud_webauthn_credential.get_by_credential_id(
        db, credential_id=credential_id_bytes
    )
    if (
        current is None
        or current.user_id != user.id
        or current.account_id != user.account_id
        or current.public_key_cbor != verified_key
    ):
        raise auth_failed
    if migration_context is not None:
        validate_binding(db, user, migration_context, require_transition=False)
        if user.pq_only is True:
            raise auth_failed
    if user.pq_only is True and not eligible(current):
        db.rollback()
        try:
            crud_audit_log.log_action(
                db,
                account_id=user.account_id,
                user_id=user.id,
                action="webauthn_login",
                resource_type="user",
                resource_id=str(user.id),
                status="denied",
                ip_address=client_ip,
                details={
                    "reason": "pq_passkey_required",
                    "proof_verified": True,
                    "policy_version": user.pq_policy_version,
                },
            )
        except Exception:
            db.rollback()
        raise HTTPException(
            403,
            detail={
                "code": "pq_passkey_required",
                "message": "Your passkey was verified. Use a post-quantum passkey to sign in.",
            },
        )
    crud_webauthn_credential.record_authentication(
        db,
        credential=current,
        sign_count=auth_data.counter,
        backup_state=bool(auth_data.flags & _FLAG.BS),
    )
    # Issue tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "scopes": []},
        expires_delta=access_token_expires,
    )
    refresh_token = create_access_token(
        data={"sub": str(user.id), "scopes": [], "refresh": True},
        expires_delta=timedelta(days=7),
    )

    db.commit()

    # Audit log the successful login
    try:
        crud_audit_log.log_action(
            db,
            account_id=user.account_id,
            user_id=user.id,
            action="webauthn_login",
            resource_type="user",
            resource_id=str(user.id),
            status="success",
            ip_address=client_ip,
            details={
                "kind": consumed.kind,
                "policy_version": user.pq_policy_version,
                "pq_only": user.pq_only,
            },
        )
    except Exception:
        pass

    return LoginCompleteResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
