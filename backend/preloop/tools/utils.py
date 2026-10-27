"""Utility functions for MCP tools."""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


def run_async(coro: Coroutine) -> Any:
    """Run an async function synchronously.

    Args:
        coro: The coroutine to run.

    Returns:
        The result of the coroutine.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If there's no event loop in the current thread, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


def async_to_sync(func: Callable) -> Callable:
    """Decorator to convert an async function to a sync function.

    Args:
        func: The async function to convert.

    Returns:
        A sync function that runs the async function in an event loop.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        return run_async(func(*args, **kwargs))

    return wrapper
