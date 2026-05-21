#!/usr/bin/env zsh
# Quick launch script for JobCLI development

set -e

cd "$(dirname "$0")"

# Create/activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "No virtual environment found. Creating .venv..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing requirements.txt..."
    pip install -r requirements.txt
fi

# Export source path
export PYTHONPATH="$PWD/src"

# Launch app
echo "Launching JobCLI..."
python src/jobcli/cli/entry.py