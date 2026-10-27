"""API endpoints for notification preferences."""

import os
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from preloop.models import models
from preloop.models.crud import notification_preferences
from preloop.models.db.session import get_db_session
from preloop.api.auth import get_current_active_user
from preloop.schemas.notification_preferences import (
    NotificationPreferencesUpdate,
    NotificationPreferencesResponse,
    MobileDeviceRegistration,
    MobileDeviceRegistrationResponse,
    QRCodeResponse,
)
from preloop.services.push_notifications import (
    generate_registration_token,
    validate_registration_token,
    check_token_validity,
)

router = APIRouter()


@router.get("/me", response_model=NotificationPreferencesResponse)
async def get_my_notification_preferences(
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
) -> models.NotificationPreferences:
    """Get current user's notification preferences.

    Returns:
        Notification preferences.
    """
    prefs = notification_preferences.get_or_create(db, current_user.id)
    db.commit()
    db.refresh(prefs)

    return prefs


@router.put("/me", response_model=NotificationPreferencesResponse)
async def update_my_notification_preferences(
    prefs_in: NotificationPreferencesUpdate,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
) -> models.NotificationPreferences:
    """Update current user's notification preferences.

    Args:
        prefs_in: Preferences update data.

    Returns:
        Updated notification preferences.
    """
    prefs = notification_preferences.get_or_create(db, current_user.id)

    updated_prefs = notification_preferences.update(
        db,
        prefs,
        preferred_channel=prefs_in.preferred_channel,
        enable_email=prefs_in.enable_email,
        enable_mobile_push=prefs_in.enable_mobile_push,
    )

    db.commit()
    db.refresh(updated_prefs)

    return updated_prefs


@router.post("/me/register-device", response_model=NotificationPreferencesResponse)
async def register_mobile_device(
    device_in: MobileDeviceRegistration,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
) -> models.NotificationPreferences:
    """Register a mobile device for push notifications.

    Args:
        device_in: Device registration data.

    Returns:
        Updated notification preferences.
    """
    if device_in.platform not in ["ios", "android"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform must be 'ios' or 'android'",
        )

    prefs = notification_preferences.add_device_token(
        db, current_user.id, device_in.platform, device_in.token
    )

    db.commit()
    db.refresh(prefs)

    return prefs


@router.delete("/me/device/{token}", response_model=NotificationPreferencesResponse)
async def unregister_mobile_device(
    token: str,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
) -> Optional[models.NotificationPreferences]:
    """Unregister a mobile device and delete associated API key.

    Args:
        token: Device token to remove.

    Returns:
        Updated notification preferences.

    Raises:
        HTTPException: If preferences not found.
    """
    from preloop.models.models.api_key import ApiKey

    # Find and delete any API keys that were created for this device token
    # We search for API keys that match the device token pattern in their name
    # or look for the token in a device_token metadata field if we stored it
    api_keys = (
        db.query(ApiKey)
        .filter(
            ApiKey.user_id == current_user.id,
            ApiKey.account_id == current_user.account_id,
        )
        .all()
    )

    # Delete API keys that match the device token
    for api_key in api_keys:
        # Check if this API key was created for this device
        # We stored the device token in the key metadata or name
        key_metadata = api_key.scopes or []
        if isinstance(key_metadata, list) and any(
            isinstance(s, dict) and s.get("device_token") == token for s in key_metadata
        ):
            db.delete(api_key)

    prefs = notification_preferences.remove_device_token(db, current_user.id, token)

    if not prefs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification preferences not found",
        )

    db.commit()
    db.refresh(prefs)

    return prefs


@router.get("/me/qr-code", response_model=QRCodeResponse)
async def get_registration_qr_code(
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
) -> dict:
    """Generate a QR code for mobile device registration.

    Returns:
        QR code data with registration token.
    """
    api_url = os.getenv("PRELOOP_URL", "http://localhost:8000")

    qr_data = generate_registration_token(
        db=db,
        user_id=current_user.id,
        api_url=api_url,
        expiry_minutes=15,
    )

    return qr_data


@router.post("/register-via-token", response_model=MobileDeviceRegistrationResponse)
async def register_device_via_token(
    token: str,
    device_in: MobileDeviceRegistration,
    db: Session = Depends(get_db_session),
) -> dict:
    """Register a mobile device using a QR code token and create an API key.

    This endpoint is called by the mobile app after scanning the QR code.
    It registers the device for push notifications AND creates an API key
    for the mobile app to authenticate API requests.

    Args:
        token: Registration token from QR code.
        device_in: Device registration data.

    Returns:
        Updated notification preferences with API key.

    Raises:
        HTTPException: If token is invalid or expired.
    """
    import secrets
    import string
    from datetime import timedelta
    from preloop.models.models.api_key import ApiKey
    from preloop.models.crud import crud_user

    # Validate token
    user_id = validate_registration_token(db, token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired registration token",
        )

    # Get user
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if this is the first device being registered
    existing_prefs = notification_preferences.get_by_user(db, user_id)
    is_first_device = (
        not existing_prefs
        or not existing_prefs.mobile_device_tokens
        or len(existing_prefs.mobile_device_tokens) == 0
    )

    # Register device
    prefs = notification_preferences.add_device_token(
        db, user_id, device_in.platform, device_in.token
    )

    # Enable push notifications by default when adding the first device
    if is_first_device and not prefs.enable_mobile_push:
        prefs.enable_mobile_push = True
        db.flush()

    # Generate API key for mobile app
    alphabet = string.ascii_letters + string.digits
    api_key_value = "".join(secrets.choice(alphabet) for _ in range(40))

    # Create device name with timestamp to avoid conflicts
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base_name = device_in.device_name or f"{device_in.platform.title()} Device"
    device_name = f"{base_name} ({timestamp})"

    # Set expiration to 1 year
    expires_at = datetime.now(UTC) + timedelta(days=365)

    # Create API key with device_token reference for later cleanup
    # Store the device token in scopes metadata so we can delete this key
    # when the device is unregistered
    new_api_key = ApiKey(
        name=device_name,
        key=api_key_value,
        scopes=[{"device_token": device_in.token}],
        account_id=user.account_id,
        user_id=user_id,
        expires_at=expires_at,
    )

    db.add(new_api_key)
    db.commit()
    db.refresh(prefs)
    db.refresh(new_api_key)

    # Send WebSocket notification to user about device registration
    from preloop.services.websocket_manager import manager

    await manager.broadcast_json(
        {
            "type": "device_registered",
            "user_id": str(user_id),
            "account_id": str(user.account_id),
            "platform": device_in.platform,
            "device_name": device_name,
            "registered_at": prefs.mobile_device_tokens[-1]["registered_at"]
            if prefs.mobile_device_tokens
            else None,
        },
        account_id=str(user.account_id),
    )

    return {
        "preferences": prefs,
        "api_key": new_api_key.key,
        "api_key_id": new_api_key.id,
        "api_key_expires_at": new_api_key.expires_at,
    }


@router.get("/register-device", response_class=HTMLResponse, include_in_schema=False)
async def register_device_landing_page(
    request: Request, token: str, db: Session = Depends(get_db_session)
) -> str:
    """Landing page for device registration deep link.

    This endpoint serves as the universal link target for QR code scanning.
    It will:
    1. Attempt to open the Preloop.AI app if installed (via custom URL scheme)
    2. If app doesn't open within 2 seconds, redirect to appropriate app store

    Args:
        request: FastAPI request object (for user agent detection).
        token: Registration token from QR code.

    Returns:
        HTML page with app launch logic and store fallbacks.

    Note:
        For this to work as a universal link:
        - iOS: Configure Apple App Site Association (AASA) file at /.well-known/apple-app-site-association
        - Android: Configure Digital Asset Links at /.well-known/assetlinks.json
    """
    # Get environment variables for app store URLs
    app_store_url = os.getenv(
        "IOS_APP_STORE_URL", "https://apps.apple.com/app/preloop/id6757803021"
    )
    play_store_url = os.getenv(
        "ANDROID_PLAY_STORE_URL",
        "https://play.google.com/store/apps/details?id=ai.spacecode.preloop&pli=1",
    )

    # Get user agent to determine device type
    user_agent = request.headers.get("user-agent", "").lower()
    is_ios = "iphone" in user_agent or "ipad" in user_agent
    is_android = "android" in user_agent

    # Determine which store to redirect to
    store_url = app_store_url if is_ios else play_store_url

    # Check if token is valid (just for messaging - don't consume it yet)
    # The app will consume it when it registers
    is_valid_token = check_token_validity(db, token)

    if not is_valid_token:
        # Token expired or invalid
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Registration Link Expired - Preloop.AI</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 20px;
                }
                .container {
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                    max-width: 400px;
                    text-align: center;
                }
                h1 {
                    color: #333;
                    margin-bottom: 16px;
                    font-size: 24px;
                }
                p {
                    color: #666;
                    line-height: 1.6;
                    margin-bottom: 24px;
                }
                .error-icon {
                    font-size: 64px;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">⏰</div>
                <h1>Registration Link Expired</h1>
                <p>This device registration link has expired or is invalid. Please generate a new QR code from your Preloop.AI settings.</p>
            </div>
        </body>
        </html>
        """

    # Valid token - serve the deep link page
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Opening Preloop.AI...</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                max-width: 400px;
                text-align: center;
            }}
            h1 {{
                color: #333;
                margin-bottom: 16px;
                font-size: 24px;
            }}
            p {{
                color: #666;
                line-height: 1.6;
                margin-bottom: 24px;
            }}
            .spinner {{
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .store-links {{
                display: flex;
                flex-direction: column;
                gap: 12px;
                margin-top: 24px;
            }}
            .store-button {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                padding: 12px 24px;
                background: #000;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: background 0.2s;
            }}
            .store-button:hover {{
                background: #333;
            }}
            .hidden {{
                display: none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div id="loading">
                <div class="spinner"></div>
                <h1>Opening Preloop.AI...</h1>
                <p>If the app doesn't open automatically, use the buttons below to download it.</p>
            </div>

            <div id="fallback" class="hidden">
                <h1>Get Preloop.AI</h1>
                <p>Install the Preloop.AI app to complete device registration.</p>
                <div class="store-links">
                    <a href="{app_store_url}" class="store-button" {'style="display: none;"' if not is_ios else ""}>
                        <span>📱</span>
                        Download on App Store
                    </a>
                    <a href="{play_store_url}" class="store-button" {'style="display: none;"' if not is_android else ""}>
                        <span>🤖</span>
                        Get it on Google Play
                    </a>
                </div>
            </div>
        </div>

        <script>
            // Try to open the app with custom URL scheme
            const appUrl = 'preloop://register?token={token}';

            // Attempt to open the app
            window.location.href = appUrl;

            // After 2 seconds, show the store download options
            // If the app opened successfully, the user won't see this
            setTimeout(() => {{
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('fallback').classList.remove('hidden');
            }}, 2000);

            // Alternative approach: Use iframe for better detection (iOS)
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            iframe.src = appUrl;
            document.body.appendChild(iframe);
            setTimeout(() => {{
                document.body.removeChild(iframe);
            }}, 500);
        </script>
    </body>
    </html>
    """
