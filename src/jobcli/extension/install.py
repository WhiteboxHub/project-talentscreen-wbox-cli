"""Install bundled TalentScreen extension to ~/.jobcli/extension_unpacked."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from jobcli.utils.logger import global_logger

_BUNDLED_SUBDIR = "talentscreen_extension"


def jobcli_home() -> Path:
    """Return ``Path.home() / '.jobcli'``."""
    return Path.home() / ".jobcli"


def extension_install_dir() -> Path:
    """Return ``~/.jobcli/extension_unpacked``."""
    return jobcli_home() / "extension_unpacked"


def is_valid_extension_dir(path: Path) -> bool:
    """Return True if *path* is a directory containing ``manifest.json``."""
    return path.is_dir() and (path / "manifest.json").is_file()


def _bundled_assets() -> Any:
    """Return traversable for packaged extension assets; raise if incomplete."""
    root = resources.files("jobcli.assets")
    bundled = root.joinpath(_BUNDLED_SUBDIR)
    if not bundled.is_dir():
        raise RuntimeError(
            f"Bundled TalentScreen extension missing in package: jobcli.assets/{_BUNDLED_SUBDIR}"
        )
    if not bundled.joinpath("manifest.json").is_file():
        raise RuntimeError(
            f"Bundled extension has no manifest.json at jobcli.assets/{_BUNDLED_SUBDIR}/manifest.json"
        )
    if not bundled.joinpath("src", "core", "pageWorldBridge.js").is_file():
        raise RuntimeError(
            "Bundled extension missing src/core/pageWorldBridge.js (v2.0.0+ required)"
        )
    return bundled


def bundled_extension_source() -> Any:
    """Locate bundled extension in package resources; raise if invalid."""
    return _bundled_assets()


def _copy_traversable_tree(source: Any, dest: Path) -> None:
    """Recursively copy a Traversable tree to a filesystem *dest*."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = dest / item.name
        if item.is_dir():
            _copy_traversable_tree(item, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())


def _copy_bundled_to(target: Path) -> None:
    """Copy packaged extension tree into *target* (caller removes *target* first if needed)."""
    bundled = _bundled_assets()
    with resources.as_file(bundled) as src_path:
        if src_path.is_dir():
            shutil.copytree(src_path, target)
        else:
            _copy_traversable_tree(bundled, target)

    if not is_valid_extension_dir(target):
        raise RuntimeError(
            f"Extension install failed: {target} does not contain manifest.json after copy"
        )


def install_bundled_extension(force: bool = False) -> Path:
    """Copy packaged extension to ``~/.jobcli/extension_unpacked``.

    - Valid target and ``force=False`` → return target without copying.
    - ``force=True`` or invalid target → remove target and recopy from package assets.
    """
    target = extension_install_dir()
    jobcli_home().mkdir(parents=True, exist_ok=True)

    if not force and is_valid_extension_dir(target):
        return target

    if target.exists():
        shutil.rmtree(target, ignore_errors=True)

    _copy_bundled_to(target)
    global_logger.info(f"Installed bundled extension to {target}")
    return target


def refresh_installed_extension() -> Path:
    """Force reinstall bundled extension (used by ``jobcli setup``)."""
    jobcli_home().mkdir(parents=True, exist_ok=True)
    return install_bundled_extension(force=True)
