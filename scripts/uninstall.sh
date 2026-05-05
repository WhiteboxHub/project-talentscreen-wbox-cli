#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  JobCLI Global Uninstaller
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/uninstall.sh | bash
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
WRAPPER="$HOME/.local/bin/jobcli"

echo ""
echo -e "${BOLD}${RED}JobCLI — Uninstaller${NC}"
echo ""

# Confirm
read -r -p "This will delete $INSTALL_DIR and $WRAPPER. Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Cancelled.${NC}"
    exit 0
fi

# Remove wrapper
if [ -f "$WRAPPER" ]; then
    rm -f "$WRAPPER"
    echo -e "${GREEN}[✓]${NC} Removed $WRAPPER"
else
    echo -e "${YELLOW}[—]${NC} Wrapper not found at $WRAPPER"
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
