#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  JobCLI Global Uninstaller
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.sh | bash
#    — or —
#    bash ~/.jobcli/src/scripts/uninstall.sh
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="$HOME/.jobcli"
WRAPPER_JOBCLI="$HOME/.local/bin/jobcli"
WRAPPER_WBOXCLI="$HOME/.local/bin/wboxcli"

echo ""
echo -e "${BOLD}${RED}JobCLI — Uninstaller${NC}"
echo ""

# Reconnect stdin if piped so read works
if [ ! -t 0 ]; then
    if [ -c /dev/tty ]; then
        exec < /dev/tty
    else
        echo -e "${YELLOW}Cannot prompt for confirmation interactively.${NC}"
        echo -e "${YELLOW}Please run: bash ~/.jobcli/src/scripts/uninstall.sh${NC}"
        exit 1
    fi
fi

# Confirm
read -r -p "This will delete $INSTALL_DIR, $WRAPPER_JOBCLI, and $WRAPPER_WBOXCLI. Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Cancelled.${NC}"
    exit 0
fi

# Remove wrappers
if [ -f "$WRAPPER_JOBCLI" ]; then
    rm -f "$WRAPPER_JOBCLI"
    echo -e "${GREEN}[✓]${NC} Removed $WRAPPER_JOBCLI"
else
    echo -e "${YELLOW}[—]${NC} Wrapper not found at $WRAPPER_JOBCLI"
fi

if [ -f "$WRAPPER_WBOXCLI" ]; then
    rm -f "$WRAPPER_WBOXCLI"
    echo -e "${GREEN}[✓]${NC} Removed $WRAPPER_WBOXCLI"
else
    echo -e "${YELLOW}[—]${NC} Wrapper not found at $WRAPPER_WBOXCLI"
fi

# Remove install dir
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}[✓]${NC} Removed $INSTALL_DIR"
else
    echo -e "${YELLOW}[—]${NC} Install directory not found at $INSTALL_DIR"
fi

echo ""
echo -e "${GREEN}JobCLI has been uninstalled.${NC}"
echo -e "${YELLOW}Note:${NC} The PATH entry in your shell profile (~/.zshrc) was left intact — remove it manually if you wish."
echo ""
