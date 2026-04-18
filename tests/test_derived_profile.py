"""Tests for deterministic derived profile fields."""

from jobcli.core.derived_profile import (
    derived_pronouns_for_resume,
    infer_country_from_city_state,
    infer_pronouns_from_gender,
)
from jobcli.core.schemas import Demographics, PersonalInfo, ResumeData, WorkAuthorization


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
