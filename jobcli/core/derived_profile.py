"""Deterministic profile enrichments from resume JSON (pronouns, country).

Used when explicit JSON fields are empty. Conservative defaults only.
"""

from __future__ import annotations

import re
from typing import Optional

from jobcli.core.schemas import ResumeData

_US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA "
    "WV WI WY DC".split()
)


def infer_pronouns_from_gender(gender: Optional[str], explicit_pronouns: Optional[str]) -> Optional[str]:
    """Return pronouns string for forms when user did not set pronouns explicitly.

    Only fills when gender is clearly male/female/non-binary; never overrides
    explicit pronouns or 'prefer not' style answers.
    """
    if explicit_pronouns and explicit_pronouns.strip():
        return None  # caller should use explicit
    if not gender:
        return None
    g = gender.lower().strip()
    if any(x in g for x in ("prefer not", "decline", "rather not", "not say", "undisclosed")):
        return None
    if g in ("male", "m", "man", "masculine"):
        return "he/him"
    if g in ("female", "f", "woman", "feminine"):
        return "she/her"
    if "non-binary" in g or "nonbinary" in g or "non binary" in g:
        return "they/them"
    if "male" in g and "female" not in g:
        return "he/him"
    if "female" in g and "male" not in g:
        return "she/her"
    return None


def infer_country_from_city_state(
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
) -> Optional[str]:
    """Infer United States when city/state clearly indicate US and country empty."""
    if country and str(country).strip():
        return None
    st = (state or "").strip().upper()
    if st in _US_STATE_CODES:
        return "United States"
    # Common full state names → US (lightweight)
    if st and len(st) > 2 and re.search(
        r"\b(california|texas|new york|florida|washington|illinois)\b",
        (state or "").lower(),
    ):
        return "United States"
    city_l = (city or "").lower()
    us_cities = (
        "san francisco",
        "new york",
        "los angeles",
        "chicago",
        "houston",
        "seattle",
        "boston",
        "austin",
        "denver",
        "atlanta",
    )
    if any(c in city_l for c in us_cities) and (st in _US_STATE_CODES or not state):
        return "United States"
    return None


def derived_country_for_resume(resume: ResumeData) -> Optional[str]:
    """Country string to use when personal.country is blank."""
    return infer_country_from_city_state(
        resume.personal.city,
        resume.personal.state,
        resume.personal.country,
    )


def derived_pronouns_for_resume(resume: ResumeData) -> Optional[str]:
    """Pronouns when demographics.pronouns unset but gender suggests a default."""
    demo = resume.demographics
    gender = demo.gender if demo else None
    explicit = demo.pronouns if demo else None
    return infer_pronouns_from_gender(gender, explicit)
