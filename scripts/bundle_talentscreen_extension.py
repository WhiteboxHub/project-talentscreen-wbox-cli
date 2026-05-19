#!/usr/bin/env python3
"""Copy TalentScreen extension runtime files into jobcli package assets.

Usage:
    python scripts/bundle_talentscreen_extension.py
    python scripts/bundle_talentscreen_extension.py --source /path/to/extension
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Repo root: scripts/ -> project-avatar-wbox-cli/
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SOURCE = _REPO_ROOT.parent / "project-talentscreen-autofill-extension"
_DEST = _REPO_ROOT / "src" / "jobcli" / "assets" / "talentscreen_extension"

_EXCLUDE_DIRS = {".git", "docs", "tests", "node_modules", ".github", "__pycache__"}
_EXCLUDE_FILES = {
    "package.json",
    "package-lock.json",
    "validate.sh",
    "README.md",
    ".gitignore",
    ".gitattributes",
}


def _should_skip(path: Path, source_root: Path) -> bool:
    rel = path.relative_to(source_root)
    parts = rel.parts
    if parts and parts[0] in _EXCLUDE_DIRS:
        return True
    if any(p in _EXCLUDE_DIRS for p in parts):
        return True
    if path.is_file() and path.name in _EXCLUDE_FILES:
        return True
    return False


def bundle_extension(source: Path, dest: Path) -> str:
    """Copy extension tree to *dest*; return manifest version string."""
    if not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")

    manifest_src = source / "manifest.json"
    if not manifest_src.is_file():
        raise SystemExit(f"manifest.json missing in source: {source}")

    bridge_src = source / "src" / "core" / "pageWorldBridge.js"
    if not bridge_src.is_file():
        raise SystemExit(f"pageWorldBridge.js missing in source: {bridge_src}")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for item in source.rglob("*"):
        if _should_skip(item, source):
            continue
        rel = item.relative_to(source)
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    manifest_dest = dest / "manifest.json"
    if not manifest_dest.is_file():
        raise SystemExit(f"Bundle failed: {manifest_dest} not created")

    bridge_dest = dest / "src" / "core" / "pageWorldBridge.js"
    if not bridge_dest.is_file():
        raise SystemExit(f"Bundle failed: {bridge_dest} not created")

    data = json.loads(manifest_dest.read_text(encoding="utf-8"))
    version = str(data.get("version", "?"))
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description="Bundle TalentScreen into jobcli assets")
    parser.add_argument(
        "--source",
        type=Path,
        default=_DEFAULT_SOURCE,
        help=f"Extension repo root (default: {_DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=_DEST,
        help=f"Output directory (default: {_DEST})",
    )
    args = parser.parse_args()

    version = bundle_extension(args.source.resolve(), args.dest.resolve())
    print(f"Bundled TalentScreen v{version} -> {args.dest}")
    print(f"  manifest.json: OK")
    print(f"  pageWorldBridge.js: OK")


if __name__ == "__main__":
    main()
