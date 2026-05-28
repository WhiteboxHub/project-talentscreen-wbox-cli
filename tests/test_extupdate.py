"""Tests for the ``wboxcli extupdate`` command and its helper.

Covers:
  * ``jobcli.utils.extension_helpers.build_and_install_extension`` —
    pipeline behaviour (clone → build → copy → unpack), platform
    detection, source-dir reuse, branch argument, and the three main
    failure modes (missing manifest, non-zero build exit, no ZIP).
  * ``jobcli.cli.main.extupdate_cmd`` — Typer CLI exit codes and that it
    calls the helper exactly once.

These tests do not touch the network or run real subprocesses: every
``subprocess.run`` call is stubbed with ``MagicMock``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from jobcli.utils import extension_helpers
from jobcli.utils.extension_helpers import (
    EXTENSION_REPO_URL,
    EXTUPDATE_INSTALLED_ZIP_NAME,
    build_and_install_extension,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _seed_clone(clone_dir: Path, *, manifest_version: str = "1.2.3") -> None:
    """Write a fake extension clone layout (manifest + build.sh + build.ps1)."""
    clone_dir.mkdir(parents=True, exist_ok=True)
    (clone_dir / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "version": manifest_version})
    )
    (clone_dir / "build.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    (clone_dir / "build.ps1").write_text("Write-Host 'fake'")


def _make_zip_factory(clone_dir: Path, *, version: str = "9.9.9", filename: str | None = None):
    """Return a side_effect that drops a stub ZIP into ``clone_dir/dist/``."""
    def _side_effect(*args, **kwargs):
        dist = clone_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        name = filename or f"talentscreen-autofill-v{version}.zip"
        (dist / name).write_bytes(b"PK\x03\x04 fake zip")
        return MagicMock(returncode=0, stdout="ok", stderr="")
    return _side_effect


# ---------------------------------------------------------------------------
# Helper pipeline tests (build_and_install_extension)
# ---------------------------------------------------------------------------


def test_build_and_install_calls_clone_then_build_then_install(tmp_path, monkeypatch):
    """Happy path: clone → build → copy ZIP → unpack — all in order."""
    fake_clone = tmp_path / "clone"
    extension_dir = tmp_path / "extension"

    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", extension_dir)
    monkeypatch.setattr(
        extension_helpers, "maybe_install_local_extension_zip",
        MagicMock(return_value=str(tmp_path / "unpacked")),
    )

    call_log: list[str] = []

    def _fake_run(argv, *args, **kwargs):
        if argv[:2] == ["git", "clone"]:
            call_log.append("clone")
            _seed_clone(fake_clone)
            assert argv[-1] == str(fake_clone), "clone destination should be the tempdir"
            return MagicMock(returncode=0, stdout="", stderr="")
        if argv[:1] == ["bash"] or argv[:1] == ["powershell"]:
            call_log.append("build")
            return _make_zip_factory(fake_clone)(argv)
        if argv[:2] == ["git", "-C"]:
            call_log.append("git_meta")
            return MagicMock(returncode=0, stdout="abc1234\n", stderr="")
        raise AssertionError(f"Unexpected subprocess.run call: {argv}")

    monkeypatch.setattr(extension_helpers, "tempfile", _StubTempfile(fake_clone))

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        result = build_and_install_extension(branch=None)

    assert call_log[0] == "clone", "git clone must be called first"
    assert "build" in call_log, "build script must run"
    installed_zip = extension_dir / EXTUPDATE_INSTALLED_ZIP_NAME
    assert installed_zip.is_file(), "ZIP should be copied into _EXTENSION_DIR"
    extension_helpers.maybe_install_local_extension_zip.assert_called_once_with(force=True)
    assert result["zip_path"] == str(installed_zip)
    assert result["manifest_version"] == "1.2.3"


def test_build_and_install_uses_source_dir_skips_clone(tmp_path, monkeypatch):
    """When ``source_dir`` is given the helper must not run git clone."""
    source = tmp_path / "existing_clone"
    _seed_clone(source, manifest_version="2.0.0")
    extension_dir = tmp_path / "extension"

    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", extension_dir)
    monkeypatch.setattr(
        extension_helpers, "maybe_install_local_extension_zip",
        MagicMock(return_value=str(tmp_path / "unpacked")),
    )

    def _fake_run(argv, *args, **kwargs):
        assert argv[:2] != ["git", "clone"], "clone must be skipped when source_dir set"
        if argv[:1] in (["bash"], ["powershell"]):
            return _make_zip_factory(source)(argv)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        result = build_and_install_extension(source_dir=source)

    assert result["manifest_version"] == "2.0.0"
    assert result["commit"] == "", "commit metadata is skipped for --source clones"
    assert (extension_dir / EXTUPDATE_INSTALLED_ZIP_NAME).is_file()


def test_build_and_install_picks_powershell_on_windows(tmp_path, monkeypatch):
    """On Windows the helper should invoke ``powershell ... build.ps1``."""
    source = tmp_path / "clone"
    _seed_clone(source)
    extension_dir = tmp_path / "extension"

    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", extension_dir)
    monkeypatch.setattr(
        extension_helpers, "maybe_install_local_extension_zip",
        MagicMock(return_value=str(tmp_path / "unpacked")),
    )
    monkeypatch.setattr(extension_helpers.platform, "system", lambda: "Windows")

    seen_argvs: list[list[str]] = []

    def _fake_run(argv, *args, **kwargs):
        seen_argvs.append(list(argv))
        if argv[:1] == ["powershell"]:
            return _make_zip_factory(source)(argv)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        build_and_install_extension(source_dir=source)

    ps_calls = [a for a in seen_argvs if a and a[0] == "powershell"]
    assert ps_calls, "expected at least one powershell invocation on Windows"
    assert "-ExecutionPolicy" in ps_calls[0] and "Bypass" in ps_calls[0]
    assert ps_calls[0][-1] == str(source / "build.ps1")


def test_build_and_install_uses_bash_on_unix(tmp_path, monkeypatch):
    """On macOS / Linux the helper should invoke ``bash build.sh``."""
    source = tmp_path / "clone"
    _seed_clone(source)
    extension_dir = tmp_path / "extension"

    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", extension_dir)
    monkeypatch.setattr(
        extension_helpers, "maybe_install_local_extension_zip",
        MagicMock(return_value=str(tmp_path / "unpacked")),
    )
    monkeypatch.setattr(extension_helpers.platform, "system", lambda: "Darwin")

    seen_argvs: list[list[str]] = []

    def _fake_run(argv, *args, **kwargs):
        seen_argvs.append(list(argv))
        if argv[:1] == ["bash"]:
            return _make_zip_factory(source)(argv)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        build_and_install_extension(source_dir=source)

    bash_calls = [a for a in seen_argvs if a and a[0] == "bash"]
    assert bash_calls, "expected at least one bash invocation on Unix"
    assert bash_calls[0][-1] == str(source / "build.sh")


def test_build_and_install_fails_when_clone_missing_manifest(tmp_path, monkeypatch):
    """If the cloned repo has no manifest.json the helper must error out."""
    fake_clone = tmp_path / "clone"
    monkeypatch.setattr(extension_helpers, "tempfile", _StubTempfile(fake_clone))
    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", tmp_path / "extension")

    def _fake_run(argv, *args, **kwargs):
        if argv[:2] == ["git", "clone"]:
            # Create the dir but DON'T drop a manifest.json — that's the bug.
            fake_clone.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        with pytest.raises(RuntimeError, match="manifest.json"):
            build_and_install_extension()


def test_build_and_install_fails_when_build_returns_nonzero(tmp_path, monkeypatch):
    """Non-zero build exit must raise RuntimeError including the stderr."""
    source = tmp_path / "clone"
    _seed_clone(source)
    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", tmp_path / "extension")
    monkeypatch.setattr(extension_helpers.platform, "system", lambda: "Darwin")

    def _fake_run(argv, *args, **kwargs):
        if argv[:1] == ["bash"]:
            return MagicMock(returncode=2, stdout="", stderr="zip: command not found")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        with pytest.raises(RuntimeError, match="zip: command not found"):
            build_and_install_extension(source_dir=source)


def test_build_and_install_fails_when_no_zip_produced(tmp_path, monkeypatch):
    """A successful build that produces no ZIP must raise mentioning ``dist/``."""
    source = tmp_path / "clone"
    _seed_clone(source)
    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", tmp_path / "extension")
    monkeypatch.setattr(extension_helpers.platform, "system", lambda: "Darwin")

    def _fake_run(argv, *args, **kwargs):
        if argv[:1] == ["bash"]:
            # Build "succeeds" but never writes anything to dist/.
            return MagicMock(returncode=0, stdout="ok", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        with pytest.raises(RuntimeError, match=r"dist/?"):
            build_and_install_extension(source_dir=source)


def test_build_and_install_passes_branch_to_clone(tmp_path, monkeypatch):
    """``branch='dev'`` must appear in the clone argv as ``-b dev``."""
    fake_clone = tmp_path / "clone"
    extension_dir = tmp_path / "extension"

    monkeypatch.setattr(extension_helpers, "_EXTENSION_DIR", extension_dir)
    monkeypatch.setattr(
        extension_helpers, "maybe_install_local_extension_zip",
        MagicMock(return_value=str(tmp_path / "unpacked")),
    )
    monkeypatch.setattr(extension_helpers, "tempfile", _StubTempfile(fake_clone))
    monkeypatch.setattr(extension_helpers.platform, "system", lambda: "Darwin")

    captured: dict = {}

    def _fake_run(argv, *args, **kwargs):
        if argv[:2] == ["git", "clone"]:
            captured["clone_argv"] = list(argv)
            _seed_clone(fake_clone)
            return MagicMock(returncode=0, stdout="", stderr="")
        if argv[:1] == ["bash"]:
            return _make_zip_factory(fake_clone)(argv)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(extension_helpers.subprocess, "run", side_effect=_fake_run):
        build_and_install_extension(branch="dev")

    clone_argv = captured.get("clone_argv") or []
    assert "-b" in clone_argv and "dev" in clone_argv, f"branch flag missing: {clone_argv}"
    assert EXTENSION_REPO_URL in clone_argv


# ---------------------------------------------------------------------------
# CLI tests (extupdate_cmd via Typer's CliRunner)
# ---------------------------------------------------------------------------


def test_extupdate_cli_invokes_helper(monkeypatch):
    """``wboxcli extupdate`` should call the helper exactly once and exit 0."""
    from jobcli.cli import main as cli_main

    fake = MagicMock(return_value={
        "zip_path": "/tmp/extension/talentscreen-autofill.zip",
        "unpacked_dir": "/tmp/unpacked",
        "manifest_version": "1.2.3",
        "commit": "abc1234",
    })
    monkeypatch.setattr(cli_main, "build_and_install_extension", fake, raising=False)
    # The CLI imports the helper *inside* the command, so also patch the source.
    monkeypatch.setattr(extension_helpers, "build_and_install_extension", fake)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["extupdate"])

    assert result.exit_code == 0, result.output
    fake.assert_called_once()
    assert "talentscreen-autofill v1.2.3" in result.output


def test_extupdate_cli_propagates_helper_error(monkeypatch):
    """If the helper raises, the CLI should print the message and exit 1."""
    from jobcli.cli import main as cli_main

    boom = MagicMock(side_effect=RuntimeError("git clone failed (exit 128): repo not found"))
    monkeypatch.setattr(extension_helpers, "build_and_install_extension", boom)

    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["extupdate"])

    assert result.exit_code == 1
    assert "Extension update failed" in result.output
    assert "repo not found" in result.output


# ---------------------------------------------------------------------------
# tempfile stub (avoid polluting the real /tmp)
# ---------------------------------------------------------------------------


class _StubTempfile:
    """Stand-in for ``tempfile`` whose ``mkdtemp`` returns a fixed path."""

    def __init__(self, path: Path):
        self._path = path

    def mkdtemp(self, *args, **kwargs) -> str:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Do NOT pre-create the path itself — _clone_extension_repo's git
        # clone is what writes into it via the fake _fake_run side-effect.
        return str(self._path)
