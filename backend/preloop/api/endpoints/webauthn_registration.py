"""WebAuthn credential registration endpoints."""

from datetime import datetime, timezone
from importlib.metadata import version
import copy
import threading
import uuid
from preloop.services.previewsign_catalog import PREVIEWSIGN_MODELS
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fido2.cbor import decode as cbor_decode
from fido2.cbor import encode as cbor_encode
from fido2.server import Fido2Server
from fido2.webauthn import (
    AuthenticatorData,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialUserEntity,
    RegistrationResponse,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from pydantic import BaseModel
from sqlalchemy.orm import Session

from preloop.services.webauthn_context import validate_ceremony_context
from preloop.services.pq_authentication import (
    eligible as _pq_eligible,
    authentication_tested as _authentication_tested,
)
from preloop.api.auth import get_current_active_user
from preloop.api.auth.jwt import decode_token, oauth2_scheme_optional
from preloop.api.endpoints._webauthn_utils import b64url_decode as _from_b64url
from preloop.api.endpoints._webauthn_utils import b64url_encode as _b64url
from preloop.models.crud.webauthn_credential import crud_webauthn_credential
from preloop.models.db.session import get_db_session
from preloop.models.models.user import User
from preloop.services.browser_migration import (
    binding,
    bound_credential,
    require_workshop,
    validate_binding,
)
from preloop.api.endpoints._webauthn_utils import acd_from_stored, auth_options_to_dict
from fido2.webauthn import AuthenticationResponse

# Authenticated MDS is display enrichment; it never establishes key attestation.
import os
from preloop.services.fido_metadata import metadata_cache, pq_upgrade_support

_ARKG_ENABLED: bool = os.getenv("WEBAUTHN_ARKG_ENABLED", "false").lower() not in (
    "false",
    "0",
    "no",
)


def _get_mds_entries() -> List[Dict[str, Any]]:
    return metadata_cache.entries()


def _get_mds_snapshot() -> tuple[List[Dict[str, Any]], str]:
    return metadata_cache.snapshot()


def _warm_mds_cache_background() -> None:
    threading.Thread(
        target=_get_mds_entries, daemon=True, name="mds-cache-warm"
    ).start()


_FLAG = AuthenticatorData.FLAG

router = APIRouter(prefix="/webauthn", tags=["WebAuthn"])

_RP_ID = "localhost"
_RP_NAME = "Preloop"

try:
    from preloop.config import settings as _settings

    # Read from the declared Settings fields (pydantic-settings v2 requires declared fields;
    # getattr on an extra="ignore" model silently returns the default).
    _RP_ID = _settings.webauthn_rp_id
    _RP_NAME = _settings.webauthn_rp_name
except Exception:
    pass

fido2_server = Fido2Server(PublicKeyCredentialRpEntity(id=_RP_ID, name=_RP_NAME))

_MLDSA44_ALGORITHM = -48
_SESSION_REQUESTED_ALGORITHM = "_preloop_requested_alg"
_SESSION_ACCOUNT_ID = "_preloop_account_id"
_SESSION_USER_ID = "_preloop_user_id"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterBeginRequest(BaseModel):
    name: str = ""
    algorithm: Literal["default", "mldsa44", "es256"] = "default"
    authorization_id: Optional[uuid.UUID] = None
    upgrade_authorization_id: Optional[uuid.UUID] = None
    replacement_source_id: Optional[uuid.UUID] = None


class MigrationContext(BaseModel):
    source_record_id: str
    source_credential_id: str
    source_algorithm: int
    target_algorithm: int
    exclude_credentials_before: List[Dict[str, str]]


class RegisterBeginResponse(BaseModel):
    session_id: str
    options: Dict[str, Any]
    migration_context: Optional[MigrationContext] = None


class RegisterCompleteRequest(BaseModel):
    session_id: str
    name: str = ""
    response: Dict[str, Any]
    # Optional ARKG previewSign seed fields — populated when the authenticator
    # supports the previewSign extension (e.g. YubiKey 5.8+).
    arkg_seed_pub_b64: Optional[str] = None
    arkg_seed_kh_b64: Optional[str] = None


def _require_human_access_token(token: Optional[str], current_user: User) -> None:
    if not token:
        raise HTTPException(401, "Human access token required")
    token_data = decode_token(token)
    if (
        token_data.refresh is not False
        or token_data.exp is None
        or token_data.sub != str(current_user.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Human access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )


class CredentialRecord(BaseModel):
    id: str
    credential_id: str
    replaced_credential_id: Optional[str] = None
    name: str
    aaguid: str
    created_at: str
    last_used_at: Optional[str]
    arkg_capable: bool = False
    discoverability_source: Optional[str] = None
    discoverable: Optional[bool] = None
    backup_eligible: Optional[bool] = None
    backup_state: Optional[bool] = None
    cose_algorithm: Optional[int] = None
    pq_eligible: bool = False
    authentication_tested_at: Optional[str] = None


def _previewsign_ready(credential: Any) -> bool:
    return (
        credential.arkg_protocol == "arkg_preview"
        and isinstance(credential.arkg_seed_pub_cbor, bytes)
        and bool(credential.arkg_seed_pub_cbor)
        and isinstance(credential.arkg_seed_kh, bytes)
        and bool(credential.arkg_seed_kh)
    )


def _previewsign_model_support(
    entries: List[Dict[str, Any]], status: str, target: str
) -> bool:
    if status != "current" or target == "00000000-0000-0000-0000-000000000000":
        return False
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("aaguid"), str)
        and entry["aaguid"].lower() == target
    ]
    if len(matches) != 1:
        return False
    statement = matches[0].get("metadataStatement", {})
    if not isinstance(statement, dict) or statement.get("protocolFamily") != "fido2":
        return False
    info = statement.get("authenticatorGetInfo")
    extensions = info.get("extensions") if isinstance(info, dict) else None
    return (
        isinstance(extensions, list)
        and all(isinstance(item, str) for item in extensions)
        and "previewSign" in extensions
    )


def _stored_algorithm(public_key_cbor: bytes) -> Optional[int]:
    """Read the registered key's COSE algorithm, independently of device metadata."""
    if not isinstance(public_key_cbor, bytes):
        return None
    try:
        key = cbor_decode(public_key_cbor)
        algorithm = key.get(3) if isinstance(key, dict) else None
        return algorithm if type(algorithm) is int else None
    except (ValueError, TypeError, KeyError, IndexError):
        return None


class RenameRequest(BaseModel):
    name: str = ""


class MdsMetadata(BaseModel):
    """FIDO MDS metadata for a specific authenticator AAGUID."""

    found: bool
    pq_upgrade_supported: Optional[bool] = None
    previewsign_supported: bool = False
    previewsign_vendor_catalog_supported: bool = False
    previewsign_workshop_assumption: bool = False
    metadata_status: Literal["current", "stale", "unavailable"] = "unavailable"
    metadata_authenticated: bool = False
    attestation_verified: bool = False
    description: Optional[str] = None
    icon: Optional[str] = None
    key_protection: List[str] = []
    attachment_hint: List[str] = []
    user_verification_methods: List[str] = []
    protocol_family: Optional[str] = None
    certification_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _options_to_dict(
    options: Any, *, requested_algorithm: Optional[int] = None
) -> Dict[str, Any]:
    pk = options.public_key
    supported = [p.alg for p in (pk.pub_key_cred_params or [])]
    # Normal enrollment negotiates the preferred supported PQ algorithm, then
    # conventional algorithms. The relying party records what was actually used.
    default_algorithms = (
        [_MLDSA44_ALGORITHM] if _MLDSA44_ALGORITHM in supported else []
    ) + [alg for alg in supported if alg != _MLDSA44_ALGORITHM]
    pub_key_params = [
        {"type": "public-key", "alg": alg}
        for alg in (
            [requested_algorithm]
            if requested_algorithm is not None
            else default_algorithms
        )
    ]
    rk = pk.authenticator_selection
    authenticator_selection = None
    if rk:
        authenticator_selection = {
            "residentKey": rk.resident_key.value if rk.resident_key else None,
            "userVerification": rk.user_verification.value
            if rk.user_verification
            else None,
        }
    return {
        "rp": {"id": pk.rp.id, "name": pk.rp.name},
        "user": {
            "id": _b64url(bytes(pk.user.id)),
            "name": pk.user.name,
            "displayName": pk.user.display_name,
        },
        "challenge": _b64url(bytes(pk.challenge)),
        "pubKeyCredParams": pub_key_params,
        # fido2 library may return None here; WebAuthn spec requires a positive
        # integer. Fall back to 60 000 ms (60 s) — enough for a YubiKey touch.
        "timeout": pk.timeout if pk.timeout is not None else 60_000,
        "authenticatorSelection": authenticator_selection,
        # fido2 2.x doesn't expose attestation in register_begin(), so we force
        # "direct" here — Yubico Authenticator requires it to identify the device
        # as a genuine YubiKey 5.8+ and activate previewSign.
        "attestation": "direct",
        # previewSign extension — only sent when WEBAUTHN_ARKG_ENABLED=true (explicit opt-in).
        # When false: omit the extension entirely so deployments without the Yubico
        # Authenticator browser extension don't fail with "Native messaging host
        # disconnected" (Chrome routes previewSign through a native host).
        **(
            {"extensions": {"previewSign": {"generateKey": {"algorithms": [-65539]}}}}
            if _ARKG_ENABLED and requested_algorithm is None
            else {}
        ),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class MigrationBeginRequest(BaseModel):
    credential_id: uuid.UUID
    target_algorithm: Literal[-7, -48] = -48


@router.get("/migration/status")
def migration_status(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, bool]:
    return {
        "enabled": os.getenv("WORKSHOP_ONBOARDING_ENABLED", "").lower() == "true",
        "pq_only": current_user.pq_only is True,
    }


class MigrationCompleteRequest(BaseModel):
    session_id: uuid.UUID
    response: Dict[str, Any]


def _migration_begin(
    body: MigrationBeginRequest, current_user: User, db: Session, *, signin: bool
) -> Dict[str, Any]:
    require_workshop()
    current_user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if current_user is None:
        raise HTTPException(401, "Authentication failed")
    credential = bound_credential(db, current_user, body.credential_id)
    context = binding(current_user, credential, target_algorithm=body.target_algorithm)
    validate_binding(db, current_user, context, require_transition=not signin)
    if current_user.pq_only is True:
        raise HTTPException(403, "Workshop migration is unavailable under PQ-only")
    options, state = fido2_server.authenticate_begin(
        [
            acd_from_stored(
                credential.credential_id, credential.public_key_cbor, credential.aaguid
            )
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    state["_migration_binding"] = context
    session_id = uuid.uuid4()
    crud_webauthn_credential.create_login_session(
        db,
        session_id=session_id,
        state_dict=dict(state),
        challenge=bytes(options.public_key.challenge),
        kind="2fa" if signin else "migration_auth",
        user_id=current_user.id,
        account_id=current_user.account_id,
        ttl_seconds=180,
    )
    return {"session_id": str(session_id), "options": auth_options_to_dict(options)}


@router.post("/migration/begin")
def migration_begin(
    body: MigrationBeginRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    return _migration_begin(body, current_user, db, signin=False)


@router.post("/migration/signin/begin")
def migration_signin_begin(
    body: MigrationBeginRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    return _migration_begin(body, current_user, db, signin=True)


@router.post("/migration/complete")
def migration_complete(
    body: MigrationCompleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> Dict[str, str]:
    require_workshop()
    consumed = crud_webauthn_credential.consume_login_session(
        db, session_id=body.session_id
    )
    if (
        consumed is None
        or consumed.kind != "migration_auth"
        or consumed.user_id != current_user.id
        or consumed.account_id != current_user.account_id
    ):
        raise HTTPException(403, "Invalid migration authorization")
    current_user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if current_user is None:
        raise HTTPException(401, "Authentication failed")
    context = consumed.state_dict.get("_migration_binding", {})
    credential = validate_binding(db, current_user, context)
    try:
        assertion = AuthenticationResponse.from_dict(body.response)
        if (
            assertion.response.user_handle is not None
            and assertion.response.user_handle != current_user.id.bytes
        ):
            raise ValueError("Wrong user handle")
        fido2_server.authenticate_complete(
            consumed.state_dict,
            [
                acd_from_stored(
                    credential.credential_id,
                    credential.public_key_cbor,
                    credential.aaguid,
                )
            ],
            assertion,
        )
        validate_ceremony_context(
            assertion.response.client_data,
            assertion.response.authenticator_data,
            backup_eligible=credential.backup_eligible,
        )
    except Exception:
        raise HTTPException(403, "Source authentication failed")
    crud_webauthn_credential.record_authentication(
        db,
        credential=credential,
        sign_count=assertion.response.authenticator_data.counter,
        backup_state=bool(assertion.response.authenticator_data.flags & _FLAG.BS),
    )
    grant_id = uuid.uuid4()
    crud_webauthn_credential.create_login_session(
        db,
        session_id=grant_id,
        state_dict=context,
        challenge=b"",
        kind="migration_grant",
        user_id=current_user.id,
        account_id=current_user.account_id,
        ttl_seconds=180,
    )
    return {"upgrade_authorization_id": str(grant_id)}


@router.post("/migration/identify/begin")
def identify_begin(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Observe browser credential discovery without issuing sign-in authority."""
    require_workshop()
    _require_human_access_token(token, current_user)
    options, state = fido2_server.authenticate_begin(
        [], user_verification=UserVerificationRequirement.REQUIRED
    )
    session_id = uuid.uuid4()
    crud_webauthn_credential.create_login_session(
        db,
        session_id=session_id,
        state_dict=dict(state),
        challenge=bytes(options.public_key.challenge),
        kind="workshop_ident",
        user_id=current_user.id,
        account_id=current_user.account_id,
        ttl_seconds=180,
    )
    serialized = auth_options_to_dict(options)
    serialized["allowCredentials"] = []
    return {"session_id": str(session_id), "options": serialized}


@router.post("/migration/identify/complete")
def identify_complete(
    body: MigrationCompleteRequest,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    require_workshop()
    _require_human_access_token(token, current_user)
    consumed = crud_webauthn_credential.consume_login_session(
        db,
        session_id=body.session_id,
        expected_kind="workshop_ident",
        expected_user_id=current_user.id,
        expected_account_id=current_user.account_id,
    )
    if (
        consumed is None
        or consumed.kind != "workshop_ident"
        or consumed.user_id != current_user.id
        or consumed.account_id != current_user.account_id
    ):
        raise HTTPException(403, "Passkey identification expired. Try again.")
    current_user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if current_user is None:
        raise HTTPException(403, "Passkey identification failed.")
    try:
        assertion = AuthenticationResponse.from_dict(body.response)
        credentials = crud_webauthn_credential.list_by_user(
            db, user_id=current_user.id, account_id=current_user.account_id
        )
        credential = next(
            (
                item
                for item in credentials
                if item.credential_id == assertion.raw_id
                and item.user_id == current_user.id
                and item.account_id == current_user.account_id
                and item.retired_at is None
            ),
            None,
        )
        if (
            credential is None
            or credential.discoverable is False
            or credential.uv_initialized is not True
            or assertion.response.user_handle != current_user.id.bytes
        ):
            raise ValueError("Unavailable credential")
        fido2_server.authenticate_complete(
            consumed.state_dict,
            [
                acd_from_stored(
                    credential.credential_id,
                    credential.public_key_cbor,
                    credential.aaguid,
                )
            ],
            assertion,
        )
        validate_ceremony_context(
            assertion.response.client_data,
            assertion.response.authenticator_data,
            backup_eligible=credential.backup_eligible,
        )
    except Exception:
        raise HTTPException(
            403, "Use an existing passkey from this account to identify it."
        )
    # Empty allow-list behaviour and userHandle are browser observations, not
    # signed proof of residency. Never overwrite contradictory stored evidence.
    crud_webauthn_credential.record_discovery_observation(
        db, user=current_user, credential=credential
    )
    return {
        "credential_record_id": str(credential.id),
        "credential_id": _b64url(bytes(credential.credential_id)),
        "cose_algorithm": _stored_algorithm(credential.public_key_cbor),
        "discoverable": credential.discoverable,
        "discoverability_source": credential.discoverability_source,
    }


@router.post("/register/begin", response_model=RegisterBeginResponse)
def register_begin(
    body: RegisterBeginRequest,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> RegisterBeginResponse:
    """Start a WebAuthn registration ceremony."""
    grant = None
    migration_grant = None
    replacement_binding = None
    selected_modes = sum(
        value is not None
        for value in (
            body.authorization_id,
            body.upgrade_authorization_id,
            body.replacement_source_id,
        )
    )
    if selected_modes > 1:
        raise HTTPException(
            400, "Registration authorization modes are mutually exclusive"
        )
    if body.replacement_source_id is not None:
        require_workshop()
        _require_human_access_token(token, current_user)
        if body.algorithm not in ("es256", "mldsa44"):
            raise HTTPException(
                400, "Replacement requires an explicit target algorithm"
            )
    if body.algorithm == "es256" or body.upgrade_authorization_id is not None:
        require_workshop()
    if body.upgrade_authorization_id is not None:
        if (
            body.algorithm not in ("es256", "mldsa44")
            or body.authorization_id is not None
        ):
            raise HTTPException(400, "Migration requires an explicit target algorithm")
        migration_grant = crud_webauthn_credential.consume_login_session(
            db, session_id=body.upgrade_authorization_id
        )
        if (
            migration_grant is None
            or migration_grant.kind != "migration_grant"
            or migration_grant.user_id != current_user.id
            or migration_grant.account_id != current_user.account_id
        ):
            raise HTTPException(403, "Invalid upgrade authorization")
    if body.authorization_id is not None:
        grant = crud_webauthn_credential.consume_login_session(
            db, session_id=body.authorization_id
        )
    current_user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if current_user is None:
        raise HTTPException(401, "Authentication failed")
    if body.algorithm == "es256" and current_user.pq_only is True:
        raise HTTPException(403, "Classical setup is unavailable under PQ-only")
    source = None
    if body.replacement_source_id is not None:
        source = bound_credential(db, current_user, body.replacement_source_id)
        target_algorithm = {"es256": -7, "mldsa44": -48}[body.algorithm]
        replacement_binding = binding(
            current_user, source, target_algorithm=target_algorithm
        )
        source = validate_binding(db, current_user, replacement_binding)
    if migration_grant is not None:
        source = validate_binding(db, current_user, migration_grant.state_dict)
        selected_algorithm = {"es256": -7, "mldsa44": -48}[body.algorithm]
        if selected_algorithm != migration_grant.state_dict["target"]:
            raise HTTPException(403, "Registration algorithm does not match the grant")
    if current_user.pq_only is True and (
        grant is None
        or grant.kind != "pq_enroll"
        or grant.user_id != current_user.id
        or grant.account_id != current_user.account_id
        or grant.state_dict.get("version") != current_user.pq_policy_version
    ):
        raise HTTPException(
            403, "Confirm with a PQ passkey before adding a replacement."
        )
    user_entity = PublicKeyCredentialUserEntity(
        id=current_user.id.bytes,
        name=current_user.username,
        display_name=current_user.username,
    )
    options, state = fido2_server.register_begin(
        user_entity,
        # The guided lab requires discoverable credentials; normal enrollment
        # retains its existing compatibility preference.
        resident_key_requirement=(
            ResidentKeyRequirement.REQUIRED
            if source is not None or body.algorithm == "es256"
            else ResidentKeyRequirement.PREFERRED
        ),
        # userVerification REQUIRED — intentional and unchanged.
        # The credential is only usable by a verified user (YubiKey PIN or
        # biometric). Do NOT lower this to PREFERRED.
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    requested_algorithm = {"mldsa44": -48, "es256": -7}.get(body.algorithm)
    session_state = dict(state)
    session_state.update(
        {
            _SESSION_REQUESTED_ALGORITHM: requested_algorithm,
            _SESSION_ACCOUNT_ID: str(current_user.account_id),
            _SESSION_USER_ID: str(current_user.id),
            "_pq_policy_version": current_user.pq_policy_version,
            "_resident_key_required": source is not None or body.algorithm == "es256",
            "_offered_algorithms": [requested_algorithm]
            if requested_algorithm is not None
            else [p["alg"] for p in _options_to_dict(options)["pubKeyCredParams"]],
        }
    )

    session_id = uuid.uuid4()
    if migration_grant is not None:
        session_state["_migration_binding"] = migration_grant.state_dict
    if replacement_binding is not None:
        session_state["_migration_binding"] = replacement_binding
        session_state["_workshop_session_replacement"] = True
    if body.algorithm == "es256":
        session_state["_workshop_classical"] = True
    existing_credentials = crud_webauthn_credential.list_by_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    exclusions = [
        {"type": "public-key", "id": _b64url(bytes(credential.credential_id))}
        for credential in existing_credentials
    ]
    migration_metadata = None
    if source is not None:
        source_algorithm = _stored_algorithm(source.public_key_cbor)
        if source_algorithm is None or (
            migration_grant is None and replacement_binding is None
        ):
            raise HTTPException(403, "Invalid migration source")
        migration_metadata = MigrationContext(
            source_record_id=str(source.id),
            source_credential_id=_b64url(bytes(source.credential_id)),
            source_algorithm=source_algorithm,
            target_algorithm=(replacement_binding or migration_grant.state_dict)[
                "target"
            ],
            exclude_credentials_before=exclusions,
        )

    serialized = _options_to_dict(options, requested_algorithm=requested_algorithm)
    serialized["extensions"] = {**serialized.get("extensions", {}), "credProps": True}
    serialized["excludeCredentials"] = [
        {"type": "public-key", "id": _b64url(bytes(credential.credential_id))}
        for credential in existing_credentials
        if source is None or credential.id != source.id
    ]
    session_state["_registration_options"] = copy.deepcopy(serialized)
    crud_webauthn_credential.create_reg_session(
        db,
        session_id=session_id,
        account_id=current_user.account_id,
        user_id=current_user.id,
        state_dict=session_state,
    )

    return RegisterBeginResponse(
        session_id=str(session_id),
        options=serialized,
        migration_context=migration_metadata,
    )


@router.post("/register/complete", response_model=CredentialRecord)
def register_complete(
    body: RegisterCompleteRequest,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> CredentialRecord:
    """Complete a WebAuthn registration ceremony."""
    try:
        session_uuid = uuid.UUID(body.session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session_id format.",
        )
    state = crud_webauthn_credential.consume_reg_session(db, session_id=session_uuid)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration session expired or not found. Please start again.",
        )
    registration_options = state.pop("_registration_options", None)
    requested_algorithm = state.pop(_SESSION_REQUESTED_ALGORITHM, None)
    session_account_id = state.pop(_SESSION_ACCOUNT_ID, None)
    session_user_id = state.pop(_SESSION_USER_ID, None)
    policy_version = state.pop("_pq_policy_version", None)
    offered_algorithms = state.pop("_offered_algorithms", None)
    resident_key_required = state.pop("_resident_key_required", False)
    workshop_session_replacement = state.pop("_workshop_session_replacement", False)
    if workshop_session_replacement:
        require_workshop()
        _require_human_access_token(token, current_user)
    if session_account_id != str(current_user.account_id) or session_user_id != str(
        current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration session does not belong to the current account and user.",
        )
    current_user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if current_user is None or policy_version != current_user.pq_policy_version:
        raise HTTPException(409, "Passkey settings changed. Start registration again.")
    migration_context = state.pop("_migration_binding", None)
    migration_source = None
    if migration_context is not None:
        migration_source = validate_binding(db, current_user, migration_context)
        if requested_algorithm != migration_context["target"]:
            raise HTTPException(403, "Registration algorithm does not match the grant")
    if state.pop("_workshop_classical", False):
        require_workshop()
        if current_user.pq_only is True:
            raise HTTPException(403, "Classical setup is unavailable under PQ-only")
    try:
        reg_response = RegistrationResponse.from_dict(body.response)
        auth_data = fido2_server.register_complete(state, reg_response)
        validate_ceremony_context(reg_response.response.client_data, auth_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {exc}",
        )

    acd = auth_data.credential_data
    if acd is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed: no credential data in response.",
        )
    actual_algorithm = int(acd.public_key.get(3, 0))
    if (
        migration_context is not None
        and actual_algorithm != migration_context["target"]
    ):
        raise HTTPException(400, "Registration returned a different migration target")
    if (
        requested_algorithm == _MLDSA44_ALGORITHM
        and actual_algorithm != _MLDSA44_ALGORITHM
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"PQC registration returned COSE algorithm {actual_algorithm}; "
                "ML-DSA-44 (-48) is required. The browser and authenticator may "
                "not support this beta mode."
            ),
        )
    if not offered_algorithms or actual_algorithm not in offered_algorithms:
        raise HTTPException(
            400, "Registration returned an algorithm that was not offered."
        )
    public_key_cbor = cbor_encode(dict(acd.public_key))

    arkg_seed_pub_cbor: Optional[bytes] = None
    arkg_seed_kh: Optional[bytes] = None
    arkg_protocol: Optional[str] = None
    if body.arkg_seed_pub_b64:
        try:
            arkg_seed_pub_cbor = _from_b64url(body.arkg_seed_pub_b64)
            arkg_seed_kh = _from_b64url(body.arkg_seed_kh_b64 or "")
            arkg_protocol = "arkg_preview"
        except Exception:
            pass

    flags = auth_data.flags
    backup_eligible = bool(flags & _FLAG.BE)
    backup_state = bool(flags & _FLAG.BS)
    uv_initialized = bool(flags & _FLAG.UV)

    extension_results = body.response.get("clientExtensionResults", {})
    properties = (
        extension_results.get("credProps", {})
        if isinstance(extension_results, dict)
        else {}
    )
    reported_rk = properties.get("rk") if isinstance(properties, dict) else None
    discoverable = reported_rk if type(reported_rk) is bool else None

    if resident_key_required and discoverable is False:
        raise HTTPException(
            400,
            "This exercise requires a discoverable credential. No replacement was saved.",
        )

    discovery_source = "cred_props" if discoverable is not None else None
    saved_required = (
        isinstance(registration_options, dict)
        and registration_options.get("authenticatorSelection", {}).get("residentKey")
        == "required"
    )
    if discoverable is None and saved_required:
        discoverable = True
        discovery_source = "required_registration"
    # Only protocol fields are retained, never arbitrary body properties.
    raw_response = body.response.get("response", {})
    saved_response = {
        key: copy.deepcopy(body.response[key])
        for key in ("id", "rawId", "type")
        if key in body.response
    }
    saved_response["response"] = {
        key: copy.deepcopy(raw_response[key])
        for key in ("attestationObject", "clientDataJSON", "transports")
        if key in raw_response
    }
    # PRF, hmac-secret and arbitrary extension outputs can contain secrets.
    # Retain only the teaching-safe public residency observation.
    safe_extensions = (
        {"credProps": {"rk": reported_rk}} if type(reported_rk) is bool else {}
    )
    saved_response["clientExtensionResults"] = safe_extensions
    registration_evidence = None
    if isinstance(registration_options, dict):
        registration_evidence = {
            "schema_version": 1,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "request": {"publicKey": registration_options},
            "response": saved_response,
            "verification": {
                "implementation": "python-fido2",
                "implementation_version": version("fido2"),
                "policy": "preloop-registration-v1",
                "checks": [
                    "client_data_type",
                    "challenge",
                    "origin",
                    "rp_id_hash",
                    "user_presence",
                    "user_verification",
                    "offered_algorithm",
                ],
                "attestation_trust_chain_verified": False,
                "client_extension_results_redacted": extension_results
                != safe_extensions,
            },
        }

    credential_values: Dict[str, Any] = dict(
        account_id=current_user.account_id,
        user_id=current_user.id,
        credential_id=bytes(acd.credential_id),
        public_key_cbor=public_key_cbor,
        aaguid=bytes(acd.aaguid),
        sign_count=0,
        name=body.name.strip(),
        arkg_seed_pub_cbor=arkg_seed_pub_cbor,
        arkg_seed_kh=arkg_seed_kh,
        arkg_protocol=arkg_protocol,
        registration_evidence=registration_evidence,
        discoverability_source=discovery_source,
        discoverable=discoverable,
        backup_eligible=backup_eligible,
        backup_state=backup_state,
        uv_initialized=uv_initialized,
    )
    replaced_credential_id = None
    if migration_source is not None:
        replaced_credential_id = str(migration_source.id)
        try:
            cred = crud_webauthn_credential.replace_credential(
                db, user=current_user, source=migration_source, **credential_values
            )
        except Exception:
            raise HTTPException(
                500,
                "Replacement could not be confirmed. Refresh passkeys before trying again.",
            )
    else:
        crud_webauthn_credential.advance_policy_version(db, user=current_user)
        cred = crud_webauthn_credential.create_credential(db, **credential_values)

    # Metadata is display enrichment fetched independently by the UI. Never
    # wait for its network/cache lock on the credential registration path.
    return CredentialRecord(
        id=str(cred.id),
        credential_id=_b64url(bytes(cred.credential_id)),
        replaced_credential_id=replaced_credential_id,
        name=cred.name,
        aaguid=_b64url(cred.aaguid),
        created_at=str(cred.created_at),
        last_used_at=str(cred.last_used_at) if cred.last_used_at else None,
        arkg_capable=_previewsign_ready(cred),
        cose_algorithm=_stored_algorithm(cred.public_key_cbor),
        pq_eligible=_pq_eligible(cred),
        authentication_tested_at=str(cred.authentication_tested_at)
        if _authentication_tested(cred)
        else None,
        discoverability_source=cred.discoverability_source,
        discoverable=cred.discoverable,
        backup_eligible=cred.backup_eligible,
        backup_state=cred.backup_state,
    )


@router.get("/credentials", response_model=List[CredentialRecord])
def list_credentials(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> List[CredentialRecord]:
    """List the current user's registered security keys."""
    creds = crud_webauthn_credential.list_by_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    return [
        CredentialRecord(
            id=str(c.id),
            credential_id=_b64url(bytes(c.credential_id)),
            name=c.name,
            aaguid=_b64url(c.aaguid),
            created_at=str(c.created_at),
            last_used_at=str(c.last_used_at) if c.last_used_at else None,
            arkg_capable=_previewsign_ready(c),
            cose_algorithm=_stored_algorithm(c.public_key_cbor),
            pq_eligible=_pq_eligible(c),
            authentication_tested_at=str(c.authentication_tested_at)
            if _authentication_tested(c)
            else None,
            discoverability_source=c.discoverability_source,
            discoverable=c.discoverable,
            backup_eligible=c.backup_eligible,
            backup_state=c.backup_state,
        )
        for c in creds
    ]


@router.get("/credentials/{credential_id}/registration-evidence")
def get_registration_evidence(
    credential_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    credential = crud_webauthn_credential.get_evidence_record(
        db,
        credential_id=credential_id,
        user_id=current_user.id,
        account_id=current_user.account_id,
    )
    if (
        credential is None
        or credential.user_id != current_user.id
        or credential.account_id != current_user.account_id
    ):
        raise HTTPException(404, "Registration details were not found.")
    return {
        "available": credential.registration_evidence is not None,
        "evidence": credential.registration_evidence,
    }


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> None:
    """Delete a registered security key owned by the current user."""
    current_user = crud_webauthn_credential.lock_user(
        db, user_id=current_user.id, account_id=current_user.account_id
    )
    if current_user is None:
        raise HTTPException(401, "Authentication failed")
    if current_user.pq_only is True:
        raise HTTPException(403, "Confirm removal with a PQ passkey first.")
    cred = crud_webauthn_credential.get_by_id(
        db, credential_id=credential_id, user_id=current_user.id
    )
    if cred is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )
    crud_webauthn_credential.advance_policy_version(db, user=current_user)
    crud_webauthn_credential.delete_by_id(db, credential_id=credential_id)


@router.patch("/credentials/{credential_id}/rename", response_model=CredentialRecord)
def rename_credential(
    credential_id: uuid.UUID,
    body: RenameRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session),
) -> CredentialRecord:
    """Rename a registered security key owned by the current user."""
    cred = crud_webauthn_credential.get_by_id(
        db, credential_id=credential_id, user_id=current_user.id
    )
    if cred is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )
    cred = crud_webauthn_credential.rename_credential(
        db, credential=cred, name=body.name.strip()
    )
    return CredentialRecord(
        id=str(cred.id),
        credential_id=_b64url(bytes(cred.credential_id)),
        name=cred.name,
        aaguid=_b64url(cred.aaguid),
        created_at=str(cred.created_at),
        last_used_at=str(cred.last_used_at) if cred.last_used_at else None,
        arkg_capable=_previewsign_ready(cred),
        cose_algorithm=_stored_algorithm(cred.public_key_cbor),
        pq_eligible=_pq_eligible(cred),
        authentication_tested_at=str(cred.authentication_tested_at)
        if _authentication_tested(cred)
        else None,
    )


@router.get("/mds/{aaguid}", response_model=MdsMetadata)
def get_mds_metadata(
    aaguid: str,
    db: Session = Depends(get_db_session),
    _current_user: User = Depends(get_current_active_user),
) -> MdsMetadata:
    """Return authenticated current model metadata, distinct from key provenance."""
    entries, metadata_status = _get_mds_snapshot()
    target = aaguid.lower()
    workshop_assumption = (
        os.getenv("WORKSHOP_ONBOARDING_ENABLED", "").lower() == "true"
        and target == "2165deef-e5a8-4efa-9fe7-fea9ddb2d227"
    )
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("aaguid"), str)
            or entry["aaguid"].lower() != target
        ):
            continue
        stmt = entry.get("metadataStatement", {})
        if not isinstance(stmt, dict):
            continue

        # Flatten userVerificationDetails: [[{userVerification: "..."}], ...]
        uv_methods: List[str] = []
        for combo in stmt.get("userVerificationDetails", []):
            for method in combo:
                mv = method.get("userVerification", "")
                if mv and mv not in uv_methods:
                    uv_methods.append(mv)

        # Most recent certification status
        status_reports = entry.get("statusReports", [])
        cert_status: Optional[str] = None
        if status_reports:
            latest = status_reports[-1]
            cert_status = latest.get("status")

        raw_icon = stmt.get("icon", "") or ""
        return MdsMetadata(
            found=True,
            previewsign_vendor_catalog_supported=target in PREVIEWSIGN_MODELS,
            previewsign_workshop_assumption=workshop_assumption,
            previewsign_supported=_previewsign_model_support(
                entries, metadata_status, target
            ),
            pq_upgrade_supported=pq_upgrade_support(entries, metadata_status, target),
            metadata_status=metadata_status,
            metadata_authenticated=metadata_status == "current",
            description=stmt.get("description"),
            icon=raw_icon[:65535] if raw_icon else None,
            key_protection=stmt.get("keyProtection", []),
            attachment_hint=stmt.get("attachmentHint", []),
            user_verification_methods=uv_methods,
            protocol_family=stmt.get("protocolFamily"),
            certification_status=cert_status,
        )

    # Historical database snapshots predate authenticated MDS and cannot be
    # upgraded into trusted model evidence or used to hide an outage.
    return MdsMetadata(
        found=False,
        previewsign_vendor_catalog_supported=target in PREVIEWSIGN_MODELS,
        previewsign_workshop_assumption=workshop_assumption,
        metadata_status=metadata_status,
        metadata_authenticated=metadata_status == "current",
    )
