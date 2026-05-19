"""Comprehensive tests for the confidence-gated memory system.

Tests cover:
- Confidence gate enforcement (≥ 0.6 confidence AND ≥ 3 successes)
- Merge protection (human answers never overwritten by auto-learned)
- PII filtering (never exported to sync)
- Race condition prevention (UNIQUE constraint + row locking)
- Confidence calculation accuracy
"""

import pytest
from sqlalchemy.orm import Session

from jobcli.core.memory import AgentMemory
from jobcli.core.schemas import ATSType, ResumeData, PersonalInfo
from jobcli.storage.models import Database, FieldAnswerModel
from jobcli.storage.repositories import FieldAnswerRepository
from jobcli.sync.constants import CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT, PERSONAL_FIELDS
from jobcli.sync.extractor import extract_field_answers


@pytest.fixture
def db():
    """Create in-memory test database."""
    database = Database("sqlite:///:memory:")
    database.create_tables()
    yield database
    database.drop_tables()


@pytest.fixture
def session(db):
    """Get database session."""
    sess = db.get_session()
    yield sess
    sess.close()


@pytest.fixture
def memory(session):
    """Create AgentMemory instance."""
    return AgentMemory(session, job_id=1)


@pytest.fixture
def resume():
    """Create test resume."""
    return ResumeData(
        personal=PersonalInfo(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="+1-555-0100",
            city="San Francisco",
            state="CA",
            country="United States",
        )
    )


class TestConfidenceGate:
    """Test confidence threshold enforcement."""

    def test_low_confidence_not_returned(self, session):
        """Records below confidence threshold should not be returned."""
        repo = FieldAnswerRepository(session)

        # Create record with low confidence (2 success, 3 failure = 40%)
        repo.save_answer(
            field_label="Years of Experience",
            normalized_label="years_of_experience",
            value="5",
            ats_type=ATSType.GREENHOUSE,
            success=True,
            source="auto",
        )
        # Add failures to drop confidence below 60%
        repo.record_outcome("years_of_experience", ATSType.GREENHOUSE, success=False)
        repo.record_outcome("years_of_experience", ATSType.GREENHOUSE, success=False)
        repo.record_outcome("years_of_experience", ATSType.GREENHOUSE, success=False)

        # Should NOT be returned by confidence-gated query
        result = repo.get_by_normalized_label("years_of_experience", ATSType.GREENHOUSE)
        assert result is None, "Low-confidence record should not pass gate"

    def test_insufficient_success_count(self, session):
        """Records below MIN_SUCCESS_COUNT should not be returned."""
        repo = FieldAnswerRepository(session)

        # Create record with 100% confidence but only 2 successes
        repo.save_answer(
            field_label="Desired Salary",
            normalized_label="desired_salary",
            value="120000",
            ats_type=ATSType.LEVER,
            success=True,
            source="auto",
        )
        repo.record_outcome("desired_salary", ATSType.LEVER, success=True)

        # Should NOT be returned (needs ≥ 3 successes)
        result = repo.get_by_normalized_label("desired_salary", ATSType.LEVER)
        assert result is None, "Record with <3 successes should not pass gate"

    def test_high_confidence_passes_gate(self, session):
        """Records meeting both gates should be returned."""
        repo = FieldAnswerRepository(session)

        # Create record with high confidence (4 success, 1 failure = 80%)
        repo.save_answer(
            field_label="Years of Experience",
            normalized_label="years_of_experience",
            value="5",
            ats_type=ATSType.GREENHOUSE,
            success=True,
            source="auto",
        )
        # Add more successes to meet threshold
        for _ in range(3):
            repo.record_outcome("years_of_experience", ATSType.GREENHOUSE, success=True)

        # Add one failure (still above 60%)
        repo.record_outcome("years_of_experience", ATSType.GREENHOUSE, success=False)

        # Should be returned
        result = repo.get_by_normalized_label("years_of_experience", ATSType.GREENHOUSE)
        assert result is not None, "High-confidence record should pass gate"
        assert result.value == "5"
        assert result.confidence >= CONFIDENCE_THRESHOLD
        assert result.success_count >= MIN_SUCCESS_COUNT


class TestMergeProtection:
    """Test merge protection rules (human answers preserved)."""

    def test_human_answer_not_overwritten_by_auto(self, session):
        """Auto-learned answers cannot overwrite human input."""
        repo = FieldAnswerRepository(session)

        # Human enters "Yes, I am authorized"
        repo.save_answer(
            field_label="Work Authorization",
            normalized_label="work_authorization",
            value="Yes, I am authorized",
            ats_type=ATSType.ASHBY,
            success=True,
            source="human",
        )

        # LLM later tries to overwrite with "Yes"
        repo.save_answer(
            field_label="Work Authorization",
            normalized_label="work_authorization",
            value="Yes",
            ats_type=ATSType.ASHBY,
            success=True,
            source="auto",
        )

        # Original human value should be preserved
        result = repo.get_by_normalized_label("work_authorization", ATSType.ASHBY)
        assert result is not None
        assert result.value == "Yes, I am authorized", "Human answer was corrupted!"
        assert result.source == "human"

    def test_user_answer_overwrites_auto(self, session):
        """User answers (high trust) can overwrite auto-learned (low trust)."""
        repo = FieldAnswerRepository(session)

        # Auto-learned value
        repo.save_answer(
            field_label="Sponsorship Required",
            normalized_label="sponsorship_required",
            value="No",
            ats_type=ATSType.WORKDAY,
            success=True,
            source="auto",
        )

        # User corrects it
        repo.save_answer(
            field_label="Sponsorship Required",
            normalized_label="sponsorship_required",
            value="Yes, I need sponsorship",
            ats_type=ATSType.WORKDAY,
            success=True,
            source="user",
        )

        # User's correction should win
        result = repo.get_by_normalized_label("sponsorship_required", ATSType.WORKDAY)
        assert result is not None
        assert result.value == "Yes, I need sponsorship"
        assert result.source == "user"

    def test_human_seeded_above_threshold(self, session):
        """Human answers start with MIN_SUCCESS_COUNT (immediately usable)."""
        repo = FieldAnswerRepository(session)

        # Human enters answer (first time)
        repo.save_answer(
            field_label="Gender",
            normalized_label="gender",
            value="Female",
            ats_type=ATSType.LEVER,
            success=True,
            source="human",
        )

        # Should immediately pass confidence gate
        result = repo.get_by_normalized_label("gender", ATSType.LEVER)
        assert result is not None, "Human answer should be immediately available"
        assert result.success_count >= MIN_SUCCESS_COUNT
        assert result.confidence >= CONFIDENCE_THRESHOLD


class TestPIIFiltering:
    """Test PII never exported to sync."""

    def test_pii_fields_filtered_from_export(self, session):
        """Personal fields should never appear in sync export."""
        repo = FieldAnswerRepository(session)

        # Save both PII and non-PII fields with high confidence
        pii_fields = ["email", "phone", "ssn", "salary"]
        safe_fields = ["years_of_experience", "preferred_work_location"]

        for field in pii_fields + safe_fields:
            # Give all fields high confidence
            repo.save_answer(
                field_label=field.replace("_", " ").title(),
                normalized_label=field,
                value="test_value",
                ats_type=ATSType.GREENHOUSE,
                success=True,
                source="human",  # High trust
            )
            # Add successes to meet threshold
            for _ in range(3):
                repo.record_outcome(field, ATSType.GREENHOUSE, success=True)

        # Extract for sync
        exported = extract_field_answers(session)

        # Check PII is filtered out
        exported_labels = {item["normalized_label"] for item in exported}
        for pii_field in pii_fields:
            assert pii_field not in exported_labels, f"PII field '{pii_field}' was exported!"

        # Check safe fields are included
        for safe_field in safe_fields:
            assert safe_field in exported_labels, f"Safe field '{safe_field}' was filtered!"

    def test_pii_substring_match(self, session):
        """Fields containing PII keywords should be filtered."""
        repo = FieldAnswerRepository(session)

        # Fields with PII keywords in them
        tricky_fields = [
            ("current_salary_expectation", "current salary expectation"),
            ("home_address_line_1", "home address line 1"),
            ("emergency_contact_phone", "emergency contact phone"),
        ]

        for normalized, display in tricky_fields:
            repo.save_answer(
                field_label=display,
                normalized_label=normalized,
                value="test",
                ats_type=ATSType.LEVER,
                success=True,
                source="human",
            )
            for _ in range(3):
                repo.record_outcome(normalized, ATSType.LEVER, success=True)

        exported = extract_field_answers(session)
        exported_labels = {item["normalized_label"] for item in exported}

        for normalized, _ in tricky_fields:
            assert normalized not in exported_labels, f"PII substring '{normalized}' leaked!"


class TestRaceConditionPrevention:
    """Test UNIQUE constraint prevents concurrent writes."""

    def test_unique_constraint_enforced(self, session):
        """Duplicate (normalized_label, ats_type) should be blocked."""
        from sqlalchemy.exc import IntegrityError

        # Insert first record directly (bypassing repository logic)
        record1 = FieldAnswerModel(
            field_label="Years Experience",
            normalized_label="years_experience",
            value="5",
            ats_type=ATSType.GREENHOUSE,
            success_count=3,
            failure_count=0,
            confidence=1.0,
            source="human",
        )
        session.add(record1)
        session.commit()

        # Try to insert duplicate
        record2 = FieldAnswerModel(
            field_label="Years of Experience",
            normalized_label="years_experience",  # Same normalized label
            value="10",
            ats_type=ATSType.GREENHOUSE,  # Same ATS
            success_count=1,
            failure_count=0,
            confidence=1.0,
            source="auto",
        )
        session.add(record2)

        # Should raise IntegrityError due to UNIQUE constraint
        with pytest.raises(IntegrityError):
            session.commit()

    def test_row_locking_prevents_race(self, session):
        """Row-level locking prevents concurrent confidence corruption."""
        repo = FieldAnswerRepository(session)

        # Save initial answer
        repo.save_answer(
            field_label="Disability Status",
            normalized_label="disability_status",
            value="No disability",
            ats_type=ATSType.ASHBY,
            success=True,
            source="human",
        )

        # Simulate two concurrent updates (sequential in test, but uses same locking)
        repo.record_outcome("disability_status", ATSType.ASHBY, success=True)
        repo.record_outcome("disability_status", ATSType.ASHBY, success=True)

        # Check confidence calculated correctly (no corruption)
        result = repo.get_raw_by_label("disability_status", ATSType.ASHBY)
        assert result is not None
        # Should be (3+2) successes, 0 failures = 1.0 confidence
        # (3 from human seed + 2 from record_outcome)
        expected_success = MIN_SUCCESS_COUNT + 2
        assert result.success_count == expected_success
        assert result.confidence == 1.0


class TestConfidenceCalculation:
    """Test Bayesian confidence math."""

    def test_confidence_formula(self, session):
        """Confidence = success_count / (success_count + failure_count)."""
        repo = FieldAnswerRepository(session)

        repo.save_answer(
            field_label="Test Field",
            normalized_label="test_field",
            value="test",
            ats_type=ATSType.GREENHOUSE,
            success=True,
            source="auto",
        )

        # Add outcomes: 6 success, 4 failure = 6/10 = 0.6 (exactly at threshold)
        for _ in range(5):
            repo.record_outcome("test_field", ATSType.GREENHOUSE, success=True)
        for _ in range(4):
            repo.record_outcome("test_field", ATSType.GREENHOUSE, success=False)

        result = repo.get_raw_by_label("test_field", ATSType.GREENHOUSE)
        assert result is not None
        assert result.success_count == 6
        assert result.failure_count == 4
        assert abs(result.confidence - 0.6) < 0.001, "Confidence math incorrect"

    def test_zero_total_gives_zero_confidence(self, session):
        """Edge case: 0 successes, 0 failures = 0.0 confidence."""
        from jobcli.storage.repositories import _compute_confidence

        confidence = _compute_confidence(0, 0)
        assert confidence == 0.0


class TestMemoryIntegration:
    """Test AgentMemory wrapper logic."""

    def test_resume_takes_priority_over_memory(self, memory, resume, session):
        """Resume JSON should override saved memory."""
        repo = FieldAnswerRepository(session)

        # Save high-confidence memory answer
        repo.save_answer(
            field_label="First Name",
            normalized_label="first_name",
            value="John",
            ats_type=ATSType.LEVER,
            success=True,
            source="human",
        )
        for _ in range(3):
            repo.record_outcome("first_name", ATSType.LEVER, success=True)

        # But resume says "Jane"
        value, source = memory.get_best_answer("First Name", ATSType.LEVER, resume)

        assert value == "Jane", "Resume should take priority"
        assert source == "resume_json"

    def test_ats_specific_memory_over_universal(self, memory, session):
        """ATS-specific answer should beat universal answer."""
        repo = FieldAnswerRepository(session)

        # Universal answer (UNKNOWN ATS)
        repo.save_answer(
            field_label="Sponsorship",
            normalized_label="sponsorship",
            value="No",
            ats_type=ATSType.UNKNOWN,
            success=True,
            source="human",
        )
        for _ in range(3):
            repo.record_outcome("sponsorship", ATSType.UNKNOWN, success=True)

        # Greenhouse-specific answer
        repo.save_answer(
            field_label="Sponsorship",
            normalized_label="sponsorship",
            value="Yes, I need H1B",
            ats_type=ATSType.GREENHOUSE,
            success=True,
            source="human",
        )
        for _ in range(3):
            repo.record_outcome("sponsorship", ATSType.GREENHOUSE, success=True)

        # Should get Greenhouse-specific answer
        value, source = memory.get_best_answer("Sponsorship", ATSType.GREENHOUSE, None)

        assert value == "Yes, I need H1B", "ATS-specific answer should win"
        assert source == "saved_memory"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
