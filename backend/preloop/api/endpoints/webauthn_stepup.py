"""WebAuthn step-up ceremony endpoints for public approval pages.

Token-based (no login required) — same auth model as existing public approval
endpoints. The approver calls /begin to receive a challenge, touches their
hardware key, then calls /complete. On success, ApprovalRequest.step_up_verified
is set to True and the approval gate in ApprovalService.approve_request() opens.
"""

import hashlib
import json
import secrets
import struct
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fido2.cbor import decode as cbor_decode
from fido2.cose import CoseKey
from fido2.webauthn import (
    AuthenticationResponse,
    UserVerificationRequirement,
)
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from preloop.api.endpoints._webauthn_utils import acd_from_stored as _acd_from_stored
from preloop.api.endpoints._webauthn_utils import (
    auth_options_to_dict as _auth_options_to_dict,
)
from preloop.api.endpoints._webauthn_utils import b64url_decode as _from_b64url
from preloop.api.endpoints._webauthn_utils import b64url_encode as _b64url
from preloop.api.endpoints.webauthn_registration import fido2_server
from preloop.models.crud import crud_approval_request, crud_approval_workflow
from preloop.models.crud.webauthn_credential import crud_webauthn_credential
from preloop.models.db.session import get_db_session
from preloop.services.rdt_intent import build_intent_envelope
from preloop.services.approval_verification import resolve_credential
from preloop.services.approval_expiry import require_unexpired_approval

router = APIRouter(prefix="/approval", tags=["WebAuthn Step-Up"])

# ---------------------------------------------------------------------------
# Rate limiting — 10 requests per token per 60 s (DB-backed, process-safe)
# ---------------------------------------------------------------------------

_RATE_WINDOW = 60
_RATE_MAX = 10


def _check_rate_limit(token: str, db: Session) -> None:
    """DB-backed fixed-window rate limiter.

    Uses a single-row upsert per token keyed by SHA-256 of the token so the
    plaintext token is never stored. The upsert is atomic — no SELECT+INSERT
    races — and the counter survives process restarts and spans multiple API
    instances behind a load balancer.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=_RATE_WINDOW)

    result = db.execute(
        text(
            """
            INSERT INTO webauthn_step_up_rate_limit (token_hash, hit_count, window_start)
            VALUES (:token_hash, 1, :now)
            ON CONFLICT (token_hash) DO UPDATE
            SET
                hit_count = CASE
                    WHEN webauthn_step_up_rate_limit.window_start < :window_start
                    THEN 1
                    ELSE webauthn_step_up_rate_limit.hit_count + 1
                END,
                window_start = CASE
                    WHEN webauthn_step_up_rate_limit.window_start < :window_start
                    THEN :now
                    ELSE webauthn_step_up_rate_limit.window_start
                END
            RETURNING hit_count
            """
        ),
        {"token_hash": token_hash, "now": now, "window_start": window_start},
    )
    hit_count = result.scalar()
    db.commit()

    if hit_count > _RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in 1 minute.",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StepUpBeginResponse(BaseModel):
    session_id: str
    options: Dict[str, Any]
    # previewSign / ARKG fields — set when an ARKG-capable credential is registered.
    # The frontend uses these to perform client-side ARKG key derivation and build
    # the signByCredential extension for navigator.credentials.get().
    # Authenticators without previewSign silently ignore the extension.
    preview_sign_tbs_b64: Optional[str] = None
    # origKh — the generatedKey.keyHandle captured at registration time.
    preview_sign_kh_b64: Optional[str] = None
    # ARKG seed COSE key (generatedKey.publicKey from registration) — needed by
    # the frontend to perform ARKG derivation (derive a fresh P-256 key pair).
    preview_sign_seed_pub_b64: Optional[str] = None
    # Credential ID for the ARKG-capable credential — used as the key in the
    # signByCredential map sent to navigator.credentials.get().
    preview_sign_credential_id_b64: Optional[str] = None


class StepUpCompleteRequest(BaseModel):
    session_id: str
    response: Dict[str, Any]
    # Optional previewSign output from the authenticator. Present when the
    # authenticator supports previewSign (e.g. YubiKey 5.8+ with Yubico
    # Authenticator extension running). Absent for all other authenticators.
    preview_sign_sig_b64: Optional[str] = None
    preview_sign_pk_b64: Optional[str] = None


class StepUpCompleteResponse(BaseModel):
    verified: bool
    credential_name: Optional[str] = None


class WebAuthnConsumptionReceipt(BaseModel):
    """Self-contained, auditor-verifiable record of a WebAuthn step-up (RDT §4.1)."""

    version: str = "1.0"
    receipt_type: str = "webauthn_step_up"
    # COSE algorithm from the credential public key. None is only possible for
    # legacy rows whose credential can no longer be resolved.
    alg: Optional[int] = None
    intent_envelope: Dict[str, Any]
    intent_hash_hex: str
    challenge_nonce_hex: str
    challenge_hex: str
    client_data_json_hex: str
    authenticator_data_hex: str
    signature_hex: str
    public_key_cbor_hex: Optional[str]
    # AAGUID of the authenticator that signed (UUID format, from registration).
    # Look up in FIDO MDS (https://mds3.fidoalliance.org/) to determine whether
    # the private key is hardware-bound or cloud-syncable.
    aaguid: Optional[str] = None
    signed_at: str
    # Authenticator sign counter at step-up time. CISOs use this to detect
    # potential credential cloning: an unexpected counter regression means
    # the private key may have been duplicated (FIDO2 §6.1.1 clone detection).
    authenticator_sign_count: Optional[int] = None
    # previewSign fields — present when the authenticator also signed the intent
    # hash directly via the ARKG previewSign extension (YubiKey 5.8+). When
    # present, an offline verifier can check ECDSA-P256 sig over intent_hash_hex
    # bytes using arkg_derived_pk_hex without the WebAuthn challenge indirection.
    arkg_signature_hex: Optional[str] = None
    arkg_derived_pk_hex: Optional[str] = None
    arkg_step_up_verified: bool = False
    scitt_receipt: Optional[str] = None
    # FIDO MDS snapshot from credential registration — for audit UI display.
    authenticator_description: Optional[str] = None
    authenticator_key_protection: Optional[str] = None
    authenticator_icon: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{request_id}/step-up/begin", response_model=StepUpBeginResponse)
def step_up_begin(
    request_id: uuid.UUID,
    token: str = Query(..., description="Approval token"),
    db: Session = Depends(get_db_session),
) -> StepUpBeginResponse:
    """Begin a WebAuthn step-up challenge for an approval request."""
    _check_rate_limit(token, db)

    approval_request = crud_approval_request.get_by_id_and_token(
        db, request_id=str(request_id), token=token
    )
    if not approval_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found or invalid token",
        )

    require_unexpired_approval(approval_request)

    if approval_request.step_up_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Step-up already verified for this approval request",
        )

    intent_hash_hex: Optional[str] = approval_request.intent_hash_hex
    if not intent_hash_hex:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Step-up requires an intent hash. Upgrade your SDK.",
        )

    # Generate fresh nonce for replay protection
    challenge_nonce = secrets.token_bytes(32)

    # The challenge derives from intent_hash + nonce (verification script expects this)
    # intent_hash is already SHA-256(JCS(intent_envelope)), so we hash it with the nonce
    intent_hash_bytes = bytes.fromhex(intent_hash_hex)
    derived_challenge = hashlib.sha256(intent_hash_bytes + challenge_nonce).digest()

    # Build allowCredentials from the account's registered keys so the browser
    # only prompts with credentials we recognise and can verify.
    account_creds = crud_webauthn_credential.list_by_account(
        db, account_id=approval_request.account_id
    )
    acds = [
        _acd_from_stored(c.credential_id, c.public_key_cbor, c.aaguid)
        for c in account_creds
    ]

    options, state = fido2_server.authenticate_begin(
        credentials=acds,
        user_verification=UserVerificationRequirement.REQUIRED,
        challenge=derived_challenge,
    )

    state_bytes = json.dumps(state).encode()
    challenge_bytes = bytes(options.public_key.challenge)

    # Reuse the challenge session keyed by approval_request_id;
    # create_challenge_session deletes any prior session for the same id.
    crud_webauthn_credential.create_challenge_session(
        db,
        account_id=approval_request.account_id,
        approval_request_id=request_id,
        fido2_state=state_bytes,
        challenge=challenge_bytes,
        challenge_nonce=challenge_nonce,
    )

    # Build previewSign / ARKG data. The frontend needs:
    #   tbs         — bytes to sign (= intent hash, already 32 bytes)
    #   kh          — origKh from registration's generatedKey.keyHandle
    #   seed_pub    — ARKG seed COSE key for client-side key derivation
    #   cred_id     — credential ID to key the signByCredential map
    preview_sign_tbs_b64: Optional[str] = _b64url(bytes.fromhex(intent_hash_hex))
    preview_sign_kh_b64: Optional[str] = None
    preview_sign_seed_pub_b64: Optional[str] = None
    preview_sign_credential_id_b64: Optional[str] = None
    for c in account_creds:
        if c.arkg_seed_kh:
            preview_sign_kh_b64 = _b64url(bytes(c.arkg_seed_kh))
            if c.arkg_seed_pub_cbor:
                preview_sign_seed_pub_b64 = _b64url(bytes(c.arkg_seed_pub_cbor))
            preview_sign_credential_id_b64 = _b64url(bytes(c.credential_id))
            break

    return StepUpBeginResponse(
        session_id=str(request_id),
        options=_auth_options_to_dict(options),
        preview_sign_tbs_b64=preview_sign_tbs_b64,
        preview_sign_kh_b64=preview_sign_kh_b64,
        preview_sign_seed_pub_b64=preview_sign_seed_pub_b64,
        preview_sign_credential_id_b64=preview_sign_credential_id_b64,
    )


@router.post("/{request_id}/step-up/complete", response_model=StepUpCompleteResponse)
def step_up_complete(
    request_id: uuid.UUID,
    body: StepUpCompleteRequest,
    token: str = Query(..., description="Approval token"),
    db: Session = Depends(get_db_session),
) -> StepUpCompleteResponse:
    """Complete a WebAuthn step-up ceremony and mark the approval as verified."""
    _check_rate_limit(token, db)

    approval_request = crud_approval_request.get_by_id_and_token(
        db, request_id=str(request_id), token=token
    )
    if not approval_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found or invalid token",
        )

    require_unexpired_approval(approval_request)

    challenge_session = crud_webauthn_credential.get_challenge_session(
        db, approval_request_id=request_id
    )
    if challenge_session is None or challenge_session.is_expired():
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step-up session expired or not found. Please start again.",
        )

    # Extract credential_id from the browser response to look up the credential
    raw_id_b64 = body.response.get("rawId") or body.response.get("id") or ""
    if not raw_id_b64:
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing credential id in response",
        )

    try:
        credential_id_bytes = _from_b64url(str(raw_id_b64))
    except Exception:
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential id encoding",
        )

    # Look up the credential
    cred = crud_webauthn_credential.get_by_credential_id(
        db, credential_id=credential_id_bytes
    )
    if cred is None:
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security key not registered",
        )

    # Cross-tenant isolation: credential must belong to the same account
    if cred.account_id != approval_request.account_id:
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security key does not belong to this account",
        )

    if not crud_approval_workflow.is_user_authorized_approver(
        db,
        workflow_id=approval_request.approval_workflow_id,
        account_id=approval_request.account_id,
        user_id=cred.user_id,
    ):
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security key owner is not an authorized approver for this workflow",
        )

    # Reconstruct the AttestedCredentialData and run authenticate_complete
    verified_key = bytes(cred.public_key_cbor)
    verified_owner_id = cred.user_id
    try:
        state = json.loads(challenge_session.fido2_state.decode())
        acd = _acd_from_stored(cred.credential_id, cred.public_key_cbor, cred.aaguid)
        auth_response = AuthenticationResponse.from_dict(body.response)
        fido2_server.authenticate_complete(state, [acd], auth_response)
    except Exception as exc:
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authentication failed: {exc}",
        )

    # Verify user_handle matches the credential owner when present.
    # Non-resident (server-side) credentials may omit user_handle in the
    # assertion response; the credential_id lookup already binds the key to the
    # correct account, so we only reject an explicit mismatch.
    user_handle = auth_response.response.user_handle
    if user_handle is not None and bytes(user_handle) != cred.user_id.bytes:
        crud_webauthn_credential.delete_challenge_session(
            db, approval_request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User handle mismatch",
        )

    # Update sign_count on the credential
    owner = crud_webauthn_credential.lock_user(
        db, user_id=verified_owner_id, account_id=approval_request.account_id
    )
    current_credential = crud_webauthn_credential.get_by_credential_id(
        db,
        credential_id=credential_id_bytes,
        account_id=approval_request.account_id,
    )
    if (
        owner is None
        or current_credential is None
        or current_credential.user_id != verified_owner_id
        or bytes(current_credential.public_key_cbor) != verified_key
    ):
        db.rollback()
        raise HTTPException(403, "Security key is no longer active. Start again.")
    cred = current_credential
    new_sign_count = auth_response.response.authenticator_data.counter
    crud_webauthn_credential.update_sign_count(
        db, credential=cred, sign_count=new_sign_count, commit=False
    )

    # Process optional previewSign output — ECDSA-P256 signature over the
    # intent hash bytes, produced by the authenticator alongside the standard
    # WebAuthn assertion. Verify the signature; store regardless of verification
    # result so the receipt captures what the authenticator actually produced.
    arkg_sig_bytes: Optional[bytes] = None
    arkg_pk_bytes: Optional[bytes] = None
    arkg_verified = False
    if body.preview_sign_sig_b64 and body.preview_sign_pk_b64:
        try:
            arkg_sig_bytes = _from_b64url(body.preview_sign_sig_b64)
            arkg_pk_bytes = _from_b64url(body.preview_sign_pk_b64)
            tbs = bytes.fromhex(approval_request.intent_hash_hex)

            # Decode P-256 uncompressed point (0x04 || X || Y, 65 bytes)
            x = int.from_bytes(arkg_pk_bytes[1:33], "big")
            y = int.from_bytes(arkg_pk_bytes[33:65], "big")
            derived_pub = ec.EllipticCurvePublicNumbers(
                x, y, ec.SECP256R1()
            ).public_key()
            # TBS is already a SHA-256 digest — use Prehashed to avoid double-hashing
            derived_pub.verify(
                arkg_sig_bytes, tbs, ec.ECDSA(Prehashed(hashes.SHA256()))
            )
            arkg_verified = True
        except (InvalidSignature, ValueError, TypeError):
            pass

    # RDT Phase A: Reconstruct envelope WITH signatures and store complete envelope
    from preloop.services.rdt_envelope import construct_rdt_envelope

    # CRITICAL: Use same values as /begin to maintain hash consistency
    # - timestamp: approval_request.requested_at
    # - approver_id: approval_request.account_id
    # - tool_args: deterministic JSON serialization
    rdt_timestamp = approval_request.requested_at.isoformat()
    tool_args = approval_request.tool_args or {}
    tool_args_str = json.dumps(tool_args, sort_keys=True, separators=(",", ":"))

    rdt_envelope_complete = construct_rdt_envelope(
        action_class=approval_request.action_class or "unknown",
        operation=f"{approval_request.tool_name} {tool_args_str}",
        context={
            "tool_name": approval_request.tool_name,
            "tool_args": tool_args,  # Dict form (construct_rdt_envelope handles serialization)
            "execution_id": approval_request.execution_id,
        },
        reasoning=approval_request.agent_reasoning or "Approval requested",
        approver_id=str(
            approval_request.account_id
        ),  # MUST match /begin value for hash consistency
        timestamp=rdt_timestamp,  # MUST match /begin value for hash consistency
        credential_id=bytes(cred.credential_id),
        credential_name=cred.name,
        signature=bytes(auth_response.response.signature),
        authenticator_data=bytes(auth_response.response.authenticator_data),
        client_data_json=bytes(auth_response.response.client_data),
    )

    # Mark the approval request as step-up verified and store assertion bytes
    # for future audit re-verification.
    key_id_tail = _b64url(cred.credential_id)[-8:]
    update_fields: Dict[str, Any] = {
        "step_up_verified": True,
        "step_up_verified_at": datetime.now(timezone.utc),
        "step_up_key_name": cred.name,
        "step_up_key_id_tail": key_id_tail,
        "step_up_credential_id": bytes(cred.credential_id),
        "step_up_sign_count": new_sign_count,
        "step_up_challenge_nonce": challenge_session.challenge_nonce,
        "step_up_client_data_json": bytes(auth_response.response.client_data),
        "step_up_authenticator_data": bytes(auth_response.response.authenticator_data),
        "step_up_signature": bytes(auth_response.response.signature),
        "arkg_step_up_signature": arkg_sig_bytes,
        "arkg_step_up_derived_pk": arkg_pk_bytes,
        "arkg_step_up_verified": arkg_verified,
        "rdt_envelope": rdt_envelope_complete,  # Store complete RDT envelope
    }
    crud_approval_request.update_step_up_fields(
        db, approval_request=approval_request, fields=update_fields
    )
    db.commit()

    # Clean up challenge session
    crud_webauthn_credential.delete_challenge_session(
        db, approval_request_id=request_id
    )

    return StepUpCompleteResponse(verified=True, credential_name=cred.name)


@router.get("/{request_id}/step-up/receipt", response_model=WebAuthnConsumptionReceipt)
def get_webauthn_receipt(
    request_id: uuid.UUID,
    token: str = Query(..., description="Approval token"),
    db: Session = Depends(get_db_session),
) -> WebAuthnConsumptionReceipt:
    """Return the ConsumptionReceipt for a verified WebAuthn step-up.

    Can be called any time after step_up_complete succeeds. The receipt is
    computed deterministically from the stored approval request and credential.
    """
    approval_request = crud_approval_request.get_by_id_and_token(
        db, request_id=str(request_id), token=token
    )
    if not approval_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found or invalid token",
        )
    if not approval_request.step_up_verified:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No verified WebAuthn step-up for this request",
        )
    if not approval_request.intent_hash_hex:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Step-up requires an intent hash. Upgrade your SDK.",
        )
    if not approval_request.step_up_challenge_nonce:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Challenge nonce not stored — re-run step-up",
        )

    import hashlib

    # Challenge derives from intent_hash + nonce (must match /begin derivation)
    intent_hash_bytes = bytes.fromhex(approval_request.intent_hash_hex)
    nonce_bytes = bytes(approval_request.step_up_challenge_nonce)
    challenge_hex = hashlib.sha256(intent_hash_bytes + nonce_bytes).hexdigest()

    intent_envelope = build_intent_envelope(
        account_id=approval_request.account_id,
        approval_request_id=approval_request.id,
        tool_name=approval_request.tool_name,
        tool_args=approval_request.tool_args or {},
        requested_at=approval_request.requested_at,
        intent_risk_tier=approval_request.intent_risk_tier,
        intent_flags=approval_request.intent_flags,
    )

    # Use the same account-scoped historical identity rules as audit verification.
    public_key_cbor_hex: Optional[str] = None
    aaguid_uuid: Optional[str] = None
    matched_cred = resolve_credential(db, approval_request.account_id, approval_request)
    authenticator_description: Optional[str] = None
    authenticator_key_protection: Optional[str] = None
    authenticator_icon: Optional[str] = None
    if matched_cred is not None:
        public_key_cbor_hex = matched_cred.public_key_cbor.hex()
        try:
            decoded_key = cbor_decode(matched_cred.public_key_cbor)
            if not isinstance(decoded_key, dict):
                raise ValueError("Stored COSE key must be a map")
            cose_key = CoseKey.parse(decoded_key)
            credential_alg = int(cose_key[3])
        except (ValueError, TypeError, KeyError, IndexError, struct.error):
            # Corrupt historical key data must not invent an algorithm or crash
            # the receipt page. Preserve the raw bytes for diagnosis.
            credential_alg = None
        h = matched_cred.aaguid.hex()
        aaguid_uuid = f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        authenticator_description = matched_cred.mds_description
        authenticator_key_protection = matched_cred.mds_key_protection
        authenticator_icon = matched_cred.mds_icon
    else:
        credential_alg = None

    signed_at = (
        approval_request.step_up_verified_at.isoformat()
        if approval_request.step_up_verified_at
        else ""
    )

    arkg_signature_hex: Optional[str] = None
    arkg_derived_pk_hex: Optional[str] = None
    if approval_request.arkg_step_up_signature:
        arkg_signature_hex = bytes(approval_request.arkg_step_up_signature).hex()
    if approval_request.arkg_step_up_derived_pk:
        arkg_derived_pk_hex = bytes(approval_request.arkg_step_up_derived_pk).hex()

    return WebAuthnConsumptionReceipt(
        alg=credential_alg,
        intent_envelope=intent_envelope,
        intent_hash_hex=approval_request.intent_hash_hex,
        challenge_nonce_hex=nonce_bytes.hex(),
        challenge_hex=challenge_hex,
        client_data_json_hex=bytes(approval_request.step_up_client_data_json).hex(),
        authenticator_data_hex=bytes(approval_request.step_up_authenticator_data).hex(),
        signature_hex=bytes(approval_request.step_up_signature).hex(),
        public_key_cbor_hex=public_key_cbor_hex,
        aaguid=aaguid_uuid,
        signed_at=signed_at,
        arkg_signature_hex=arkg_signature_hex,
        arkg_derived_pk_hex=arkg_derived_pk_hex,
        arkg_step_up_verified=bool(approval_request.arkg_step_up_verified),
        authenticator_sign_count=approval_request.step_up_sign_count,
        authenticator_description=authenticator_description,
        authenticator_key_protection=authenticator_key_protection,
        authenticator_icon=authenticator_icon,
    )
