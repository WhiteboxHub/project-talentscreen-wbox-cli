"""DB reset, config-driven discovery, and clear-jobs behavior."""

from __future__ import annotations

from pathlib import Path
import os
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from jobcli.core.schemas import ApplicationStatus, Config, Job
from jobcli.storage.models import ApplicationLogModel, Database
from jobcli.storage.repositories import ConfigRepository, JobRepository, UserDataRepository
from jobcli.core.schemas import ExecutionPhase, ResumeData, PersonalInfo
from jobcli.core.wbox_discoverer import WboxDiscoverer
from jobcli.sync.client import SyncClient


@pytest.fixture
def isolated_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Dedicated SQLite file; DATABASE_PATH points here for the test process."""
    dbf = tmp_path / "jobcli_isolated.db"
    monkeypatch.setenv("DATABASE_PATH", str(dbf))
    monkeypatch.chdir(tmp_path)
    return dbf


def test_clear_jobs_preserves_config_and_memory_deletes_logs(isolated_db_path: Path) -> None:
    db = Database(f"sqlite:///{isolated_db_path.as_posix()}")
    db.create_tables()

    with db.get_session() as session:
        cfg_repo = ConfigRepository(session)
        cfg_repo.set("job_board_username", "keepme")
        job = Job(
            url="https://boards.greenhouse.io/acme/jobs/1",
            title="T",
            status=ApplicationStatus.PENDING,
            is_cli_friendly=True,
            is_already_applied=False,
        )
        jm = JobRepository(session).create(job)
        session.add(
            ApplicationLogModel(
                job_id=jm.id,
                phase=ExecutionPhase.RULES,
                action="click",
                success=True,
                error=None,
            )
        )
        ud = UserDataRepository(session)
        resume = ResumeData(personal=PersonalInfo(first_name="A", last_name="B", email="a@b.com"))
        ud.save_resume(resume)
        session.commit()

    assert isolated_db_path.exists()

    from jobcli.cli.main import db_clear_jobs

    db_clear_jobs(force=True)

    with db.get_session() as session:
        assert ConfigRepository(session).get("job_board_username") == "keepme"
        assert JobRepository(session).get_by_url("https://boards.greenhouse.io/acme/jobs/1") is None
        assert session.query(ApplicationLogModel).count() == 0
        assert UserDataRepository(session).get_resume() is not None


def test_db_reset_removes_data_and_sidecars(isolated_db_path: Path) -> None:
    wal = Path(f"{isolated_db_path}-wal")
    wal.write_bytes(b"x")

    db = Database(f"sqlite:///{isolated_db_path.as_posix()}")
    db.create_tables()
    with db.get_session() as session:
        ConfigRepository(session).save_config(
            Config(job_board_username="gone", job_board_password="secret", sync_server_url="http://x/api")
        )
        session.commit()
    db.engine.dispose()

    from jobcli.cli import main as main_mod

    main_mod._run_db_reset(force=True)

    assert isolated_db_path.exists()
    assert not wal.exists()

    db2 = Database(f"sqlite:///{isolated_db_path.as_posix()}")
    db2.create_tables()
    with db2.get_session() as session:
        c = ConfigRepository(session).get_all()
        assert c.job_board_username is None
        assert c.job_board_password is None


def test_resolve_active_sqlite_database_path_respects_database_path(
    isolated_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobcli.cli.main import resolve_active_sqlite_database_path

    monkeypatch.setenv("DATABASE_PATH", str(isolated_db_path))
    assert resolve_active_sqlite_database_path() == isolated_db_path.resolve()


def test_wbox_discoverer_api_uses_explicit_config_for_sync_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JOBCLI_USERNAME", raising=False)
    monkeypatch.delenv("JOBCLI_PASSWORD", raising=False)
    monkeypatch.delenv("JOBCLI_SYNC_SERVER_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_API_URL", raising=False)

    db = Database("sqlite:///:memory:")
    db.create_tables()

    cfg = Config(
        job_board_username="sqlite_user",
        job_board_password="sqlite_pass",
        sync_server_url="http://127.0.0.1:9999/api",
    )
    captured: dict[str, str] = {}

    def _capture_fetch(self: SyncClient, **kwargs: object) -> dict:
        captured["base"] = self._get_server_url()
        return {"data": []}

    def _login_ok(self: SyncClient) -> bool:
        self.token = "tok"
        self.candidate_id = 1
        return True

    with patch.object(SyncClient, "login", _login_ok):
        with patch.object(SyncClient, "fetch_cli_window_listings", _capture_fetch):
            with db.get_session() as session:
                WboxDiscoverer(session, config=cfg).discover(legacy_ui=False)

    assert captured.get("base") == "http://127.0.0.1:9999/api"


def test_discover_cli_missing_credentials_message(isolated_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Discover exits before hitting the network when no credentials are configured."""

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    for k in list(os.environ.keys()):
        if k.upper().startswith("JOBCLI_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_API_URL", raising=False)

    from jobcli.cli.main import app

    r = CliRunner().invoke(app, ["discover"])
    assert r.exit_code == 1
    out = (r.stdout or "") + (r.stderr or "")
    assert "Missing WBL credentials or API URL. Run setup or login first." in out
