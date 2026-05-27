#!/usr/bin/env zsh
# Quick launch script for JobCLI development

set -e

cd "$(dirname "$0")"

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "No virtual environment found. Creating .venv..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

python -m pip install --upgrade pip

export PYTHONPATH="$PWD/src"

echo "Launching JobCLI..."
python src/jobcli/cli/entry.py
