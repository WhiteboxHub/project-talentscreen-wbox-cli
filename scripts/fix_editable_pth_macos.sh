#!/usr/bin/env bash
# Python 3.14 on macOS skips .pth files with the UF_HIDDEN flag (see site.addpackage).
# pip/setuptools editable installs use __editable__*.pth, which may be marked hidden,
# so `jobcli` fails while `python -c "import jobcli"` works only when cwd is the repo.
# Run this from the repo root after `pip install -e .` if console scripts cannot import jobcli.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${1:-$ROOT/.venv}"
PY="$VENV/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No python at $PY — pass your venv directory as the first argument." >&2
  exit 1
fi
SITE="$("$PY" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"

if [[ ! -d "$SITE" ]]; then
  echo "No site-packages at $SITE" >&2
  exit 1
fi

shopt -s nullglob
for p in "$SITE"/__editable__*.pth; do
  echo "chflags nohidden $p"
  chflags nohidden "$p"
done
