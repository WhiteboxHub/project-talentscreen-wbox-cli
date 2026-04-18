"""Tests for repository pattern and data access."""

import pytest

from jobcli.core.schemas import Job, ApplicationStatus, ATSType
from jobcli.storage.models import Database
from jobcli.storage.repositories import JobRepository
from jobcli.storage.session import get_db_session


@pytest.fixture
def test_database():
    """Create test database."""
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


def test_job_create(test_database):
    """Test creating a job."""
    job = Job(
        url="https://example.com/job/1",
        title="Software Engineer",
        company="Test Corp",
    )

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)

        assert created.id is not None
        assert created.url == job.url
        assert created.title == job.title
        assert created.status == ApplicationStatus.PENDING


def test_job_create_strips_tracking_query_params(test_database):
    """URLs are normalized on insert (dedupe-friendly)."""
    job = Job(
        url="https://example.com/job/2?utm_source=linkedin",
        title="Tracked",
    )
    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)
    assert "utm_" not in created.url
    assert created.url == "https://example.com/job/2"
    assert created.title == job.title


def test_job_get_by_id(test_database):
    """Test retrieving job by ID."""
    job = Job(url="https://example.com/job/1")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)
        job_id = created.id

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        retrieved = repo.get(job_id)

        assert retrieved is not None
        assert retrieved.id == job_id
        assert retrieved.url == job.url


def test_job_get_by_url(test_database):
    """Test retrieving job by URL."""
    job = Job(url="https://example.com/job/1")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        repo.create(job)

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        retrieved = repo.get_by_url(job.url)

        assert retrieved is not None
        assert retrieved.url == job.url


def test_job_update_status(test_database):
    """Test updating job status."""
    job = Job(url="https://example.com/job/1")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)
        job_id = created.id

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        repo.update_status(job_id, ApplicationStatus.SUBMITTED)

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        updated = repo.get(job_id)

        assert updated.status == ApplicationStatus.SUBMITTED


def test_job_update_ats_type(test_database):
    """Test updating ATS type."""
    job = Job(url="https://boards.greenhouse.io/company/job/1")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        created = repo.create(job)
        job_id = created.id

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        repo.update_ats_type(job_id, ATSType.GREENHOUSE)

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        updated = repo.get(job_id)

        assert updated.ats_type == ATSType.GREENHOUSE


def test_list_pending_jobs(test_database):
    """Test listing pending jobs."""
    jobs = [
        Job(url="https://example.com/job/1", status=ApplicationStatus.PENDING),
        Job(url="https://example.com/job/2", status=ApplicationStatus.PENDING),
        Job(url="https://example.com/job/3", status=ApplicationStatus.SUBMITTED),
    ]

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        for job in jobs:
            repo.create(job)

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        pending = repo.list_pending()

        assert len(pending) == 2
        assert all(j.status == ApplicationStatus.PENDING for j in pending)


def test_unique_url_constraint(test_database):
    """Test that duplicate URLs are rejected."""
    job1 = Job(url="https://example.com/job/1")

    with get_db_session(test_database) as session:
        repo = JobRepository(session)
        repo.create(job1)

    # Try to create duplicate
    job2 = Job(url="https://example.com/job/1")

    with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
        with get_db_session(test_database) as session:
            repo = JobRepository(session)
            repo.create(job2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
