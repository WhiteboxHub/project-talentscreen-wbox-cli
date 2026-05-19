"""Tests for JSON Resume export used by TalentScreen v2 bridge."""

from jobcli.profile.resume_export import normalize_extension_date, resume_to_json_resume
from jobcli.profile.schemas import Education, Experience, PersonalInfo, ResumeData


def test_resume_to_json_resume_basics_and_work():
    resume = ResumeData(
        personal=PersonalInfo(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="+1-555-0100",
            city="San Francisco",
            state="CA",
            country="US",
        ),
        experience=[
            Experience(
                company="Acme Corp",
                title="Engineer",
                start_date="2020-01",
                end_date="present",
                current=True,
                description="Built things",
            )
        ],
        education=[
            Education(
                school="State U",
                degree="BS",
                field_of_study="CS",
                graduation_year=2019,
            )
        ],
        skills=["Python", "JavaScript"],
    )

    profile = resume_to_json_resume(resume)

    assert profile["basics"]["name"] == "Jane Doe"
    assert profile["basics"]["email"] == "jane@example.com"
    assert len(profile["work"]) == 1
    assert profile["work"][0]["name"] == "Acme Corp"
    assert "endDate" not in profile["work"][0]
    assert profile["work"][0]["startDate"] == "2020-01"
    assert len(profile["education"]) == 1
    assert profile["skills"][0]["keywords"] == ["Python", "JavaScript"]
    assert profile["schema_version"] == "1.0"


def test_normalize_extension_date_present_and_slash_formats():
    assert normalize_extension_date("present") is None
    assert normalize_extension_date("01/2020") == "2020-01"
    assert normalize_extension_date("Jan 2020") == "2020-01"
    assert normalize_extension_date("2020-03-15") == "2020-03-15"


def test_invalid_url_omitted_from_basics():
    resume = ResumeData(
        personal=PersonalInfo(
            first_name="A",
            last_name="B",
            email="a@b.com",
            website="not a valid url",
        ),
    )
    profile = resume_to_json_resume(resume)
    assert "url" not in profile["basics"]
