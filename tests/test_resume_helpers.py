"""Tests for resume profile summary helpers."""

from pathlib import Path

import pytest

from jobcli.profile.schemas import Experience, PersonalInfo, ResumeData, WorkAuthorization
from jobcli.utils.resume_helpers import (
    build_profile_summary_lines,
    estimate_experience_years,
    format_visa_label,
    load_resume_from_paths,
)


def _sample_resume() -> ResumeData:
    return ResumeData(
        personal=PersonalInfo(
            first_name="Rajesh",
            last_name="Kosuri",
            email="xyz@gmail.com",
        ),
        experience=[
            Experience(
                company="Acme",
                title="Engineer",
                start_date="2020-01-01",
                end_date="2025-01-01",
            )
        ],
        skills=["Python", "ML", "GenAI"],
        work_authorization=WorkAuthorization(visa_status="H1B"),
    )


def test_build_profile_summary_lines(tmp_path):
    pdf = tmp_path / "rajesh_resume.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    lines = build_profile_summary_lines(_sample_resume(), pdf)
    text = "\n".join(lines)
    assert "Rajesh Kosuri" in text
    assert "xyz@gmail.com" in text
    assert "rajesh_resume.pdf" in text
    assert "Python" in text
    assert "H1B" in text


def test_estimate_experience_years_from_dates():
    resume = _sample_resume()
    assert "year" in estimate_experience_years(resume.experience).lower()


def test_format_visa_fallback():
    assert format_visa_label(WorkAuthorization()) == "Not listed"
    assert format_visa_label(WorkAuthorization(require_sponsorship=True)) == "Requires sponsorship"


def test_load_resume_from_paths(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    json_path = tmp_path / "resume.json"
    json_path.write_text(
        """{
          "personal": {
            "first_name": "Harishwar",
            "last_name": "Patlolla",
            "email": "harish@test.com"
          },
          "experience": [],
          "education": [],
          "skills": ["Python"]
        }""",
        encoding="utf-8",
    )
    resume, pdf_out, json_out = load_resume_from_paths(str(pdf), str(json_path))
    assert resume.personal.first_name == "Harishwar"
    assert pdf_out == pdf.resolve()
    assert json_out == json_path.resolve()


def test_load_resume_missing_pdf(tmp_path):
    with pytest.raises(ValueError, match="PDF file not found"):
        load_resume_from_paths(str(tmp_path / "nope.pdf"), str(tmp_path / "nope.json"))


def test_load_resume_json_resume_empty_gpa(tmp_path):
    """JSON Resume exports often use \"\" for missing GPA — must not block upload."""
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    json_path = tmp_path / "resume.json"
    json_path.write_text(
        """{
          "basics": {
            "name": "Harishwar Patlolla",
            "email": "harish@test.com",
            "phone": "512-000-0000"
          },
          "education": [
            {
              "institution": "University of Houston",
              "studyType": "M.S.",
              "endDate": "2018",
              "gpa": ""
            },
            {
              "institution": "IIT Roorkee",
              "studyType": "B.Tech",
              "endDate": "2014",
              "score": "",
              "gpa": "3.7/4.0"
            }
          ],
          "work": [],
          "skills": []
        }""",
        encoding="utf-8",
    )
    resume, _, _ = load_resume_from_paths(str(pdf), str(json_path))
    assert resume.personal.first_name == "Harishwar"
    assert len(resume.education) == 2
    assert resume.education[0].gpa is None
    assert resume.education[1].gpa == 3.7


def test_coerce_gpa_value():
    from jobcli.profile.schemas import coerce_gpa_value

    assert coerce_gpa_value("") is None
    assert coerce_gpa_value("3.85/4.0") == 3.85
    assert coerce_gpa_value(3.9) == 3.9
    assert coerce_gpa_value("N/A") is None
