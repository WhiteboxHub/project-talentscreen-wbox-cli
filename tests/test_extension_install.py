"""Tests for bundled extension install and resolver integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from importlib import resources


# ───────────────────────────────────────────────────────────────────────
# Package assets
# ───────────────────────────────────────────────────────────────────────


def test_bundled_assets_present_in_package():
    """Wheel/sdist must ship talentscreen_extension with manifest.json."""
    root = resources.files("jobcli.assets")
    manifest = root.joinpath("talentscreen_extension", "manifest.json")
    assert manifest.is_file(), "jobcli.assets/talentscreen_extension/manifest.json missing"
    bridge = root.joinpath("talentscreen_extension", "src", "core", "pageWorldBridge.js")
    assert bridge.is_file(), "pageWorldBridge.js missing from bundled assets"


# ───────────────────────────────────────────────────────────────────────
# install_bundled_extension
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def jobcli_home_tmp(tmp_path, monkeypatch):
    """Redirect ~/.jobcli to a temp directory."""
    home = tmp_path / "jobcli_home"
    home.mkdir()
    monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)
    return home


class TestInstallBundledExtension:
    def test_install_copies_files(self, jobcli_home_tmp):
        from jobcli.extension.install import extension_install_dir, install_bundled_extension

        target = install_bundled_extension(force=True)
        assert target == extension_install_dir()
        assert (target / "manifest.json").is_file()
        assert (target / "src" / "core" / "pageWorldBridge.js").is_file()

    def test_install_is_idempotent(self, jobcli_home_tmp):
        from jobcli.extension.install import extension_install_dir, install_bundled_extension

        first = install_bundled_extension(force=True)
        count_after_first = sum(1 for _ in first.rglob("*") if _.is_file())

        second = install_bundled_extension(force=False)
        assert second == first
        count_after_second = sum(1 for _ in second.rglob("*") if _.is_file())
        assert count_after_second == count_after_first

    def test_invalid_existing_dir_replaced(self, jobcli_home_tmp):
        from jobcli.extension.install import extension_install_dir, install_bundled_extension

        bad = extension_install_dir()
        bad.mkdir(parents=True)
        (bad / "not_a_manifest.txt").write_text("x")

        target = install_bundled_extension(force=False)
        assert (target / "manifest.json").is_file()


class TestChromiumExtensionLaunchArgs:
    def test_returns_correct_flags(self, tmp_path):
        from jobcli.extension.helpers import chromium_extension_launch_args

        ext = str(tmp_path / "ext")
        args = chromium_extension_launch_args(ext)
        assert args == [
            f"--disable-extensions-except={ext}",
            f"--load-extension={ext}",
        ]


class TestResolveExtensionDirInstall:
    def test_config_over_installed_copy(self, tmp_path, monkeypatch):
        """config.extension_path wins over ~/.jobcli/extension_unpacked."""
        from jobcli.extension import helpers

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)

        installed = home / "extension_unpacked"
        installed.mkdir(parents=True)
        (installed / "manifest.json").write_text('{"version": "bundled"}')

        custom = tmp_path / "custom_ext"
        custom.mkdir()
        (custom / "manifest.json").write_text('{"version": "custom"}')

        monkeypatch.delenv("JOBCLI_EXTENSION_PATH", raising=False)
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", tmp_path / "nope")
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope")

        result = helpers.resolve_extension_dir(str(custom))
        assert result == str(custom.resolve())

    def test_env_var_takes_priority(self, tmp_path, monkeypatch):
        from jobcli.extension import helpers

        env_ext = tmp_path / "env_extension"
        env_ext.mkdir()
        (env_ext / "manifest.json").write_text('{"version": "2.0.0"}')

        monkeypatch.setenv("JOBCLI_EXTENSION_PATH", str(env_ext))
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", tmp_path / "nope_bundled")
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope_sibling")

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)

        result = helpers.resolve_extension_dir(str(tmp_path / "config_ext"))
        assert result == str(env_ext.resolve())

    def test_falls_back_to_bundled_install(self, tmp_path, monkeypatch):
        from jobcli.extension import helpers

        monkeypatch.delenv("JOBCLI_EXTENSION_PATH", raising=False)
        monkeypatch.setattr(helpers, "_BUNDLED_BIN_DIR", tmp_path / "nope_bundled")
        monkeypatch.setattr(helpers, "_SIBLING_EXT_DIR", tmp_path / "nope_sibling")

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("jobcli.extension.install.jobcli_home", lambda: home)

        result = helpers.resolve_extension_dir(None)
        assert result is not None
        installed = home / "extension_unpacked"
        assert result == str(installed.resolve())
        assert (installed / "manifest.json").is_file()


class TestRefreshInstalledExtension:
    def test_refresh_force_reinstalls(self, jobcli_home_tmp):
        import json

        from jobcli.extension.install import (
            extension_install_dir,
            install_bundled_extension,
            refresh_installed_extension,
        )

        first = install_bundled_extension(force=True)
        (first / "manifest.json").write_text('{"version": "stale"}')

        refreshed = refresh_installed_extension()
        assert refreshed == extension_install_dir()
        assert (refreshed / "src" / "core" / "pageWorldBridge.js").is_file()
        manifest = json.loads((refreshed / "manifest.json").read_text(encoding="utf-8"))
        assert manifest.get("version") == "2.0.0"


class TestEngineLaunchArgsWithExtension:
    def test_start_session_includes_extension_flags(self, tmp_path):
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text("{}")

        resolved = str(ext_dir.resolve())
        captured_args: list = []

        mock_context = MagicMock()

        def capture_launch(*_args, **kwargs):
            captured_args.extend(kwargs.get("args") or [])
            return mock_context

        with patch("jobcli.extension.helpers.resolve_extension_dir", return_value=resolved), \
             patch("playwright.sync_api.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value.chromium.launch_persistent_context.side_effect = (
                capture_launch
            )

            from jobcli.orchestration.engine import ApplicationEngine

            config = MagicMock()
            config.extension_path = None
            engine = ApplicationEngine(config, MagicMock(), MagicMock())
            engine.start_session()

            assert any("--load-extension=" in a for a in captured_args)
            assert any("--disable-extensions-except=" in a for a in captured_args)
            assert any(resolved in a for a in captured_args)
