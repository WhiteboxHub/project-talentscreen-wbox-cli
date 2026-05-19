#!/usr/bin/env zsh
# Quick launch script for JobCLI development

# Ensure we are in the project root
cd "$(dirname "$0")"

# Activate the virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Warning: No virtual environment found!"
fi

# Run the CLI directly from source
echo "Launching JobCLI..."
export PYTHONPATH=src
python src/jobcli/cli/entry.py
