"""Support `python -m jobcli` (same entry point as the `jobcli` console script)."""

from jobcli.cli.main import app

if __name__ == "__main__":
    app()
