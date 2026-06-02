"""Client-side usage analytics queueing and flushing service."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

logger = logging.getLogger(__name__)

from jobcli.analytics.usage import UsageEvent
from jobcli.storage.models import Database
from jobcli.storage.repositories import JobRepository, UsageEventQueueRepository
from jobcli.sync.client import get_client

if TYPE_CHECKING:
    from jobcli.profile.schemas import Config

_MAX_JSONL_LINES_PER_JOB = 250
_MAX_JOBS_IN_RUN_LOG = 100


def track_usage_event(
    db: Database,
    *,
    user_id: str,
    event_name: str,
    command: Optional[str] = None,
    result: Optional[str] = None,
    duration_ms: Optional[int] = None,
    jobs_attempted_count: Optional[int] = None,
    jobs_submitted_count: Optional[int] = None,
    jobs_failed_count: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Persist a usage event into local outbox queue."""
    evt = UsageEvent(
        user_id=user_id,
        event_name=event_name,
        command=command,
        result=result,
        duration_ms=duration_ms,
        jobs_attempted_count=jobs_attempted_count,
        jobs_submitted_count=jobs_submitted_count,
        jobs_failed_count=jobs_failed_count,
        metadata=metadata or {},
    )
    with db.get_session() as session:
        UsageEventQueueRepository(session).enqueue(
            user_id=evt.user_id,
            event_name=evt.event_name,
            command=evt.command,
            result=evt.result,
            event_ts=evt.event_ts.replace(tzinfo=None),
            duration_ms=evt.duration_ms,
            payload=evt.to_payload(),
        )


def _read_application_jsonl(log_directory: str, job_id: int) -> List[dict[str, Any]]:
    """Read per-job ``application.jsonl`` (same file JobLogger writes locally)."""
    base = Path(os.path.expanduser(log_directory or "~/.jobcli/logs"))
    log_file = base / f"job_{job_id}" / "application.jsonl"
    if not log_file.is_file():
        return []
    entries: List[dict[str, Any]] = []
    try:
        with log_file.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if len(entries) > _MAX_JSONL_LINES_PER_JOB:
            entries = entries[-_MAX_JSONL_LINES_PER_JOB :]
    except Exception as exc:
        logger.debug("Could not read %s: %s", log_file, exc)
    return entries


def _serialize_db_application_logs(session, job_id: int) -> tuple[list[dict[str, Any]], int]:
    from jobcli.storage.repositories import ApplicationLogRepository

    rows = ApplicationLogRepository(session).get_logs(job_id)
    out: List[dict[str, Any]] = []
    total_tokens: int = 0
    for row in rows:
        metadata = row.log_metadata if isinstance(row.log_metadata, dict) else {}
        # Accumulate token cost from every llm_tokens_used entry
        if row.action == "llm_tokens_used":
            total_tokens += int(metadata.get("tokens", 0) or 0)
        out.append(
            {
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "phase": row.phase.value if row.phase else None,
                "action": row.action,
                "success": row.success,
                "error": row.error,
                "metadata": metadata,
            }
        )
    return out, total_tokens


def build_apply_run_log(
    db: Database,
    *,
    config: "Config",
    user_id: str,
    result: str,
    run_started_at: float,
    jobs_attempted_count: int,
    jobs_submitted_count: int,
    jobs_failed_count: int,
    processed_job_ids: List[int],
    exit_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Build full apply-run log (jobs + local application.jsonl) for analytics upload."""
    user_id = (user_id or "").strip() or "unknown_user"
    run_log: dict[str, Any] = {
        "candidate": user_id,
        "run_started_at": datetime.utcfromtimestamp(run_started_at).isoformat() + "Z",
        "run_ended_at": datetime.utcnow().isoformat() + "Z",
        "result": result,
        "exit_reason": exit_reason,
        "summary": {
            "jobs_attempted": int(jobs_attempted_count or 0),
            "jobs_submitted": int(jobs_submitted_count or 0),
            "jobs_failed": int(jobs_failed_count or 0),
        },
        "jobs": [],
    }

    job_ids = [int(j) for j in processed_job_ids if j is not None][:_MAX_JOBS_IN_RUN_LOG]
    log_directory = config.log_directory or "~/.jobcli/logs"

    run_log["summary"]["total_llm_tokens"] = 0

    with db.get_session() as session:
        jobs = JobRepository(session).list_by_ids(job_ids)
        for job in jobs:
            if job.id is None:
                continue
            status_val = getattr(job.status, "value", str(job.status))
            applied_at = None
            if job.updated_at:
                applied_at = (
                    job.updated_at.isoformat()
                    if hasattr(job.updated_at, "isoformat")
                    else str(job.updated_at)
                )

            db_logs, token_total = _serialize_db_application_logs(session, job.id)
            jsonl_logs = _read_application_jsonl(log_directory, job.id)
            application_log = db_logs if db_logs else jsonl_logs

            # If DB logs were missing, attempt to count tokens from the JSONL file
            if not db_logs and jsonl_logs:
                token_total = sum(
                    int(entry.get("tokens", 0) or 0)
                    for entry in jsonl_logs
                    if entry.get("action") == "llm_tokens_used"
                )

            run_log["summary"]["total_llm_tokens"] = (
                run_log["summary"].get("total_llm_tokens", 0) + token_total
            )

            run_log["jobs"].append(
                {
                    "job_id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "url": job.url,
                    "status": status_val,
                    "applied_at": applied_at,
                    "total_llm_tokens": token_total,
                    "application_log": application_log,
                    "application_log_source": "database" if db_logs else "application.jsonl",
                    "local_log_file": str(
                        Path(os.path.expanduser(log_directory)) / f"job_{job.id}" / "application.jsonl"
                    ),
                }
            )

    try:
        log_dir = Path.home() / ".jobcli" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "candidate_apply_run_log.jsonl"
        with log_file.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(run_log, ensure_ascii=True) + "\n")
        run_log["local_run_log_file"] = str(log_file)
    except Exception as exc:
        logger.debug("Unable to persist apply run log: %s", exc)

    return run_log


def flush_usage_events(db: Database, batch_size: int = 20) -> dict:
    """Flush queued usage events to the central analytics endpoint."""
    with db.get_session() as session:
        repo = UsageEventQueueRepository(session)
        rows = repo.list_ready(limit=batch_size)
        if not rows:
            return {"status": "skipped", "count": 0}
        payload = [row.payload for row in rows]
        try:
            resp = get_client().upload_usage_events(payload)
            repo.mark_sent(rows)
            return {"status": "success", "count": len(rows), "response": resp}
        except Exception as exc:
            logger.warning(
                "Failed to flush %s usage event(s) to %s: %s",
                len(rows),
                get_client()._get_server_url(),
                exc,
            )
            repo.mark_retry(rows, retry_after_seconds=60)
            return {
                "status": "retry_scheduled",
                "count": len(rows),
                "error": str(exc),
            }


def resolve_user_id(username: Optional[str]) -> str:
    """Resolve analytics identity from Whitebox username."""
    text = (username or "").strip()
    return text or "unknown_user"


def track_apply_analytics(
    db: Database,
    config: "Config",
    *,
    result: str,
    run_started_at: float,
    jobs_attempted_count: int,
    jobs_submitted_count: int,
    jobs_failed_count: int,
    processed_job_ids: list[int],
    exit_reason: Optional[str] = None,
    extra_metadata: Optional[dict[str, Any]] = None,
) -> dict:
    """Queue and flush one apply-run analytics event (same payload as ``wboxcli apply`` end)."""
    if not config.tracking_enabled:
        return {"status": "skipped", "reason": "tracking_disabled", "count": 0}

    user_id = resolve_user_id(config.job_board_username)
    md: dict[str, Any] = dict(extra_metadata or {})
    run_log = build_apply_run_log(
        db,
        config=config,
        user_id=user_id,
        result=result,
        run_started_at=run_started_at,
        jobs_attempted_count=jobs_attempted_count,
        jobs_submitted_count=jobs_submitted_count,
        jobs_failed_count=jobs_failed_count,
        processed_job_ids=processed_job_ids,
        exit_reason=exit_reason,
    )
    md["apply_run_log"] = run_log
    md["apply_summary"] = run_log.get("summary", {})

    duration_ms = int(max(0, (time.time() - run_started_at) * 1000))
    track_usage_event(
        db,
        user_id=user_id,
        event_name="cli_command_completed",
        command="apply",
        result=result,
        duration_ms=duration_ms,
        jobs_attempted_count=jobs_attempted_count,
        jobs_submitted_count=jobs_submitted_count,
        jobs_failed_count=jobs_failed_count,
        metadata=md,
    )
    return flush_usage_events(db, batch_size=50)
