"""Tests for post-apply upload pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jobcli.cli.upload_pipeline import (
    DEFAULT_BACKFILL_HOURS,
    ApplyUploadContext,
    run_post_apply_upload,
)
from jobcli.profile.schemas import Config
from jobcli.storage.models import Database


def _db(tmp_path):
    db_file = tmp_path / "pipeline_test.db"
    db = Database(f"sqlite:///{db_file.as_posix()}")
    db.create_tables()
    return db


def _config(*, tracking: bool = True, username: str = "alice@example.com") -> Config:
    return Config(
        job_board_username=username if username else None,
        tracking_enabled=tracking,
        sync_server_url="https://api.example.com/api",
    )


def test_default_backfill_hours_is_24():
    assert DEFAULT_BACKFILL_HOURS == 24


def test_pipeline_runs_sync_then_backfill_with_24h(tmp_path):
    db = _db(tmp_path)
    config = _config()
    sync_results = {"status": "success", "activity_count": 1}
    backfill_results = {"jobs_attempted": 2, "flush": {"status": "success", "count": 1}}

    with patch("jobcli.sync.manager.SyncManager") as mock_mgr_cls:
        mock_mgr_cls.return_value.perform_sync.return_value = sync_results
        with patch(
            "jobcli.analytics.backfill.backfill_apply_analytics",
            return_value=backfill_results,
        ) as mock_backfill:
            result = run_post_apply_upload(
                db,
                config,
                apply_context=None,
                since_hours=24,
                console=MagicMock(),
            )

    assert result.sync == sync_results
    mock_backfill.assert_called_once()
    assert mock_backfill.call_args.kwargs["since_hours"] == 24
    assert result.apply_analytics_skipped is True


def test_pipeline_runs_apply_analytics_when_context_set(tmp_path):
    db = _db(tmp_path)
    config = _config()
    apply_flush = {"status": "success", "count": 1}

    with patch("jobcli.sync.manager.SyncManager") as mock_mgr_cls:
        mock_mgr_cls.return_value.perform_sync.return_value = {"status": "success"}
        with patch(
            "jobcli.analytics.backfill.backfill_apply_analytics",
            return_value={"jobs_attempted": 0, "flush": {"status": "skipped", "count": 0}},
        ):
            with patch(
                "jobcli.analytics.service.track_apply_analytics",
                return_value=apply_flush,
            ) as mock_track:
                ctx = ApplyUploadContext(
                    started_at=1000.0,
                    result="interrupted",
                    jobs_attempted_count=1,
                    jobs_submitted_count=0,
                    jobs_failed_count=1,
                    processed_job_ids=[42],
                    exit_reason="Ctrl+C between jobs",
                )
                result = run_post_apply_upload(
                    db,
                    config,
                    apply_context=ctx,
                    since_hours=24,
                    console=MagicMock(),
                )

    mock_track.assert_called_once()
    assert mock_track.call_args.kwargs["result"] == "interrupted"
    assert mock_track.call_args.kwargs["processed_job_ids"] == [42]
    assert result.apply_analytics == apply_flush


def test_pipeline_skips_backfill_when_disabled(tmp_path):
    db = _db(tmp_path)
    config = _config()

    with patch("jobcli.sync.manager.SyncManager") as mock_mgr_cls:
        mock_mgr_cls.return_value.perform_sync.return_value = {"status": "success"}
        with patch("jobcli.analytics.backfill.backfill_apply_analytics") as mock_backfill:
            result = run_post_apply_upload(
                db,
                config,
                run_backfill=False,
                console=MagicMock(),
            )

    mock_backfill.assert_not_called()
    assert result.backfill_skipped is True


def test_pipeline_sync_failure_isolated(tmp_path):
    db = _db(tmp_path)
    config = _config()

    with patch("jobcli.sync.manager.SyncManager") as mock_mgr_cls:
        mock_mgr_cls.return_value.perform_sync.side_effect = RuntimeError("network down")
        with patch(
            "jobcli.analytics.backfill.backfill_apply_analytics",
            return_value={"jobs_attempted": 0, "flush": {"status": "skipped", "count": 0}},
        ) as mock_backfill:
            result = run_post_apply_upload(db, config, console=MagicMock())

    assert result.sync_error == "network down"
    mock_backfill.assert_called_once()


def test_backfill_module_defaults_24_hours():
    import inspect

    from jobcli.analytics import backfill as bf

    sig_collect = inspect.signature(bf.collect_apply_job_ids)
    sig_backfill = inspect.signature(bf.backfill_apply_analytics)
    assert sig_collect.parameters["since_hours"].default == 24
    assert sig_backfill.parameters["since_hours"].default == 24
