#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  WboxCLI Global Installer
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/bavish13_dev/scripts/install.sh | bash
#
#  What it does:
#    1. Clones (or updates) the repo into ~/.jobcli/src
#    2. Creates a Python venv at ~/.jobcli/venv
#    3. Installs the package + Playwright Chromium
#    4. Drops a `wboxcli` wrapper at ~/.local/bin/
#    5. Adds ~/.local/bin to PATH in your shell profile (if not already there)
#    6. Launches the interactive TUI
#
#  Uninstall:
#    rm -rf ~/.jobcli ~/.local/bin/wboxcli ~/.local/bin/jobcli
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}[✓]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail()  { echo -e "${RED}[✗]${NC}    $*"; exit 1; }

# ── Config ───────────────────────────────────────────────────────────
INSTALL_DIR="$HOME/.jobcli"
SRC_DIR="$INSTALL_DIR/src"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/wboxcli"
WRAPPER_JOBCLI="$BIN_DIR/jobcli"
REPO_URL="https://github.com/WhiteboxHub/wbox-cli.git"
BRANCH="${JOBCLI_BRANCH:-bavish13_dev}"  # Override with JOBCLI_BRANCH=<branch> if needed

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║     WboxCLI — Global Installer       ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Prerequisites ────────────────────────────────────────────
info "Checking prerequisites..."

# Python 3.10+
if ! command -v python3 &>/dev/null; then
    fail "python3 is not installed. Install Python 3.10+ first."
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ is required (found $PY_VERSION)."
fi
ok "Python $PY_VERSION"

# Git
if ! command -v git &>/dev/null; then
    fail "git is not installed."
fi
ok "git found"

# ── Step 2: Clone or update repo ─────────────────────────────────────
info "Setting up source at $SRC_DIR..."

mkdir -p "$INSTALL_DIR"

if [ -d "$SRC_DIR/.git" ]; then
    info "Existing installation found — pulling latest..."
    git -C "$SRC_DIR" fetch origin "$BRANCH" --quiet
    git -C "$SRC_DIR" checkout "$BRANCH" --quiet 2>/dev/null || git -C "$SRC_DIR" checkout -b "$BRANCH" "origin/$BRANCH" --quiet
    git -C "$SRC_DIR" reset --hard "origin/$BRANCH" --quiet
    ok "Updated to latest $BRANCH"
else
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$SRC_DIR" --quiet
    ok "Cloned $BRANCH branch"
fi

# ── Step 3: Create venv and install ──────────────────────────────────
info "Setting up Python virtual environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    ok "Created venv at $VENV_DIR"
else
    ok "Venv already exists"
fi

info "Installing wboxcli and dependencies (this may take a minute)..."

# Activate and install
"$VENV_DIR/bin/pip" install --upgrade pip --quiet 2>/dev/null
"$VENV_DIR/bin/pip" install -e "$SRC_DIR" --quiet 2>/dev/null
ok "wboxcli installed"

# ── Step 4: Install Playwright browsers ──────────────────────────────
info "Installing Playwright Chromium browser..."
"$VENV_DIR/bin/python" -m playwright install chromium --quiet 2>/dev/null || \
    "$VENV_DIR/bin/python" -m playwright install chromium 2>/dev/null || \
    warn "Playwright browser install had issues — run 'jobcli doctor' to verify."
ok "Playwright Chromium ready"

# ── Step 5: Create global wrapper scripts ────────────────────────────
info "Creating global commands at $BIN_DIR..."

mkdir -p "$BIN_DIR"

# Primary command: wboxcli (interactive TUI when bare, CLI with args)
cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# WboxCLI global wrapper — activates the managed venv transparently.
JOBCLI_VENV="$HOME/.jobcli/venv"

if [ ! -f "$JOBCLI_VENV/bin/python" ]; then
    echo "Error: WboxCLI installation not found at $JOBCLI_VENV"
    echo "Re-install with: curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/bavish13_dev/scripts/install.sh | bash"
    exit 1
fi

exec "$JOBCLI_VENV/bin/wboxcli" "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"

# Alias: jobcli (direct Typer CLI for scripting)
cat > "$WRAPPER_JOBCLI" << 'WRAPPER_EOF'
#!/usr/bin/env bash
JOBCLI_VENV="$HOME/.jobcli/venv"
exec "$JOBCLI_VENV/bin/jobcli" "$@"
WRAPPER_EOF
chmod +x "$WRAPPER_JOBCLI"

ok "Commands created: wboxcli (interactive) + jobcli (direct CLI)"

# ── Step 6: Ensure ~/.local/bin is on PATH ────────────────────────────
_add_to_path() {
    local profile_file="$1"
    local marker='# JobCLI PATH'

    if [ -f "$profile_file" ] && grep -q "$marker" "$profile_file" 2>/dev/null; then
        return 0  # Already added
    fi

    echo "" >> "$profile_file"
    echo "$marker" >> "$profile_file"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$profile_file"
    return 1  # Was added
}

NEEDS_RELOAD=false

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    info "Adding ~/.local/bin to PATH..."

    SHELL_NAME=$(basename "$SHELL")
    case "$SHELL_NAME" in
        zsh)
            _add_to_path "$HOME/.zshrc" || true
            NEEDS_RELOAD=true
            ok "Updated ~/.zshrc"
            ;;
        bash)
            _add_to_path "$HOME/.bashrc" || true
            # Also .bash_profile on macOS
            if [ "$(uname)" = "Darwin" ]; then
                _add_to_path "$HOME/.bash_profile" || true
            fi
            NEEDS_RELOAD=true
            ok "Updated shell profile"
            ;;
        *)
            warn "Unknown shell ($SHELL_NAME). Add this to your shell profile manually:"
            echo '  export PATH="$HOME/.local/bin:$PATH"'
            ;;
    esac
else
    ok "~/.local/bin already on PATH"
fi

# ── Step 7: Copy .env template if no .env exists ─────────────────────
if [ ! -f "$INSTALL_DIR/.env" ] && [ -f "$SRC_DIR/.env.template" ]; then
    cp "$SRC_DIR/.env.template" "$INSTALL_DIR/.env"
    info "Created default config at $INSTALL_DIR/.env — edit it with your API keys."
fi

# ── Done! ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║       Installation Complete! 🎉      ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Install dir  : ${CYAN}$INSTALL_DIR${NC}"
echo -e "  Command      : ${CYAN}wboxcli${NC}"
echo ""

if [ "$NEEDS_RELOAD" = true ]; then
    echo -e "  ${YELLOW}→ Restart your terminal or run:${NC}"
    echo -e "    ${BOLD}source ~/.zshrc${NC}"
    echo ""
fi

# ── Auto-launch interactive TUI ───────────────────────────────────────
# If this is a fresh install (not piped/non-interactive), launch wboxcli
if [ -t 0 ] && [ -t 1 ]; then
    echo -e "  ${BOLD}Launching WboxCLI...${NC}"
    echo ""
    # Ensure PATH is current for this session
    export PATH="$BIN_DIR:$PATH"
    exec "$WRAPPER"
else
    echo -e "  ${BOLD}Next steps:${NC}"
    echo -e "    1. Restart your terminal (or source ~/.zshrc)"
    echo -e "    2. Type: ${CYAN}wboxcli${NC}"
    echo ""
fi
