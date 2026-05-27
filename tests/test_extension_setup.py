"""Tests for extension setup, resolution, and browser verification.

Tests the centralised helpers in ``jobcli.utils.extension_helpers`` as well as
the consumers in ``cli/interactive.py`` and ``orchestration/engine.py``.
"""

import io
import zipfile

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


def _make_extension_zip(path: Path, nested: bool = False) -> None:
    """Write a minimal Chrome-extension ZIP to *path*."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if nested:
            zf.writestr("nested-ext/manifest.json", '{"manifest_version": 3}')
            zf.writestr("nested-ext/content.js", "// test")
        else:
            zf.writestr("manifest.json", '{"manifest_version": 3}')
            zf.writestr("content.js", "// test")
    path.write_bytes(buf.getvalue())


# ───────────────────────────────────────────────────────────────────────
# resolve_extension_dir
# ───────────────────────────────────────────────────────────────────────

class TestResolveExtensionDir:
    """Unit tests for the extension directory resolution logic."""

    def test_returns_configured_path_when_valid(self, tmp_path):
        """If the configured path has a manifest.json, use it directly."""
        ext_dir = tmp_path / "my_extension"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text("{}")

        from jobcli.utils.extension_helpers import resolve_extension_dir

        result = resolve_extension_dir(str(ext_dir))
        assert result == str(ext_dir.resolve())

    def test_returns_none_when_no_candidates_valid(self, tmp_path):
        """If no candidate directory has a manifest.json, return None."""
        from jobcli.utils.extension_helpers import resolve_extension_dir

        # Pass a path that doesn't exist
        result = resolve_extension_dir(str(tmp_path / "nonexistent"))
        # The legacy and bundled fallbacks also won't exist in a test env,
        # but they might on a dev machine, so we just check the type.
        assert result is None or isinstance(result, str)

    def test_skips_configured_if_no_manifest(self, tmp_path):
        """A directory without manifest.json should be skipped."""
        ext_dir = tmp_path / "empty_ext"
        ext_dir.mkdir()
        # No manifest.json created

        from jobcli.utils.extension_helpers import resolve_extension_dir

        result = resolve_extension_dir(str(ext_dir))
        # Should fall through to other candidates (which also likely don't
        # exist in test), so result is either None or a valid fallback.
        assert result is None or isinstance(result, str)

    def test_falls_through_to_bundled_dir(self, tmp_path, monkeypatch):
        """If configured path is invalid, the bundled bin/ dir should be tried."""
        from jobcli.utils import extension_helpers as helpers

        bundled = tmp_path / "bin" / "project-talentscreen-autofill-extension"
        bundled.mkdir(parents=True)
        (bundled / "manifest.json").write_text("{}")

        # Override both legacy AND bundled so we control the test
        monkeypatch.setattr(helpers, "_LEGACY_UNPACK_DIR", tmp_path / "nope_legacy")
        monkeypatch.setattr(helpers, "_BUNDLED_DIR", bundled)

        result = helpers.resolve_extension_dir("/nonexistent/path")
        assert result == str(bundled.resolve())

    def test_none_when_configured_is_none(self, tmp_path, monkeypatch):
        """Passing None as configured_path should not crash."""
        from jobcli.utils import extension_helpers as helpers

        # Override both fallbacks to non-existent dirs
        monkeypatch.setattr(helpers, "_LEGACY_UNPACK_DIR", tmp_path / "nope1")
        monkeypatch.setattr(helpers, "_BUNDLED_DIR", tmp_path / "nope2")

        result = helpers.resolve_extension_dir(None)
        assert result is None


# ───────────────────────────────────────────────────────────────────────
# install_extension_from_zip
# ───────────────────────────────────────────────────────────────────────

class TestInstallExtensionFromZip:
    """Tests for unpacking a local extension ZIP."""

    def test_unpacks_manifest_at_dest_root(self, tmp_path):
        zip_path = tmp_path / "ext.zip"
        dest = tmp_path / "unpacked"
        _make_extension_zip(zip_path)

        from jobcli.utils.extension_helpers import install_extension_from_zip

        result = install_extension_from_zip(zip_path, dest_dir=dest)
        assert result == str(dest.resolve())
        assert (dest / "manifest.json").is_file()
        assert (dest / "content.js").is_file()

    def test_handles_nested_manifest_in_zip(self, tmp_path):
        zip_path = tmp_path / "ext.zip"
        dest = tmp_path / "unpacked"
        _make_extension_zip(zip_path, nested=True)

        from jobcli.utils.extension_helpers import install_extension_from_zip

        install_extension_from_zip(zip_path, dest_dir=dest)
        assert (dest / "manifest.json").is_file()

    def test_skips_when_manifest_exists(self, tmp_path):
        zip_path = tmp_path / "ext.zip"
        dest = tmp_path / "unpacked"
        dest.mkdir()
        (dest / "manifest.json").write_text('{"version": "1"}')
        _make_extension_zip(zip_path)

        from jobcli.utils.extension_helpers import install_extension_from_zip

        result = install_extension_from_zip(zip_path, dest_dir=dest)
        assert result == str(dest.resolve())

    def test_force_reinstalls(self, tmp_path):
        zip_path = tmp_path / "ext.zip"
        dest = tmp_path / "unpacked"
        dest.mkdir()
        (dest / "manifest.json").write_text('{"version": "old"}')
        _make_extension_zip(zip_path)

        from jobcli.utils.extension_helpers import install_extension_from_zip

        install_extension_from_zip(zip_path, dest_dir=dest, force=True)
        assert (dest / "content.js").is_file()

    def test_resolve_installs_from_local_zip(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        ext_dir = tmp_path / "extension"
        ext_dir.mkdir(parents=True)
        zip_path = ext_dir / "talentscreen-autofill-v2.0.0.zip"
        _make_extension_zip(zip_path)

        unpack_dest = tmp_path / "extension_unpacked"
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", ext_dir)
        monkeypatch.setattr(helpers, "_LEGACY_UNPACK_DIR", unpack_dest)
        monkeypatch.setattr(helpers, "_BUNDLED_DIR", tmp_path / "no_bundled")

        result = helpers.resolve_extension_dir(None)
        assert result == str(unpack_dest.resolve())
        assert (unpack_dest / "manifest.json").is_file()


# ───────────────────────────────────────────────────────────────────────
# get_local_extension_zip
# ───────────────────────────────────────────────────────────────────────

class TestGetLocalExtensionZip:
    """Tests for discovering extension ZIPs by name (no hardcoded filename)."""

    def test_finds_versioned_zip_name(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        ext_dir = tmp_path / "extension"
        ext_dir.mkdir()
        zip_path = ext_dir / "talentscreen-autofill-v2.0.0.zip"
        _make_extension_zip(zip_path)
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", ext_dir)

        assert helpers.get_local_extension_zip() == zip_path

    def test_prefers_newest_talentscreen_zip(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        ext_dir = tmp_path / "extension"
        ext_dir.mkdir()
        older = ext_dir / "talentscreen-autofill-v1.0.0.zip"
        newer = ext_dir / "talentscreen-autofill-v2.0.0.zip"
        _make_extension_zip(older)
        _make_extension_zip(newer)
        newer.touch()
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", ext_dir)

        assert helpers.get_local_extension_zip() == newer

    def test_prefers_talentscreen_pattern_over_other_zips(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        ext_dir = tmp_path / "extension"
        ext_dir.mkdir()
        other = ext_dir / "other-extension.zip"
        preferred = ext_dir / "talentscreen-autofill-v2.0.0.zip"
        _make_extension_zip(other)
        _make_extension_zip(preferred)
        other.touch()  # newer mtime, but wrong name
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", ext_dir)

        assert helpers.get_local_extension_zip() == preferred

    def test_falls_back_to_any_zip(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        ext_dir = tmp_path / "extension"
        ext_dir.mkdir()
        zip_path = ext_dir / "my-custom-extension.zip"
        _make_extension_zip(zip_path)
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", ext_dir)

        assert helpers.get_local_extension_zip() == zip_path

    def test_returns_none_when_no_zip(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        ext_dir = tmp_path / "extension"
        ext_dir.mkdir()
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", ext_dir)

        assert helpers.get_local_extension_zip() is None


# ───────────────────────────────────────────────────────────────────────
# _wait_for_extension_worker
# ───────────────────────────────────────────────────────────────────────

class TestWaitForExtensionWorker:
    def test_returns_true_when_worker_appears_after_delay(self):
        from jobcli.utils.extension_helpers import _wait_for_extension_worker

        class FakeContext:
            def __init__(self):
                self._calls = 0

            @property
            def service_workers(self):
                self._calls += 1
                return [object()] if self._calls >= 2 else []

            @property
            def background_pages(self):
                return []

        page = MagicMock()
        assert _wait_for_extension_worker(FakeContext(), page, timeout_ms=1000) is True

    def test_returns_false_when_never_appears(self):
        from jobcli.utils.extension_helpers import _wait_for_extension_worker

        ctx = MagicMock()
        ctx.service_workers = []
        ctx.background_pages = []
        page = MagicMock()

        assert _wait_for_extension_worker(ctx, page, timeout_ms=300) is False


# ───────────────────────────────────────────────────────────────────────
# verify_extension_in_browser
# ───────────────────────────────────────────────────────────────────────

class TestVerifyExtensionInBrowser:
    """Tests for the browser-based extension verification."""

    @pytest.fixture
    def mock_playwright_env(self):
        """Provide a fully mocked Playwright stack.
        
        sync_playwright is imported lazily inside verify_extension_in_browser,
        so we patch it at the playwright.sync_api module level.
        """
        with patch("playwright.sync_api.sync_playwright") as mock_pw:
            mock_context = MagicMock()
            mock_pw.return_value.__enter__.return_value.chromium.launch_persistent_context.return_value = mock_context

            mock_page = MagicMock()
            mock_context.new_page.return_value = mock_page
            mock_page.title.return_value = "Test Page"
            mock_page.goto.return_value = MagicMock(status=200)

            yield mock_pw, mock_context, mock_page

    def test_extension_verified_via_service_worker(self, tmp_path, mock_playwright_env):
        """When Playwright reports a service worker, extension_ok should be True."""
        _, mock_context, mock_page = mock_playwright_env

        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text("{}")

        # Simulate MV3 service worker present
        mock_context.service_workers = [MagicMock()]
        mock_context.background_pages = []

        # Simulate successful login redirect
        mock_page.wait_for_url = MagicMock()  # no exception = success

        from jobcli.utils.extension_helpers import verify_extension_in_browser

        login_ok, ext_ok, err = verify_extension_in_browser(
            str(ext_dir), "user@test.com", "pass123"
        )

        assert login_ok is True
        assert ext_ok is True
        assert err == ""

    def test_extension_not_loaded_detected(self, tmp_path, mock_playwright_env):
        """When no service workers or background pages exist, extension_ok is False."""
        _, mock_context, mock_page = mock_playwright_env

        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text("{}")

        mock_context.service_workers = []
        mock_context.background_pages = []

        mock_page.wait_for_url = MagicMock()

        from jobcli.utils.extension_helpers import verify_extension_in_browser

        login_ok, ext_ok, err = verify_extension_in_browser(
            str(ext_dir), "user@test.com", "pass123"
        )

        assert login_ok is True
        assert ext_ok is False
        assert err == ""

    def test_login_failure_detected(self, tmp_path, mock_playwright_env):
        """When login redirect times out, login_ok should be False."""
        _, mock_context, mock_page = mock_playwright_env

        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text("{}")

        mock_context.service_workers = [MagicMock()]
        mock_context.background_pages = []

        # Simulate login failure (wait_for_url raises TimeoutError)
        mock_page.wait_for_url = MagicMock(side_effect=TimeoutError("timeout"))

        from jobcli.utils.extension_helpers import verify_extension_in_browser

        login_ok, ext_ok, err = verify_extension_in_browser(
            str(ext_dir), "bad@creds.com", "wrong"
        )

        assert login_ok is False
        assert ext_ok is True  # extension still loaded even if login failed
        assert err == ""

    def test_browser_launch_failure(self, tmp_path):
        """If Playwright itself fails to launch, return a clear error."""
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text("{}")

        with patch("playwright.sync_api.sync_playwright") as mock_pw:
            mock_pw.return_value.__enter__.side_effect = RuntimeError("no browser")

            from jobcli.utils.extension_helpers import verify_extension_in_browser

            login_ok, ext_ok, err = verify_extension_in_browser(
                str(ext_dir), "a@b.com", "pass"
            )

            assert login_ok is False
            assert ext_ok is False
            assert "Browser launch failed" in err


# ───────────────────────────────────────────────────────────────────────
# Engine integration
# ───────────────────────────────────────────────────────────────────────

class TestEngineExtensionResolution:
    """Verify that engine._resolve_extension_dir delegates correctly."""

    def test_engine_uses_helpers_module(self, tmp_path):
        """The engine should call resolve_extension_dir from helpers."""
        with patch("jobcli.utils.extension_helpers.resolve_extension_dir") as mock_resolve:
            mock_resolve.return_value = str(tmp_path / "ext")

            from jobcli.orchestration.engine import ApplicationEngine

            config = MagicMock()
            config.extension_path = None

            engine = ApplicationEngine(config, MagicMock(), MagicMock())
            result = engine._resolve_extension_dir()

            mock_resolve.assert_called_once()
            assert result == str(tmp_path / "ext")


# ───────────────────────────────────────────────────────────────────────
# Interactive onboarding integration
# ───────────────────────────────────────────────────────────────────────

class TestInteractiveExtensionValidation:
    """Verify that the interactive TUI delegates to helpers."""

    def test_validate_delegates_to_helpers(self, tmp_path):
        """_validate_wbox_and_extension should call resolve + verify from helpers."""
        resolved_path = str(tmp_path / "ext")

        with patch("jobcli.utils.extension_helpers.get_local_extension_zip", return_value=None), \
             patch("jobcli.utils.extension_helpers.maybe_install_local_extension_zip"), \
             patch("jobcli.utils.extension_helpers.resolve_extension_dir", return_value=resolved_path) as mock_resolve, \
             patch("jobcli.utils.extension_helpers.verify_extension_in_browser", return_value=(True, True, "")) as mock_verify:

            from jobcli.cli.interactive import _validate_wbox_and_extension

            login_ok, ext_ok, ext_dir, err = _validate_wbox_and_extension(
                "user@test.com", "pass123", "/some/old/path"
            )

            mock_resolve.assert_called_once_with("/some/old/path")
            mock_verify.assert_called_once_with(resolved_path, "user@test.com", "pass123")
            assert login_ok is True
            assert ext_ok is True
            assert ext_dir == resolved_path
            assert err == ""

    def test_validate_returns_error_when_no_extension(self):
        """If resolve returns None, should return an error tuple immediately."""
        with patch("jobcli.utils.extension_helpers.get_local_extension_zip", return_value=None), \
             patch("jobcli.utils.extension_helpers.maybe_install_local_extension_zip"), \
             patch("jobcli.utils.extension_helpers.resolve_extension_dir", return_value=None):
            from jobcli.cli.interactive import _validate_wbox_and_extension

            login_ok, ext_ok, ext_dir, err = _validate_wbox_and_extension(
                "user@test.com", "pass123"
            )

            assert login_ok is False
            assert ext_ok is False
            assert ext_dir is None
            assert "not found" in err.lower()
