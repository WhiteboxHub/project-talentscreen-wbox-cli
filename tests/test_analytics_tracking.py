from datetime import datetime

from jobcli.analytics.service import flush_usage_events, track_usage_event
from jobcli.analytics.usage import sanitize_event_payload
from jobcli.storage.models import Database
from jobcli.storage.repositories import AnalyticsEventRepository, UsageEventQueueRepository


def _db(tmp_path):
    db_file = tmp_path / "analytics_test.db"
    db = Database(f"sqlite:///{db_file.as_posix()}")
    db.create_tables()
    return db


def test_sanitize_payload_removes_sensitive_keys():
    payload = {
        "user_id": "alice@example.com",
        "event_name": "cli_command_completed",
        "password": "secret",
        "metadata": {"openai_api_key": "sk-123", "safe": "ok"},
    }
    clean = sanitize_event_payload(payload)
    assert "password" not in clean
    assert "openai_api_key" not in clean["metadata"]
    assert clean["metadata"]["safe"] == "ok"


def test_analytics_per_user_summary_counts(tmp_path):
    db = _db(tmp_path)
    with db.get_session() as session:
        repo = AnalyticsEventRepository(session)
        repo.ingest_events(
            [
                {
                    "user_id": "u1",
                    "event_name": "cli_command_completed",
                    "event_ts": datetime.now(),
                    "jobs_attempted_count": 3,
                    "jobs_submitted_count": 2,
                    "jobs_failed_count": 1,
                    "metadata": {},
                },
                {
                    "user_id": "u1",
                    "event_name": "cli_command_completed",
                    "event_ts": datetime.now(),
                    "jobs_attempted_count": 2,
                    "jobs_submitted_count": 1,
                    "jobs_failed_count": 1,
                    "metadata": {},
                },
            ]
        )
        summary = repo.per_user_summary("u1")
        assert summary["jobs_attempted"] == 5
        assert summary["jobs_submitted"] == 3
        assert summary["jobs_failed"] == 2


def test_usage_queue_flush_marks_sent(monkeypatch, tmp_path):
    db = _db(tmp_path)
    track_usage_event(
        db,
        user_id="u1",
        event_name="cli_command_completed",
        command="login",
        result="success",
        metadata={"safe": True},
    )

    class StubClient:
        def upload_usage_events(self, events):
            assert len(events) == 1
            return {"status": "success", "ingested": 1}

    monkeypatch.setattr("jobcli.analytics.service.get_client", lambda: StubClient())
    out = flush_usage_events(db, batch_size=20)
    assert out["status"] == "success"

    with db.get_session() as session:
        rows = UsageEventQueueRepository(session).list_ready(limit=10)
        assert rows == []
