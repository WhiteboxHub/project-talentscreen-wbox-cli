"""Extension resolution and validation helpers.

Centralises all the logic for locating, validating, and verifying the
TalentScreen browser extension so that ``cli/main.py``,
``cli/interactive.py``, and ``orchestration/engine.py`` can import from
one place instead of duplicating path-resolution code.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Host fragments for ATS job pages (aligned with TalentScreen manifest).
ATS_HOST_FRAGMENTS: tuple[str, ...] = (
    "myworkdayjobs.com",
    "greenhouse.io",
    "lever.co",
    "smartrecruiters.com",
    "applytojob.com",
    "bamboohr.com",
    "icims.com",
    "indeed.com",
    "linkedin.com",
    "workable.com",
    "taleo.net",
    "successfactors.com",
    "successfactors.eu",
    "personio.com",
    "personio.de",
    "recruitee.com",
    "teamtailor.com",
    "ultipro.com",
    "myultipro.com",
    "ukg.com",
    "paycomonline.net",
    "paychex.com",
    "oraclecloud.com",
    "brassring.com",
    "ashbyhq.com",
    "workforcenow.adp.com",
    "jobvite.com",
    "rippling-ats.com",
)

#: Default subdirectory under ``~/.jobcli`` where older installs unpacked
#: the extension via CRX download.
_LEGACY_UNPACK_DIR = Path.home() / ".jobcli" / "extension_unpacked"

#: Relative path from this file to the project root's ``bin/`` folder
#: where ``install.sh`` / ``install.ps1`` clone the extension repo.
_BUNDLED_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "bin"
    / "project-talentscreen-autofill-extension"
)

#: Sibling repo when developing wbox-cli + extension side-by-side (``wbox/`` layout).
_SIBLING_EXT_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "project-talentscreen-autofill-extension"
)


def _has_manifest(directory: Path) -> bool:
    """Return True if *directory* exists and contains a ``manifest.json``."""
    return directory.is_dir() and (directory / "manifest.json").is_file()


def is_likely_ats_frame_url(url: str) -> bool:
    """Return True if *url* looks like a job-application page (not captcha CDN, etc.)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return any(fragment in host for fragment in ATS_HOST_FRAGMENTS)


def chromium_extension_launch_args(ext_dir: str) -> list[str]:
    """Chrome flags to load exactly one unpacked extension directory."""
    return [
        f"--disable-extensions-except={ext_dir}",
        f"--load-extension={ext_dir}",
    ]


def read_extension_manifest_version(ext_dir: str) -> Optional[str]:
    """Return ``manifest.json`` version string, or ``None`` if unreadable."""
    try:
        manifest_path = Path(ext_dir) / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = data.get("version")
        return str(version) if version is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_extension_dir(configured_path: Optional[str] = None) -> Optional[str]:
    """Return the first valid extension directory, or ``None``.

    Candidate order:
    1. ``JOBCLI_EXTENSION_PATH`` environment variable.
    2. *configured_path* (``config.extension_path`` from SQLite).
    3. ``~/.jobcli/extension_unpacked`` — legacy fallback.
    4. ``<project-root>/bin/project-talentscreen-autofill-extension`` — installer clone.
    5. Sibling ``project-talentscreen-autofill-extension`` (local dev monorepo).

    A directory is valid only if it contains ``manifest.json``.
    """
    candidates: list[tuple[str, Path]] = []

    env_path = (os.getenv("JOBCLI_EXTENSION_PATH") or "").strip()
    if env_path:
        candidates.append(("JOBCLI_EXTENSION_PATH", Path(env_path).expanduser()))

    if configured_path and configured_path.strip():
        candidates.append(("config.extension_path", Path(configured_path).expanduser()))

    candidates.append(("~/.jobcli/extension_unpacked", _LEGACY_UNPACK_DIR))
    candidates.append(("bundled bin directory", _BUNDLED_DIR))
    candidates.append(("sibling extension repo", _SIBLING_EXT_DIR))

    for _source, path in candidates:
        if _has_manifest(path):
            return str(path.resolve())

    return None


def verify_extension_in_browser(
    ext_dir: str,
    email: str,
    password: str,
) -> tuple[bool, bool, str]:
    """Launch a headless browser, load the extension, and attempt login.

    Returns ``(login_ok, extension_ok, error_message)``.

    * ``login_ok``      — credentials were accepted (redirected to dashboard).
    * ``extension_ok``  — Playwright detected a service-worker or background
                          page from the extension (proves it registered).
    * ``error_message`` — empty on success; human-readable on failure.
    """
    try:
        from jobcli.automation.stealth import (
            LAUNCH_ARGS,
            IGNORE_DEFAULT_ARGS,
            CONTEXT_OPTIONS,
        )
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, False, f"Missing dependency: {exc}"

    user_data_dir = tempfile.mkdtemp(prefix="jobcli_ext_verify_")
    launch_args = list(LAUNCH_ARGS) + chromium_extension_launch_args(ext_dir)

    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,
                args=launch_args,
                ignore_default_args=IGNORE_DEFAULT_ARGS,
                **CONTEXT_OPTIONS,
            )
            try:
                page = ctx.new_page()

                # Navigate to the login page
                try:
                    page.goto(
                        "https://whitebox-learning.com/login",
                        timeout=30000,
                        wait_until="domcontentloaded",
                    )
                except Exception as exc:
                    return False, False, f"Could not reach login page: {exc}"

                # Fill in credentials
                try:
                    page.fill('input[name="email"]', email)
                    page.fill('input[name="password"]', password)
                    page.click('button:has-text("Login")')
                except Exception as exc:
                    return False, False, f"Could not interact with login form: {exc}"

                # Check login success
                try:
                    page.wait_for_url("**/user_dashboard**", timeout=10000)
                    login_ok = True
                except Exception:
                    login_ok = False

                # Check extension loaded (service workers for MV3, background
                # pages for MV2)
                try:
                    extension_ok = bool(
                        list(ctx.service_workers) or list(ctx.background_pages)
                    )
                except Exception:
                    extension_ok = False

                return login_ok, extension_ok, ""
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
    except Exception as exc:
        return False, False, f"Browser launch failed: {exc}"
