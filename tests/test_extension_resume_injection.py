"""Tests for extension JSON Resume + PDF payload loading and injection."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from jobcli.profile.schemas import PersonalInfo, ResumeData
from jobcli.storage.models import Database
from jobcli.storage.repositories import UserDataRepository
from jobcli.utils.extension_resume import (
    ExtensionResumeError,
    build_resume_file_blob,
    get_json_resume_for_extension,
    is_valid_json_resume_shape,
    load_extension_payloads,
)


@pytest.fixture
def test_database():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


SAMPLE_JSON_RESUME = {
    "basics": {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "(555) 123-4567",
    },
    "work": [{"name": "Acme", "position": "Engineer", "startDate": "2020-01-01"}],
    "education": [
        {
            "institution": "State U",
            "area": "CS",
            "Discipline": "BS",
        }
    ],
    "skills": [{"name": "Lang", "keywords": ["Python"]}],
}


def test_is_valid_json_resume_shape():
    assert is_valid_json_resume_shape(SAMPLE_JSON_RESUME) is True
    assert is_valid_json_resume_shape({"personal": {"first_name": "x"}}) is True
    assert is_valid_json_resume_shape({}) is False


def test_build_resume_file_blob(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    blob = build_resume_file_blob(pdf)
    assert blob["name"] == "resume.pdf"
    assert blob["type"] == "application/pdf"
    assert blob["size"] == len(pdf.read_bytes())
    assert blob["data"].startswith("data:application/pdf;base64,")


def test_get_json_resume_for_extension_missing(test_database):
    session = test_database.get_session()
    try:
        with pytest.raises(ExtensionResumeError, match="No JSON Resume stored"):
            get_json_resume_for_extension(session)
    finally:
        session.close()


def test_load_extension_payloads(test_database, tmp_path):
    session = test_database.get_session()
    pdf = tmp_path / "tiny.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    try:
        repo = UserDataRepository(session)
        resume = ResumeData(
            personal=PersonalInfo(first_name="J", last_name="D", email="j@d.com")
        )
        blob = build_resume_file_blob(pdf)
        repo.save_resume_upload_bundle(resume, SAMPLE_JSON_RESUME, blob)
        data, file_blob = load_extension_payloads(session)
        assert data["basics"]["email"] == "john.doe@example.com"
        assert file_blob is not None
        assert file_blob["name"] == "tiny.pdf"
    finally:
        session.close()


def test_inject_js_uses_resume_processor():
    """Engine injection must call ResumeProcessor.normalize, not model_dump."""
    import inspect

    from jobcli.orchestration.engine import ApplicationEngine

    src = inspect.getsource(ApplicationEngine._inject_resume_into_extension)
    assert "ResumeProcessor.normalize" in src
    assert "resumeData" in src
    assert "model_dump" not in src


def test_send_fill_uses_normalized_and_pdf():
    import inspect

    from jobcli.orchestration.engine import ApplicationEngine

    src = inspect.getsource(ApplicationEngine._send_extension_fill_message)
    assert "normalizedData" in src
    assert "resumeFile" in src
    assert "null" not in src or "resumeFile || null" in src
