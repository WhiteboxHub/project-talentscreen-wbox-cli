"""Tests for AgentMemory confidence gate, outcome recording, and sync counter."""

import pytest

from jobcli.core.schemas import ATSType
from jobcli.storage.models import Database
from jobcli.core.memory import AgentMemory
from jobcli.storage.repositories import FieldAnswerRepository, SyncMetadataRepository
from jobcli.sync.constants import CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT


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


@pytest.fixture
def memory(session):
    return AgentMemory(session, infer_location_country=False, job_id=1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pump_successes(session, normalized_label, ats_type, value, n=MIN_SUCCESS_COUNT):
    """Insert N successes directly via repo (bypasses synonym resolver)."""
    repo = FieldAnswerRepository(session)
    for _ in range(n):
        repo.save_answer(
            field_label=normalized_label.title(),
            normalized_label=normalized_label,
            value=value,
            ats_type=ats_type,
            success=True,
        )


# ── get_best_answer: confidence gate ─────────────────────────────────────────

class TestGetBestAnswerConfidenceGate:
    """AgentMemory.get_best_answer must not return low-confidence records."""

    def test_returns_none_before_threshold(self, memory, session):
        """Only 1 success — no record returned from memory."""
        # Use repo directly so we control exact normalized_label
        repo = FieldAnswerRepository(session)
        repo.save_answer(
            "Work Style", "work style", "Remote",
            ATSType.GREENHOUSE, success=True,
        )
        val, src = memory.get_best_answer("Work Style", ATSType.GREENHOUSE)
        assert val is None
        assert src == "not_found"

    def test_returns_value_after_threshold(self, memory, session):
        """After MIN_SUCCESS_COUNT successes the answer is returned."""
        # synonym_resolver.resolve_field_label("Notice Period") == "notice_period"
        _pump_successes(session, "notice_period", ATSType.WORKDAY, "2 weeks")
        val, src = memory.get_best_answer("Notice Period", ATSType.WORKDAY)
        assert val == "2 weeks"
        assert src == "saved_memory"

    def test_resume_always_returned_regardless_of_confidence(self, memory):
        """Resume JSON bypasses the confidence gate entirely (Priority 1)."""
        from jobcli.core.schemas import ResumeData, PersonalInfo, WorkAuthorization
        resume = ResumeData(
            personal=PersonalInfo(
                first_name="Alice",
                last_name="Smith",
                email="alice@example.com",
                phone="555-0100",
            ),
            work_authorization=WorkAuthorization(),
        )
        val, src = memory.get_best_answer("First Name", ATSType.GREENHOUSE, resume=resume)
        assert val == "Alice"
        assert src == "resume_json"

    def test_universal_memory_requires_threshold(self, memory, session):
        """Cross-ATS universal lookup also obeys the gate."""
        repo = FieldAnswerRepository(session)
        # Only 1 hit — below gate
        repo.save_answer("Sponsorship Required", "sponsor_req", "No",
                         ATSType.UNKNOWN, success=True)
        val, src = memory.get_best_answer("Sponsorship Required", ATSType.GREENHOUSE)
        assert val is None

    def test_universal_memory_above_threshold(self, memory, session):
        """Universal lookup returns confident cross-ATS answers."""
        # synonym_resolver.resolve_field_label("Sponsorship Required") == "sponsorship"
        _pump_successes(session, "sponsorship", ATSType.UNKNOWN, "No")
        val, src = memory.get_best_answer("Sponsorship Required", ATSType.GREENHOUSE)
        assert val == "No"
        assert src == "universal_memory"


# ── save_field_answer dedup ───────────────────────────────────────────────────

class TestSaveFieldAnswerDedup:
    def test_same_value_not_saved_again(self, memory, session):
        """Saving identical value twice does not create a duplicate row.

        AgentMemory.save_field_answer signature:
            (self, field_label, value, ats_type, success=True, source="human")
        """
        memory.save_field_answer("Work Auth", "Yes", ATSType.LEVER)
        saved = memory.save_field_answer("Work Auth", "Yes", ATSType.LEVER)
        assert saved is False  # dedup blocked the second save
        from jobcli.storage.models import FieldAnswerModel
        count = session.query(FieldAnswerModel).count()
        assert count == 1

    def test_different_value_saved(self, memory, session):
        """A new/different value for the same field IS saved."""
        memory.save_field_answer("Work Auth", "Yes", ATSType.LEVER)
        saved = memory.save_field_answer("Work Auth", "No", ATSType.LEVER)
        assert saved is True

    def test_dedup_works_even_when_below_confidence(self, memory, session):
        """Dedup check uses raw lookup (no gate) so it catches low-confidence rows."""
        # After 1st success the record exists but is below gate
        memory.save_field_answer("Visa Status", "US Citizen", ATSType.GREENHOUSE)
        # Should still detect the existing value and skip
        saved = memory.save_field_answer("Visa Status", "US Citizen", ATSType.GREENHOUSE)
        assert saved is False


# ── record_field_outcome ──────────────────────────────────────────────────────

class TestRecordFieldOutcome:
    def test_success_increments_success_count(self, memory, session):
        """record_field_outcome with success=True increments success_count."""
        repo = FieldAnswerRepository(session)
        # Insert a row with known normalized_label
        repo.save_answer("Work Auth", "work auth", "Yes", ATSType.GREENHOUSE, success=True)
        # record_outcome via memory (uses synonym_resolver → same normalized key)
        memory.record_field_outcome("Work Auth", "Yes", success=True, ats_type=ATSType.GREENHOUSE)
        row = repo.get_raw_by_label("work auth", ATSType.GREENHOUSE)
        assert row is not None
        assert row.success_count == 2

    def test_failure_increments_failure_count(self, memory, session):
        """record_field_outcome with success=False increments failure_count."""
        repo = FieldAnswerRepository(session)
        repo.save_answer("Work Auth", "work auth", "Yes", ATSType.GREENHOUSE, success=True)
        memory.record_field_outcome("Work Auth", "Yes", success=False, ats_type=ATSType.GREENHOUSE)
        row = repo.get_raw_by_label("work auth", ATSType.GREENHOUSE)
        assert row is not None
        assert row.failure_count == 1

    def test_confidence_updated_by_outcome(self, memory, session):
        """Confidence is recomputed after recording an outcome."""
        repo = FieldAnswerRepository(session)
        repo.save_answer("Avail", "avail", "Now", ATSType.WORKDAY, success=True)
        # 2nd success via outcome
        memory.record_field_outcome("Avail", "Now", success=True, ats_type=ATSType.WORKDAY)
        # 1 failure via outcome
        memory.record_field_outcome("Avail", "Now", success=False, ats_type=ATSType.WORKDAY)
        row = repo.get_raw_by_label("avail", ATSType.WORKDAY)
        # 2 success / 3 total
        assert row.confidence == pytest.approx(2 / 3, rel=1e-3)

    def test_outcome_for_nonexistent_label_is_noop(self, memory, session):
        """Recording outcome for unknown label must not raise."""
        memory.record_field_outcome("Ghost Field", "anything", success=True, ats_type=ATSType.UNKNOWN)

    def test_outcome_empty_label_is_noop(self, memory, session):
        """Empty field_label must not raise."""
        memory.record_field_outcome("", "anything", success=True, ats_type=ATSType.UNKNOWN)


# ── increment_apps_since_sync ─────────────────────────────────────────────────

class TestIncrementAppsSinceSync:
    def test_increments_counter(self, memory, session):
        memory.increment_apps_since_sync()
        memory.increment_apps_since_sync()
        memory.increment_apps_since_sync()
        repo = SyncMetadataRepository(session)
        assert repo.get_apps_since_sync() == 3

    def test_multiple_memory_instances_share_singleton(self, session, db):
        """Different AgentMemory instances using the same session share the singleton."""
        m1 = AgentMemory(session, infer_location_country=False, job_id=1)
        m2 = AgentMemory(session, infer_location_country=False, job_id=2)
        m1.increment_apps_since_sync()
        m2.increment_apps_since_sync()
        repo = SyncMetadataRepository(session)
        assert repo.get_apps_since_sync() == 2


# ── build_llm_context confidence filter ──────────────────────────────────────

class TestBuildLLMContext:
    def test_low_confidence_excluded_from_context(self, memory, session):
        """Low-confidence records must not appear in the LLM context block."""
        repo = FieldAnswerRepository(session)
        # 1 hit only — below gate
        repo.save_answer("Secret", "secret", "xyz", ATSType.GREENHOUSE, success=True)
        ctx = memory.build_llm_context(ATSType.GREENHOUSE)
        assert "xyz" not in ctx

    def test_high_confidence_included_in_context(self, memory, session):
        """High-confidence records appear in the LLM context block."""
        _pump_successes(session, "remote", ATSType.GREENHOUSE, "Yes")
        ctx = memory.build_llm_context(ATSType.GREENHOUSE)
        assert "Yes" in ctx

    def test_empty_context_returns_fallback_message(self, memory):
        ctx = memory.build_llm_context(ATSType.GREENHOUSE)
        assert "No high-confidence memory" in ctx


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
