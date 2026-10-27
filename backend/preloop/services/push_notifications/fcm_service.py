"""Firebase Cloud Messaging (FCM) service for Android push notifications."""

import asyncio
import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Thread pool for FCM operations to avoid blocking the event loop
_fcm_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fcm_")

# Global FCM service instance
_fcm_initialized = False


def _initialize_fcm() -> bool:
    """Initialize Firebase Admin SDK if not already done.

    Environment variables:
        FCM_CREDENTIALS_JSON: JSON string of Firebase service account credentials (preferred for K8s)
        FCM_CREDENTIALS_PATH: Path to Firebase service account JSON file (fallback)

    Returns:
        True if initialization succeeded, False otherwise.
    """
    global _fcm_initialized

    if _fcm_initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _fcm_initialized = True
            return True

        # Try JSON string first (preferred for Kubernetes secrets)
        creds_json = os.getenv("FCM_CREDENTIALS_JSON")
        if creds_json:
            try:
                # Try to decode from base64 first (in case it's base64 encoded)
                try:
                    decoded = base64.b64decode(creds_json).decode("utf-8")
                    cred_dict = json.loads(decoded)
                    logger.debug("FCM credentials decoded from base64")
                except Exception:
                    # If base64 decode fails, assume it's already plain JSON
                    cred_dict = json.loads(creds_json)
                    logger.debug("FCM credentials parsed as plain JSON")

                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                _fcm_initialized = True
                logger.info("FCM initialized from FCM_CREDENTIALS_JSON")
                return True
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse FCM_CREDENTIALS_JSON: {e}")

        # Fallback to file path
        creds_path = os.getenv("FCM_CREDENTIALS_PATH")
        if creds_path and os.path.exists(creds_path):
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)
            _fcm_initialized = True
            logger.info(f"FCM initialized from {creds_path}")
            return True

        logger.warning(
            "FCM not configured (no FCM_CREDENTIALS_JSON or FCM_CREDENTIALS_PATH)"
        )
        return False

    except ImportError:
        logger.warning("firebase-admin package not installed")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize FCM: {e}")
        return False


def is_fcm_configured() -> bool:
    """Check if FCM is configured and can be initialized."""
    creds_json = os.getenv("FCM_CREDENTIALS_JSON")
    creds_path = os.getenv("FCM_CREDENTIALS_PATH")
    return bool(creds_json or (creds_path and os.path.exists(creds_path)))


def _send_fcm_sync(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    priority: str = "high",
) -> Dict[str, Any]:
    """Synchronous FCM send - runs in thread pool to avoid blocking event loop."""
    try:
        from firebase_admin import messaging

        # Convert data values to strings (FCM requirement)
        string_data = {}
        if data:
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    string_data[key] = json.dumps(value)
                else:
                    string_data[key] = str(value)

        # Build FCM message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=string_data,
            token=token,
            android=messaging.AndroidConfig(
                priority=priority,
                notification=messaging.AndroidNotification(
                    channel_id="preloop_approvals",  # Must match Android app's CHANNEL_APPROVALS
                    priority="max" if priority == "high" else "default",
                ),
            ),
        )

        # Send message (blocking HTTP call)
        response = messaging.send(message)
        logger.info(f"FCM notification sent: {response}")

        return {
            "success": True,
            "message_id": response,
        }

    except Exception as e:
        error_str = str(e)
        logger.error(f"Failed to send FCM notification: {error_str}")

        # Check for invalid token errors
        invalid_token = any(
            err in error_str.lower()
            for err in ["not registered", "invalid registration", "unregistered"]
        )

        return {
            "success": False,
            "error": error_str,
            "invalid_token": invalid_token,
        }


async def send_fcm_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    priority: str = "high",
) -> Dict[str, Any]:
    """Send a push notification via Firebase Cloud Messaging.

    Runs the Firebase SDK call in a thread pool to avoid blocking the event loop.

    Args:
        token: FCM device token.
        title: Notification title.
        body: Notification body.
        data: Optional data payload.
        priority: Message priority ("high" or "normal").

    Returns:
        Dict with send result including:
            - success: bool
            - message_id: str (if successful)
            - error: str (if failed)
            - invalid_token: bool (if token is invalid/expired)
    """
    if not _initialize_fcm():
        return {"success": False, "error": "FCM not configured"}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _fcm_executor,
        partial(_send_fcm_sync, token, title, body, data, priority),
    )
