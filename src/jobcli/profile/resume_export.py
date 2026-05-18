"""Export JobCLI ``ResumeData`` to JSON Resume format for TalentScreen v2."""

from __future__ import annotations

from typing import Any, Optional

from jobcli.profile.derived_profile import derived_country_for_resume
from jobcli.profile.schemas import CommonQuestions, ResumeData


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
        "url": p.website or p.portfolio,
        "summary": None,
        "location": {
            "city": p.city,
            "region": p.state,
            "postalCode": p.zip_code,
            "countryCode": country[:2].upper() if len(country) == 2 else country,
        },
        "profiles": [],
    }

    if p.linkedin:
        basics["profiles"].append({"network": "LinkedIn", "url": p.linkedin})
    if p.github:
        basics["profiles"].append({"network": "GitHub", "url": p.github})

    basics["location"] = {k: v for k, v in basics["location"].items() if v}

    work: list[dict[str, Any]] = []
    for exp in resume.experience or []:
        if not exp.company and not exp.title:
            continue
        end = exp.end_date
        if exp.current and not end:
            end = None
        work.append(
            {
                "name": exp.company or "",
                "position": exp.title or "",
                "startDate": exp.start_date or "",
                "endDate": end,
                "summary": exp.description or "",
            }
        )

    education: list[dict[str, Any]] = []
    for edu in resume.education or []:
        if not edu.school and not edu.degree:
            continue
        end_date = ""
        if edu.graduation_year:
            end_date = f"{edu.graduation_year}-12-01"
        education.append(
            {
                "institution": edu.school or "",
                "studyType": edu.degree or "",
                "area": edu.field_of_study or "",
                "endDate": end_date or None,
            }
        )

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
