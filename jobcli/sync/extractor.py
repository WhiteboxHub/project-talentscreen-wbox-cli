"""Sync data extractor — Phase 1 (local only, no network calls).

``extract_field_answers`` and ``extract_locators`` produce structured
JSON-serialisable dicts that are fully ready for a Phase 2 sync client to
POST to a central server.  Nothing in this module performs any I/O beyond
reading the local SQLite database.

Usage example::

    from jobcli.storage.models import Database
    from jobcli.sync.extractor import extract_field_answers, extract_locators

    db = Database("sqlite:///~/.jobcli/jobcli.db")
    with db.get_session() as session:
        answers  = extract_field_answers(session)
        locators = extract_locators(session)
        # answers / locators are plain dicts — json.dumps() them or POST directly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from jobcli.storage.models import FieldAnswerModel, LearnedLocatorModel
from jobcli.sync.constants import (
    CONFIDENCE_THRESHOLD,
    MIN_SUCCESS_COUNT,
    PERSONAL_FIELDS,
)


def _is_personal(normalized_label: str | None) -> bool:
    """Return True if the label represents a personal / PII field."""
    if not normalized_label:
        return False
    label = normalized_label.lower().strip()
    # Exact match
    if label in PERSONAL_FIELDS:
        return True
    # Substring match — catches e.g. "current salary expectation"
    return any(personal in label for personal in PERSONAL_FIELDS)


def extract_field_answers(
    session: Session,
    min_confidence: float = CONFIDENCE_THRESHOLD,
    min_success_count: int = MIN_SUCCESS_COUNT,
) -> list[dict[str, Any]]:
    """Return high-confidence, non-personal field answers as JSON-serialisable dicts.

    Filters applied:
    * ``confidence >= min_confidence``          (default 0.6)
    * ``success_count >= min_success_count``    (default 3)
    * ``normalized_label`` not in ``PERSONAL_FIELDS``

    Returns:
        List of dicts with keys:
        ``normalized_label``, ``field_label``, ``value``, ``ats_type``,
        ``field_type``, ``success_count``, ``failure_count``, ``confidence``,
        ``source``.
    """
    rows = (
        session.query(FieldAnswerModel)
        .filter(
            FieldAnswerModel.confidence >= min_confidence,
            FieldAnswerModel.success_count >= min_success_count,
        )
        .order_by(FieldAnswerModel.confidence.desc(), FieldAnswerModel.success_count.desc())
        .all()
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        # Skip personal / PII fields — never share these
        if _is_personal(row.normalized_label):
            continue
        if _is_personal(row.field_label):
            continue

        results.append(
            {
                "normalized_label": row.normalized_label,
                "field_label": row.field_label,
                "value": row.value,
                "ats_type": row.ats_type.value if row.ats_type else None,
                "field_type": row.field_type,
                "success_count": row.success_count,
                "failure_count": row.failure_count,
                "confidence": round(row.confidence, 4),
                "source": row.source,
            }
        )

    return results


def extract_locators(
    session: Session,
    min_confidence: float = CONFIDENCE_THRESHOLD,
    min_success_count: int = MIN_SUCCESS_COUNT,
) -> list[dict[str, Any]]:
    """Return high-confidence learned locators as JSON-serialisable dicts.

    Filters applied:
    * ``confidence_score >= min_confidence``    (default 0.6)
    * ``success_count >= min_success_count``    (default 3)

    Locators are structural / behavioural patterns — not personal data — so no
    label-filtering is applied.  The ``notes`` field may contain user-entered
    context; callers may wish to strip it before sending to a public server.

    Returns:
        List of dicts with keys:
        ``ats_type``, ``selector``, ``selector_type``, ``purpose``,
        ``success_count``, ``failure_count``, ``confidence_score``,
        ``domain_pattern``, ``url_pattern``, ``created_by``.
    """
    rows = (
        session.query(LearnedLocatorModel)
        .filter(
            LearnedLocatorModel.confidence_score >= min_confidence,
            LearnedLocatorModel.success_count >= min_success_count,
        )
        .order_by(
            LearnedLocatorModel.confidence_score.desc(),
            LearnedLocatorModel.success_count.desc(),
        )
        .all()
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "ats_type": row.ats_type.value if row.ats_type else None,
                "selector": row.selector,
                "selector_type": row.selector_type.value if row.selector_type else None,
                "purpose": row.purpose,
                "success_count": row.success_count,
                "failure_count": row.failure_count,
                "confidence_score": round(row.confidence_score, 4),
                "domain_pattern": row.domain_pattern,
                "url_pattern": row.url_pattern,
                "created_by": row.created_by,
            }
        )

    return results
