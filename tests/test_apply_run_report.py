import json

from jobcli.utils.apply_run_report import (
    build_run_table_from_jobs,
    load_last_apply_run_log,
)


def test_build_run_table_from_jobs_has_rows():
    table = build_run_table_from_jobs(
        [
            {
                "title": "Engineer",
                "company": "Acme",
                "status": "submitted",
                "applied_at": "2024-01-01T12:00:00",
            }
        ]
    )
    assert table.row_count == 1


def test_load_last_apply_run_log_reads_last_line(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    path = log_dir / "candidate_apply_run_log.jsonl"
    path.write_text(
        json.dumps({"jobs": [], "summary": {"jobs_attempted": 1}}) + "\n"
        + json.dumps(
            {
                "jobs": [{"title": "B", "company": "Co", "status": "failed"}],
                "summary": {"jobs_attempted": 2},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobcli.utils.apply_run_report._APPLY_RUN_LOG",
        path,
    )
    data = load_last_apply_run_log()
    assert data is not None
    assert data["summary"]["jobs_attempted"] == 2
    assert data["jobs"][0]["title"] == "B"
