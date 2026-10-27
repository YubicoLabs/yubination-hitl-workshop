"""CRUD operations for WebAuthn credentials and challenge sessions."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, NamedTuple, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..models.user import User
from ..models.webauthn_credential import (
    UserWebAuthnCredential,
    WebAuthnChallengeSession,
    WebAuthnLoginSession,
    WebAuthnRegistrationSession,
    _LOGIN_SESSION_TTL_MINUTES,
)

_REG_SESSION_TTL_SECONDS = 300
_LOGIN_SESSION_TTL_SECONDS = _LOGIN_SESSION_TTL_MINUTES * 60


class ConsumedLoginSession(NamedTuple):
    session_id: uuid.UUID
    state_dict: Dict[str, Any]
    challenge: bytes
    user_id: Optional[uuid.UUID]
    account_id: Optional[uuid.UUID]
    kind: str


class CRUDWebAuthnCredential:
    """CRUD for UserWebAuthnCredential and WebAuthnChallengeSession."""

    def lock_user(
        self, db: Session, *, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> Optional[User]:
        """Serialize sign-in policy and credential mutations for one tenant user."""
        return (
            db.query(User)
            .filter(User.id == user_id, User.account_id == account_id)
            .populate_existing()
            .with_for_update()
            .first()
        )

    def record_authentication(
        self,
        db: Session,
        *,
        credential: UserWebAuthnCredential,
        sign_count: int,
        backup_state: bool,
    ) -> None:
        """Flush dedicated fresh-proof evidence; caller owns the transaction."""
        import hashlib

        credential.authentication_tested_at = datetime.now(timezone.utc)
        credential.authentication_key_hash = hashlib.sha256(
            credential.public_key_cbor
        ).hexdigest()
        credential.last_used_at = credential.authentication_tested_at
        credential.sign_count = sign_count
        credential.backup_state = backup_state
        db.add(credential)
        db.flush()

    def advance_policy_version(self, db: Session, *, user: User) -> None:
        """Invalidate outstanding management ceremonies in the caller's lock."""
        user.pq_policy_version += 1
        db.add(user)
        db.flush()

    def set_policy(self, db: Session, *, user: User, enabled: bool) -> None:
        user.pq_only = enabled
        self.advance_policy_version(db, user=user)

    def delete_owned(self, db: Session, *, credential: UserWebAuthnCredential) -> None:
        db.delete(credential)
        db.flush()

    # ------------------------------------------------------------------
    # UserWebAuthnCredential
    # ------------------------------------------------------------------

    def record_discovery_observation(
        self, db: Session, *, user: User, credential: UserWebAuthnCredential
    ) -> None:
        """Record browser discovery while caller holds the owning user lock."""
        if (
            credential.user_id != user.id
            or credential.account_id != user.account_id
            or credential.retired_at is not None
            or credential.discoverable is False
        ):
            raise ValueError("Credential is not eligible for discovery observation")
        if credential.discoverable is None:
            credential.discoverable = True
            credential.discoverability_source = "browser_discovery_observation"
            db.add(credential)
            db.commit()

    def create_credential(
        self,
        db: Session,
        *,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        credential_id: bytes,
        public_key_cbor: bytes,
        aaguid: bytes,
        sign_count: int,
        name: str,
        arkg_seed_pub_cbor: Optional[bytes] = None,
        arkg_seed_kh: Optional[bytes] = None,
        arkg_derived_pk: Optional[bytes] = None,
        arkg_derived_kh: Optional[bytes] = None,
        arkg_protocol: Optional[str] = None,
        registration_evidence: Optional[Dict[str, Any]] = None,
        discoverability_source: Optional[str] = None,
        discoverable: Optional[bool] = None,
        backup_eligible: Optional[bool] = None,
        backup_state: Optional[bool] = None,
        uv_initialized: Optional[bool] = None,
        commit: bool = True,
    ) -> UserWebAuthnCredential:
        cred = UserWebAuthnCredential(
            account_id=account_id,
            user_id=user_id,
            credential_id=credential_id,
            public_key_cbor=public_key_cbor,
            aaguid=aaguid,
            sign_count=sign_count,
            name=name,
            arkg_seed_pub_cbor=arkg_seed_pub_cbor,
            arkg_seed_kh=arkg_seed_kh,
            arkg_derived_pk=arkg_derived_pk,
            arkg_derived_kh=arkg_derived_kh,
            arkg_protocol=arkg_protocol,
            registration_evidence=registration_evidence,
            discoverability_source=discoverability_source,
            discoverable=discoverable,
            backup_eligible=backup_eligible,
            backup_state=backup_state,
            uv_initialized=uv_initialized,
        )
        db.add(cred)
        if commit:
            db.commit()
            db.refresh(cred)
        else:
            db.flush()
        return cred

    def replace_credential(
        self,
        db: Session,
        *,
        user: User,
        source: UserWebAuthnCredential,
        **values: Any,
    ) -> UserWebAuthnCredential:
        """Persist replacement and retire its bound source under the caller's lock."""
        try:
            if (
                source.user_id != user.id
                or source.account_id != user.account_id
                or source.retired_at is not None
                or values.get("user_id") != user.id
                or values.get("account_id") != user.account_id
            ):
                raise ValueError("Replacement source is not active and owned")
            replacement = self.create_credential(db, commit=False, **values)
            source.retired_at = datetime.now(timezone.utc)
            db.add(source)
            self.advance_policy_version(db, user=user)
            db.flush()
            db.commit()
        except Exception:
            db.rollback()
            raise
        return replacement

    def get_by_credential_id(
        self,
        db: Session,
        *,
        credential_id: bytes,
        account_id: Optional[uuid.UUID] = None,
        include_retired: bool = False,
    ) -> Optional[UserWebAuthnCredential]:
        if include_retired and account_id is None:
            raise ValueError("Historical credential lookup requires account scope")
        return (
            db.query(UserWebAuthnCredential)
            .filter(UserWebAuthnCredential.credential_id == credential_id)
            .filter(
                True
                if account_id is None
                else UserWebAuthnCredential.account_id == account_id
            )
            .filter(
                True if include_retired else UserWebAuthnCredential.retired_at.is_(None)
            )
            .populate_existing()
            .first()
        )

    def list_by_account(
        self, db: Session, *, account_id: uuid.UUID, include_retired: bool = False
    ) -> List[UserWebAuthnCredential]:
        return (
            db.query(UserWebAuthnCredential)
            .filter(UserWebAuthnCredential.account_id == account_id)
            .filter(
                True if include_retired else UserWebAuthnCredential.retired_at.is_(None)
            )
            .populate_existing()
            .order_by(UserWebAuthnCredential.created_at)
            .all()
        )

    def list_by_user(
        self, db: Session, *, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> List[UserWebAuthnCredential]:
        return (
            db.query(UserWebAuthnCredential)
            .filter(
                UserWebAuthnCredential.user_id == user_id,
                UserWebAuthnCredential.account_id == account_id,
                UserWebAuthnCredential.retired_at.is_(None),
            )
            .populate_existing()
            .order_by(UserWebAuthnCredential.created_at)
            .all()
        )

    def update_sign_count(
        self,
        db: Session,
        *,
        credential: UserWebAuthnCredential,
        sign_count: int,
        commit: bool = True,
    ) -> UserWebAuthnCredential:
        credential.sign_count = sign_count
        db.add(credential)
        if commit:
            db.commit()
            db.refresh(credential)
        else:
            db.flush()
        return credential

    def get_evidence_record(
        self,
        db: Session,
        *,
        credential_id: uuid.UUID,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
    ) -> Optional[UserWebAuthnCredential]:
        """Owned active or retired enrollment history; never a sign-in lookup."""
        return (
            db.query(UserWebAuthnCredential)
            .filter(
                UserWebAuthnCredential.id == credential_id,
                UserWebAuthnCredential.user_id == user_id,
                UserWebAuthnCredential.account_id == account_id,
            )
            .first()
        )

    def get_by_id(
        self, db: Session, *, credential_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[UserWebAuthnCredential]:
        return (
            db.query(UserWebAuthnCredential)
            .filter(
                UserWebAuthnCredential.id == credential_id,
                UserWebAuthnCredential.user_id == user_id,
                UserWebAuthnCredential.retired_at.is_(None),
            )
            .populate_existing()
            .first()
        )

    def update_mds_metadata(
        self,
        db: Session,
        *,
        credential: UserWebAuthnCredential,
        description: str,
        key_protection: str,
        icon: str,
    ) -> UserWebAuthnCredential:
        credential.mds_description = description
        credential.mds_key_protection = key_protection
        credential.mds_icon = icon
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    def get_mds_snapshot_by_aaguid(
        self,
        db: Session,
        *,
        aaguid_bytes: bytes,
    ) -> Optional[UserWebAuthnCredential]:
        """Return any credential whose aaguid matches and has stored MDS data.

        MDS metadata is public, so we don't scope by account/user.
        Used as a fallback when the live FIDO MDS endpoint is unavailable.
        """
        return (
            db.query(UserWebAuthnCredential)
            .filter(
                UserWebAuthnCredential.aaguid == aaguid_bytes,
                UserWebAuthnCredential.mds_description.isnot(None),
                UserWebAuthnCredential.retired_at.is_(None),
            )
            .first()
        )

    def rename_credential(
        self, db: Session, *, credential: UserWebAuthnCredential, name: str
    ) -> UserWebAuthnCredential:
        credential.name = name
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    def delete_by_id(self, db: Session, *, credential_id: uuid.UUID) -> None:
        db.query(UserWebAuthnCredential).filter(
            UserWebAuthnCredential.id == credential_id
        ).delete()
        db.commit()

    def account_has_credential(self, db: Session, *, account_id: uuid.UUID) -> bool:
        return (
            db.query(UserWebAuthnCredential.id)
            .filter(UserWebAuthnCredential.account_id == account_id)
            .filter(UserWebAuthnCredential.retired_at.is_(None))
            .limit(1)
            .scalar()
            is not None
        )

    # ------------------------------------------------------------------
    # WebAuthnChallengeSession
    # ------------------------------------------------------------------

    def create_challenge_session(
        self,
        db: Session,
        *,
        account_id: uuid.UUID,
        approval_request_id: uuid.UUID,
        fido2_state: bytes,
        challenge: bytes,
        challenge_nonce: Optional[bytes] = None,
    ) -> WebAuthnChallengeSession:
        # Delete any existing session for this approval request before creating a new one
        db.query(WebAuthnChallengeSession).filter(
            WebAuthnChallengeSession.approval_request_id == approval_request_id
        ).delete()
        sess = WebAuthnChallengeSession(
            account_id=account_id,
            approval_request_id=approval_request_id,
            fido2_state=fido2_state,
            challenge=challenge,
            challenge_nonce=challenge_nonce,
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return sess

    def get_challenge_session(
        self, db: Session, *, approval_request_id: uuid.UUID
    ) -> Optional[WebAuthnChallengeSession]:
        return (
            db.query(WebAuthnChallengeSession)
            .filter(WebAuthnChallengeSession.approval_request_id == approval_request_id)
            .first()
        )

    def delete_challenge_session(
        self, db: Session, *, approval_request_id: uuid.UUID
    ) -> None:
        db.query(WebAuthnChallengeSession).filter(
            WebAuthnChallengeSession.approval_request_id == approval_request_id
        ).delete()
        db.commit()

    # ------------------------------------------------------------------
    # WebAuthnRegistrationSession
    # ------------------------------------------------------------------

    def create_reg_session(
        self,
        db: Session,
        *,
        session_id: uuid.UUID,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        state_dict: Dict[str, Any],
        ttl_seconds: int = _REG_SESSION_TTL_SECONDS,
    ) -> WebAuthnRegistrationSession:
        now = datetime.now(timezone.utc)
        # Sweep expired sessions for this user before inserting a new one.
        db.query(WebAuthnRegistrationSession).filter(
            WebAuthnRegistrationSession.user_id == user_id,
            WebAuthnRegistrationSession.expires_at < now,
        ).delete()
        sess = WebAuthnRegistrationSession(
            id=session_id,
            account_id=account_id,
            user_id=user_id,
            state_json=json.dumps(state_dict),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        db.add(sess)
        db.commit()
        return sess

    def consume_reg_session(
        self, db: Session, *, session_id: uuid.UUID
    ) -> Optional[Dict[str, Any]]:
        row = (
            db.query(WebAuthnRegistrationSession)
            .filter(WebAuthnRegistrationSession.id == session_id)
            .with_for_update()
            .first()
        )
        if row is None:
            return None
        db.delete(row)
        db.commit()
        if row.is_expired():
            return None
        return json.loads(row.state_json)

    # ------------------------------------------------------------------
    # WebAuthnLoginSession
    # ------------------------------------------------------------------

    def create_login_session(
        self,
        db: Session,
        *,
        session_id: uuid.UUID,
        state_dict: Dict[str, Any],
        challenge: bytes,
        kind: str = "passwordless",
        user_id: Optional[uuid.UUID] = None,
        account_id: Optional[uuid.UUID] = None,
        ttl_seconds: int = _LOGIN_SESSION_TTL_SECONDS,
    ) -> WebAuthnLoginSession:
        now = datetime.now(timezone.utc)
        # Sweep expired discoverable sessions (no user_id, never GC'd per-user).
        db.query(WebAuthnLoginSession).filter(
            WebAuthnLoginSession.expires_at < now,
        ).delete()
        if user_id is not None:
            # Sweep any prior sessions for this specific user.
            db.query(WebAuthnLoginSession).filter(
                WebAuthnLoginSession.user_id == user_id,
                WebAuthnLoginSession.kind == kind,
            ).delete()
        sess = WebAuthnLoginSession(
            id=session_id,
            user_id=user_id,
            account_id=account_id,
            state_json=json.dumps(state_dict),
            challenge=challenge,
            kind=kind,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        db.add(sess)
        db.commit()
        return sess

    def get_login_session(
        self, db: Session, *, session_id: uuid.UUID
    ) -> Optional[WebAuthnLoginSession]:
        return (
            db.query(WebAuthnLoginSession)
            .filter(WebAuthnLoginSession.id == session_id)
            .first()
        )

    def consume_login_session(
        self,
        db: Session,
        *,
        session_id: uuid.UUID,
        expected_kind: Optional[str] = None,
        expected_user_id: Optional[uuid.UUID] = None,
        expected_account_id: Optional[uuid.UUID] = None,
    ) -> Optional[ConsumedLoginSession]:
        """Atomically DELETE the session row and return its data.

        Uses DELETE ... RETURNING to prevent TOCTOU replay: two concurrent
        /complete requests for the same session_id can only one of them get the
        row; the other sees NULL and gets a 401.
        """
        stmt = (
            delete(WebAuthnLoginSession)
            .where(WebAuthnLoginSession.id == session_id)
            .returning(
                WebAuthnLoginSession.id,
                WebAuthnLoginSession.state_json,
                WebAuthnLoginSession.challenge,
                WebAuthnLoginSession.expires_at,
                WebAuthnLoginSession.user_id,
                WebAuthnLoginSession.account_id,
                WebAuthnLoginSession.kind,
            )
        )
        if expected_kind is not None:
            stmt = stmt.where(WebAuthnLoginSession.kind == expected_kind)
        if expected_user_id is not None:
            stmt = stmt.where(WebAuthnLoginSession.user_id == expected_user_id)
        if expected_account_id is not None:
            stmt = stmt.where(WebAuthnLoginSession.account_id == expected_account_id)
        row = db.execute(stmt).first()
        db.commit()
        if row is None:
            return None
        # Check TTL after consuming — prevents replaying an expired session.
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            return None
        return ConsumedLoginSession(
            session_id=row.id,
            state_dict=json.loads(row.state_json),
            challenge=bytes(row.challenge),
            user_id=row.user_id,
            account_id=row.account_id,
            kind=row.kind,
        )

    def update_last_used_at(
        self,
        db: Session,
        *,
        credential: UserWebAuthnCredential,
        ts: Optional[datetime] = None,
    ) -> UserWebAuthnCredential:
        credential.last_used_at = ts or datetime.now(timezone.utc)
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    def update_backup_state(
        self,
        db: Session,
        *,
        credential: UserWebAuthnCredential,
        backup_state: bool,
    ) -> UserWebAuthnCredential:
        credential.backup_state = backup_state
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential


crud_webauthn_credential = CRUDWebAuthnCredential()


async def get_webauthn_credential_owner_async(
    db: AsyncSession,
    *,
    credential_id: bytes,
    account_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """Return the owner of an account-scoped WebAuthn credential."""
    result = await db.execute(
        select(UserWebAuthnCredential.user_id).where(
            UserWebAuthnCredential.credential_id == credential_id,
            UserWebAuthnCredential.account_id == account_id,
            UserWebAuthnCredential.retired_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
