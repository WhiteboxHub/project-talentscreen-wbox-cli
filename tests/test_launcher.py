"""Tests for managed wboxcli launcher / PATH helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from jobcli.cli.launcher import (
    is_running_from_managed_venv,
    jobcli_venv_python,
    managed_wboxcli_shim,
    remove_stale_global_shims,
)


def test_jobcli_venv_python_points_under_home():
    path = jobcli_venv_python()
    if path is not None:
        assert ".jobcli" in str(path)
        assert path.name in ("python", "python.exe")


def test_remove_stale_skips_managed_shim(tmp_path, monkeypatch):
    """Stale shim removal must not delete ~/.local/bin wrapper."""
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    wrapper = local_bin / ("wboxcli.cmd" if __import__("os").name == "nt" else "wboxcli")
    wrapper.write_text("managed", encoding="utf-8")

    fake_py = tmp_path / "AppData" / "Local" / "Programs" / "Python" / "Python310" / "Scripts"
    fake_py.mkdir(parents=True)
    stale = fake_py / "wboxcli.exe"
    stale.write_bytes(b"broken")

    monkeypatch.setattr("jobcli.cli.launcher.Path.home", lambda: tmp_path)

    with patch("jobcli.cli.launcher.managed_wboxcli_shim", return_value=wrapper):
        removed = remove_stale_global_shims()

    assert str(stale) in removed
    assert wrapper.is_file()


def test_is_running_from_managed_venv_when_executable_matches(monkeypatch, tmp_path):
    venv = tmp_path / "venv" / "Scripts"
    venv.mkdir(parents=True)
    py = venv / "python.exe"
    py.touch()

    monkeypatch.setattr("jobcli.cli.launcher.jobcli_venv_python", lambda: py)
    monkeypatch.setattr("jobcli.cli.launcher.sys.executable", str(py))

    assert is_running_from_managed_venv() is True
