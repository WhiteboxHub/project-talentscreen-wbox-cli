"""Rich table for the latest wboxcli apply run (jobs applied in last batch)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_APPLY_RUN_LOG = Path.home() / ".jobcli" / "logs" / "candidate_apply_run_log.jsonl"


def apply_run_log_path() -> Path:
    return _APPLY_RUN_LOG


def load_last_apply_run_log() -> Optional[dict[str, Any]]:
    """Return the most recent apply-run JSON object, or None."""
    path = _APPLY_RUN_LOG
    if not path.is_file():
        return None
    last_line: Optional[str] = None
    try:
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
    except OSError:
        return None
    if not last_line:
        return None
    try:
        data = json.loads(last_line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _status_style(status: str) -> str:
    s = (status or "").lower()
    if s == "submitted":
        return "green"
    if s == "failed":
        return "red"
    if s in ("skipped", "pending"):
        return "yellow"
    return "white"


def build_run_table_from_jobs(jobs: list[dict[str, Any]]) -> Table:
    """Build a Rich table from apply_run_log ``jobs`` entries or job dicts."""
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
        title="Latest application run",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", style="cyan", max_width=36)
    table.add_column("Company", style="white", max_width=24)
    table.add_column("Status", width=12)
    table.add_column("Tokens", style="dim magenta", width=10, justify="right")
    table.add_column("Applied at", style="dim", width=20)

    for idx, job in enumerate(jobs, 1):
        title = (job.get("title") or "Untitled").strip()
        if len(title) > 36:
            title = title[:33] + "..."
        company = (job.get("company") or "—").strip()
        if len(company) > 24:
            company = company[:21] + "..."
        status = str(job.get("status") or "—")
        applied = job.get("applied_at") or job.get("run_ended_at") or "—"
        if hasattr(applied, "strftime"):
            applied = applied.strftime("%Y-%m-%d %H:%M")
        else:
            applied = str(applied)[:19] if applied else "—"
        raw_tokens = job.get("total_llm_tokens") or 0
        tokens_str = f"{int(raw_tokens):,}" if raw_tokens else "—"
        table.add_row(
            str(idx),
            title,
            company,
            f"[{_status_style(status)}]{status}[/]",
            tokens_str,
            applied,
        )
    return table


def _jobs_from_run_log(run_log: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = run_log.get("jobs")
    if isinstance(jobs, list):
        return [j for j in jobs if isinstance(j, dict)]
    return []


def _summary_line(run_log: dict[str, Any]) -> str:
    summary = run_log.get("summary")
    if not isinstance(summary, dict):
        return ""
    attempted = summary.get("jobs_attempted", "?")
    submitted = summary.get("jobs_submitted", "?")
    failed = summary.get("jobs_failed", "?")
    result = run_log.get("result") or ""
    ended = run_log.get("run_ended_at") or ""
    parts = [
        f"Attempted: [bold]{attempted}[/bold]",
        f"Submitted: [green]{submitted}[/green]",
        f"Failed: [red]{failed}[/red]",
    ]
    total_tokens = summary.get("total_llm_tokens")
    if total_tokens:
        parts.append(f"Tokens: [magenta]{int(total_tokens):,}[/magenta]")
    if result:
        parts.append(f"Result: {result}")
    if ended:
        parts.append(f"Ended: [dim]{str(ended)[:19]}[/dim]")
    return "   ".join(parts)


def print_last_apply_run_table(
    console: Console,
    *,
    run_log: Optional[dict[str, Any]] = None,
    show_urls: bool = False,
) -> None:
    """Print latest apply-run jobs table (from arg or candidate_apply_run_log.jsonl)."""
    log = run_log if run_log is not None else load_last_apply_run_log()
    if not log:
        console.print(
            "\n[yellow]No apply run recorded yet.[/yellow] "
            "Run [cyan]wboxcli apply[/cyan] first.\n"
        )
        return

    jobs = _jobs_from_run_log(log)
    if not jobs:
        console.print(
            "\n[yellow]Last apply run has no job details.[/yellow] "
            f"Summary: {_summary_line(log) or 'n/a'}\n"
        )
        return

    table = build_run_table_from_jobs(jobs)
    summary = _summary_line(log)
    console.print()
    console.print(
        Panel(
            table,
            title="[bold green]Latest application run[/bold green]",
            subtitle=summary or None,
            border_style="green",
            expand=True,
        )
    )
    if show_urls:
        console.print("[dim]URLs:[/dim]")
        for job in jobs:
            url = job.get("url") or ""
            if url:
                console.print(f"  [dim]{job.get('title') or 'Job'}:[/dim] {url}")
    console.print()


def print_apply_run_table_for_job_ids(
    session: "Session",
    job_ids: list[int],
    *,
    console: Optional[Console] = None,
    result: Optional[str] = None,
) -> None:
    """Build table from DB job rows (used right after apply when IDs are known)."""
    from jobcli.storage.repositories import JobRepository

    out = console or Console()
    if not job_ids:
        print_last_apply_run_table(out)
        return

    jobs = JobRepository(session).list_by_ids(job_ids)
    rows: list[dict[str, Any]] = []
    submitted = failed = 0
    for job in jobs:
        status_val = getattr(job.status, "value", str(job.status))
        if status_val == "submitted":
            submitted += 1
        elif status_val == "failed":
            failed += 1
        applied_at = None
        if job.updated_at:
            applied_at = (
                job.updated_at.isoformat()
                if hasattr(job.updated_at, "isoformat")
                else str(job.updated_at)
            )
        rows.append(
            {
                "title": job.title,
                "company": job.company,
                "status": status_val,
                "applied_at": applied_at,
                "url": job.url,
            }
        )

    run_log: dict[str, Any] = {
        "jobs": rows,
        "summary": {
            "jobs_attempted": len(job_ids),
            "jobs_submitted": submitted,
            "jobs_failed": failed,
        },
        "result": result or "success",
    }
    print_last_apply_run_table(out, run_log=run_log)
