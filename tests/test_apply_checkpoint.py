"""Tests for interrupted apply checkpoint persistence."""

from jobcli.profile.schemas import ApplicationStatus, Job
from jobcli.storage.models import Database
from jobcli.storage.repositories import ConfigRepository, JobRepository
from jobcli.utils.apply_checkpoint import (
    _CHECKPOINT_KEY,
    clear_apply_checkpoint,
    jobs_from_checkpoint,
    load_apply_checkpoint,
    save_apply_checkpoint,
)


def test_save_and_load_checkpoint():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    session = db.get_session()
    repo = JobRepository(session)
    j1 = repo.create(Job(title="A", url="https://boards.greenhouse.io/a/jobs/1", status=ApplicationStatus.PENDING))
    j2 = repo.create(Job(title="B", url="https://boards.greenhouse.io/b/jobs/2", status=ApplicationStatus.PENDING))

    save_apply_checkpoint(
        session,
        job_ids=[j1.id, j2.id],
        next_index=1,
        mode="supervised",
        sort="oldest",
        limit=5,
    )
    cp = load_apply_checkpoint(session)
    assert cp is not None
    assert cp.job_ids == [j1.id, j2.id]
    assert cp.next_index == 1
    assert cp.remaining_count == 1
    assert cp.mode == "supervised"
    assert cp.limit == 5

    remaining = jobs_from_checkpoint(session, cp)
    assert len(remaining) == 1
    assert remaining[0].id == j2.id

    clear_apply_checkpoint(session)
    assert load_apply_checkpoint(session) is None
    raw = ConfigRepository(session).get(_CHECKPOINT_KEY)
    assert raw in ("", None)

    session.close()
