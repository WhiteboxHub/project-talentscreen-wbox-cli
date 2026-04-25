"""Tests for Phase 1 repository enhancements: confidence, merge protection, thresholds."""

import pytest

from jobcli.core.schemas import ATSType, ApplicationStatus, Job
from jobcli.storage.models import Database
from jobcli.storage.repositories import (
    FieldAnswerRepository,
    JobRepository,
    LearnedLocatorRepository,
    SyncMetadataRepository,
)
from jobcli.storage.session import get_db_session
from jobcli.sync.constants import CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT
from jobcli.core.locator_schemas import LearnedLocator
from jobcli.core.schemas import SelectorType


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_database():
    """In-memory SQLite DB, freshly created per test."""
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


@pytest.fixture
def session(test_database):
    """Session that commits/closes automatically via context manager."""
    s = test_database.get_session()
    yield s
    s.close()


# ── _compute_confidence helper ────────────────────────────────────────────────

def test_confidence_zero_on_first_failure(session):
    """A single failure means 0% confidence."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Work Auth", "wa", "No", ATSType.UNKNOWN, success=False)
    row = repo.get_raw_by_label("wa", ATSType.UNKNOWN)
    assert row is not None
    assert row.confidence == pytest.approx(0.0)


def test_confidence_one_on_first_success(session):
    """A single success means 100% confidence."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Availability", "availability", "Immediate", ATSType.UNKNOWN, success=True)
    row = repo.get_raw_by_label("availability", ATSType.UNKNOWN)
    assert row is not None
    assert row.confidence == pytest.approx(1.0)


def test_confidence_recomputed_on_update(session):
    """Confidence updates correctly as successes accumulate."""
    repo = FieldAnswerRepository(session)
    label = "cover letter"
    # 1 success
    repo.save_answer("Cover Letter", label, "Motivated...", ATSType.GREENHOUSE, success=True)
    # 2nd success
    repo.save_answer("Cover Letter", label, "Motivated...", ATSType.GREENHOUSE, success=True)
    # 1 failure
    repo.save_answer("Cover Letter", label, "Motivated...", ATSType.GREENHOUSE, success=False)
    row = repo.get_raw_by_label(label, ATSType.GREENHOUSE)
    # 2 successes / 3 total = 0.667
    assert row.success_count == 2
    assert row.failure_count == 1
    assert row.confidence == pytest.approx(2 / 3, rel=1e-3)


def test_confidence_record_outcome(session):
    """record_outcome increments counts without changing the stored value."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Years Exp", "years_exp", "5", ATSType.WORKDAY, success=True)
    # Record 2 more successes without re-saving
    repo.record_outcome("years_exp", ATSType.WORKDAY, success=True)
    repo.record_outcome("years_exp", ATSType.WORKDAY, success=True)
    row = repo.get_raw_by_label("years_exp", ATSType.WORKDAY)
    assert row.success_count == 3
    assert row.value == "5"  # value unchanged
    assert row.confidence == pytest.approx(1.0)


# ── Merge protection ──────────────────────────────────────────────────────────

def test_merge_protection_human_not_overwritten_by_auto(session):
    """A 'human' source value must not be replaced by an 'auto' source."""
    repo = FieldAnswerRepository(session)
    # Human writes first
    repo.save_answer("Salary", "salary", "80000", ATSType.LEVER, source="human")
    # Auto tries to overwrite with different value
    repo.save_answer("Salary", "salary", "999999", ATSType.LEVER, source="auto")
    row = repo.get_raw_by_label("salary", ATSType.LEVER)
    assert row.value == "80000"   # human value preserved
    assert row.source == "human"  # source unchanged


def test_merge_protection_human_not_overwritten_by_local(session):
    """A 'human' source must survive a 'local' (LLM-learned) overwrite attempt."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Notice", "notice", "2 weeks", ATSType.ASHBY, source="human")
    repo.save_answer("Notice", "notice", "1 month", ATSType.ASHBY, source="local")
    row = repo.get_raw_by_label("notice", ATSType.ASHBY)
    assert row.value == "2 weeks"
    assert row.source == "human"


def test_merge_protection_user_not_overwritten_by_auto(session):
    """'user' source is also high-trust and must not be overwritten by 'auto'."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Start Date", "start_date", "ASAP", ATSType.ICIMS, source="user")
    repo.save_answer("Start Date", "start_date", "3 months", ATSType.ICIMS, source="auto")
    row = repo.get_raw_by_label("start_date", ATSType.ICIMS)
    assert row.value == "ASAP"
    assert row.source == "user"


def test_merge_protection_auto_overwritten_by_human(session):
    """A low-trust 'auto' answer IS replaced when a human corrects it."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Referral", "referral", "Online", ATSType.LEVER, source="auto")
    repo.save_answer("Referral", "referral", "Friend", ATSType.LEVER, source="human")
    row = repo.get_raw_by_label("referral", ATSType.LEVER)
    assert row.value == "Friend"
    assert row.source == "human"


def test_merge_protection_counts_always_updated(session):
    """Even when the value is protected, success/failure counts still increment."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Visa", "visa", "No Sponsorship", ATSType.WORKDAY, source="human")
    repo.save_answer("Visa", "visa", "Different", ATSType.WORKDAY, success=False, source="auto")
    row = repo.get_raw_by_label("visa", ATSType.WORKDAY)
    # value must stay
    assert row.value == "No Sponsorship"
    # but failure was recorded
    assert row.failure_count == 1


# ── Threshold-gated retrieval ─────────────────────────────────────────────────

def test_get_by_normalized_label_below_threshold_returns_none(session):
    """A record below the confidence gate is not returned by get_by_normalized_label."""
    repo = FieldAnswerRepository(session)
    # 1 success only — below MIN_SUCCESS_COUNT=3
    repo.save_answer("Pronouns", "pronouns", "They/Them", ATSType.GREENHOUSE, success=True)
    result = repo.get_by_normalized_label("pronouns", ATSType.GREENHOUSE)
    assert result is None


def _make_high_confidence_answer(repo, label, ats_type, value="Yes"):
    """Helper: insert MIN_SUCCESS_COUNT successes so the row passes the gate."""
    for _ in range(MIN_SUCCESS_COUNT):
        repo.save_answer(label.title(), label.lower(), value, ats_type, success=True)


def test_get_by_normalized_label_above_threshold_returns_row(session):
    """A record that clears both gates is returned."""
    repo = FieldAnswerRepository(session)
    _make_high_confidence_answer(repo, "remote", ATSType.WORKDAY, "Yes")
    result = repo.get_by_normalized_label("remote", ATSType.WORKDAY)
    assert result is not None
    assert result.value == "Yes"
    assert result.confidence >= CONFIDENCE_THRESHOLD
    assert result.success_count >= MIN_SUCCESS_COUNT


def test_get_universal_below_threshold_returns_none(session):
    """Universal lookup also respects the confidence gate."""
    repo = FieldAnswerRepository(session)
    repo.save_answer("Years", "years", "5", ATSType.UNKNOWN, success=True)
    assert repo.get_universal("years") is None


def test_get_universal_above_threshold_returns_row(session):
    """Universal lookup returns confident cross-ATS answers."""
    repo = FieldAnswerRepository(session)
    _make_high_confidence_answer(repo, "remote", ATSType.UNKNOWN, "Remote")
    result = repo.get_universal("remote")
    assert result is not None
    assert result.value == "Remote"


# ── Locator confidence gate ───────────────────────────────────────────────────

def _make_high_confidence_locator(repo, ats_type, purpose, selector):
    """Insert MIN_SUCCESS_COUNT successes for a locator."""
    for _ in range(MIN_SUCCESS_COUNT):
        repo.upsert_for_field(
            ats_type=ats_type,
            domain="boards.greenhouse.io",
            purpose=purpose,
            selector=selector,
            selector_type=SelectorType.CSS,
            success=True,
        )


def test_locator_get_best_below_threshold_returns_none(session):
    """Locator with only 1 success is not returned by get_best_for_field."""
    repo = LearnedLocatorRepository(session)
    repo.upsert_for_field(
        ats_type=ATSType.GREENHOUSE,
        domain="boards.greenhouse.io",
        purpose="apply_button",
        selector="#apply",
        selector_type=SelectorType.CSS,
        success=True,
    )
    result = repo.get_best_for_field("apply_button", ATSType.GREENHOUSE)
    assert result is None


def test_locator_get_best_above_threshold_returns_row(session):
    """Locator with enough successes is returned."""
    repo = LearnedLocatorRepository(session)
    _make_high_confidence_locator(repo, ATSType.GREENHOUSE, "apply_button", "#apply-now")
    result = repo.get_best_for_field("apply_button", ATSType.GREENHOUSE)
    assert result is not None
    assert result.selector == "#apply-now"
    assert result.confidence_score >= CONFIDENCE_THRESHOLD
    assert result.success_count >= MIN_SUCCESS_COUNT


def test_locator_confidence_degrades_on_failure(session):
    """Failures properly reduce confidence_score."""
    repo = LearnedLocatorRepository(session)
    _make_high_confidence_locator(repo, ATSType.LEVER, "submit", "#submit-btn")
    # Two failures
    repo.upsert_for_field(
        ats_type=ATSType.LEVER,
        domain="boards.greenhouse.io",
        purpose="submit",
        selector="#submit-btn",
        selector_type=SelectorType.CSS,
        success=False,
    )
    repo.upsert_for_field(
        ats_type=ATSType.LEVER,
        domain="boards.greenhouse.io",
        purpose="submit",
        selector="#submit-btn",
        selector_type=SelectorType.CSS,
        success=False,
    )
    from jobcli.storage.models import LearnedLocatorModel
    row = session.query(LearnedLocatorModel).filter_by(selector="#submit-btn").first()
    # 3 success / 5 total = 0.6 (exactly at threshold, still passes)
    assert row.confidence_score == pytest.approx(3 / 5, rel=1e-3)


# ── SyncMetadataRepository ────────────────────────────────────────────────────

def test_sync_metadata_created_on_first_get(session):
    """get_or_create initializes the singleton row."""
    repo = SyncMetadataRepository(session)
    meta = repo.get_or_create()
    assert meta.id == 1
    assert meta.apps_since_sync == 0
    assert meta.last_version == "0.0.0"
    assert meta.last_sync_at is None


def test_sync_metadata_increment(session):
    """Incrementing apps_since_sync works correctly."""
    repo = SyncMetadataRepository(session)
    repo.increment_apps_since_sync()
    repo.increment_apps_since_sync()
    repo.increment_apps_since_sync()
    assert repo.get_apps_since_sync() == 3


def test_sync_metadata_record_sync_resets_counter(session):
    """record_sync sets last_sync_at and resets the counter."""
    repo = SyncMetadataRepository(session)
    repo.increment_apps_since_sync()
    repo.increment_apps_since_sync()
    repo.record_sync(version="1.2.3")
    meta = repo.get_or_create()
    assert meta.apps_since_sync == 0
    assert meta.last_version == "1.2.3"
    assert meta.last_sync_at is not None


def test_sync_metadata_idempotent_get_or_create(session):
    """get_or_create does not create duplicate rows."""
    repo = SyncMetadataRepository(session)
    repo.get_or_create()
    repo.get_or_create()
    repo.get_or_create()
    from jobcli.storage.models import SyncMetadataModel
    count = session.query(SyncMetadataModel).count()
    assert count == 1


# ── Existing job tests (smoke-check nothing broke) ────────────────────────────

def test_job_create(test_database):
    """Test creating a job — smoke check no regression."""
    job = Job(
        url="https://example.com/job/1",
        title="Software Engineer",
        company="Test Corp",
    )
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)
        assert created.id is not None
        assert created.status == ApplicationStatus.PENDING


def test_job_create_strips_tracking_query_params(test_database):
    """URLs are normalized on insert."""
    job = Job(url="https://example.com/job/2?utm_source=linkedin", title="Tracked")
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)
    assert "utm_" not in created.url
    assert created.url == "https://example.com/job/2"


def test_unique_url_constraint(test_database):
    """Duplicate URLs are rejected."""
    job1 = Job(url="https://example.com/job/1")
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        repo.create(job1)

    with pytest.raises(Exception):
        with get_db_session(test_database) as session:
            repo = JobRepository(session)
            repo.create(Job(url="https://example.com/job/1"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
