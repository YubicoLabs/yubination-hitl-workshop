"""Permission utilities with OSS fallback.

When the proprietary RBAC plugin is unavailable, this module exposes a no-op
decorator. When it is available, the exported decorator preserves the wrapped
function's sync/async nature so FastAPI can keep dispatching sync handlers via
its threadpool.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import threading

try:
    from preloop.plugins.proprietary.rbac.permissions import (
        require_permission as _plugin_require_permission,
    )
except ModuleNotFoundError:
    _plugin_require_permission = None


def _run_awaitable_sync(awaitable):
    """Run an awaitable from sync code, even if this thread already has a loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, object] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # pragma: no cover - re-raised below
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]
    return result.get("value")


def require_permission(permission_name: str):
    """Return a decorator that preserves sync/async behavior."""

    def decorator(func):
        if _plugin_require_permission is None:
            return func

        plugin_wrapped = _plugin_require_permission(permission_name)(func)

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if "current_user" not in kwargs or "db" not in kwargs:
                    return await func(*args, **kwargs)
                return await plugin_wrapped(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if "current_user" not in kwargs or "db" not in kwargs:
                return func(*args, **kwargs)
            result = plugin_wrapped(*args, **kwargs)
            if inspect.isawaitable(result):
                return _run_awaitable_sync(result)
            return result

        return sync_wrapper

    return decorator
