"""Discovery logic for Whitebox Learning — API-first via /positions/cli_window."""

import os
import time
from datetime import datetime
from typing import Any, List, Optional

# Key on each WBL API row that carries the dashboard "Source" column
# (e.g. ``linkedin``, ``jobright``, ``hiring.cafe``, ``trueup.io``).
# Confirmed via ``scripts/probe_source_key.py``; values arrive lowercased
# from the server.
_SOURCE_API_KEY = "source"

from playwright.sync_api import sync_playwright
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jobcli.core.logger import JobLogger, global_logger
from jobcli.core.url_normalize import normalize_job_url
from jobcli.core.schemas import ApplicationStatus, Config, Job
from jobcli.core.constants import job_url_is_cli_friendly
from jobcli.orchestration.source_filter import DEFAULT_SOURCES, normalize_source
from jobcli.storage.repositories import JobRepository
from jobcli.sync.client import get_client


# Precomputed normalised allow-list for the discover-time Source filter.
# Built once at import (the values in ``DEFAULT_SOURCES`` are constants).
_ALLOWED_SOURCES_NORMALIZED: frozenset[str] = frozenset(
    normalize_source(s) for s in DEFAULT_SOURCES
)


def _is_allowed_source(source: Optional[str]) -> bool:
    """Return True if the row's ``source`` is in the hardcoded allow-list.

    Rows with a missing/empty source are rejected so legacy listings that
    pre-date the column (or any future row that the server returns without
    a source tag) can't sneak into the local DB.
    """
    if not source:
        return False
    return normalize_source(source) in _ALLOWED_SOURCES_NORMALIZED


def _parse_listing_datetime(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None) if val.tzinfo else val
    if isinstance(val, str):
        s = val.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None
    return None


class WboxDiscoverer:
    """Discover jobs from Whitebox Learning (default: WBL API)."""

    def __init__(
        self,
        session: Session,
        logger: Optional[JobLogger] = None,
        config: Optional[Config] = None,
    ) -> None:
        self.session = session
        self.logger = logger or global_logger
        self.job_repo = JobRepository(session)
        self._explicit_config = config

        self.login_url = os.getenv("WBOX_LOGIN_URL", "https://whitebox-learning.com/login")
        self.dashboard_url = os.getenv("WBOX_DASHBOARD_URL", "https://whitebox-learning.com/user_dashboard")

        cfg = self._merged_config()
        self.username = (cfg.job_board_username or os.getenv("JOBCLI_USERNAME") or "").strip() or None
        self.password = cfg.job_board_password or os.getenv("JOBCLI_PASSWORD") or None

    def _merged_config(self) -> Config:
        if self._explicit_config is not None:
            return self._explicit_config
        from jobcli.cli.main import get_config

        return get_config()

    def discover(self, headless: bool = True, legacy_ui: bool = False) -> List[Job]:
        """Import jobs from WBL.

        Default: ``GET /positions/cli_window`` (no Playwright).
        Legacy UI scrape: set env ``WBOX_DISCOVER_MODE=browser`` or pass ``legacy_ui=True``.
        """
        use_browser = legacy_ui or os.getenv("WBOX_DISCOVER_MODE", "").strip().lower() == "browser"
        if use_browser:
            return self._discover_playwright(headless=headless)
        return self._discover_api()

    def _discover_api(self) -> List[Job]:
        if not self.username or not self.password:
            if self.logger:
                self.logger.error("Missing JOBCLI_USERNAME / JOBCLI_PASSWORD for WBL API discovery")
            return []

        client = get_client(self._merged_config())
        if not client.login():
            # Build a remediation-aware error message from the per-candidate
            # errors classified by ``SyncClient.login()`` (creds vs TLS vs net).
            from jobcli.sync.client import _format_login_errors

            detail = _format_login_errors(getattr(client, "last_login_errors", []) or [])
            raise RuntimeError(f"WBL login failed.\n{detail}")

        days_raw = (os.getenv("JOBCLI_DISCOVER_DAYS") or "0").strip()
        try:
            days = int(days_raw)
        except ValueError:
            days = 0
        if days < 0:
            days = 0

        ps_raw = (os.getenv("JOBCLI_DISCOVER_PAGE_SIZE") or "10000").strip()
        try:
            page_size = int(ps_raw)
        except ValueError:
            page_size = 10000
        page_size = min(max(1, page_size), 10000)

        status = (os.getenv("JOBCLI_DISCOVER_STATUS") or "open").strip() or "open"

        rows: List[dict] = []
        offset = 0
        total_in_window: Optional[int] = None
        while True:
            payload = client.fetch_cli_window_listings(
                days=days,
                page_size=page_size,
                status=status,
                offset=offset,
            )
            if total_in_window is None:
                try:
                    total_in_window = int(payload.get("total_in_window") or 0)
                except (TypeError, ValueError):
                    total_in_window = 0
            batch = payload.get("data") or []
            if not batch:
                break
            rows.extend(batch)
            offset += len(batch)
            if len(batch) < page_size or offset >= (total_in_window or 0):
                break

        self.job_repo.clear_job_related_data()

        imported: List[Job] = []
        seen: set[str] = set()
        duplicate_rows = 0
        integrity_failures = 0
        skipped_source = 0
        for row in rows:
            raw_url = (row.get("job_url") or "").strip()
            if not raw_url:
                continue
            norm = normalize_job_url(raw_url)
            if not norm:
                continue
            if norm in seen:
                duplicate_rows += 1
                continue
            seen.add(norm)

            # Hard-filter on the WBL "Source" column: rows whose source is
            # not in the canonical allow-list never touch the local DB.
            raw_source = row.get(_SOURCE_API_KEY)
            if not _is_allowed_source(raw_source):
                skipped_source += 1
                continue

            listing_at = _parse_listing_datetime(row.get("created_at")) or datetime.utcnow()
            api_applied = bool(row.get("already_applied", False))
            friendly = job_url_is_cli_friendly(norm)

            if api_applied:
                st = ApplicationStatus.SUBMITTED
                already = True
            elif friendly:
                st = ApplicationStatus.PENDING
                already = False
            else:
                st = ApplicationStatus.SKIPPED
                already = False

            job = Job(
                url=norm,
                normalized_url=norm,
                title=row.get("title") or "Untitled",
                company=row.get("company_name"),
                status=st,
                scan_source="wbox_api",
                listing_created_at=listing_at,
                is_cli_friendly=friendly,
                is_already_applied=already,
                source_status=str(row.get("status") or ""),
                external_id=str(row.get("id")) if row.get("id") is not None else None,
                source=(str(row.get(_SOURCE_API_KEY)).strip() or None)
                if row.get(_SOURCE_API_KEY) is not None
                else None,
            )
            try:
                imported.append(self.job_repo.create(job))
            except IntegrityError:
                self.session.rollback()
                integrity_failures += 1
                continue

        if self.logger:
            self.logger.info(
                f"Imported {len(imported)} job(s) from WBL cli_window API "
                f"(days={days}, status={status!r}, fetched_rows={len(rows)}, "
                f"deduped={duplicate_rows}, integrity_skips={integrity_failures}, "
                f"skipped_source={skipped_source}, "
                f"allowed_sources={','.join(DEFAULT_SOURCES)})"
            )
        return imported

    def _discover_playwright(self, headless: bool = True) -> List[Job]:
        """Legacy: scrape user_dashboard AG Grid (Playwright)."""
        discovered_jobs: List[Job] = []

        if not self.username or not self.password:
            if self.logger:
                self.logger.error("Missing credentials for Wbox login")
            return []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--start-maximized"])
            context = browser.new_context(
                viewport=None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            try:
                if self.logger:
                    self.logger.info(f"Logging into {self.login_url}")

                page.goto(self.login_url)
                page.fill('input[name="email"]', self.username)
                page.fill('input[name="password"]', self.password)
                page.click('button:has-text("Login")')
                page.wait_for_url("**/user_dashboard**", timeout=30000)

                if self.logger:
                    self.logger.info("Successfully logged in, navigating to dashboard")

                page.goto(self.dashboard_url)
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(500)
                page.wait_for_selector(".ag-center-cols-container", timeout=30000)

                if self.logger:
                    self.logger.info("Extracting job links from grid (scrolling through all rows)")

                time.sleep(2)
                discovered_urls = set()

                for _ in range(50):
                    links = page.query_selector_all("a.font-semibold.text-blue-600")

                    for link in links:
                        try:
                            url = link.get_attribute("href")
                            title = link.inner_text().strip()
                            canonical = normalize_job_url(url)

                            if canonical and title and canonical not in discovered_urls:
                                discovered_urls.add(canonical)
                                existing = self.job_repo.get_by_url(canonical)
                                if not existing:
                                    # Pull the surrounding ag-grid row first
                                    # so we can apply the hard source filter
                                    # before persisting anything.
                                    row_company: Optional[str] = None
                                    row_source: Optional[str] = None
                                    try:
                                        row_handle = link.evaluate_handle(
                                            "el => el.closest(\".ag-row\")"
                                        )
                                        if row_handle:
                                            row_el = row_handle.as_element()
                                            company_cell = row_el.query_selector('[col-id="company"]')
                                            if company_cell:
                                                row_company = company_cell.inner_text().strip() or None
                                            source_cell = row_el.query_selector('[col-id="source"]')
                                            if source_cell:
                                                src_text = source_cell.inner_text().strip()
                                                if src_text:
                                                    row_source = src_text.lower()
                                    except Exception:
                                        pass

                                    # Hard-filter on Source; rows whose
                                    # source isn't in the allow-list (or
                                    # whose grid didn't expose a source
                                    # cell) never reach the local DB.
                                    if not _is_allowed_source(row_source):
                                        discovered_urls.discard(canonical)
                                        continue

                                    job = Job(
                                        url=canonical,
                                        title=title,
                                        status=ApplicationStatus.PENDING,
                                        scan_source="wbox",
                                        company=row_company,
                                        source=row_source,
                                    )
                                    self.job_repo.create(job)
                                    discovered_jobs.append(job)
                        except Exception:
                            continue

                    try:
                        page.evaluate(
                            "() => { const vp = document.querySelector(\".ag-body-viewport\"); if (vp) vp.scrollBy(0, 1200); }"
                        )
                        page.wait_for_timeout(600)
                    except Exception:
                        break

                if self.logger:
                    self.logger.info(f"Discovered {len(discovered_jobs)} new jobs")

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Discovery failed: {str(e)}")
                raise e
            finally:
                browser.close()

        return discovered_jobs

    def open_interactive(self) -> None:
        """Open dashboard in an interactive browser window."""
        if not self.username or not self.password:
            raise ValueError("Missing credentials for Wbox login")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
            context = browser.new_context(
                viewport=None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            page.goto(self.login_url)
            page.fill('input[name="email"]', self.username)
            page.fill('input[name="password"]', self.password)
            page.click('button:has-text("Login")')
            page.wait_for_url("**/user_dashboard**", timeout=30000)

            print("\n[bold green]✓ Dashboard opened and logged in![/bold green]")
            print("The browser will remain open until you close the terminal or interrupt this command.")

            page.wait_for_event("close", timeout=0)
