"""Tests for jobcli.sync.extractor — personal-field filtering, confidence gate, dict output."""

import pytest

from jobcli.core.schemas import ATSType, SelectorType
from jobcli.storage.models import Database, FieldAnswerModel, LearnedLocatorModel
from jobcli.sync.constants import CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT
from jobcli.sync.extractor import extract_field_answers, extract_locators


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    d = Database("sqlite:///:memory:")
    d.create_tables()
    return d


@pytest.fixture
def session(db):
    s = db.get_session()
    yield s
    s.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _insert_field_answer(
    session,
    normalized_label: str,
    field_label: str,
    value: str,
    ats_type=ATSType.GREENHOUSE,
    success_count: int = 5,
    failure_count: int = 0,
    source: str = "auto",
):
    confidence = success_count / (success_count + failure_count) if (success_count + failure_count) > 0 else 0.0
    row = FieldAnswerModel(
        field_label=field_label,
        normalized_label=normalized_label,
        value=value,
        ats_type=ats_type,
        success_count=success_count,
        failure_count=failure_count,
        confidence=confidence,
        source=source,
    )
    session.add(row)
    session.commit()
    return row


def _insert_locator(
    session,
    selector: str,
    purpose: str,
    ats_type=ATSType.GREENHOUSE,
    success_count: int = 5,
    failure_count: int = 0,
):
    confidence = success_count / (success_count + failure_count) if (success_count + failure_count) > 0 else 0.0
    row = LearnedLocatorModel(
        ats_type=ats_type,
        selector=selector,
        selector_type=SelectorType.CSS,
        purpose=purpose,
        success_count=success_count,
        failure_count=failure_count,
        confidence_score=confidence,
        created_by="auto",
    )
    session.add(row)
    session.commit()
    return row


# ── extract_field_answers ─────────────────────────────────────────────────────

class TestExtractFieldAnswers:
    def test_returns_list_of_dicts(self, session):
        """Output is a list of plain dicts (not ORM objects)."""
        _insert_field_answer(session, "remote_work", "Remote Work", "Yes")
        result = extract_field_answers(session)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_returns_correct_keys(self, session):
        """Every dict has the expected keys."""
        _insert_field_answer(session, "sponsorship", "Sponsorship", "No")
        result = extract_field_answers(session)
        expected_keys = {
            "normalized_label", "field_label", "value", "ats_type",
            "field_type", "success_count", "failure_count", "confidence", "source",
        }
        for item in result:
            assert expected_keys == set(item.keys())

    def test_respects_min_confidence(self, session):
        """Records below the threshold are excluded."""
        # Below threshold: 1/5 = 0.2
        _insert_field_answer(session, "notice_period", "Notice Period", "2 weeks",
                              success_count=1, failure_count=4)
        result = extract_field_answers(session)
        labels = [r["normalized_label"] for r in result]
        assert "notice_period" not in labels

    def test_respects_min_success_count(self, session):
        """Records with fewer than MIN_SUCCESS_COUNT successes are excluded."""
        # Confidence is fine (1.0) but only 2 successes
        _insert_field_answer(session, "bonus", "Bonus", "Yes",
                              success_count=2, failure_count=0)
        result = extract_field_answers(session)
        labels = [r["normalized_label"] for r in result]
        assert "bonus" not in labels

    def test_includes_qualifying_records(self, session):
        """High-confidence, non-personal records are included."""
        _insert_field_answer(session, "remote_work", "Remote Work", "Yes",
                              success_count=5, failure_count=0)
        result = extract_field_answers(session)
        labels = [r["normalized_label"] for r in result]
        assert "remote_work" in labels

    # ── Personal field filtering ──────────────────────────────────────────────

    def test_skips_email(self, session):
        _insert_field_answer(session, "email", "Email", "test@example.com")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "email" for r in result)

    def test_skips_phone(self, session):
        _insert_field_answer(session, "phone", "Phone", "+1-555-0100")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "phone" for r in result)

    def test_skips_first_name(self, session):
        _insert_field_answer(session, "first name", "First Name", "Alice")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "first name" for r in result)

    def test_skips_last_name(self, session):
        _insert_field_answer(session, "last name", "Last Name", "Smith")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "last name" for r in result)

    def test_skips_linkedin(self, session):
        _insert_field_answer(session, "linkedin", "LinkedIn", "https://linkedin.com/in/alice")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "linkedin" for r in result)

    def test_skips_github(self, session):
        _insert_field_answer(session, "github", "GitHub", "https://github.com/alice")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "github" for r in result)

    def test_skips_address(self, session):
        _insert_field_answer(session, "address", "Address", "123 Main St")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "address" for r in result)

    def test_skips_salary(self, session):
        _insert_field_answer(session, "salary", "Salary", "100000")
        result = extract_field_answers(session)
        assert all(r["normalized_label"] != "salary" for r in result)

    def test_skips_partial_personal_match(self, session):
        """Labels that contain a PERSONAL_FIELDS entry are also excluded."""
        _insert_field_answer(session, "current salary expectation",
                             "Current Salary Expectation", "90000")
        result = extract_field_answers(session)
        labels = [r["normalized_label"] for r in result]
        assert "current salary expectation" not in labels

    def test_non_personal_included_alongside_personal(self, session):
        """Personal fields are stripped; non-personal survive alongside them."""
        _insert_field_answer(session, "email", "Email", "a@b.com")
        _insert_field_answer(session, "remote_ok", "Remote OK", "Yes")
        result = extract_field_answers(session)
        labels = {r["normalized_label"] for r in result}
        assert "email" not in labels
        assert "remote_ok" in labels

    def test_empty_db_returns_empty_list(self, session):
        assert extract_field_answers(session) == []

    def test_ats_type_serialised_as_string(self, session):
        """ats_type is returned as a string value, not an Enum."""
        _insert_field_answer(session, "remote_work", "Remote", "Yes",
                              ats_type=ATSType.GREENHOUSE)
        result = extract_field_answers(session)
        for item in result:
            assert isinstance(item["ats_type"], str)

    def test_custom_min_confidence_override(self, session):
        """Callers can lower the threshold."""
        # Confidence = 0.4, normally excluded
        _insert_field_answer(session, "bonus", "Bonus", "10%",
                              success_count=4, failure_count=6)
        # With default threshold (0.6): excluded
        assert extract_field_answers(session) == []
        # With threshold=0.3: included (success_count=4 >= MIN_SUCCESS_COUNT=3)
        result = extract_field_answers(session, min_confidence=0.3)
        labels = [r["normalized_label"] for r in result]
        assert "bonus" in labels


# ── extract_locators ──────────────────────────────────────────────────────────

class TestExtractLocators:
    def test_returns_list_of_dicts(self, session):
        _insert_locator(session, "#apply", "apply_button")
        result = extract_locators(session)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_returns_correct_keys(self, session):
        _insert_locator(session, "#apply", "apply_button")
        result = extract_locators(session)
        expected = {
            "ats_type", "selector", "selector_type", "purpose",
            "success_count", "failure_count", "confidence_score",
            "domain_pattern", "url_pattern", "created_by",
        }
        for item in result:
            assert expected == set(item.keys())

    def test_excludes_low_confidence_locators(self, session):
        _insert_locator(session, "#bad", "bad_button", success_count=1, failure_count=4)
        result = extract_locators(session)
        assert all(r["selector"] != "#bad" for r in result)

    def test_excludes_low_success_count(self, session):
        _insert_locator(session, "#new", "new_button", success_count=2, failure_count=0)
        result = extract_locators(session)
        assert all(r["selector"] != "#new" for r in result)

    def test_includes_qualifying_locators(self, session):
        _insert_locator(session, "#submit", "submit_form", success_count=5, failure_count=1)
        result = extract_locators(session)
        selectors = [r["selector"] for r in result]
        assert "#submit" in selectors

    def test_ats_type_serialised_as_string(self, session):
        _insert_locator(session, "#btn", "apply_button", ats_type=ATSType.WORKDAY)
        result = extract_locators(session)
        for item in result:
            assert isinstance(item["ats_type"], str)

    def test_empty_db_returns_empty_list(self, session):
        assert extract_locators(session) == []

    def test_custom_threshold(self, session):
        # 0.5 confidence, normally excluded
        _insert_locator(session, "#maybe", "maybe_button", success_count=3, failure_count=3)
        assert extract_locators(session) == []
        result = extract_locators(session, min_confidence=0.4)
        selectors = [r["selector"] for r in result]
        assert "#maybe" in selectors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
