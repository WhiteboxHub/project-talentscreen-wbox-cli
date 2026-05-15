"""Normalize resume-derived strings for ATS validation (LinkedIn, etc.)."""

from __future__ import annotations

import re
from typing import Optional


def normalize_linkedin_url(raw: Optional[str]) -> Optional[str]:
    """Return a canonical https://www.linkedin.com/in/.../ URL or None.

    Workday and other ATS reject partial handles or missing schemes. Optional
    fields should stay empty (None) rather than invalid text.
    """
    if raw is None:
        return None
    s = str(raw).strip().strip("<>")
    if not s:
        return None
    low = s.lower()

    if "linkedin.com" in low:
        if "/in/" not in low:
            return None
        m = re.search(r"linkedin\.com/in/([^/?\s#]+)", low, re.I)
        if not m:
            return None
        slug = m.group(1).strip("/")
        if not slug or len(slug) < 2:
            return None
        return f"https://www.linkedin.com/in/{slug}/"

    if low.startswith("http://") or low.startswith("https://"):
        return None

    if re.fullmatch(r"[A-Za-z0-9\-]{3,100}", s):
        return f"https://www.linkedin.com/in/{s}/"

    return None
