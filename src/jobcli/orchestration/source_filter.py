"""Source allow-list for the WBL discover ingest filter.

The WBL backend tags every listing with a ``Source`` value (``linkedin``,
``jobright``, ``hiring.cafe``, ``trueup.io``, ``indeed`` ...). The CLI is
opinionated about which of those it knows how to autoapply against, so
:mod:`jobcli.orchestration.wbox_discoverer` drops every row whose ``source`` value
isn't one of :data:`DEFAULT_SOURCES` before persisting it to the local DB.

Two things live here, both consumed only by the discoverer:

* :data:`DEFAULT_SOURCES` — the canonical allow-list. To change it, edit
  this tuple (no CLI flag, no env var; the filter is unconditional).
* :func:`normalize_source` — collapses casing and punctuation so that
  ``"Trueup.Io"``, ``"trueup.io"``, ``"TRUEUP IO"`` and ``"Trueup-Io"``
  all hash to the same token (``"trueupio"``).

Keeping this logic in its own tiny module lets the unit tests run without
dragging in the entire Typer CLI surface.
"""

from __future__ import annotations

from typing import Optional


# Hardcoded allow-list. Every WBL row whose ``source`` value normalises to
# something outside this tuple is dropped at discover time and never
# touches the local SQLite database.
DEFAULT_SOURCES: tuple[str, ...] = (
    "trueup.io",
    "hiring.cafe",
    "jobright",
    "linkedin",
)


def normalize_source(raw: Optional[str]) -> str:
    """Lowercase + drop non-alphanumeric characters.

    Examples:
        ``"Trueup.Io"`` -> ``"trueupio"``
        ``"hiring.cafe"`` -> ``"hiringcafe"``
        ``"Hiring-Cafe"`` -> ``"hiringcafe"``
        ``"LINKEDIN"`` -> ``"linkedin"``
        ``None`` or ``""`` -> ``""``
    """
    if not raw:
        return ""
    return "".join(c for c in str(raw).lower() if c.isalnum())
