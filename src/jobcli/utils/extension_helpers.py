"""Extension resolution and validation helpers.

Centralises all the logic for locating, validating, and verifying the
TalentScreen browser extension so that ``cli/main.py``,
``cli/interactive.py``, and ``orchestration/engine.py`` can import from
one place instead of duplicating path-resolution code.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import zipfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable, Optional

ProgressCallback = Optional[Callable[[str], None]]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default subdirectory under ``~/.jobcli`` where installs unpack the extension.
_LEGACY_UNPACK_DIR = Path.home() / ".jobcli" / "extension_unpacked"

#: Project root (repo root containing pyproject.toml / build.sh).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

#: Directory where a built extension ZIP is copied (any ``*.zip`` name).
_EXTENSION_DIR = _PROJECT_ROOT / "extension"

#: Preferred glob for extension ZIPs (build output is versioned).
LOCAL_EXTENSION_ZIP_GLOB = "talentscreen-autofill*.zip"

#: Relative path from project root's ``bin/`` folder where install scripts
#: may clone the extension repo (legacy fallback).
_BUNDLED_DIR = (
    _PROJECT_ROOT
    / "bin"
    / "project-talentscreen-autofill-extension"
)

#: HTTPS URL for the public TalentScreen extension repository.
#: ``wboxcli extupdate`` clones from here and runs the repo's build.sh.
EXTENSION_REPO_URL = (
    "https://github.com/WhiteboxHub/project-talentscreen-autofill-extension.git"
)

#: Canonical filename used by extupdate when copying the built ZIP into
#: ``extension/``. Stable name keeps the resolver/doctor messages tidy.
EXTUPDATE_INSTALLED_ZIP_NAME = "talentscreen-autofill.zip"


def _has_manifest(directory: Path) -> bool:
    """Return True if *directory* exists and contains a ``manifest.json``."""
    return directory.is_dir() and (directory / "manifest.json").is_file()


def _find_manifest_root(search_root: Path) -> Optional[Path]:
    """Return the directory containing ``manifest.json`` under *search_root*."""
    if _has_manifest(search_root):
        return search_root
    for path in search_root.rglob("manifest.json"):
        if path.is_file():
            return path.parent
    return None


def _extension_zip_candidates() -> list[Path]:
    """Return ZIP files under ``extension/``, newest modification time first."""
    if not _EXTENSION_DIR.is_dir():
        return []
    zips = [p for p in _EXTENSION_DIR.glob("*.zip") if p.is_file()]
    zips.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return zips


def get_local_extension_zip() -> Optional[Path]:
    """Return the newest extension ZIP under ``extension/``.

    Prefers files matching ``talentscreen-autofill*.zip`` (build output). Falls
    back to any other ``*.zip`` in that folder when no preferred match exists.
    """
    zips = _extension_zip_candidates()
    if not zips:
        return None

    preferred = [
        p for p in zips if fnmatch(p.name, LOCAL_EXTENSION_ZIP_GLOB)
    ]
    return preferred[0] if preferred else zips[0]


def install_extension_from_zip(
    zip_path: Path | str,
    dest_dir: Optional[Path | str] = None,
    force: bool = False,
) -> str:
    """Unpack a Chrome extension ZIP into *dest_dir* for Playwright loading.

    Playwright requires an unpacked directory with ``manifest.json`` at its
    root — not a ``.zip`` file.

    Args:
        zip_path: Path to the extension ZIP archive.
        dest_dir: Target directory (default ``~/.jobcli/extension_unpacked``).
        force: Reinstall even when a valid manifest already exists.

    Returns:
        Absolute path to the unpacked extension directory.

    Raises:
        FileNotFoundError: ZIP or manifest inside archive not found.
        RuntimeError: Unpack/copy failed.
    """
    zip_path = Path(zip_path).expanduser().resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"Extension ZIP not found: {zip_path}")

    dest = Path(dest_dir).expanduser() if dest_dir else _LEGACY_UNPACK_DIR
    manifest = dest / "manifest.json"

    if manifest.is_file() and not force:
        return str(dest.resolve())

    if force and dest.exists():
        shutil.rmtree(dest)
    elif dest.exists() and not manifest.is_file():
        shutil.rmtree(dest)

    tmpdir = Path(tempfile.mkdtemp(prefix="jobcli_ext_zip_"))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        ext_root = _find_manifest_root(tmpdir)
        if ext_root is None:
            raise FileNotFoundError(
                f"manifest.json not found inside {zip_path}. "
                "Ensure the ZIP was built from the extension repo root."
            )

        dest.mkdir(parents=True, exist_ok=True)
        for item in ext_root.iterdir():
            target = dest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not manifest.is_file():
        raise RuntimeError(
            f"Extension install failed: manifest.json not found at {manifest}"
        )

    return str(dest.resolve())


def maybe_install_local_extension_zip(force: Optional[bool] = None) -> Optional[str]:
    """Install from the newest ``extension/*.zip`` when appropriate.

    Installs when:
    - ZIP exists and unpacked manifest is missing, or
    - ZIP is newer than unpacked manifest (mtime), or
    - *force* is True (or ``FORCE_REINSTALL_EXTENSION=1`` env).

    Returns:
        Unpacked directory path if install ran or was skipped with valid
        manifest; ``None`` if no ZIP is present.
    """
    zip_path = get_local_extension_zip()
    if zip_path is None:
        return None

    if force is None:
        force = os.environ.get("FORCE_REINSTALL_EXTENSION", "0") == "1"

    dest = _LEGACY_UNPACK_DIR
    manifest = dest / "manifest.json"
    needs_install = force or not _has_manifest(dest)

    if not needs_install and manifest.is_file():
        try:
            if zip_path.stat().st_mtime > manifest.stat().st_mtime:
                needs_install = True
        except OSError:
            pass

    if needs_install:
        return install_extension_from_zip(zip_path, dest_dir=dest, force=force)

    return str(dest.resolve())


def resolve_extension_dir(configured_path: Optional[str] = None) -> Optional[str]:
    """Return the first valid extension directory, or ``None``.

    Candidate order:
    1. *configured_path* (saved in ``config.extension_path``).
    2. ``~/.jobcli/extension_unpacked`` if already valid.
    3. Newest ``extension/*.zip`` — unpack to ``~/.jobcli/``.
    4. ``<project-root>/bin/project-talentscreen-autofill-extension`` (legacy).

    A directory is valid only if it contains ``manifest.json``.
    """
    if configured_path and configured_path.strip():
        path = Path(configured_path).expanduser()
        if _has_manifest(path):
            return str(path.resolve())

    if _has_manifest(_LEGACY_UNPACK_DIR):
        return str(_LEGACY_UNPACK_DIR.resolve())

    installed = maybe_install_local_extension_zip()
    if installed and _has_manifest(Path(installed)):
        return installed

    if _has_manifest(_BUNDLED_DIR):
        return str(_BUNDLED_DIR.resolve())

    return None


def _wait_for_extension_worker(
    context: Any,
    page: Any,
    timeout_ms: int = 5000,
) -> bool:
    """Poll until Playwright reports an extension service worker or background page.

    MV3 workers start lazily; a single immediate check often false-negatives even
    when ``--load-extension`` succeeded. Mirrors the polling used during apply.
    """
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        try:
            if list(context.service_workers) or list(context.background_pages):
                return True
        except Exception:
            pass
        try:
            page.wait_for_timeout(150)
        except Exception:
            time.sleep(0.15)
    return False


def _report(progress: ProgressCallback, message: str) -> None:
    if progress:
        progress(message)


def verify_extension_in_browser(
    ext_dir: str,
    email: str,
    password: str,
    *,
    progress: ProgressCallback = None,
) -> tuple[bool, bool, str]:
    """Launch a visible browser, load the extension, and attempt login.

    Returns ``(login_ok, extension_ok, error_message)``.

    * ``login_ok``      — credentials were accepted (redirected to dashboard).
    * ``extension_ok``  — Playwright detected a service-worker or background
                          page from the extension (polls up to 5s for MV3).
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
    launch_args = list(LAUNCH_ARGS) + [
        f"--disable-extensions-except={ext_dir}",
        f"--load-extension={ext_dir}",
    ]

    try:
        with sync_playwright() as pw:
            headless = os.environ.get("WBOX_VERIFY_HEADLESS", "0") == "1"
            _report(
                progress,
                "Launching Chrome"
                + (" (headless)" if headless else " (a window will open — please wait)"),
            )
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir,
                headless=headless,
                args=launch_args,
                ignore_default_args=IGNORE_DEFAULT_ARGS,
                **CONTEXT_OPTIONS,
            )
            try:
                page = ctx.new_page()

                _report(progress, "Opening Whitebox login page…")
                try:
                    page.goto(
                        "https://whitebox-learning.com/login",
                        timeout=30000,
                        wait_until="domcontentloaded",
                    )
                except Exception as exc:
                    return False, False, f"Could not reach login page: {exc}"

                _report(progress, "Loading TalentScreen extension (plugin)…")
                extension_ok = _wait_for_extension_worker(ctx, page, timeout_ms=3000)

                _report(progress, "Validating email and password…")
                try:
                    page.fill('input[name="email"]', email)
                    page.fill('input[name="password"]', password)
                    page.click('button:has-text("Login")')
                except Exception as exc:
                    return False, False, f"Could not interact with login form: {exc}"

                _report(progress, "Waiting for dashboard (login check)…")
                try:
                    page.wait_for_url("**/user_dashboard**", timeout=10000)
                    login_ok = True
                except Exception:
                    login_ok = False

                if login_ok and not extension_ok:
                    _report(progress, "Re-checking extension plugin…")
                    extension_ok = _wait_for_extension_worker(ctx, page, timeout_ms=5000)

                return login_ok, extension_ok, ""
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
    except Exception as exc:
        return False, False, f"Browser launch failed: {exc}"


# ---------------------------------------------------------------------------
# extupdate — clone + build + install the latest extension ZIP
# ---------------------------------------------------------------------------


def _clone_extension_repo(branch: Optional[str], dest: Path) -> None:
    """Run ``git clone --depth 1 [-b <branch>] EXTENSION_REPO_URL <dest>``.

    Captures stderr so we can surface a useful message if the clone fails
    (e.g. no git on PATH, network unreachable, private repo gated).
    """
    argv: list[str] = ["git", "clone", "--depth", "1"]
    if branch:
        argv.extend(["-b", branch])
    argv.extend([EXTENSION_REPO_URL, str(dest)])

    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:1000]
        raise RuntimeError(
            f"git clone failed (exit {result.returncode}): {stderr or 'no stderr'}"
        )


def _git_head_commit(clone_dir: Path) -> str:
    """Best-effort ``git rev-parse --short HEAD`` for the success message."""
    try:
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except Exception:
        pass
    return ""


def _read_manifest_version(clone_dir: Path) -> str:
    """Read the ``version`` field from ``manifest.json`` (best effort)."""
    manifest_path = clone_dir / "manifest.json"
    if not manifest_path.is_file():
        return ""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return str(data.get("version", "")).strip()
    except Exception:
        return ""


def _run_extension_build(clone_dir: Path) -> Path:
    """Run the extension repo's ``build.sh`` (Unix) or ``build.ps1`` (Windows).

    Returns the path to the newest produced ZIP under ``clone_dir / "dist"``
    matching ``talentscreen-autofill-v*.zip``.

    Raises:
        FileNotFoundError: when the build script itself is missing.
        RuntimeError: when the script exits non-zero or produces no ZIP.
    """
    is_windows = platform.system().lower().startswith("win")

    if is_windows:
        build_script = clone_dir / "build.ps1"
        if not build_script.is_file():
            raise FileNotFoundError(
                f"build.ps1 not found in clone at {clone_dir}. "
                "The extension repo layout may have changed."
            )
        argv: list[str] = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(build_script),
        ]
    else:
        build_script = clone_dir / "build.sh"
        if not build_script.is_file():
            raise FileNotFoundError(
                f"build.sh not found in clone at {clone_dir}. "
                "The extension repo layout may have changed."
            )
        argv = ["bash", str(build_script)]

    result = subprocess.run(argv, cwd=str(clone_dir), capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:2000]
        stdout = (result.stdout or "").strip()[:1000]
        raise RuntimeError(
            f"extension build exited {result.returncode}. "
            f"stderr: {stderr or '<empty>'} | stdout tail: {stdout[-500:] if stdout else '<empty>'}"
        )

    dist_dir = clone_dir / "dist"
    if not dist_dir.is_dir():
        raise RuntimeError(
            f"extension build succeeded but no dist/ directory found at {dist_dir}"
        )
    zips = sorted(
        (p for p in dist_dir.glob("talentscreen-autofill-v*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not zips:
        # Fall back to any *.zip in dist/ — covers a renamed pattern.
        zips = sorted(
            (p for p in dist_dir.glob("*.zip") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not zips:
        raise RuntimeError(
            f"extension build produced no ZIP under {dist_dir}. "
            "Check that the build script is wired correctly upstream."
        )
    return zips[0]


def build_and_install_extension(
    *,
    branch: Optional[str] = None,
    source_dir: Optional[Path | str] = None,
    progress: ProgressCallback = None,
    keep_clone: bool = False,
) -> dict:
    """Clone + build + install the TalentScreen extension.

    The full pipeline used by ``wboxcli extupdate``:

    1. If *source_dir* is given, treat it as an existing local clone (no
       git operations). Otherwise ``git clone --depth 1`` (optionally with
       ``-b <branch>``) to a tempdir.
    2. Verify ``manifest.json`` exists at the clone root.
    3. Run the build script (``build.sh`` on Unix, ``build.ps1`` on Windows).
    4. Locate the newest ``dist/talentscreen-autofill-v*.zip``.
    5. Copy it to ``<project-root>/extension/talentscreen-autofill.zip``.
    6. Call :func:`maybe_install_local_extension_zip` with ``force=True`` to
       unpack into ``~/.jobcli/extension_unpacked/``.

    Args:
        branch: Optional non-default branch to clone.
        source_dir: Reuse an existing local clone instead of cloning fresh.
        progress: Optional callback receiving human-readable status strings.
        keep_clone: When True the temp clone is not deleted; its path is
            included in the return dict for inspection.

    Returns:
        Dict with keys ``zip_path`` (installed ZIP location),
        ``unpacked_dir`` (target unpack dir), ``manifest_version``
        (from ``manifest.json``), ``commit`` (HEAD short-sha, may be empty
        for ``source_dir``), and ``clone_dir`` (only when ``keep_clone``).

    Raises:
        RuntimeError: on any step failure, with a human-friendly message
            that includes the captured subprocess stderr where available.
    """
    using_external_source = source_dir is not None
    tmp_clone: Optional[Path] = None

    if using_external_source:
        clone_dir = Path(source_dir).expanduser().resolve()
        if not _has_manifest(clone_dir):
            raise RuntimeError(
                f"--source path {clone_dir} does not contain manifest.json. "
                "Point --source at the root of a TalentScreen extension clone."
            )
    else:
        tmp_clone = Path(tempfile.mkdtemp(prefix="jobcli_extupdate_"))
        clone_dir = tmp_clone
        _report(progress, f"Cloning extension repo (branch={branch or 'default'})…")
        try:
            _clone_extension_repo(branch, clone_dir)
        except Exception:
            shutil.rmtree(tmp_clone, ignore_errors=True)
            raise
        if not _has_manifest(clone_dir):
            shutil.rmtree(tmp_clone, ignore_errors=True)
            raise RuntimeError(
                f"Cloned repo at {clone_dir} has no manifest.json at the root. "
                "The extension repo layout may have changed."
            )

    try:
        _report(progress, "Building extension ZIP (build.sh)…")
        produced_zip = _run_extension_build(clone_dir)

        _EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
        installed_zip = _EXTENSION_DIR / EXTUPDATE_INSTALLED_ZIP_NAME
        _report(progress, f"Copying ZIP -> {installed_zip}…")
        shutil.copy2(produced_zip, installed_zip)

        _report(progress, "Unpacking ZIP into ~/.jobcli/extension_unpacked/…")
        unpacked = maybe_install_local_extension_zip(force=True)
        if not unpacked:
            raise RuntimeError(
                "Built ZIP was copied but maybe_install_local_extension_zip() "
                "did not unpack it. Re-run with WBOXCLI_DEBUG=1 for details."
            )

        result = {
            "zip_path": str(installed_zip),
            "unpacked_dir": unpacked,
            "manifest_version": _read_manifest_version(clone_dir),
            "commit": "" if using_external_source else _git_head_commit(clone_dir),
        }
        if keep_clone and tmp_clone is not None:
            result["clone_dir"] = str(tmp_clone)
        return result
    finally:
        if tmp_clone is not None and not keep_clone:
            shutil.rmtree(tmp_clone, ignore_errors=True)
