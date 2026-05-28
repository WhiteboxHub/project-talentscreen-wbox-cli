"""URL comparison helpers for handoff / navigation detection."""

from __future__ import annotations

from urllib.parse import urlparse


def urls_meaningfully_different(before: str, after: str) -> bool:
    """True when navigation moved to a different page (not hash/query noise)."""
    if not before or not after:
        return False
    b, a = urlparse(before), urlparse(after)
    if b.netloc.lower() != a.netloc.lower():
        return True
    return b.path.rstrip("/") != a.path.rstrip("/")
