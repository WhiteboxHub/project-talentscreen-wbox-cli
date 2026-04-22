#!/usr/bin/env bash
# Python 3.14 on macOS has a persistent problem with editable installs:
#   1. `pip install -e .` writes an __editable__*.pth into site-packages.
#   2. macOS auto-applies UF_HIDDEN (and usually UF_TRACKED) to every new
#      .pth file in the venv.
#   3. Python 3.14's site.addpackage skips hidden .pth files.
#   4. Result: `jobcli` console script fails with
#      "ModuleNotFoundError: No module named 'jobcli'".
#
# Merely running `chflags nohidden` is not enough on many systems — the flag
# is re-applied asynchronously. So this script *also* patches the console
# script wrappers to prepend the repo root to sys.path themselves, which is
# immune to the .pth-hiding behaviour.
#
# Usage:
#   bash scripts/fix_editable_pth_macos.sh             # uses ./.venv
#   bash scripts/fix_editable_pth_macos.sh /path/to/venv

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

# ── 1. Un-hide every .pth (best-effort; macOS may re-hide them) ─────────────
shopt -s nullglob
for p in "$SITE"/*.pth; do
  chflags nohidden "$p" 2>/dev/null || true
  xattr -c "$p" 2>/dev/null || true
done

# ── 2. Patch console-script wrappers so they don't depend on .pth at all ────
# Any exe in $VENV/bin whose body contains "from jobcli" gets a sys.path
# insert line prepended just after the imports.  Idempotent.
PATCH_MARKER="# JobCLI sys.path self-bootstrap"
for exe in "$VENV/bin"/*; do
  [[ -f "$exe" && -x "$exe" ]] || continue
  head -1 "$exe" | grep -q "^#!" || continue
  grep -q "from jobcli" "$exe" || continue
  grep -q "$PATCH_MARKER" "$exe" && continue
  python3 - "$exe" "$ROOT" "$PATCH_MARKER" <<'PY'
import sys, re, pathlib
exe_path, repo_root, marker = sys.argv[1:]
p = pathlib.Path(exe_path)
src = p.read_text()
lines = src.splitlines()
out = [lines[0]]  # shebang
out.append(marker)
out.append(f"import sys as _sys; _sys.path.insert(0, {repo_root!r})")
out.extend(lines[1:])
p.write_text("\n".join(out) + "\n")
print(f"  patched: {p}")
PY
done

echo "Done. Verify with:  $VENV/bin/jobcli --help"
