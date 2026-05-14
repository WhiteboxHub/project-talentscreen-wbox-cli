"""Tests for session management to prevent leaks."""

import pytest

from jobcli.core.schemas import ATSType, ApplicationStatus, Job
from jobcli.storage.models import Database, JobModel
from jobcli.storage.repositories import JobRepository
from jobcli.storage.session import get_db_session, get_db_transaction


def _assert_pool_fully_returned(engine) -> None:
    """QueuePool exposes checkedout(); SingletonThreadPool (SQLite :memory:) does not."""
    pool = engine.pool
    if hasattr(pool, "checkedout"):
        assert pool.checkedout() == 0


@pytest.fixture
def test_database():
    """Create test database."""
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


def test_session_closes_on_success(test_database):
    """Test that session closes after successful operation."""
    job = Job(url="https://example.com/job/1", is_cli_friendly=True, is_already_applied=False)

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created_job = repo.create(job)
        assert created_job.id is not None

    # Session should be closed now
    _assert_pool_fully_returned(test_database.engine)


def test_session_closes_on_error(test_database):
    """Test that session closes and rolls back on error (ORM add without inner commit)."""
    with pytest.raises(Exception):
        with get_db_session(test_database) as session:
            # Do not use JobRepository.create() here — it commits and would survive rollback.
            session.add(
                JobModel(
                    url="https://example.com/job/1",
                    title=None,
                    company=None,
                    location=None,
                    description=None,
                    ats_type=ATSType.UNKNOWN,
                    status=ApplicationStatus.PENDING,
                )
            )
            raise Exception("Test error")

    _assert_pool_fully_returned(test_database.engine)

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        assert repo.get_by_url("https://example.com/job/1") is None


def test_transaction_commits_all_or_nothing(test_database):
    """Test that transaction commits all operations or rolls back all."""
    job1 = Job(url="https://example.com/job/1", is_cli_friendly=True, is_already_applied=False)
    job2 = Job(url="https://example.com/job/2", is_cli_friendly=True, is_already_applied=False)

    # Successful transaction
    with get_db_transaction(test_database) as session:
        repo = JobRepository(session)
        repo.create(job1)
        repo.create(job2)

    # Both jobs should exist
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        assert repo.get_by_url("https://example.com/job/1") is not None
        assert repo.get_by_url("https://example.com/job/2") is not None


def test_transaction_rollback_on_error(test_database):
    """Transaction rolls back when the session never commits (JobRepository commits eagerly)."""
    with pytest.raises(Exception):
        with get_db_transaction(test_database) as session:
            session.add(
                JobModel(
                    url="https://example.com/job/tx1",
                    title=None,
                    company=None,
                    location=None,
                    description=None,
                    ats_type=ATSType.UNKNOWN,
                    status=ApplicationStatus.PENDING,
                )
            )
            session.add(
                JobModel(
                    url="https://example.com/job/tx2",
                    title=None,
                    company=None,
                    location=None,
                    description=None,
                    ats_type=ATSType.UNKNOWN,
                    status=ApplicationStatus.PENDING,
                )
            )
            raise Exception("Test error")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        assert repo.get_by_url("https://example.com/job/tx1") is None
        assert repo.get_by_url("https://example.com/job/tx2") is None


def test_multiple_sequential_sessions(test_database):
    """Test that multiple sequential sessions work correctly."""
    jobs_created = []

    # Create 10 jobs in separate sessions
    for i in range(10):
        with get_db_session(test_database) as session:
            repo = JobRepository(session)
            job = Job(
                url=f"https://example.com/job/{i}",
                is_cli_friendly=True,
                is_already_applied=False,
            )
            created = repo.create(job)
            jobs_created.append(created.id)

    _assert_pool_fully_returned(test_database.engine)

    # All jobs should exist
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        pending = repo.list_pending()
        assert len(pending) == 10


def test_no_connection_leaks(test_database):
    """Test that connections are properly returned to pool."""
    pool = test_database.engine.pool
    if not hasattr(pool, "checkedout"):
        # SQLite :memory: uses SingletonThreadPool — skip checkout accounting
        for i in range(20):
            with get_db_session(test_database) as session:
                JobRepository(session).create(
                    Job(url=f"https://example.com/leak/{i}", is_cli_friendly=True, is_already_applied=False)
                )
        return

    initial_connections = pool.checkedout()
    for i in range(100):
        with get_db_session(test_database) as session:
            repo = JobRepository(session)
            if i < 50:
                repo.create(
                    Job(url=f"https://example.com/job/{i}", is_cli_friendly=True, is_already_applied=False)
                )
    assert pool.checkedout() == initial_connections


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
