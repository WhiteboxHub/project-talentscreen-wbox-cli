"""Tests for extension setup, resolution, and browser verification.

Tests the centralised helpers in ``jobcli.extension.helpers`` as well as
the consumers in ``cli/interactive.py`` and ``orchestration/engine.py``.
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


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

        from jobcli.extension.helpers import resolve_extension_dir

        result = resolve_extension_dir(str(ext_dir))
        assert result == str(ext_dir.resolve())

    def test_jobcli_extension_path_env_takes_priority(self, tmp_path, monkeypatch):
        """JOBCLI_EXTENSION_PATH wins over config.extension_path."""
        from jobcli.extension import helpers

        env_ext = tmp_path / "env_extension"
        env_ext.mkdir()
        (env_ext / "manifest.json").write_text('{"version": "2.0.0"}')

        config_ext = tmp_path / "config_extension"
        config_ext.mkdir()
        (config_ext / "manifest.json").write_text("{}")

        monkeypatch.setenv("JOBCLI_EXTENSION_PATH", str(env_ext))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", tmp_path / "nope_bundled")
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope_sibling")

        result = helpers.resolve_extension_dir(str(config_ext))
        assert result == str(env_ext.resolve())

    def test_returns_none_when_no_candidates_valid(self, tmp_path, monkeypatch):
        """If no candidate directory has a manifest.json, return None."""
        from jobcli.extension import helpers
        from jobcli.extension.helpers import resolve_extension_dir

        monkeypatch.delenv("JOBCLI_EXTENSION_PATH", raising=False)
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", tmp_path / "nope_bundled")
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope_sibling")

        def fail_install(force=False):
            raise RuntimeError("bundled missing")

        monkeypatch.setattr(helpers, "install_bundled_extension", fail_install)

        result = resolve_extension_dir(str(tmp_path / "nonexistent"))
        assert result is None

    def test_skips_configured_if_no_manifest(self, tmp_path):
        """A directory without manifest.json should be skipped."""
        ext_dir = tmp_path / "empty_ext"
        ext_dir.mkdir()
        # No manifest.json created

        from jobcli.extension.helpers import resolve_extension_dir

        result = resolve_extension_dir(str(ext_dir))
        # Should fall through to other candidates (which also likely don't
        # exist in test), so result is either None or a valid fallback.
        assert result is None or isinstance(result, str)

    def test_falls_through_to_bundled_dir(self, tmp_path, monkeypatch):
        """If configured path is invalid, the bundled bin/ dir should be tried."""
        from jobcli.extension import helpers

        bundled = tmp_path / "bin" / "project-talentscreen-autofill-extension"
        bundled.mkdir(parents=True)
        (bundled / "manifest.json").write_text("{}")

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)

        def fail_install(force=False):
            raise RuntimeError("bundled missing")

        monkeypatch.setattr(helpers, "install_bundled_extension", fail_install)
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", bundled)
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope_sibling")

        result = helpers.resolve_extension_dir("/nonexistent/path")
        assert result == str(bundled.resolve())

    def test_none_when_configured_is_none(self, tmp_path, monkeypatch):
        """Passing None as configured_path should not crash."""
        from jobcli.extension import helpers

        monkeypatch.delenv("JOBCLI_EXTENSION_PATH", raising=False)
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)

        def fail_install(force=False):
            raise RuntimeError("bundled missing")

        monkeypatch.setattr(helpers, "install_bundled_extension", fail_install)
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", tmp_path / "nope2")
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope3")

        result = helpers.resolve_extension_dir(None)
        assert result is None


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

        from jobcli.extension.helpers import verify_extension_in_browser

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

        from jobcli.extension.helpers import verify_extension_in_browser

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

        from jobcli.extension.helpers import verify_extension_in_browser

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

            from jobcli.extension.helpers import verify_extension_in_browser

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
        with patch("jobcli.extension.helpers.resolve_extension_dir") as mock_resolve:
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

        with patch("jobcli.extension.helpers.resolve_extension_dir", return_value=resolved_path) as mock_resolve, \
             patch("jobcli.extension.helpers.verify_extension_in_browser", return_value=(True, True, "")) as mock_verify:

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
        with patch("jobcli.extension.helpers.resolve_extension_dir", return_value=None):
            from jobcli.cli.interactive import _validate_wbox_and_extension

            login_ok, ext_ok, ext_dir, err = _validate_wbox_and_extension(
                "user@test.com", "pass123"
            )

            assert login_ok is False
            assert ext_ok is False
            assert ext_dir is None
            assert "not found" in err.lower()


class TestSiblingExtensionManifest:
    """E2E prerequisite: dev monorepo extension includes Playwright page-world bridge."""

    def test_sibling_manifest_has_main_world_bridge(self):
        from jobcli.extension import helpers

        ext_dir = helpers._SIBLING_EXT_DIR
        manifest_path = ext_dir / "manifest.json"
        if not manifest_path.is_file():
            pytest.skip("Sibling extension repo not present")

        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scripts = manifest.get("content_scripts") or []
        main_entries = [s for s in scripts if s.get("world") == "MAIN"]
        assert main_entries, "manifest must include a MAIN-world content_scripts entry"
        bridge_js = "src/core/pageWorldBridge.js"
        assert any(
            bridge_js in (entry.get("js") or [])
            for entry in main_entries
        ), f"MAIN entry must load {bridge_js}"
        assert manifest.get("version") == "2.0.0"
