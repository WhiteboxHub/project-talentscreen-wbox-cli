"""Tests for the discover-time Source allow-list filter.

Covers:

* :func:`jobcli.core.source_filter.normalize_source` — casing + punctuation
  collapse used by the discoverer's allow-list check.
* :func:`jobcli.core.wbox_discoverer._is_allowed_source` — the per-row
  decision the ingest loop makes.
* End-to-end ingest: a mocked WBL API response with mixed-source rows;
  only rows whose ``source`` is in :data:`DEFAULT_SOURCES` reach
  ``JobRepository.create``.
* Schema round-trip through :class:`jobcli.storage.models.JobModel` for
  the ``source`` column.
* Lightweight migration smoke test: an old ``jobs`` table without
  ``source`` gains the column on the next ``create_tables()`` call.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Optional

import pytest
from sqlalchemy import inspect, text

from jobcli.orchestration import wbox_discoverer as wd
from jobcli.profile.schemas import ApplicationStatus, Job
from jobcli.orchestration.source_filter import DEFAULT_SOURCES, normalize_source
from jobcli.orchestration.wbox_discoverer import (
    WboxDiscoverer,
    _ALLOWED_SOURCES_NORMALIZED,
    _is_allowed_source,
)
from jobcli.storage.models import Database
from jobcli.storage.repositories import JobRepository


# ── normalize_source ──────────────────────────────────────────────────


class TestNormalizeSource:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("trueup.io", "trueupio"),
            ("Trueup.Io", "trueupio"),
            ("TRUEUP.IO", "trueupio"),
            ("hiring.cafe", "hiringcafe"),
            ("Hiring-Cafe", "hiringcafe"),
            ("Hiring Cafe", "hiringcafe"),
            ("Hiring/Cafe", "hiringcafe"),
            ("linkedin", "linkedin"),
            ("LinkedIn", "linkedin"),
            ("LINKEDIN", "linkedin"),
            ("jobright", "jobright"),
            ("  jobright  ", "jobright"),
        ],
    )
    def test_collapses_casing_and_punctuation(self, raw, expected):
        assert normalize_source(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "...", "---"])
    def test_empty_and_punctuation_only_return_empty_string(self, raw):
        assert normalize_source(raw) == ""

    def test_alphanumerics_only_are_preserved(self):
        # Hypothetical sources keep their digits.
        assert normalize_source("Job2Right.42") == "job2right42"


# ── _is_allowed_source (discoverer helper) ────────────────────────────


class TestDiscoverSourceFilter:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Jobright", True),
            ("jobright", True),
            ("hiring.cafe", True),
            ("Hiring-Cafe", True),
            ("Hiring Cafe", True),
            ("trueup.io", True),
            ("Trueup.Io", True),
            ("TRUEUPIO", True),
        ],
    )
    def test_allow_list_members_pass(self, raw, expected):
        assert _is_allowed_source(raw) is expected

    @pytest.mark.parametrize(
        "raw",
        ["linkedin", "LinkedIn", "LINKEDIN", "indeed", "workday", "dice", "glassdoor", "lever", "monster"],
    )
    def test_non_allow_list_sources_rejected(self, raw):
        assert _is_allowed_source(raw) is False

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_empty_and_none_rejected(self, raw):
        # Legacy listings discovered before the column existed have
        # ``None`` — they must NOT pass; otherwise the filter would
        # become opt-in instead of unconditional.
        assert _is_allowed_source(raw) is False

    def test_allowed_set_matches_default_sources(self):
        # Guards against accidental drift between the module-level
        # constant and the precomputed frozenset.
        expected = frozenset(normalize_source(s) for s in DEFAULT_SOURCES)
        assert _ALLOWED_SOURCES_NORMALIZED == expected

    def test_allow_list_size_matches_default_sources(self):
        # All default sources normalise to distinct tokens.
        assert len(_ALLOWED_SOURCES_NORMALIZED) == len(DEFAULT_SOURCES)


# ── End-to-end ingest filter ──────────────────────────────────────────


class _FakeJobRepo:
    """In-memory stand-in for :class:`JobRepository`.

    Records every ``create(job)`` call so the test can assert exactly
    which rows survived the source filter.
    """

    def __init__(self) -> None:
        self.created: list[Job] = []
        self.cleared = False

    def clear_job_related_data(self) -> None:
        self.cleared = True

    def create(self, job: Job) -> Job:
        # Mimic the real repo by assigning a fake primary key.
        job.id = len(self.created) + 1
        self.created.append(job)
        return job


class _FakeWBLClient:
    """Stand-in for ``jobcli.sync.client.SyncClient``.

    Yields a single payload page then signals exhaustion with an empty
    ``data`` list on the next call, matching the loop's break condition.
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._calls = 0

    def login(self) -> bool:
        return True

    def fetch_cli_window_listings(
        self,
        *,
        days: int = 0,
        page_size: int = 10000,
        status: str = "open",
        offset: int = 0,
    ) -> dict[str, Any]:
        if self._calls == 0:
            self._calls += 1
            return {"total_in_window": len(self._rows), "data": list(self._rows)}
        # Subsequent calls return an empty page so the pagination loop exits.
        return {"total_in_window": len(self._rows), "data": []}


@pytest.fixture
def mixed_rows() -> list[dict[str, Any]]:
    """Six rows: 4 allowed sources, 1 disallowed, 1 missing source."""
    return [
        {
            "id": 1,
            "job_url": "https://example.com/jobs/linkedin-1",
            "title": "LinkedIn Job",
            "company_name": "Acme",
            "source": "linkedin",
            "status": "open",
        },
        {
            "id": 2,
            "job_url": "https://example.com/jobs/jobright-2",
            "title": "JobRight Job",
            "company_name": "Beta",
            "source": "jobright",
            "status": "open",
        },
        {
            "id": 3,
            "job_url": "https://example.com/jobs/indeed-3",
            "title": "Indeed Job",
            "company_name": "Gamma",
            "source": "indeed",
            "status": "open",
        },
        {
            "id": 4,
            "job_url": "https://example.com/jobs/hiringcafe-4",
            "title": "Hiring Cafe Job",
            "company_name": "Delta",
            "source": "hiring.cafe",
            "status": "open",
        },
        {
            "id": 5,
            "job_url": "https://example.com/jobs/legacy-5",
            "title": "Legacy Row",
            "company_name": "Epsilon",
            # No "source" key at all — simulates legacy rows.
            "status": "open",
        },
        {
            "id": 6,
            "job_url": "https://example.com/jobs/trueup-6",
            "title": "TrueUp Job",
            "company_name": "Zeta",
            "source": "Trueup.Io",  # mixed-case to exercise normalisation
            "status": "open",
        },
    ]


def _make_discoverer(job_repo: _FakeJobRepo) -> WboxDiscoverer:
    """Bypass ``__init__`` and inject just the attrs ``_discover_api`` needs."""
    inst = WboxDiscoverer.__new__(WboxDiscoverer)
    inst.session = None  # unused along the success path
    inst.logger = None
    inst.job_repo = job_repo
    inst.username = "u@example.com"
    inst.password = "pw"
    inst._explicit_config = None
    return inst


class TestDiscoverApiIngestFilter:
    """Drives ``_discover_api`` against a fake WBL client + repo."""

    def test_only_allowed_sources_reach_repo(
        self,
        mixed_rows: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = _FakeWBLClient(mixed_rows)
        monkeypatch.setattr(wd, "get_client", lambda *_a, **_kw: fake_client)
        # ``_discover_api`` calls ``self._merged_config()`` — short-circuit
        # it so we don't pull from the real config DB.
        monkeypatch.setattr(
            WboxDiscoverer,
            "_merged_config",
            lambda self: None,  # value never inspected by the success path
        )

        repo = _FakeJobRepo()
        inst = _make_discoverer(repo)
        imported = inst._discover_api()

        # 3 allowed rows: jobright, hiring.cafe, trueup.io (linkedin excluded).
        assert len(imported) == 3
        assert len(repo.created) == 3
        kept_sources = {normalize_source(j.source) for j in repo.created}
        assert kept_sources == {"jobright", "hiringcafe", "trueupio"}

    def test_disallowed_and_missing_sources_dropped(
        self,
        mixed_rows: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_client = _FakeWBLClient(mixed_rows)
        monkeypatch.setattr(wd, "get_client", lambda *_a, **_kw: fake_client)
        monkeypatch.setattr(
            WboxDiscoverer, "_merged_config", lambda self: None
        )

        repo = _FakeJobRepo()
        inst = _make_discoverer(repo)
        inst._discover_api()

        kept_titles = {j.title for j in repo.created}
        # LinkedIn, Indeed (disallowed source), and Legacy row (no source) must
        # never reach the repo.
        assert "LinkedIn Job" not in kept_titles
        assert "Indeed Job" not in kept_titles
        assert "Legacy Row" not in kept_titles

    def test_clear_called_before_ingest(
        self,
        mixed_rows: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The repo must be wiped before re-ingest so a previous run's
        # disallowed sources don't linger after the filter is added.
        fake_client = _FakeWBLClient(mixed_rows)
        monkeypatch.setattr(wd, "get_client", lambda *_a, **_kw: fake_client)
        monkeypatch.setattr(
            WboxDiscoverer, "_merged_config", lambda self: None
        )

        repo = _FakeJobRepo()
        inst = _make_discoverer(repo)
        inst._discover_api()

        assert repo.cleared is True

    def test_all_disallowed_yields_empty_import(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            {
                "id": 1,
                "job_url": "https://example.com/jobs/indeed-1",
                "title": "Indeed Job",
                "source": "indeed",
                "status": "open",
            },
            {
                "id": 2,
                "job_url": "https://example.com/jobs/workday-2",
                "title": "Workday Job",
                "source": "workday",
                "status": "open",
            },
        ]
        fake_client = _FakeWBLClient(rows)
        monkeypatch.setattr(wd, "get_client", lambda *_a, **_kw: fake_client)
        monkeypatch.setattr(
            WboxDiscoverer, "_merged_config", lambda self: None
        )

        repo = _FakeJobRepo()
        inst = _make_discoverer(repo)
        imported = inst._discover_api()

        assert imported == []
        assert repo.created == []


# ── Schema round-trip ─────────────────────────────────────────────────


@pytest.fixture
def fresh_db():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return db


class TestSchemaRoundTrip:
    def test_job_with_source_persists_and_reloads(self, fresh_db):
        session = fresh_db.get_session()
        repo = JobRepository(session)
        created = repo.create(
            Job(
                url="https://example.com/jobs/123",
                title="Senior ML Engineer",
                status=ApplicationStatus.PENDING,
                source="linkedin",
            )
        )
        assert created.id is not None

        loaded = repo.get(created.id)
        assert loaded is not None
        assert loaded.source == "linkedin"
        session.close()

    def test_job_without_source_defaults_to_none(self, fresh_db):
        session = fresh_db.get_session()
        repo = JobRepository(session)
        created = repo.create(
            Job(
                url="https://example.com/jobs/456",
                title="Backend Engineer",
                status=ApplicationStatus.PENDING,
            )
        )
        loaded = repo.get(created.id)
        assert loaded is not None
        assert loaded.source is None
        session.close()


# ── Migration smoke test ──────────────────────────────────────────────


class TestMigration:
    """Verify that an old-schema SQLite file gets a ``source`` column
    appended automatically by ``Database._migrate_sqlite_schema``.
    """

    def test_old_jobs_table_without_source_gets_column_added(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            old_db = Database(f"sqlite:///{path}")
            with old_db.engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS jobs"))
                conn.execute(
                    text(
                        """
                        CREATE TABLE jobs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            url VARCHAR(1000) NOT NULL UNIQUE,
                            title VARCHAR(500)
                        )
                        """
                    )
                )
            cols_before = {c["name"] for c in inspect(old_db.engine).get_columns("jobs")}
            assert "source" not in cols_before

            migrated = Database(f"sqlite:///{path}")
            migrated.create_tables()

            cols_after = {c["name"] for c in inspect(migrated.engine).get_columns("jobs")}
            assert "source" in cols_after
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
