"""Canonical job URL normalization for deduplication and redirect tracking."""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Query params commonly used for tracking (strip for stable identity)
_STRIP_QUERY_PREFIXES = (
    "utm_",
    "fbclid",
    "gclid",
    "mc_eid",
    "msclkid",
    "_ga",
    "_gl",
    "ref",
    "source",
)


def normalize_job_url(url: str) -> str:
    """Return a stable form of a job URL for deduping and comparison.

    - Lowercases scheme and host
    - Drops trailing slash on path (except root)
    - Removes known tracking query parameters
    """
    if not url or not url.strip():
        return url
    raw = url.strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    pairs = parse_qs(parsed.query, keep_blank_values=True)
    filtered: dict[str, list[str]] = {}
    for key, vals in pairs.items():
        lk = key.lower()
        if any(lk.startswith(p) or lk == p.rstrip("_") for p in _STRIP_QUERY_PREFIXES):
            continue
        filtered[key] = vals

    new_query = urlencode(filtered, doseq=True) if filtered else ""
    fragment = ""
    return urlunparse((scheme, netloc, path, "", new_query, fragment))
