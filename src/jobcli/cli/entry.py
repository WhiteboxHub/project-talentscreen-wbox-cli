"""Entry point for the `wboxcli` command.

- No arguments  → launches the interactive TUI
- With arguments → forwards to the standard Typer CLI (e.g. `wboxcli apply`)
"""

import sys


def main():
    """Main entry: interactive TUI when called bare, Typer CLI otherwise."""
    from jobcli.cli.launcher import ensure_managed_launcher, warn_if_misconfigured_launcher

    ensure_managed_launcher()
    warn_if_misconfigured_launcher()

    # If the user typed just `wboxcli` with no args, launch the interactive TUI
    if len(sys.argv) <= 1:
        from jobcli.cli.interactive import interactive_session
        interactive_session()
    else:
        # Forward to the standard Typer app so all existing commands work:
        #   wboxcli setup
        #   wboxcli apply
        from jobcli.cli.main import app
        app()


if __name__ == "__main__":
    main()
