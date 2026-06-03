"""Post-apply and manual sync upload: knowledge sync + 24h analytics backfill."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from rich.console import Console

if TYPE_CHECKING:
    from jobcli.profile.schemas import Config
    from jobcli.storage.models import Database

logger = logging.getLogger(__name__)

DEFAULT_BACKFILL_HOURS = 24


@dataclass
class ApplyUploadContext:
    """Current apply run counters for run-scoped analytics upload."""

    started_at: float
    result: str
    jobs_attempted_count: int
    jobs_submitted_count: int
    jobs_failed_count: int
    processed_job_ids: list[int]
    exit_reason: Optional[str] = None


@dataclass
class UploadResult:
    """Structured outcome from :func:`run_post_apply_upload`."""

    sync: Optional[dict[str, Any]] = None
    sync_error: Optional[str] = None
    backfill: Optional[dict[str, Any]] = None
    backfill_error: Optional[str] = None
    backfill_skipped: bool = False
    apply_analytics: Optional[dict[str, Any]] = None
    apply_analytics_error: Optional[str] = None
    apply_analytics_skipped: bool = False


def run_post_apply_upload(
    db: "Database",
    config: "Config",
    *,
    apply_context: Optional[ApplyUploadContext] = None,
    run_sync: bool = True,
    run_backfill: bool = True,
    since_hours: int = DEFAULT_BACKFILL_HOURS,
    console: Optional[Console] = None,
) -> UploadResult:
    """Sync knowledge/activity, backfill apply analytics (24h default), optional run event."""
    out = UploadResult()
    term = console or Console()

    if run_sync:
        try:
            from jobcli.sync.manager import SyncManager

            with db.get_session() as sync_session:
                manager = SyncManager(sync_session)
                term.print("\n[dim]Syncing learned patterns and activity with central server...[/dim]")
                out.sync = manager.perform_sync()
        except Exception as exc:
            out.sync_error = str(exc)
            logger.warning("Post-run sync failed: %s", exc, exc_info=True)
            term.print(f"[yellow]⚠ Sync failed: {exc}[/yellow]")

    if run_backfill:
        if not config.tracking_enabled:
            out.backfill_skipped = True
        elif not (config.job_board_username or "").strip():
            out.backfill_skipped = True
            term.print(
                "[yellow]⚠ Analytics backfill skipped — run [cyan]wboxcli login[/cyan] first.[/yellow]"
            )
        else:
            try:
                from jobcli.analytics.backfill import backfill_apply_analytics

                term.print(
                    f"[dim]Uploading apply analytics (last {since_hours}h)...[/dim]"
                )
                out.backfill = backfill_apply_analytics(
                    db,
                    config,
                    since_hours=since_hours,
                )
            except Exception as exc:
                out.backfill_error = str(exc)
                logger.warning("Analytics backfill failed: %s", exc, exc_info=True)
                term.print(f"[yellow]⚠ Analytics backfill failed: {exc}[/yellow]")
    else:
        out.backfill_skipped = True

    if apply_context is not None:
        if not config.tracking_enabled:
            out.apply_analytics_skipped = True
        else:
            try:
                from jobcli.analytics.service import track_apply_analytics

                out.apply_analytics = track_apply_analytics(
                    db,
                    config,
                    result=apply_context.result,
                    run_started_at=apply_context.started_at,
                    jobs_attempted_count=apply_context.jobs_attempted_count,
                    jobs_submitted_count=apply_context.jobs_submitted_count,
                    jobs_failed_count=apply_context.jobs_failed_count,
                    processed_job_ids=apply_context.processed_job_ids,
                    exit_reason=apply_context.exit_reason,
                )
            except Exception as exc:
                out.apply_analytics_error = str(exc)
                logger.warning("Apply analytics upload failed: %s", exc, exc_info=True)
                term.print(f"[yellow]⚠ Apply analytics upload failed: {exc}[/yellow]")
    else:
        out.apply_analytics_skipped = True

    return out


def print_sync_step_results(results: dict[str, Any], console: Optional[Console] = None) -> None:
    """Print knowledge/activity sync lines from :meth:`SyncManager.perform_sync` output."""
    term = console or Console()
    if results.get("status") != "success":
        term.print(f"[red]Sync failed: {results.get('error', 'unknown')}[/red]")
        return

    if results.get("uploaded_answers") or results.get("uploaded_locators"):
        term.print(f"  [green]✓[/green] Uploaded {results['uploaded_answers']} field patterns")
        term.print(f"  [green]✓[/green] Uploaded {results['uploaded_locators']} locators")

    if results.get("downloaded_updates", 0) > 0:
        term.print(f"  [green]✓[/green] Downloaded {results['downloaded_updates']} global updates")
    else:
        term.print("  [blue]i[/blue] Knowledge patterns are up to date.")

    activity_status = results.get("activity_sync_status")
    if activity_status == "success":
        term.print(
            f"  [green]✓[/green] Synced {results.get('activity_count', 0)} job applications to dashboard"
        )
    elif activity_status == "skipped":
        term.print("  [blue]i[/blue] No new application activity to sync.")
    elif activity_status == "failed":
        term.print(
            f"  [yellow]⚠[/yellow] Activity sync failed: {results.get('activity_error')}"
        )

    if results.get("knowledge_sync_status") == "failed":
        term.print(
            f"  [yellow]⚠[/yellow] Knowledge sync failed: {results.get('knowledge_sync_error')}"
        )
    elif results.get("knowledge_sync_status") == "success":
        term.print("  [green]✓[/green] Knowledge patterns synced")

    usage_count = results.get("usage_event_count", 0)
    if results.get("usage_sync_status") == "success" and usage_count:
        term.print(f"  [green]✓[/green] Uploaded {usage_count} usage analytics event(s)")


def print_backfill_step_results(backfill: dict[str, Any], console: Optional[Console] = None) -> None:
    """Print analytics backfill summary."""
    term = console or Console()
    flush = backfill.get("flush") or {}
    attempted = backfill.get("jobs_attempted", 0)
    if flush.get("status") == "success" and flush.get("count", 0):
        term.print(
            f"  [green]✓[/green] Backfill uploaded {flush.get('count', 0)} event(s) "
            f"({attempted} job(s) in snapshot)"
        )
    elif attempted:
        term.print(
            f"  [yellow]⚠[/yellow] Backfill snapshot built ({attempted} jobs) but upload: {flush}"
        )
    else:
        term.print("  [blue]i[/blue] No apply jobs in backfill window to upload.")


def print_upload_status(
    result: UploadResult,
    *,
    console: Optional[Console] = None,
    show_apply_flush: bool = True,
) -> None:
    """Unified upload status for apply end (all exit reasons)."""
    term = console or Console()
    flush_info = result.apply_analytics
    if not show_apply_flush or result.apply_analytics_skipped:
        if result.backfill and not result.backfill_error:
            flush_info = result.backfill.get("flush")
        else:
            return

    if flush_info:
        n = flush_info.get("count", 0)
        if flush_info.get("status") == "success" and n:
            term.print(
                f"[green]✓ Uploaded {n} analytics event(s) to the dashboard API.[/green]"
            )
        elif flush_info.get("status") not in ("skipped",):
            term.print(
                "[yellow]Analytics upload pending or failed — run [cyan]wboxcli sync[/cyan] "
                "and ensure [cyan]sync_server_url[/cyan] matches your frontend API.[/yellow]"
            )
