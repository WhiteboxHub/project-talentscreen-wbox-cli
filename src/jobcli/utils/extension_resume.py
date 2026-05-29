"""Load JSON Resume + PDF blobs for TalentScreen extension injection."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from jobcli.storage.repositories import UserDataRepository

# Match side panel max (see extension sidepanel.js)
MAX_RESUME_PDF_BYTES = 10 * 1024 * 1024


class ExtensionResumeError(Exception):
    """Extension payload missing or invalid."""


def is_valid_json_resume_shape(data: dict) -> bool:
    """Return True if *data* looks like JSON Resume or extension-accepted input."""
    if not isinstance(data, dict) or not data:
        return False
    if "basics" in data:
        return True
    for key in ("personal", "contact", "contact_info", "work", "experience", "education"):
        if key in data:
            return True
    return False


def build_resume_file_blob(pdf_path: Path) -> dict[str, Any]:
    """Build extension ``resumeFile`` object from a PDF on disk."""
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    raw = pdf_path.read_bytes()
    if len(raw) > MAX_RESUME_PDF_BYTES:
        raise ValueError(
            f"Resume PDF exceeds {MAX_RESUME_PDF_BYTES // (1024 * 1024)}MB limit: {pdf_path}"
        )

    b64 = base64.b64encode(raw).decode("ascii")
    return {
        "data": f"data:application/pdf;base64,{b64}",
        "name": pdf_path.name,
        "type": "application/pdf",
        "size": len(raw),
    }


def get_json_resume_for_extension(session: Session) -> dict[str, Any]:
    """Load stored JSON Resume; raise if missing or invalid."""
    raw = UserDataRepository(session).get_resume_json()
    if not raw:
        raise ExtensionResumeError(
            "No JSON Resume stored for the extension. Re-run: "
            "wboxcli resume-upload --pdf <file.pdf> --json <file.json>"
        )
    if not is_valid_json_resume_shape(raw):
        raise ExtensionResumeError(
            "Stored resume JSON is not a valid JSON Resume shape "
            "(expected top-level 'basics' or work/education sections)."
        )
    return raw


def get_resume_file_for_extension(session: Session) -> Optional[dict[str, Any]]:
    """Load stored PDF blob for extension file upload, or None."""
    blob = UserDataRepository(session).get_resume_pdf()
    if not blob:
        return None
    if not isinstance(blob.get("data"), str) or not blob.get("name"):
        return None
    return blob


def load_extension_payloads(
    session: Session,
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Return ``(resumeData, resumeFile)`` for extension storage / fill_form."""
    resume_data = get_json_resume_for_extension(session)
    resume_file = get_resume_file_for_extension(session)
    return resume_data, resume_file
