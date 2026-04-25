"""Tests for deterministic derived profile fields."""

from jobcli.core.derived_profile import (
    composite_location_string,
    experience_narrative_for_forms,
    derived_pronouns_for_resume,
    infer_country_from_city_state,
    infer_pronouns_from_gender,
)
from jobcli.core.schemas import (
    Demographics,
    Education,
    Experience,
    PersonalInfo,
    ResumeData,
    WorkAuthorization,
)


def test_infer_pronouns_from_gender() -> None:
    assert infer_pronouns_from_gender("Male", None) == "he/him"
    assert infer_pronouns_from_gender("Female", None) == "she/her"
    assert infer_pronouns_from_gender("Male", "they/them") is None


def test_infer_country_us_state() -> None:
    assert infer_country_from_city_state("SF", "CA", None) == "United States"
    assert infer_country_from_city_state("SF", "CA", "Canada") is None


def test_derived_pronouns_on_resume() -> None:
    r = ResumeData(
        personal=PersonalInfo(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone="1",
        ),
        demographics=Demographics(gender="Male"),
        work_authorization=WorkAuthorization(),
    )
    assert derived_pronouns_for_resume(r) == "he/him"


def test_composite_location_string() -> None:
    r = ResumeData(
        personal=PersonalInfo(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone="1",
            city="San Jose",
            state="CA",
            zip_code="95110",
            country="United States",
        ),
        work_authorization=WorkAuthorization(),
    )
    s = composite_location_string(r)
    assert s and "San Jose" in s and "CA" in s and "95110" in s


def test_experience_narrative_uses_json_when_no_description() -> None:
    r = ResumeData(
        personal=PersonalInfo(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone="1",
            city="Hayward",
            state="CA",
        ),
        experience=[
            Experience(
                company="Co",
                title="Engineer",
                start_date="2020-01",
                end_date="2021-01",
            ),
        ],
        education=[
            Education(
                school="State U",
                degree="BS",
                field_of_study="CS",
                graduation_year=2019,
            )
        ],
        work_authorization=WorkAuthorization(),
        skills=["Python", "SQL"],
    )
    t = experience_narrative_for_forms(r, r.experience[0])
    assert "Engineer" in t and "Co" in t
    assert "Python" in t
    assert "State U" in t or "BS" in t


def test_experience_narrative_prefers_explicit_description() -> None:
    r = ResumeData(
        personal=PersonalInfo(
            first_name="A", last_name="B", email="a@b.com", phone="1"
        ),
        experience=[
            Experience(
                company="X",
                title="T",
                start_date="1",
                description="ONLY_THIS_TEXT",
            ),
        ],
        work_authorization=WorkAuthorization(),
    )
    assert experience_narrative_for_forms(r, r.experience[0]) == "ONLY_THIS_TEXT"
