"""Resume path validation, profile summary, and persistence helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from jobcli.profile.schemas import ResumeData, WorkAuthorization


def clean_path_input(raw: Optional[str]) -> Optional[str]:
    """Strip whitespace and surrounding quotes from a pasted path."""
    if raw is None:
        return None
    s = raw.strip()
    for quote in ('"', "'"):
        if len(s) >= 2 and s.startswith(quote) and s.endswith(quote):
            s = s[1:-1].strip()
            break
    return s or None


def resolve_resume_paths(pdf: str, json_file: str) -> tuple[Path, Path]:
    """Resolve and verify PDF + JSON paths exist."""
    pdf_clean = clean_path_input(pdf) or ""
    json_clean = clean_path_input(json_file) or ""
    if not pdf_clean:
        raise ValueError("PDF path is required.")
    if not json_clean:
        raise ValueError("JSON path is required.")

    pdf_path = Path(pdf_clean).expanduser().resolve()
    json_path = Path(json_clean).expanduser().resolve()

    if not pdf_path.is_file():
        raise ValueError(f"PDF file not found: {pdf_path}")
    if not json_path.is_file():
        raise ValueError(f"JSON file not found: {json_path}")

    return pdf_path, json_path


def load_resume_from_paths(pdf: str, json_file: str) -> tuple[ResumeData, Path, Path]:
    """Validate paths, parse JSON, normalize, and return a ``ResumeData`` model."""
    pdf_path, json_path = resolve_resume_paths(pdf, json_file)

    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    from jobcli.intelligence.synonym_resolver import ResumeAutoDetector

    normalized = ResumeAutoDetector.detect_and_convert(raw)
    resume = ResumeData(**normalized)
    return resume, pdf_path, json_path


def estimate_experience_years(experience: list) -> str:
    """Rough total years from experience date ranges, else role count."""
    if not experience:
        return "Not listed"

    earliest: Optional[datetime] = None
    latest: Optional[datetime] = None
    now = datetime.now()

    for exp in experience:
        start = _parse_date(exp.start_date if hasattr(exp, "start_date") else None)
        if getattr(exp, "current", False):
            end = now
        else:
            end = _parse_date(exp.end_date if hasattr(exp, "end_date") else None) or now

        if start:
            earliest = min(earliest, start) if earliest else start
        if end:
            latest = max(latest, end) if latest else end

    if earliest and latest and latest >= earliest:
        years = max(1, int((latest - earliest).days / 365.25))
        return f"{years} years"

    n = len(experience)
    return f"{n} role{'s' if n != 1 else ''}"


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    for fmt, size in (("%Y-%m-%d", 10), ("%Y-%m", 7), ("%Y", 4)):
        try:
            return datetime.strptime(s[:size], fmt)
        except ValueError:
            continue
    match = re.search(r"(20\d{2}|19\d{2})", s)
    if match:
        return datetime(int(match.group(1)), 1, 1)
    return None


def format_visa_label(work_auth: WorkAuthorization) -> str:
    if work_auth.visa_status:
        return work_auth.visa_status
    if work_auth.require_sponsorship:
        return "Requires sponsorship"
    if work_auth.authorized_to_work is False:
        return "Not authorized (per resume JSON)"
    return "Not listed"


def format_skills(skills: list[str], limit: int = 12) -> str:
    if not skills:
        return "Not listed"
    shown = skills[:limit]
    text = ", ".join(shown)
    if len(skills) > limit:
        text += f", +{len(skills) - limit} more"
    return text


def build_profile_summary_lines(resume: ResumeData, pdf_path: Path) -> list[str]:
    """Lines for the onboarding profile confirmation block."""
    first = (resume.personal.first_name or "").strip()
    last = (resume.personal.last_name or "").strip()
    name = f"{first} {last}".strip() or "Not listed"
    email = resume.personal.email or "Not listed"

    return [
        "Profile Summary",
        "-----------------------",
        f"Name: {name}",
        f"Email: {email}",
        f"Resume: {pdf_path.name}",
        f"Skills: {format_skills(resume.skills)}",
        f"Experience: {estimate_experience_years(resume.experience)}",
        f"Visa: {format_visa_label(resume.work_authorization)}",
        f"Education entries: {len(resume.education)}",
        f"Work history entries: {len(resume.experience)}",
    ]


def print_profile_summary(
    console: Console,
    resume: ResumeData,
    pdf_path: Path,
) -> None:
    """Show validation checkmarks and the profile summary block."""
    console.print("[green]✓ Resume JSON validated[/green]")
    first = (resume.personal.first_name or "").strip()
    last = (resume.personal.last_name or "").strip()
    full_name = f"{first} {last}".strip() or "(not listed)"
    console.print(f"  Name: {full_name}")
    console.print(f"  Email: {resume.personal.email or 'Not listed'}")
    console.print(f"  Experience entries: {len(resume.experience)}")
    console.print(f"  Education entries: {len(resume.education)}")
    console.print()
    for line in build_profile_summary_lines(resume, pdf_path):
        console.print(line)
    console.print()


def persist_resume(
    resume: ResumeData,
    pdf_path: Path,
    json_path: Path,
) -> None:
    """Save resume + file paths to the local database and config."""
    from jobcli.cli.main import get_config, get_database, save_config
    from jobcli.storage.repositories import UserDataRepository

    db = get_database()
    session = db.get_session()
    try:
        UserDataRepository(session).save_resume(resume)
        session.commit()
    finally:
        session.close()

    config = get_config()
    config.resume_pdf_path = str(pdf_path)
    config.resume_json_path = str(json_path)
    save_config(config)


def confirm_profile_prompt() -> bool:
    """Return True if the user confirms the profile summary."""
    while True:
        answer = input("Confirm? (Y/N): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
