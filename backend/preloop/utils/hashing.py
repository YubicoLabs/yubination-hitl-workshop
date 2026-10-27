"""Hashing utility functions."""

import hashlib
import json
from typing import Any


def compute_content_hash(content: Any) -> str:
    """Compute a hash of content for detecting changes.

    For strings (prompts), hashes the string directly.
    For lists/dicts (tools), serializes to JSON first.
    Returns first 16 chars of SHA256 hash.

    Args:
        content: The content to hash (string, dict, list, or other serializable type).

    Returns:
        First 16 characters of the SHA256 hash.
    """
    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        # Serialize to JSON with sorted keys for consistent hashing
        data = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]
