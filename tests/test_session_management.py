"""Tests for session management to prevent leaks."""

import pytest
from sqlalchemy import create_engine

from jobcli.storage.models import Base, Database
from jobcli.storage.repositories import JobRepository
from jobcli.storage.session import get_db_session, get_db_transaction
from jobcli.core.schemas import Job


@pytest.fixture
def test_database():
    """Create test database."""
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


def test_session_closes_on_success(test_database):
    """Test that session closes after successful operation."""
    job = Job(url="https://example.com/job/1")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created_job = repo.create(job)
        assert created_job.id is not None

    # Session should be closed now
    # Verify by checking connection pool
    assert test_database.engine.pool.checkedout() == 0


def test_session_closes_on_error(test_database):
    """Test that session closes and rolls back on error."""
    with pytest.raises(Exception):
        with get_db_session(test_database) as session:
            repo = JobRepository(session)

            # Create job
            job = Job(url="https://example.com/job/1")
            repo.create(job)

            # Raise error
            raise Exception("Test error")

    # Session should be closed and rolled back
    assert test_database.engine.pool.checkedout() == 0

    # Job should not exist (rolled back)
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        job = repo.get_by_url("https://example.com/job/1")
        assert job is None


def test_transaction_commits_all_or_nothing(test_database):
    """Test that transaction commits all operations or rolls back all."""
    job1 = Job(url="https://example.com/job/1")
    job2 = Job(url="https://example.com/job/2")

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
    """Test that transaction rolls back all operations on error."""
    job1 = Job(url="https://example.com/job/1")
    job2 = Job(url="https://example.com/job/2")

    with pytest.raises(Exception):
        with get_db_transaction(test_database) as session:
            repo = JobRepository(session)
            repo.create(job1)
            repo.create(job2)
            raise Exception("Test error")

    # Neither job should exist (rolled back)
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        assert repo.get_by_url("https://example.com/job/1") is None
        assert repo.get_by_url("https://example.com/job/2") is None


def test_multiple_sequential_sessions(test_database):
    """Test that multiple sequential sessions work correctly."""
    jobs_created = []

    # Create 10 jobs in separate sessions
    for i in range(10):
        with get_db_session(test_database) as session:
            repo = JobRepository(session)
            job = Job(url=f"https://example.com/job/{i}")
            created = repo.create(job)
            jobs_created.append(created.id)

    # No sessions should be checked out
    assert test_database.engine.pool.checkedout() == 0

    # All jobs should exist
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        pending = repo.list_pending()
        assert len(pending) == 10


def test_no_connection_leaks(test_database):
    """Test that connections are properly returned to pool."""
    initial_connections = test_database.engine.pool.checkedout()

    # Perform 100 operations
    for i in range(100):
        with get_db_session(test_database) as session:
            repo = JobRepository(session)
            if i < 50:
                job = Job(url=f"https://example.com/job/{i}")
                repo.create(job)

    # Should return to initial state
    final_connections = test_database.engine.pool.checkedout()
    assert final_connections == initial_connections


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
