"""Persist interrupted ``apply`` runs so the user can resume the same job queue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from jobcli.profile.schemas import ApplicationStatus, Job
from jobcli.storage.repositories import ConfigRepository, JobRepository

_CHECKPOINT_KEY = "apply_run_checkpoint"


@dataclass(frozen=True)
class ApplyRunCheckpoint:
    """Snapshot of a batch apply stopped by the user (Ctrl+C / quit)."""

    job_ids: List[int]
    next_index: int
    mode: str
    sort: str
    limit: Optional[int]
    saved_at: str

    @property
    def remaining_count(self) -> int:
        return max(0, len(self.job_ids) - self.next_index)


def save_apply_checkpoint(
    session: Session,
    *,
    job_ids: List[int],
    next_index: int,
    mode: str,
    sort: str,
    limit: Optional[int],
) -> None:
    """Store the remaining batch so ``continue`` / resume can pick up."""
    payload = {
        "job_ids": [int(i) for i in job_ids],
        "next_index": max(0, int(next_index)),
        "mode": mode,
        "sort": sort,
        "limit": limit,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    ConfigRepository(session).set(_CHECKPOINT_KEY, json.dumps(payload))


def load_apply_checkpoint(session: Session) -> Optional[ApplyRunCheckpoint]:
    raw = ConfigRepository(session).get(_CHECKPOINT_KEY)
    if not raw:
        return None
    try:
        data: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    job_ids = data.get("job_ids") or []
    if not isinstance(job_ids, list) or not job_ids:
        return None
    return ApplyRunCheckpoint(
        job_ids=[int(x) for x in job_ids],
        next_index=max(0, int(data.get("next_index") or 0)),
        mode=str(data.get("mode") or "supervised"),
        sort=str(data.get("sort") or "oldest"),
        limit=data.get("limit"),
        saved_at=str(data.get("saved_at") or ""),
    )


def clear_apply_checkpoint(session: Session) -> None:
    repo = ConfigRepository(session)
    if repo.get(_CHECKPOINT_KEY):
        repo.set(_CHECKPOINT_KEY, "")


def reset_interrupted_job_to_pending(session: Session, job_id: Optional[int]) -> None:
    """Leave a partially processed job eligible for the next apply pass."""
    if not job_id:
        return
    job_repo = JobRepository(session)
    job = job_repo.get(job_id)
    if job and job.status == ApplicationStatus.IN_PROGRESS:
        job_repo.update_status(job_id, ApplicationStatus.PENDING)


def jobs_from_checkpoint(
    session: Session,
    checkpoint: ApplyRunCheckpoint,
) -> List[Job]:
    """Return jobs from the saved queue, starting at ``next_index``."""
    ordered = JobRepository(session).list_by_ids(checkpoint.job_ids)
    by_id = {j.id: j for j in ordered if j.id is not None}
    remaining: List[Job] = []
    for jid in checkpoint.job_ids[checkpoint.next_index :]:
        job = by_id.get(jid)
        if not job:
            continue
        if job.status in (
            ApplicationStatus.PENDING,
            ApplicationStatus.IN_PROGRESS,
        ):
            remaining.append(job)
    return remaining
