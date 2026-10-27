"""Push notification and device registration services.

This module provides services for:
- QR code generation for mobile device registration
- Device token validation
- Push notification delivery (FCM for Android, APNS for iOS)
"""

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


# In-memory token storage (for MVP - should be Redis/database in production)
_registration_tokens: Dict[str, Dict[str, Any]] = {}


def generate_registration_token(
    user_id: uuid.UUID, api_url: str, expiry_minutes: int = 15
) -> Dict[str, Any]:
    """Generate a secure registration token for QR code device registration.

    Args:
        user_id: User ID for device registration.
        api_url: API base URL for registration endpoint.
        expiry_minutes: Token expiry time in minutes (default: 15).

    Returns:
        Dictionary containing:
            - token: Secure URL-safe token
            - qr_data: Universal link URL (https://...) for QR code
            - expires_at: ISO formatted expiry timestamp
            - expires_in_seconds: Seconds until expiry

    Note:
        The qr_data URL uses Universal Links (iOS) and App Links (Android).
        - If the Preloop.AI app is installed, it will open automatically
        - If not installed, the web page will redirect to appropriate app store
        - Requires proper domain configuration (AASA file for iOS, assetlinks.json for Android)
    """
    # Generate secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=expiry_minutes)

    # Store token with user_id and expiry
    _registration_tokens[token] = {
        "user_id": str(user_id),
        "expires_at": expires_at,
    }

    # Generate universal link URL (works for both iOS Universal Links and Android App Links)
    # This URL will:
    # 1. Open the app directly if installed (via OS deep linking)
    # 2. Show a web page with app store links if app not installed
    qr_data = f"{api_url}/api/v1/notification-preferences/register-device?token={token}"

    return {
        "token": token,
        "qr_data": qr_data,
        "expires_at": expires_at.isoformat() + "Z",
        "expires_in_seconds": expiry_minutes * 60,
    }


def validate_registration_token(token: str) -> Optional[uuid.UUID]:
    """Validate a registration token and return the associated user ID.

    Args:
        token: Registration token from QR code.

    Returns:
        User ID if token is valid and not expired, None otherwise.
    """
    token_data = _registration_tokens.get(token)

    if not token_data:
        return None

    # Check if token is expired
    expires_at = token_data["expires_at"]
    if datetime.utcnow() > expires_at:
        # Clean up expired token
        del _registration_tokens[token]
        return None

    # Token is valid - clean it up (one-time use)
    user_id = uuid.UUID(token_data["user_id"])
    del _registration_tokens[token]

    return user_id


def send_push_notification(
    device_token: str,
    platform: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send a push notification to a mobile device.

    This is a placeholder for future FCM/APNS integration.

    Args:
        device_token: Device push notification token.
        platform: Device platform ('ios' or 'android').
        title: Notification title.
        body: Notification body.
        data: Optional custom data payload.

    Returns:
        True if notification sent successfully, False otherwise.
    """
    # TODO: Implement FCM for Android
    # TODO: Implement APNS for iOS

    # For now, just log the notification
    print(f"[PUSH NOTIFICATION] {platform} - {title}: {body}")
    print(f"[PUSH NOTIFICATION] Device: {device_token[:20]}...")
    if data:
        print(f"[PUSH NOTIFICATION] Data: {data}")

    # Placeholder: return True for now
    return True
