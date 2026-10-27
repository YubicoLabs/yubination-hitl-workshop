"""Session management for unified WebSocket connections."""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import WebSocket
from sqlalchemy.orm import Session

from preloop.models.models import User, Event
from preloop.models.db.session import get_db_session

logger = logging.getLogger(__name__)

# Thread pool for DB operations to avoid blocking the event loop
_db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="session_db_")


@dataclass
class WebSocketSession:
    """Represents an active WebSocket session.

    This tracks the runtime state of a WebSocket connection. The persistent
    session data is stored in Event table in the database.
    """

    id: str
    connection_id: str
    websocket: WebSocket
    user_id: Optional[uuid.UUID]
    account_id: Optional[uuid.UUID]
    fingerprint: Optional[str]
    ip_address: str
    user_agent: str
    connected_at: datetime
    last_activity: datetime
    metadata: dict

    @property
    def is_authenticated(self) -> bool:
        """Check if this is an authenticated session."""
        return self.user_id is not None


class SessionManager:
    """Manages WebSocket sessions and tracks user activity.

    This class:
    - Tracks active WebSocket sessions in memory
    - Persists session events to Event table
    - Manages session lifecycle (connect/disconnect)
    - Tracks last activity for heartbeat monitoring
    """

    def __init__(self):
        """Initialize the session manager."""
        self.sessions: Dict[str, WebSocketSession] = {}
        self.connection_to_session: Dict[str, str] = {}  # connection_id -> session_id

    async def create_session(
        self,
        websocket: WebSocket,
        user: Optional[User],
        fingerprint: Optional[str],
        ip_address: str,
        user_agent: str,
        db: Session,
    ) -> WebSocketSession:
        """Create a new WebSocket session.

        Args:
            websocket: The WebSocket connection
            user: The authenticated user (if any)
            fingerprint: Browser fingerprint for anonymous users
            ip_address: Client IP address
            user_agent: Browser user agent string
            db: Database session

        Returns:
            WebSocketSession object
        """
        session_id = str(uuid.uuid4())
        connection_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        session = WebSocketSession(
            id=session_id,
            connection_id=connection_id,
            websocket=websocket,
            user_id=user.id if user else None,
            account_id=user.account_id if user else None,
            fingerprint=fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            connected_at=now,
            last_activity=now,
            metadata={},
        )

        self.sessions[session_id] = session
        self.connection_to_session[connection_id] = session_id

        # Persist session_start event to database (in thread pool to avoid blocking)
        activity = Event(
            session_id=uuid.UUID(session_id),
            user_id=session.user_id,
            account_id=session.account_id,
            fingerprint=session.fingerprint,
            event_type="session_start",
            timestamp=now,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={
                "connection_id": connection_id,
                "authenticated": session.is_authenticated,
            },
        )

        def _persist_event():
            # Create a new session for thread-safety (SQLAlchemy sessions are not thread-safe)
            thread_db = next(get_db_session())
            try:
                thread_db.add(activity)
                thread_db.commit()
            finally:
                thread_db.close()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_db_executor, _persist_event)

        logger.info(
            f"Created session {session_id} for "
            f"{'user ' + str(session.user_id) if session.user_id else 'anonymous ' + (fingerprint[:8] if fingerprint else 'unknown')}"
            f" from {ip_address}"
        )

        return session

    async def end_session(self, session_id: str, db: Session) -> None:
        """End a WebSocket session.

        Args:
            session_id: The session ID to end
            db: Database session
        """
        session = self.sessions.pop(session_id, None)
        if not session:
            logger.warning(f"Attempted to end non-existent session {session_id}")
            return

        # Remove connection mapping
        if session.connection_id in self.connection_to_session:
            del self.connection_to_session[session.connection_id]

        # Calculate session duration
        now = datetime.now(timezone.utc)
        duration_seconds = (now - session.connected_at).total_seconds()

        # Persist session_end event to database (in thread pool to avoid blocking)
        activity = Event(
            session_id=uuid.UUID(session_id),
            user_id=session.user_id,
            account_id=session.account_id,
            fingerprint=session.fingerprint,
            event_type="session_end",
            timestamp=now,
            ip_address=session.ip_address,
            event_data={
                "connection_id": session.connection_id,
                "duration_seconds": duration_seconds,
            },
        )

        def _persist_event():
            # Create a new session for thread-safety (SQLAlchemy sessions are not thread-safe)
            thread_db = next(get_db_session())
            try:
                thread_db.add(activity)
                thread_db.commit()
            finally:
                thread_db.close()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_db_executor, _persist_event)

        logger.info(
            f"Ended session {session_id} after {duration_seconds:.1f}s "
            f"for {'user ' + str(session.user_id) if session.user_id else 'anonymous ' + (session.fingerprint[:8] if session.fingerprint else 'unknown')}"
        )

    def get_session(self, session_id: str) -> Optional[WebSocketSession]:
        """Get session by ID.

        Args:
            session_id: The session ID to retrieve

        Returns:
            WebSocketSession object or None if not found
        """
        return self.sessions.get(session_id)

    def get_session_by_connection(
        self, connection_id: str
    ) -> Optional[WebSocketSession]:
        """Get session by connection ID.

        Args:
            connection_id: The connection ID to look up

        Returns:
            WebSocketSession object or None if not found
        """
        session_id = self.connection_to_session.get(connection_id)
        if session_id:
            return self.sessions.get(session_id)
        return None

    def update_activity(self, session_id: str) -> None:
        """Update last activity timestamp for a session.

        Args:
            session_id: The session ID to update
        """
        session = self.sessions.get(session_id)
        if session:
            session.last_activity = datetime.now(timezone.utc)

    def get_active_sessions_count(self) -> int:
        """Get count of active sessions.

        Returns:
            Number of active sessions
        """
        return len(self.sessions)

    def get_sessions_for_account(self, account_id: uuid.UUID) -> list[WebSocketSession]:
        """Get all active sessions for an account.

        Args:
            account_id: The account ID to filter by

        Returns:
            List of WebSocketSession objects
        """
        return [s for s in self.sessions.values() if s.account_id == account_id]

    def upgrade_session(
        self, session_id: str, user: "User", db: Session
    ) -> Optional[WebSocketSession]:
        """Upgrade an anonymous session to authenticated.

        This is used for message-based authentication where the client
        connects anonymously and then sends an authenticate message.

        Args:
            session_id: The session ID to upgrade
            user: The authenticated user
            db: Database session

        Returns:
            Updated WebSocketSession or None if session not found
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"Cannot upgrade non-existent session {session_id}")
            return None

        if session.user_id:
            logger.warning(f"Session {session_id} is already authenticated")
            return session

        # Update session with user info
        session.user_id = user.id
        session.account_id = user.account_id

        # Log the upgrade event
        now = datetime.now(timezone.utc)
        activity = Event(
            session_id=uuid.UUID(session_id),
            user_id=user.id,
            account_id=user.account_id,
            fingerprint=session.fingerprint,
            event_type="session_authenticated",
            timestamp=now,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            event_data={
                "connection_id": session.connection_id,
                "username": user.username,
            },
        )

        db.add(activity)
        db.commit()

        logger.info(
            f"Upgraded session {session_id} to authenticated user {user.username}"
        )

        return session


# Global singleton instance
session_manager = SessionManager()
