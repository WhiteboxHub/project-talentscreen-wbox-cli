"""Deterministic profile enrichments from resume JSON (pronouns, country).

Used when explicit JSON fields are empty. Conservative defaults only.
"""

from __future__ import annotations

import re
from typing import Optional

from jobcli.profile.schemas import Experience, ResumeData

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


def composite_location_string(resume: ResumeData) -> Optional[str]:
    """Single-line location for ATS 'Location' / typeahead (city, state, zip, country)."""
    p = resume.personal
    bits: list[str] = []
    for b in (p.city, p.state, p.zip_code, p.country):
        if b is not None and str(b).strip():
            bits.append(str(b).strip())
    if not bits:
        return None
    return ", ".join(bits)


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


def experience_narrative_for_forms(resume: ResumeData, ex: Experience) -> str:
    """Long-form text for responsibility / description fields.

    If ``ex.description`` is set, that text is used. Otherwise we build a
    short professional summary from the rest of the profile so ATS forms
    with required description boxes are not left blank. This is
    **deterministic**; the LLM is separately instructed to refine or
    expand when a richer free-text answer is needed.
    """
    raw = (ex.description or "").strip() if ex.description is not None else ""
    if raw:
        return raw[:8000]

    parts: list[str] = []
    span = f"{ex.title} at {ex.company}"
    if ex.start_date:
        end = "Present" if getattr(ex, "current", False) else (ex.end_date or "Present")
        span += f" ({ex.start_date} – {end})"
    parts.append(f"{span}.")

    if resume.skills:
        parts.append(
            "Relevant skills: " + ", ".join(resume.skills[:16]) + "."
        )
    if resume.experience and len(resume.experience) > 1:
        other = [e.company for e in resume.experience if e.company and e.company != ex.company]
        if other:
            unique = list(dict.fromkeys(other))[:4]
            parts.append("Other experience: " + ", ".join(unique) + ".")
    if resume.education:
        e0 = resume.education[0]
        if e0.degree and e0.school:
            y = f", {e0.graduation_year}" if e0.graduation_year else ""
            parts.append(
                f"Education: {e0.degree} — {e0.school}{y}."
            )

    if len(" ".join(parts)) < 60 and resume.personal:
        p = resume.personal
        loc = ", ".join(
            x
            for x in (p.city, p.state, p.country)
            if x and str(x).strip()
        )
        if loc:
            parts.append(f"Location: {loc}.")

    return " ".join(parts)[:8000]
