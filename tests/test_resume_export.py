"""Tests for JSON Resume export used by TalentScreen v2 bridge."""

from jobcli.profile.resume_export import resume_to_json_resume
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
    assert len(profile["education"]) == 1
    assert profile["skills"][0]["keywords"] == ["Python", "JavaScript"]
    assert profile["schema_version"] == "1.0"
