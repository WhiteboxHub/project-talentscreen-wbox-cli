"""Export JobCLI ``ResumeData`` to JSON Resume format for TalentScreen v2."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from jobcli.profile.derived_profile import derived_country_for_resume
from jobcli.profile.schemas import CommonQuestions, ResumeData

_PRESENT_DATE_TOKENS = frozenset(
    {"present", "current", "now", "ongoing", "till date", "till now", "today"}
)


def _is_valid_extension_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def normalize_extension_date(value: Optional[str]) -> Optional[str]:
    """Map JobCLI date strings to YYYY-MM / YYYY-MM-DD accepted by TalentScreen v2."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in _PRESENT_DATE_TOKENS:
        return None

    # Already ISO-shaped
    if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", s):
        return s

    # MM/YYYY or M/YYYY
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"

    # YYYY-MM with slash or dot
    m = re.match(r"^(\d{4})[./](\d{1,2})$", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    # Month name + year (e.g. Jan 2020, January 2020)
    m = re.match(
        r"^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"[\s,]+(\d{4})$",
        s,
        re.IGNORECASE,
    )
    if m:
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        key = m.group(1).lower()[:3]
        return f"{m.group(2)}-{months[key]:02d}"

    # Year only
    if re.match(r"^\d{4}$", s):
        return s

    return None


def resume_to_json_resume(
    resume: ResumeData,
    questions: Optional[CommonQuestions] = None,
) -> dict[str, Any]:
    """Convert internal ``ResumeData`` to JSON Resume + ``custom_fields`` for the extension."""
    p = resume.personal
    first = (p.first_name or "").strip()
    last = (p.last_name or "").strip()
    full_name = f"{first} {last}".strip() or first or last or "Applicant"

    country = (p.country or "").strip() or derived_country_for_resume(resume) or ""

    basics: dict[str, Any] = {
        "name": full_name,
        "email": (p.email or "").strip(),
        "phone": (p.phone or "").strip() or None,
        "summary": None,
        "location": {
            "city": p.city,
            "region": p.state,
            "postalCode": p.zip_code,
            "countryCode": country[:2].upper() if len(country) == 2 else country,
        },
        "profiles": [],
    }

    website = (p.website or p.portfolio or "").strip()
    if website and _is_valid_extension_url(website):
        basics["url"] = website

    if p.linkedin:
        url = p.linkedin.strip()
        if not url.startswith("http"):
            url = f"https://{url.lstrip('/')}"
        if _is_valid_extension_url(url):
            basics["profiles"].append({"network": "LinkedIn", "url": url})
    if p.github:
        url = p.github.strip()
        if not url.startswith("http"):
            url = f"https://{url.lstrip('/')}"
        if _is_valid_extension_url(url):
            basics["profiles"].append({"network": "GitHub", "url": url})

    basics["location"] = {k: v for k, v in basics["location"].items() if v}

    work: list[dict[str, Any]] = []
    for exp in resume.experience or []:
        if not exp.company and not exp.title:
            continue
        entry: dict[str, Any] = {
            "name": exp.company or "",
            "position": exp.title or "",
            "summary": exp.description or "",
        }
        start = normalize_extension_date(exp.start_date)
        if start:
            entry["startDate"] = start
        end = None if exp.current else normalize_extension_date(exp.end_date)
        if end:
            entry["endDate"] = end
        work.append(entry)

    education: list[dict[str, Any]] = []
    for edu in resume.education or []:
        if not edu.school and not edu.degree:
            continue
        entry: dict[str, Any] = {
            "institution": edu.school or "",
            "studyType": edu.degree or "",
            "area": edu.field_of_study or "",
        }
        end = normalize_extension_date(
            f"{edu.graduation_year}-12-01" if edu.graduation_year else None
        )
        if end:
            entry["endDate"] = end
        education.append(entry)

    skills_block: list[dict[str, Any]] = []
    flat_skills = [s for s in (resume.skills or []) if s and str(s).strip()]
    if flat_skills:
        skills_block.append({"name": "Skills", "keywords": flat_skills})

    custom_fields = _build_custom_fields(resume, questions)

    profile: dict[str, Any] = {
        "schema_version": "1.0",
        "basics": basics,
        "work": work,
        "education": education,
        "skills": skills_block,
    }
    if custom_fields:
        profile["custom_fields"] = custom_fields

    return profile


def _build_custom_fields(
    resume: ResumeData,
    questions: Optional[CommonQuestions],
) -> dict[str, Any]:
    """Map demographics, work authorization, and common questions to extension custom_fields."""
    custom: dict[str, Any] = {}

    if resume.demographics:
        d = resume.demographics
        eeo: dict[str, Any] = {}
        if d.gender:
            eeo["gender"] = d.gender
        if d.race:
            eeo["ethnicity"] = d.race
        if d.veteran_status:
            eeo["veteran_status"] = d.veteran_status
        if d.disability_status:
            eeo["disability_status"] = d.disability_status
        if d.pronouns:
            eeo["pronouns"] = d.pronouns
        if eeo:
            custom["eeo"] = eeo

    wa = resume.work_authorization
    if wa:
        legal: dict[str, Any] = {}
        if wa.authorized_to_work is not None:
            legal["work_auth_us"] = wa.authorized_to_work
        if wa.require_sponsorship is not None:
            legal["sponsorship_required_now"] = wa.require_sponsorship
        if wa.visa_status:
            legal["visa_status"] = wa.visa_status
        if legal:
            custom["legal"] = legal

    logistics: dict[str, Any] = {}
    screening: dict[str, str] = {}

    if questions:
        if questions.willing_to_relocate is not None:
            logistics["willing_to_relocate"] = "yes" if questions.willing_to_relocate else "no"
        if questions.start_date:
            logistics["preferred_start"] = questions.start_date
        if questions.salary_expectations:
            logistics["salary_expectation"] = questions.salary_expectations
        if questions.notice_period:
            logistics["notice_period"] = questions.notice_period
        if questions.cover_letter:
            screening["cover_letter"] = questions.cover_letter
        if questions.additional_info:
            screening["additional_info"] = questions.additional_info
        if questions.referral:
            screening["referral"] = questions.referral

    if screening:
        logistics["screening_answers"] = screening
    if logistics:
        custom["application_logistics"] = logistics

    return custom
