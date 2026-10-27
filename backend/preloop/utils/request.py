"""Request utility functions for extracting client information."""

from typing import Optional, Union

from fastapi import Request, WebSocket


def get_client_ip(request: Union[Request, WebSocket]) -> str:
    """Extract real client IP address from request or websocket.

    This function checks for IP addresses in the following order:
    1. X-Forwarded-For header (set by proxies/load balancers like Kubernetes ingress)
    2. X-Real-IP header (alternative proxy header)
    3. Direct client IP from the connection

    Args:
        request: FastAPI Request or WebSocket connection

    Returns:
        Client IP address as string. Returns "unknown" if IP cannot be determined.

    Examples:
        >>> from fastapi import Request
        >>> # Behind a proxy
        >>> request = Request(...)
        >>> get_client_ip(request)  # Returns real client IP from X-Forwarded-For
        '203.0.113.195'

        >>> # Direct connection
        >>> request = Request(...)
        >>> get_client_ip(request)  # Returns direct client IP
        '192.168.1.100'
    """
    if not request:
        return "unknown"

    # Check X-Forwarded-For header (set by ingress/load balancer)
    # Format: "client, proxy1, proxy2" - first IP is the real client
    forwarded_for = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    if forwarded_for:
        # Split by comma and take the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (alternative proxy header)
    real_ip = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct client IP from the connection
    if hasattr(request, "client") and request.client:
        return request.client.host

    return "unknown"


def get_client_ip_optional(
    request: Optional[Union[Request, WebSocket]],
) -> Optional[str]:
    """Extract real client IP address from request or websocket, returning None if unavailable.

    This is similar to get_client_ip() but returns None instead of "unknown" when
    the IP cannot be determined. Useful when you need to distinguish between
    a missing IP and an unknown IP.

    Args:
        request: FastAPI Request or WebSocket connection, or None

    Returns:
        Client IP address as string, or None if IP cannot be determined.

    Examples:
        >>> from fastapi import Request
        >>> get_client_ip_optional(None)
        None

        >>> request = Request(...)
        >>> get_client_ip_optional(request)
        '203.0.113.195'
    """
    if not request:
        return None

    # Check X-Forwarded-For header
    forwarded_for = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct client IP
    if hasattr(request, "client") and request.client:
        return request.client.host

    return None
