"""Reconcile local apply logs with the DB and upload analytics snapshots."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from jobcli.profile.schemas import ApplicationStatus
from jobcli.storage.models import Database, JobModel, UsageEventQueueModel
from jobcli.storage.repositories import JobRepository

if TYPE_CHECKING:
    from jobcli.profile.schemas import Config

logger = logging.getLogger(__name__)

_SUCCESS_MARKER = "Application completed successfully"
_E2E_URL_FRAGMENT = "greenhouse.io/example/jobs/999"


def reconcile_submitted_from_logs(
    db: Database,
    *,
    log_directory: str = "~/.jobcli/logs",
    skip_e2e: bool = True,
) -> int:
    """Promote jobs to SUBMITTED when per-job logs show a successful completion."""
    log_root = Path(log_directory).expanduser()
    updated = 0
    with db.get_session() as session:
        repo = JobRepository(session)
        for app_log in log_root.glob("job_*/application.jsonl"):
            if _SUCCESS_MARKER not in app_log.read_text(encoding="utf-8", errors="ignore"):
                continue
            try:
                job_id = int(app_log.parent.name.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            row = session.query(JobModel).filter(JobModel.id == job_id).first()
            if row is None:
                continue
            if skip_e2e and _E2E_URL_FRAGMENT in (row.url or ""):
                continue
            if row.status == ApplicationStatus.SUBMITTED:
                continue
            repo.update_status(job_id, ApplicationStatus.SUBMITTED)
            updated += 1
    return updated


def collect_apply_job_ids(
    db: Database,
    *,
    since_hours: int = 48,
    log_directory: str = "~/.jobcli/logs",
    require_application_log: bool = True,
) -> list[int]:
    """Job ids touched by apply (non-pending, recent, with optional log file)."""
    since = datetime.utcnow() - timedelta(hours=max(1, since_hours))
    log_root = Path(log_directory).expanduser()
    out: list[int] = []
    with db.get_session() as session:
        rows = (
            session.query(JobModel)
            .filter(
                JobModel.status != ApplicationStatus.PENDING,
                JobModel.updated_at >= since,
            )
            .order_by(JobModel.updated_at.desc())
            .all()
        )
        for row in rows:
            if row.id is None:
                continue
            if require_application_log:
                app_log = log_root / f"job_{row.id}" / "application.jsonl"
                if not app_log.is_file() or app_log.stat().st_size < 80:
                    continue
            out.append(int(row.id))
    return out


def summarize_jobs(db: Database, job_ids: list[int]) -> dict[str, int]:
    """Count attempted / submitted / failed / skipped for analytics upload."""
    counts = {
        "jobs_attempted": 0,
        "jobs_submitted": 0,
        "jobs_failed": 0,
        "jobs_skipped": 0,
    }
    if not job_ids:
        return counts
    with db.get_session() as session:
        jobs = JobRepository(session).list_by_ids(job_ids)
    counts["jobs_attempted"] = len(jobs)
    for job in jobs:
        status = getattr(job.status, "value", str(job.status)).lower()
        if status == ApplicationStatus.SUBMITTED.value:
            counts["jobs_submitted"] += 1
        elif status == ApplicationStatus.SKIPPED.value:
            counts["jobs_skipped"] += 1
    counts["jobs_failed"] = (
        counts["jobs_attempted"] - counts["jobs_submitted"] - counts["jobs_skipped"]
    )
    return counts


def clear_usage_event_queue(db: Database) -> int:
    """Remove queued (unsent) analytics events on this machine."""
    with db.get_session() as session:
        deleted = session.query(UsageEventQueueModel).delete()
        session.commit()
        return int(deleted or 0)


def backfill_apply_analytics(
    db: Database,
    config: "Config",
    *,
    since_hours: int = 48,
    reconcile_logs: bool = True,
    skip_e2e: bool = True,
    clear_local_queue: bool = False,
) -> dict:
    """Build an apply analytics event from local DB + logs and upload it."""
    from jobcli.analytics.service import track_apply_analytics

    if clear_local_queue:
        clear_usage_event_queue(db)

    if reconcile_logs:
        n = reconcile_submitted_from_logs(db, log_directory=config.log_directory, skip_e2e=skip_e2e)
        logger.info("Reconciled %s job(s) to SUBMITTED from application logs", n)

    job_ids = collect_apply_job_ids(
        db,
        since_hours=since_hours,
        log_directory=config.log_directory or "~/.jobcli/logs",
    )
    if skip_e2e:
        with db.get_session() as session:
            filtered: list[int] = []
            for jid in job_ids:
                row = session.query(JobModel).filter(JobModel.id == jid).first()
                if row and _E2E_URL_FRAGMENT in (row.url or ""):
                    continue
                filtered.append(jid)
            job_ids = filtered

    counts = summarize_jobs(db, job_ids)
    started_at = time.time() - max(60.0, since_hours * 3600.0)
    flush_result = track_apply_analytics(
        db,
        config,
        result="backfill",
        run_started_at=started_at,
        jobs_attempted_count=counts["jobs_attempted"],
        jobs_submitted_count=counts["jobs_submitted"],
        jobs_failed_count=counts["jobs_failed"],
        processed_job_ids=job_ids,
        exit_reason="analytics_backfill",
        extra_metadata={"backfill": True, "since_hours": since_hours, "jobs_skipped": counts["jobs_skipped"]},
    )
    return {
        "user_id": config.job_board_username,
        "job_ids": job_ids,
        **counts,
        "flush": flush_result,
    }
