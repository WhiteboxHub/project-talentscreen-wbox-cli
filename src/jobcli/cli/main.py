"""Main CLI application using Typer."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Fix UnicodeEncodeError on Windows terminals when printing checkmarks/symbols
if hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# NOTE: TLS trust roots are configured in ``jobcli/__init__.py`` so that all
# entry points (CLI, tests, interactive) inherit OS-native CA support before
# any HTTP client is built. See ``jobcli/utils/tls.py``.

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from jobcli.orchestration.engine import ApplicationEngine
from jobcli.profile.schemas import ApplicationStatus, CommonQuestions, Config, InteractionMode, Job, ResumeData
from jobcli.storage.models import Database
from jobcli.orchestration.wbox_discoverer import WboxDiscoverer
from jobcli.storage.repositories import (
    ConfigRepository,
    JobRepository,
    UserDataRepository,
)
from jobcli.utils.constants import DASHBOARD_SUMMARY_DAYS, REFERENCE_LINKS_COUNT, SUPPORTED_DOMAINS

app = typer.Typer(
    name="jobcli",
    help="Production-grade CLI for automated job applications",
)

db_app = typer.Typer(help="Local database maintenance")
app.add_typer(db_app, name="db")

console = Console()

# Default config directory
CONFIG_DIR = Path.home() / ".jobcli"
CONFIG_FILE = CONFIG_DIR / "config.json"
DATABASE_FILE = CONFIG_DIR / "jobcli.db"


def _print_next_step(command: str, hint: str = "") -> None:
    """Print a prominent boxed "Next" hint after every command succeeds.

    Keeps the flow visible to the user at every step:
        login → resume-upload → setup → discover → apply

    The hint is rendered as a Rich panel so it sticks out from regular log
    output and the user can't miss it as the terminal scrolls.
    """
    from rich.panel import Panel
    body_lines = [f"  [bold cyan]jobcli {command}[/bold cyan]"]
    if hint:
        body_lines.append(f"  [dim]{hint}[/dim]")
    console.print()
    console.print(
        Panel(
            "\n".join(body_lines),
            title="[bold green]▶ Next step[/bold green]",
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )
    )


def _suggest_after_login_or_resume() -> tuple[str, str]:
    """Pick the right next command based on what's still missing.

    Walks the canonical flow login → resume-upload → setup → discover → apply
    and returns the first step the user hasn't completed yet.
    """
    cfg = get_config()
    if not (cfg.resume_pdf_path and cfg.resume_json_path):
        return "resume-upload --pdf <file.pdf> --json <file.json>", "load your resume"
    ext = (cfg.extension_path or "").strip()
    if not ext or not Path(ext).exists():
        return "setup", "download the TalentScreen extension and verify your setup"
    return "discover", "pull job listings from WBL"

# ``jobcli config --key`` accepts these env-style names as aliases for the stored field.
CONFIG_CMD_KEY_ALIASES: dict[str, str] = {
    "JOBCLI_SYNC_SERVER_URL": "sync_server_url",
    "NEXT_PUBLIC_API_URL": "sync_server_url",
}


def ensure_config_dir() -> None:
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_database() -> Database:
    """Get database instance."""
    db_path_env = os.getenv("DATABASE_PATH")
    if db_path_env:
        db_path = Path(os.path.expandvars(os.path.expanduser(db_path_env)))
    else:
        ensure_config_dir()
        db_path = DATABASE_FILE

    db = Database(f"sqlite:///{db_path.as_posix()}")
    db.create_tables()
    return db


def resolve_active_sqlite_database_path() -> Path:
    """Filesystem path to the active SQLite DB (same rules as ``get_database``)."""
    raw = os.getenv("DATABASE_PATH")
    if raw:
        return Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
    ensure_config_dir()
    return DATABASE_FILE.resolve()


def get_config() -> Config:
    """Load configuration from the local SQLite ``config`` table.

    There is **no ``.env`` loading** — all settings (credentials, LLM keys,
    resume paths, API base URL, extension path) are written by interactive
    commands (``login``, ``resume-upload``, ``setup``) and persisted in
    ``~/.jobcli/jobcli.db``. To change a value later, use
    ``jobcli config --key <name> --set <value>`` or re-run ``jobcli login``.
    """
    db = get_database()
    session = db.get_session()
    config_repo = ConfigRepository(session)

    try:
        config = config_repo.get_all()
    except Exception:
        config = Config()

    # Browser must always be visible while applying — no env switch.
    config.headless = False

    session.close()
    return config


def save_config(config: Config) -> None:
    """Save configuration."""
    db = get_database()
    session = db.get_session()
    config_repo = ConfigRepository(session)
    config_repo.save_config(config)
    session.close()


def _require_wbl_credentials_for_discovery(config: Config) -> None:
    """Exit with a clear message unless WBL username/password are available (DB or env)."""
    u = (config.job_board_username or os.getenv("JOBCLI_USERNAME") or "").strip()
    p = config.job_board_password or os.getenv("JOBCLI_PASSWORD")
    if not u or not p:
        console.print(
            "[red]Missing WBL credentials or API URL. Run [cyan]setup[/cyan] or [cyan]login[/cyan] first.[/red]"
        )
        raise typer.Exit(1)


def ensure_configured(config: Config, require_job_board: bool = True) -> None:
    """Ensure the user has logged in and configured required credentials."""
    if require_job_board and (not config.job_board_username or not config.job_board_password):
        console.print("[yellow]Warning: Missing job board credentials.[/yellow]")
        console.print("Run [cyan]login[/cyan] if you need to discover jobs or view Whitebox-hosted listings.")
        
    has_llm = config.openai_api_key or config.anthropic_api_key or config.gemini_api_key
    if not has_llm:
        console.print("\n[yellow]Warning: No LLM API keys configured. Phase 2 (Autonomous Reasoning) will be disabled.[/yellow]")
        console.print("Run [cyan]login[/cyan] to unlock full AI automation capabilities.\n")


def print_dashboard_summary(session):
    """Print the 7-day dashboard summary as requested by the user."""
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    
    repo = JobRepository(session)
    stats = repo.get_dashboard_stats()
    
    console.print()
    summary_text = (
        f"[bold white]Total Jobs present in WBL for last {DASHBOARD_SUMMARY_DAYS} days:[/] [bold cyan]{stats['total_wbl']}[/]\n"
        f"[bold white]Already applied for you -[/] [bold green]{stats['applied_count']}[/]\n"
        f"[bold white]Remaining total jobs -[/] [bold #f0abfc]{stats['remaining_count']}[/]\n"
        f"[bold white]CLI friendly -[/] [bold #c084fc]{stats['cli_friendly']}[/]\n"
        f"[bold white]Unsupported / skipped -[/] [bold yellow]{stats.get('unsupported_skipped', 0)}[/]"
    )
    
    console.print(Panel(summary_text, title="[bold #c084fc]WBox Dashboard Summary[/]", border_style="#c084fc", expand=False))
    
    if stats['latest_links']:
        console.print(f"\n[bold #f0abfc]Oldest-first {len(stats['latest_links'])} job links for reference:[/]")
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold #c084fc")
        table.add_column("Title", style="cyan")
        table.add_column("URL", style="blue")
        table.add_column("Date", style="dim")
        
        for job in stats['latest_links']:
            url = job['url'][:50] + "..." if len(job['url']) > 50 else job['url']
            ca = job['created_at']
            date_s = ca.strftime("%Y-%m-%d") if hasattr(ca, "strftime") else str(ca)
            table.add_row(job['title'] or "Untitled", url, date_s)
        
        console.print(table)


@app.command()
def uninstall(force: bool = typer.Option(False, "--force", "-f", help="Force uninstall without confirmation")) -> None:
    """Remove all JobCLI configuration, databases, and global shims.

    Works on Windows and macOS/Linux. On Windows we cannot delete the active
    venv while ``jobcli.exe`` is still running, so the venv is left for the
    bundled ``scripts/uninstall.ps1`` to clean up (or a manual rm after the
    process exits).
    """
    import shutil

    console.print("[bold red]JobCLI Uninstall[/bold red]\n")
    if not force:
        confirm = Confirm.ask(
            "Delete all JobCLI data in ~/.jobcli (config, jobs, logs, resume, memory) and the wboxcli/jobcli shims?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Uninstall cancelled.[/yellow]")
            return

    # Release SQLite/log file handles so Windows lets us delete them.
    from jobcli.utils.logger import global_logger
    global_logger.shutdown()
    try:
        get_database().engine.dispose()
    except Exception:
        pass

    # Detect "are we running from inside ~/.jobcli/venv?" — if so, skip the venv
    # subtree so we don't hit "file in use" on Windows.
    is_windows = os.name == "nt"
    venv_dir = CONFIG_DIR / "venv"
    running_from_venv = False
    try:
        exe_path = Path(sys.executable).resolve()
        running_from_venv = venv_dir.resolve() in exe_path.parents
    except Exception:
        running_from_venv = False

    leftover_paths: list[Path] = []

    if CONFIG_DIR.exists():
        if running_from_venv:
            # Delete everything inside ~/.jobcli except the venv subtree.
            for child in CONFIG_DIR.iterdir():
                if child.resolve() == venv_dir.resolve():
                    leftover_paths.append(child)
                    continue
                try:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=False)
                    else:
                        child.unlink()
                    console.print(f"[green]✓ Removed {child}[/green]")
                except Exception as e:
                    console.print(f"[red]✗ Failed to remove {child}: {e}[/red]")
                    leftover_paths.append(child)
        else:
            try:
                shutil.rmtree(CONFIG_DIR)
                console.print(f"[green]✓ Removed {CONFIG_DIR}[/green]")
            except Exception as e:
                console.print(f"[red]✗ Failed to remove {CONFIG_DIR}: {e}[/red]")
                leftover_paths.append(CONFIG_DIR)
    else:
        console.print(f"[yellow]— No configuration directory at {CONFIG_DIR}[/yellow]")

    # Remove the global shims dropped by install.ps1 / install.sh
    bin_dir = Path.home() / ".local" / "bin"
    shim_names = ("wboxcli.cmd", "jobcli.cmd") if is_windows else ("wboxcli", "jobcli")
    for name in shim_names:
        shim = bin_dir / name
        if shim.exists() or shim.is_symlink():
            try:
                shim.unlink()
                console.print(f"[green]✓ Removed {shim}[/green]")
            except Exception as e:
                console.print(f"[yellow]— Could not remove {shim}: {e}[/yellow]")
                leftover_paths.append(shim)

    if leftover_paths:
        console.print()
        console.print("[yellow]Some files could not be removed while jobcli was still running.[/yellow]")
        console.print("[yellow]Close this terminal and finish cleanup with:[/yellow]")
        if is_windows:
            console.print('  [cyan]Remove-Item -Recurse -Force "$env:USERPROFILE\\.jobcli"[/cyan]')
            console.print('  [cyan]Remove-Item -Force "$env:USERPROFILE\\.local\\bin\\wboxcli.cmd","$env:USERPROFILE\\.local\\bin\\jobcli.cmd"[/cyan]')
            console.print('  [dim](or)[/dim] [cyan]irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.ps1 | iex[/cyan]')
        else:
            console.print('  [cyan]rm -rf ~/.jobcli ~/.local/bin/wboxcli ~/.local/bin/jobcli[/cyan]')
            console.print('  [dim](or)[/dim] [cyan]curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.sh | bash[/cyan]')
    else:
        console.print("\n[green]JobCLI has been fully uninstalled.[/green]")


@db_app.command("clear-jobs")
def db_clear_jobs(
    force: bool = typer.Option(False, "--force", "-f", help="Delete without confirmation"),
) -> None:
    """Delete all local jobs and job-scoped logs (preserves resume, config, memory)."""
    console.print("[bold cyan]Clear job data[/bold cyan]\n")
    if not force:
        if not Confirm.ask(
            "Delete all jobs and application logs from the local database?\n"
            "(Resume, field answers, learned locators, and config are kept.)",
            default=False,
        ):
            console.print("[yellow]Cancelled.[/yellow]")
            return
    db = get_database()
    session = db.get_session()
    try:
        n = JobRepository(session).clear_job_related_data()
        console.print(f"[green]✓ Removed {n} job record(s) and related logs.[/green]")
    finally:
        session.close()


def _run_db_reset(force: bool) -> None:
    """Delete the SQLite DB file (+ WAL/SHM/journal) and recreate an empty schema."""
    from jobcli.sync.client import reset_sync_client_singleton
    from jobcli.storage.models import Database

    console.print("[bold red]Reset local JobCLI database[/bold red]\n")
    if not force:
        if not Confirm.ask(
            "This will delete the entire local JobCLI SQLite database, including saved login, "
            "resume data, jobs, logs, memory, learned locators, and sync metadata. Continue?",
            default=False,
        ):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    db_path = resolve_active_sqlite_database_path()
    url_s = str(db_path)
    if ":memory:" in url_s:
        console.print("[red]Cannot reset an in-memory database. Point DATABASE_PATH at a file path.[/red]")
        raise typer.Exit(1)

    from jobcli.utils.logger import global_logger

    global_logger.shutdown()

    try:
        db = get_database()
        db.engine.dispose()
    except Exception:
        pass

    reset_sync_client_singleton()

    paths_to_remove = [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        Path(f"{db_path}-journal"),
    ]
    for p in paths_to_remove:
        if p.exists():
            try:
                p.unlink()
            except OSError as e:
                console.print(f"[red]Failed to delete {p}: {e}[/red]")
                raise typer.Exit(1) from e

    db_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = Database(f"sqlite:///{db_path.as_posix()}")
    fresh.create_tables()
    console.print(
        "[green]Local JobCLI database reset successfully. Run [cyan]setup[/cyan] to configure credentials again.[/green]"
    )


@db_app.command("reset")
def db_reset(
    force: bool = typer.Option(False, "--force", "-f", help="Reset without confirmation"),
) -> None:
    """Delete the entire local SQLite database file and recreate empty tables.

    Does not remove ``~/.jobcli`` wholesale, log files, or resume PDFs.
    """
    _run_db_reset(force)


@app.command()
def setup() -> None:
    """One-shot setup: validate stored config, load resume from saved paths, discover, browser test.

    Run ``login`` first to save credentials (no ``.env`` file is used). Then ``setup`` will
    pick those up from local config and continue with resume, discover, and a browser test.
    """
    console.print("[bold cyan]╔══════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║       W-BOX CLI — One-Shot Setup     ║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════╝[/bold cyan]\n")

    # ── STEP 1: Config ────────────────────────────────────────────────────────
    console.print("[bold]Step 1/5 — Verifying configuration in local store (~/.jobcli/jobcli.db)...[/bold]")
    ensure_config_dir()
    db = get_database()
    config = get_config()
    save_config(config)

    has_llm = bool(config.openai_api_key or config.anthropic_api_key or config.gemini_api_key)
    has_wbox = bool(config.job_board_username and config.job_board_password)

    if has_llm:
        console.print(f"  [green]✓ LLM provider: {config.default_llm_provider}[/green]")
    else:
        console.print("  [red]✗ No LLM API key configured.[/red]")
        console.print("    [yellow]AI form-filling will be disabled. Run [cyan]login[/cyan] and add at least one LLM key.[/yellow]")

    if has_wbox:
        api_hint = (config.sync_server_url or "default https://api.whitebox-learning.com/api").strip()
        console.print(f"  [green]✓ Whitebox credentials for: {config.job_board_username}[/green]")
        console.print(f"    [dim]API base: {api_hint}[/dim]")
    else:
        console.print("  [yellow]⚠ No Whitebox credentials. Run [cyan]login[/cyan].[/yellow]")
        console.print("    Job discovery will be skipped.")

    # ── STEP 2: Resume ────────────────────────────────────────────────────────
    console.print("\n[bold]Step 2/5 — Checking resume (saved paths from previous resume-upload)...[/bold]")

    pdf_path_str = config.resume_pdf_path
    json_path_str = config.resume_json_path

    resume_loaded = False
    if not pdf_path_str or not json_path_str:
        console.print("  [yellow]⚠ No resume in local config.[/yellow]")
        console.print(
            "    Run [cyan]resume-upload --pdf <file.pdf> --json <file.json>[/cyan] to load one."
        )
    else:
        pdf_path = Path(pdf_path_str.strip('"').strip("'"))
        json_path = Path(json_path_str.strip('"').strip("'"))

        if not pdf_path.exists():
            console.print(f"  [red]✗ PDF not found: {pdf_path}[/red]")
        elif not json_path.exists():
            console.print(f"  [red]✗ JSON not found: {json_path}[/red]")
        else:
            try:
                import json as _json
                with open(json_path, encoding="utf-8") as f:
                    resume_data = _json.load(f)

                resume = ResumeData(**resume_data)

                session = db.get_session()
                user_data_repo = UserDataRepository(session)
                user_data_repo.save_resume(resume)
                session.close()

                config.resume_pdf_path = str(pdf_path.absolute())
                config.resume_json_path = str(json_path.absolute())
                save_config(config)

                console.print(f"  [green]✓ Resume loaded: {resume.personal.first_name} {resume.personal.last_name}[/green]")
                console.print(f"    PDF : {pdf_path.name}")
                console.print(f"    JSON: {json_path.name}")
                resume_loaded = True
            except Exception as e:
                console.print(f"  [red]✗ Failed to parse resume JSON: {e}[/red]")

    # ── STEP 3: Discover Jobs ─────────────────────────────────────────────────
    console.print("\n[bold]Step 3/5 — Discovering jobs from Whitebox dashboard...[/bold]")

    jobs_found = 0
    if not has_wbox:
        console.print("  [yellow]⚠ Skipped — no Whitebox credentials. Run [cyan]login[/cyan].[/yellow]")
    else:
        try:
            session = db.get_session()
            discoverer = WboxDiscoverer(session, config=config)
            with console.status("[bold green]Fetching jobs from WBL (API)..."):
                new_jobs = discoverer.discover(headless=config.headless)
            session.close()

            jobs_found = len(new_jobs)
            if jobs_found > 0:
                console.print(f"  [green]✓ Discovered {jobs_found} new job(s) from the dashboard.[/green]")
            else:
                console.print("  [yellow]⚠ No new jobs found (they may already be in your database).[/yellow]")
        except Exception as e:
            console.print(f"  [red]✗ Job discovery failed: {e}[/red]")
            console.print("    You can run [cyan]discover[/cyan] manually later.")


    # ── STEP 4: Browser & Extension Test ─────────────────────────────────────
    console.print("\n[bold]Step 4/5 — Testing browser & extension...[/bold]")
    browser_ok = False
    extension_loaded = False
    browser_error: str = ""

    # ── 4a: Install bundled extension & resolve path ────────────────────────
    from jobcli.extension.helpers import (
        chromium_extension_launch_args,
        extension_manifest_has_page_bridge,
        read_extension_manifest_version,
        resolve_extension_dir,
    )
    from jobcli.extension.install import refresh_installed_extension

    ext_dir: Optional[str] = None
    try:
        installed = refresh_installed_extension()
        ext_dir = str(installed)
        config.extension_path = ext_dir
        save_config(config)
        console.print("[bold]TalentScreen extension installed to:[/bold]")
        console.print(f"  {installed}")
    except RuntimeError as exc:
        console.print(f"  [red]✗ Failed to install bundled extension: {exc}[/red]")
        console.print("    Reinstall JobCLI or run [cyan]jobcli setup[/cyan] again.")
        ext_dir = resolve_extension_dir(config.extension_path)
        if ext_dir:
            config.extension_path = ext_dir
            save_config(config)

    if not ext_dir:
        console.print(
            "  [red]✗ Extension not found. Run [cyan]jobcli setup[/cyan] again or reinstall JobCLI.[/red]"
        )
        browser_error = "Extension not found"
    else:
        ext_ver = read_extension_manifest_version(ext_dir)
        ver_label = f" (v{ext_ver})" if ext_ver else ""
        console.print(f"  [green]✓ Extension directory ready{ver_label}: {ext_dir}[/green]")
        if extension_manifest_has_page_bridge(ext_dir):
            console.print(
                "  [green]✓ Manifest declares Playwright page-world bridge (pageWorldBridge.js)[/green]"
            )
        else:
            console.print(
                "  [yellow]⚠ Manifest missing MAIN-world pageWorldBridge.js — CLI autofill may not work.[/yellow]"
            )

        # ── 4b: Launch browser with extension and verify it loaded ────────
        try:
            from playwright.sync_api import sync_playwright
            from jobcli.automation.stealth import LAUNCH_ARGS, IGNORE_DEFAULT_ARGS, CONTEXT_OPTIONS
            import tempfile

            test_url = os.getenv("WBOX_LOGIN_URL", "https://whitebox-learning.com/login")
            launch_args = list(LAUNCH_ARGS) + chromium_extension_launch_args(ext_dir)

            with console.status("[bold green]Launching browser with extension (this may take ~15s)..."):
                with sync_playwright() as pw:
                    user_data_dir = tempfile.mkdtemp(prefix="jobcli_setup_test_")
                    ctx = pw.chromium.launch_persistent_context(
                        user_data_dir,
                        headless=False,
                        args=launch_args,
                        ignore_default_args=IGNORE_DEFAULT_ARGS,
                        **CONTEXT_OPTIONS,
                    )

                    page = ctx.new_page()
                    response = page.goto(test_url, timeout=30000, wait_until="domcontentloaded")
                    status_code = response.status if response else 0
                    page_title = page.title() or "(no title)"

                    # Check extension is actually attached via service workers / background pages
                    try:
                        sw = list(ctx.service_workers)
                        bp = list(ctx.background_pages)
                        extension_loaded = bool(sw or bp)
                    except Exception:
                        extension_loaded = False

                    console.print("\n  [cyan]Holding browser open for 15 seconds for visual inspection...[/cyan]")
                    page.wait_for_timeout(15000)
                    ctx.close()

            if status_code and status_code < 400:
                browser_ok = True
                if extension_loaded:
                    console.print(f"  [green]✓ Extension loaded and verified successfully: {Path(ext_dir).name}[/green]")
                else:
                    console.print(f"  [yellow]⚠ Extension directory found, but Playwright could not verify its background service. It may load on the first application.[/yellow]")
                console.print(f"  [green]✓ Test URL reachable ({test_url}) — HTTP {status_code}[/green]")
                console.print(f"    Page title: {page_title}")
            else:
                browser_error = f"HTTP {status_code} from {test_url}"
                console.print(f"  [red]✗ Test URL returned error status: {browser_error}[/red]")

        except Exception as _be:
            browser_error = str(_be)
            console.print(f"  [red]✗ Browser launch failed: {browser_error}[/red]")
            console.print("    Make sure Playwright is installed: [cyan]playwright install chromium[/cyan]")

    # ── STEP 5: Summary ───────────────────────────────────────────────────────
    console.print("\n[bold]Step 5/5 — Summary[/bold]")
    console.print("─" * 45)
    console.print(f"  Config saved   : [green]✓[/green]  {CONFIG_FILE}")
    console.print(f"  LLM ready      : {'[green]✓[/green]' if has_llm else '[red]✗[/red]'}")
    console.print(f"  Resume loaded  : {'[green]✓[/green]' if resume_loaded else '[yellow]⚠ skipped[/yellow]'}")
    console.print(f"  Jobs found     : [green]{jobs_found}[/green] new job(s)")
    console.print(f"  Browser test   : {'[green]✓ PASSED[/green]' if browser_ok else '[red]✗ FAILED[/red]'}")
    if extension_loaded:
        console.print(f"  Extension      : [green]✓ loaded[/green]")
    console.print("─" * 45)

    if has_llm and resume_loaded and browser_ok:
        console.print("\n[bold green]✓ Setup complete! You are ready to apply.[/bold green]")
        _print_next_step("discover", "pull listings, then run apply")
    else:
        console.print("\n[bold yellow]⚠ Setup finished with warnings. Fix the issues above, then re-run setup.[/bold yellow]")
        if not resume_loaded:
            _print_next_step("resume-upload --pdf <file.pdf> --json <file.json>", "load your resume")
        else:
            _print_next_step("setup", "re-run after fixing the issues above")


@app.command()
def login(
    auto: bool = typer.Option(False, "--auto", help="Skip prompts if credentials already saved in local config"),
) -> None:
    """Configure credentials for job boards and LLM APIs."""
    console.print("[bold cyan]JobCLI Login[/bold cyan]\n")

    config = get_config()
    
    if auto and config.job_board_username and (config.openai_api_key or config.anthropic_api_key or config.gemini_api_key):
        console.print("[green]✓ Credentials already saved in local config. Skipping manual entry.[/green]")
        return

    # Job board credentials
    console.print("[bold]Job Board Credentials[/bold]")
    job_board_username = Prompt.ask(
        "whitebox-learning.com username",
        default=config.job_board_username or "",
    )
    job_board_password = Prompt.ask(
        "whitebox-learning.com password",
        password=True,
    )

    if job_board_username:
        config.job_board_username = job_board_username
    if job_board_password:
        config.job_board_password = job_board_password

    # Auto-detect the WBL API base URL. Only one endpoint is probed:
    #   - https://api.whitebox-learning.com/api   (production)
    # Probe it with the supplied credentials and save it if authentication
    # succeeds. The legacy ``127.0.0.1:8000`` localhost probe was removed
    # because it added noise to error messages on machines with no local
    # backend running. Developers who need a local backend can still set it
    # explicitly via ``jobcli config --key sync_server_url --set <url>``.
    # If the probe uncovers actionable issues (bad creds, TLS) we surface a
    # concise warning.
    from jobcli.sync.client import (
        probe_wbl_api_detailed,
        WBL_API_CANDIDATES,
        LOGIN_ERR_BAD_CREDENTIALS,
        LOGIN_ERR_ACCOUNT_LOCKED,
        LOGIN_ERR_SSL,
        LOGIN_ERR_RATE_LIMIT,
    )

    probe_warning_lines: list[str] = []
    if job_board_username and job_board_password:
        winning, probe_errors = probe_wbl_api_detailed(job_board_username, job_board_password)
        config.sync_server_url = winning or WBL_API_CANDIDATES[0]
        if not winning and probe_errors:
            kinds = {e["kind"] for e in probe_errors}
            # Only flag what the user can act on right now. Pure network errors
            # (local backend down, no VPN) stay silent — login still saves
            # credentials and discover retries on demand.
            if LOGIN_ERR_BAD_CREDENTIALS in kinds:
                probe_warning_lines.append(
                    "WBL did not accept these credentials. Re-run 'jobcli login' "
                    "with the correct email/password — discover will fail otherwise."
                )
            if LOGIN_ERR_ACCOUNT_LOCKED in kinds:
                probe_warning_lines.append(
                    "Your WBL account appears inactive/locked. Contact Recruiting "
                    "before running 'jobcli discover'."
                )
            if LOGIN_ERR_SSL in kinds:
                probe_warning_lines.append(
                    "TLS certificate verification failed for the WBL API. "
                    "Set JOBCLI_SSL_CA_BUNDLE=<path-to-ca.pem> (preferred) or "
                    "JOBCLI_INSECURE_TLS=1 (insecure) before 'jobcli discover'."
                )
            if LOGIN_ERR_RATE_LIMIT in kinds:
                probe_warning_lines.append(
                    "WBL rate-limited the login probe. Wait a minute, then run "
                    "'jobcli discover' — credentials were saved successfully."
                )
    else:
        # No creds yet — save the production URL so SyncClient has a starting point.
        if not (config.sync_server_url or "").strip():
            config.sync_server_url = WBL_API_CANDIDATES[0]

    # LLM API keys
    console.print("\n[bold]LLM API Keys (optional)[/bold]")
    console.print("At least one LLM provider is recommended for better automation.")

    openai_key = Prompt.ask(
        "OpenAI API key",
        default=config.openai_api_key or "",
        show_default=False,
    )
    anthropic_key = Prompt.ask(
        "Anthropic API key",
        default=config.anthropic_api_key or "",
        show_default=False,
    )
    gemini_key = Prompt.ask(
        "Google Gemini API key",
        default=config.gemini_api_key or "",
        show_default=False,
    )

    if openai_key:
        config.openai_api_key = openai_key
    if anthropic_key:
        config.anthropic_api_key = anthropic_key
    if gemini_key:
        config.gemini_api_key = gemini_key

    # Default LLM provider
    if openai_key or anthropic_key or gemini_key:
        provider = Prompt.ask(
            "Default LLM provider",
            choices=["openai", "anthropic", "gemini"],
            default=config.default_llm_provider,
        )
        config.default_llm_provider = provider  # type: ignore

    # Save config
    save_config(config)

    console.print("\n[bold green]✓ Credentials saved successfully[/bold green]")
    for line in probe_warning_lines:
        console.print(f"[yellow]⚠ {line}[/yellow]")
    cmd, hint = _suggest_after_login_or_resume()
    _print_next_step(cmd, hint)


@app.command()
def config_cmd(
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Configuration key to view or set"),
    set_value: Optional[str] = typer.Option(None, "--set", help="Set configuration value"),
) -> None:
    """View or modify configuration.

    Use ``sync_server_url`` for the WBL API base (aliases: JOBCLI_SYNC_SERVER_URL, NEXT_PUBLIC_API_URL), e.g.:

        jobcli config --key sync_server_url --set https://api.whitebox-learning.com/api
    """
    config = get_config()

    resolved_key = CONFIG_CMD_KEY_ALIASES.get(key, key) if key else None

    if key and set_value:
        # Set configuration
        rk = resolved_key or key
        if rk and hasattr(config, rk):
            setattr(config, rk, set_value)
            save_config(config)
            console.print(f"[green]✓ Set {rk} = {set_value}[/green]")
        else:
            console.print(f"[red]Unknown configuration key: {key}[/red]")

    elif key:
        # View specific key
        rk = resolved_key or key
        if rk and hasattr(config, rk):
            value = getattr(config, rk)
            console.print(f"{rk}: {value}")
        else:
            console.print(f"[red]Unknown configuration key: {key}[/red]")

    else:
        # View all configuration
        table = Table(title="JobCLI Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")

        config_dict = config.model_dump()
        for k, v in config_dict.items():
            # Hide sensitive values
            if "key" in k.lower() or "password" in k.lower():
                if v:
                    v = "***" + str(v)[-4:] if len(str(v)) > 4 else "***"
            table.add_row(k, str(v))

        console.print(table)


def _clean_path_input(raw: Optional[str]) -> Optional[str]:
    """Strip surrounding quotes / whitespace that Windows shells often leave on
    pasted paths. Saves us from the classic ``C:\\Users\\sampa\\"C:\\..."``
    bug where the literal ``"`` becomes part of the stored path string.

    Handles three cases observed in the wild:
      1. ``"C:\\Users\\sam\\resume.pdf"`` → ``C:\\Users\\sam\\resume.pdf``
      2. ``'C:\\Users\\sam\\resume.pdf'`` → ``C:\\Users\\sam\\resume.pdf``
      3. Trailing whitespace from interactive paste.
    """
    if raw is None:
        return None
    s = raw.strip()
    # PowerShell tab-completion sometimes wraps paths with spaces in quotes
    # and the shell passes the quotes through to Python as part of argv.
    for quote in ('"', "'"):
        if len(s) >= 2 and s.startswith(quote) and s.endswith(quote):
            s = s[1:-1].strip()
            break
    return s or None


@app.command()
def resume_upload(
    pdf: str = typer.Option(..., help="Path to resume PDF"),
    json_file: Optional[str] = typer.Option(None, "--json", help="Path to resume JSON (optional)"),
) -> None:
    """Upload resume in PDF format (JSON is optional)."""
    console.print("[bold cyan]Resume Upload[/bold cyan]\n")

    # Strip surrounding quotes that PowerShell / cmd often pass through when
    # a path is pasted. Without this, a user typing
    # ``--pdf "C:\Users\sam\resume.pdf"`` would have the literal quotes
    # stored in the DB, and downstream code (which prepends CWD to relative
    # paths) would produce errors like
    # ``C:\Users\sampa\"C:\Users\sampa\Downloads\resume.pdf"``.
    pdf = _clean_path_input(pdf) or ""
    json_file = _clean_path_input(json_file)

    # Validate PDF
    pdf_path = Path(pdf).expanduser().resolve()
    if not pdf_path.exists():
        console.print(f"[red]PDF file not found: {pdf_path}[/red]")
        console.print(
            "[dim]Tip: don't wrap paths in quotes if they contain no spaces; "
            "if they do, plain quotes are fine — JobCLI strips them before saving.[/dim]"
        )
        raise typer.Exit(1)

    # Use existing JSON if provided, otherwise look for one in the same directory or use a dummy
    if json_file:
        json_path = Path(json_file).expanduser().resolve()
    else:
        # Try to find a .json file with the same name as the PDF
        json_path = pdf_path.with_suffix(".json")
        if not json_path.exists():
            # Create a minimal valid JSON so the system doesn't crash
            console.print("[yellow]No JSON provided. Creating a basic profile from your login info...[/yellow]")
            config = get_config()
            minimal_resume = {
                "personal": {
                    "first_name": config.job_board_username.split("@")[0] if config.job_board_username else "User",
                    "last_name": "Applicant",
                    "email": config.job_board_username or "user@example.com",
                    "phone": "",
                    "location": "",
                    "linkedin": "",
                    "github": "",
                    "website": ""
                },
                "education": [],
                "experience": [],
                "skills": [],
                "projects": [],
                "summary": "Professional applicant."
            }
            json_path.write_text(json.dumps(minimal_resume, indent=2))

    if not json_path.exists():
        console.print(f"[red]JSON file not found: {json_path}[/red]")
        raise typer.Exit(1)

    try:
        with open(json_path, encoding="utf-8") as f:
            resume_data = json.load(f)

        # Use project's native auto-detector to normalize various JSON formats
        from jobcli.intelligence.synonym_resolver import ResumeAutoDetector
        normalized_data = ResumeAutoDetector.detect_and_convert(resume_data)

        # Validate with Pydantic
        resume = ResumeData(**normalized_data)

        console.print(f"✓ Resume JSON validated")
        console.print(f"  Name: {resume.personal.first_name} {resume.personal.last_name}")
        console.print(f"  Email: {resume.personal.email}")
        console.print(f"  Experience entries: {len(resume.experience)}")
        console.print(f"  Education entries: {len(resume.education)}")

    except Exception as e:
        console.print(f"[red]Invalid resume JSON: {e}[/red]")
        raise typer.Exit(1)

    # Save to database
    db = get_database()
    session = db.get_session()
    user_data_repo = UserDataRepository(session)

    user_data_repo.save_resume(resume)
    session.close()

    # Save paths to config
    config = get_config()
    config.resume_pdf_path = str(pdf_path.absolute())
    config.resume_json_path = str(json_path.absolute())
    save_config(config)

    console.print("\n[bold green]✓ Resume uploaded successfully[/bold green]")
    cmd, hint = _suggest_after_login_or_resume()
    _print_next_step(cmd, hint)




@app.command()
def questions() -> None:
    """Pre-fill answers to common application questions."""
    console.print("[bold cyan]Common Application Questions[/bold cyan]\n")

    # Load existing answers if any
    db = get_database()
    session = db.get_session()
    user_data_repo = UserDataRepository(session)

    existing = user_data_repo.get_questions()

    questions_data = CommonQuestions()

    # Prompt for each question
    questions_data.salary_expectations = Prompt.ask(
        "Salary expectations",
        default=existing.salary_expectations if existing else "",
        show_default=True,
    )

    questions_data.notice_period = Prompt.ask(
        "Notice period",
        default=existing.notice_period if existing else "",
    )

    willing_relocate = Confirm.ask(
        "Willing to relocate?",
        default=existing.willing_to_relocate if existing else None,
    )
    questions_data.willing_to_relocate = willing_relocate

    questions_data.remote_preference = Prompt.ask(
        "Remote work preference",
        choices=["remote", "hybrid", "onsite", "flexible"],
        default=existing.remote_preference if existing else "flexible",
    )

    questions_data.start_date = Prompt.ask(
        "Available start date",
        default=existing.start_date if existing else "",
    )

    questions_data.referral = Prompt.ask(
        "Referral (if any)",
        default=existing.referral if existing else "",
    )

    # Save
    user_data_repo.save_questions(questions_data)
    session.close()

    console.print("\n[bold green]✓ Answers saved successfully[/bold green]")


def _run_apply(
    *,
    url: Optional[str],
    limit: Optional[int],
    sort: str,
    mode: str,
) -> None:
    """Shared implementation for ``jobcli apply`` (single URL or batch).

    Exit semantics
    --------------
    The user can quit at any interactive prompt by typing one of
    ``q``/``quit``/``exit``/``:q`` or pressing **Ctrl+C** (twice in 2s to
    force-quit). Both raise :class:`ExitRequested`, which we catch here to
    close the browser cleanly, persist learned state, and print a tally —
    distinct from an unexpected crash. This is wired uniformly across
    every prompt the engine exposes (handoff, submit confirm, ASK
    actions, LinkedIn-skip yes/no, manual pauses) via
    ``AgentInterface._get_user_input``.
    """
    from jobcli.utils.exit_signal import (
        ExitRequested,
        install_global_sigint_handler,
        is_exit_requested,
    )

    console.print("[bold cyan]Job Application[/bold cyan]\n")

    # Install the SIGINT handler before we touch any blocking primitive so
    # Ctrl+C in PowerShell wakes us cleanly instead of leaving daemon-thread
    # input() calls dangling. Safe to call multiple times.
    install_global_sigint_handler()

    config = get_config()
    ensure_configured(config, require_job_board=False)

    try:
        config.interaction_mode = InteractionMode(mode)
    except ValueError:
        console.print(f"[red]Invalid mode '{mode}'. Choose from: auto, supervised, manual[/red]")
        raise typer.Exit(1)

    console.print(f"Mode: [cyan]{config.interaction_mode.value}[/cyan]")
    console.print(
        "[dim]Press [bold]Ctrl+C[/bold] or type [bold]q[/bold] / [bold]quit[/bold] / "
        "[bold]exit[/bold] at any prompt to stop cleanly. Two Ctrl+C within 2s force quits.[/dim]\n"
    )

    db = get_database()
    session = db.get_session()

    user_data_repo = UserDataRepository(session)
    job_repo = JobRepository(session)

    resume = user_data_repo.get_resume()
    if not resume:
        console.print(
            "[red]No resume in the local database.[/red] Run "
            "[cyan]resume-upload --pdf <file.pdf> --json <file.json>[/cyan]."
        )
        raise typer.Exit(1)

    jobs = []

    if url:
        job = job_repo.get_by_url(url)
        if not job:
            job = job_repo.create(
                Job(title="Manual Entry", url=url, status=ApplicationStatus.PENDING)
            )
        if job.status != ApplicationStatus.PENDING:
            job_repo.update_status(job.id, ApplicationStatus.PENDING)
        jobs = [job]

    else:
        jobs = job_repo.list_pending()
        if sort.lower() == "newest":
            jobs.reverse()

        if limit:
            jobs = jobs[:limit]

        if not jobs:
            console.print("[yellow]No pending jobs found. Run [cyan]discover[/cyan] first.[/yellow]")
            raise typer.Exit(0)

    original_count = len(jobs)
    jobs = [
        j
        for j in jobs
        if any(d in j.url.lower() for d in SUPPORTED_DOMAINS)
        and "myworkdayjobs.com" not in j.url.lower()
    ]

    if len(jobs) < original_count:
        console.print(f"[yellow]Filtered out {original_count - len(jobs)} unsupported jobs (Workday, etc.).[/yellow]")

    if not jobs:
        console.print("[yellow]No supported jobs remaining in the list.[/yellow]")
        session.close()
        return

    console.print(f"Applying to {len(jobs)} job(s)...\n")

    engine = ApplicationEngine(config, resume, db)

    # Tally counters so the summary panel is meaningful regardless of how
    # we exit (clean finish, ExitRequested, or unexpected crash).
    submitted = 0
    skipped = 0
    failed = 0
    processed = 0
    exit_reason: Optional[str] = None

    try:
        try:
            engine.start_session()
            for i, job in enumerate(jobs, 1):
                # Allow Ctrl+C between jobs to exit before opening a new tab.
                if is_exit_requested():
                    exit_reason = "Ctrl+C between jobs"
                    break
                console.print(f"[bold]Job {i}/{len(jobs)}[/bold]: {job.url}")
                try:
                    status = engine.apply_to_job(job)
                    console.print(f"Status: [green]{status.value}[/green]\n")
                    processed += 1
                    # Match on the enum value to avoid importing every status.
                    sv = getattr(status, "value", str(status)).lower()
                    if "submit" in sv or "success" in sv or "complete" in sv:
                        submitted += 1
                    elif "skip" in sv or "cancel" in sv:
                        skipped += 1
                    else:
                        failed += 1
                except ExitRequested as ex:
                    exit_reason = ex.reason
                    break
                except KeyboardInterrupt:
                    # Fallback path if the SIGINT handler wasn't installed
                    # (e.g. running under an embedded interpreter). Treated
                    # identically to an ExitRequested.
                    exit_reason = "Ctrl+C (KeyboardInterrupt)"
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]\n")
                    failed += 1
                    processed += 1
                    continue
        except ExitRequested as ex:
            # ExitRequested raised by ``engine.start_session()`` (i.e. user
            # quit during browser startup) — handled identically to the
            # per-job path, just no jobs processed.
            exit_reason = ex.reason
        except KeyboardInterrupt:
            exit_reason = "Ctrl+C during startup"
    finally:
        # ``stop_session`` closes the Playwright browser context. Guarded
        # because a Ctrl+C during start_session() leaves no browser to
        # close and we don't want the cleanup itself to throw.
        try:
            engine.stop_session()
        except Exception as e:
            console.print(f"[dim red]Warning: error during session shutdown: {e}[/dim red]")

    session.close()

    # -----------------------------------------------------------------
    # Final summary — always rendered, branded for both clean-finish and
    # user-initiated exit so the operator immediately sees what got done.
    # -----------------------------------------------------------------
    from rich.panel import Panel
    tally = (
        f"Processed: [bold]{processed}[/bold] of {len(jobs)}\n"
        f"Submitted: [green]{submitted}[/green]   "
        f"Skipped: [yellow]{skipped}[/yellow]   "
        f"Failed: [red]{failed}[/red]"
    )
    if exit_reason:
        console.print(
            Panel(
                f"[yellow]Exit requested:[/yellow] {exit_reason}\n\n{tally}",
                title="[bold yellow]>>> JobCLI stopped at your request <<<[/bold yellow]",
                border_style="yellow",
                expand=True,
            )
        )
    else:
        console.print(
            Panel(
                tally,
                title="[bold green]>>> Application run complete <<<[/bold green]",
                border_style="green",
                expand=True,
            )
        )

    # Sync learned patterns even on an early-exit run — the data we
    # captured before the user quit is still valuable for future runs.
    try:
        from jobcli.sync.manager import SyncManager

        db = get_database()
        with db.get_session() as sync_session:
            manager = SyncManager(sync_session)
            console.print("\n[dim]Auto-syncing learned patterns...[/dim]")
            manager.perform_sync()
    except Exception:
        pass

    if exit_reason:
        # User-initiated exit is success (0), not an error — consistent
        # with Unix shells (Ctrl+C generally exits programs gracefully).
        raise typer.Exit(0)

    _print_next_step("discover", "refresh listings, then run apply again")


@app.command()
def apply(
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Single job URL to apply"),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="[Deprecated] No effect — `jobcli apply` already applies to all pending jobs when no --url is given.",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit number of jobs when applying to many"),
    sort: str = typer.Option("oldest", "--sort", "-s", help="Sort when applying to many: oldest | newest"),
    mode: str = typer.Option(
        "supervised",
        "--mode", "-m",
        help="Interaction mode: auto (fully autonomous), supervised (AI + human checkpoints, default), manual (pause at every step)",
    ),
) -> None:
    """Apply to all pending jobs from ``discover`` (or one job with ``--url``).

    Flow: ``login`` → ``resume-upload`` → ``discover`` → ``apply``.

    Modes: **auto** (minimal stops), **supervised** (default), **manual** (approve each batch).

    Source filtering happens at ``discover`` time — the local DB only ever
    contains links from the allow-list (see ``jobcli/orchestration/source_filter.py``),
    so ``apply`` simply iterates whatever is pending.
    """
    _ = batch  # accepted for backward compatibility with scripts using ``--batch``
    _run_apply(url=url, limit=limit, sort=sort, mode=mode)


@app.command()
def discover(
    headless: bool = typer.Option(False, help="Run browser in headless mode (legacy UI mode only)"),
    legacy_ui: bool = typer.Option(
        False,
        "--legacy-ui",
        help="Use Playwright user_dashboard scrape instead of WBL API (also: WBOX_DISCOVER_MODE=browser)",
    ),
) -> None:
    """Discover jobs from Whitebox Learning via API (GET /positions/cli_window).

    After login, local jobs are replaced with a mirror of the server listing set
    (default: all time, ``open`` only), paged until every row is fetched — same
    data model as the dashboard Jobs grid. Tune with ``JOBCLI_DISCOVER_DAYS``,
    ``JOBCLI_DISCOVER_PAGE_SIZE``, ``JOBCLI_DISCOVER_STATUS``. Use ``--legacy-ui``
    only for the old dashboard scraper.
    """
    console.print("[bold cyan]Job Discovery[/bold cyan]\n")

    config = get_config()
    _require_wbl_credentials_for_discovery(config)
    ensure_configured(config)

    db = get_database()
    session = db.get_session()

    try:
        discoverer = WboxDiscoverer(session, config=config)
        with console.status("[bold green]Fetching jobs from WBL API..."):
            new_jobs = discoverer.discover(headless=headless, legacy_ui=legacy_ui)

        print_dashboard_summary(session)

        if new_jobs:
            console.print(f"\n[bold green]✓ Imported {len(new_jobs)} job(s) from WBL.[/bold green]")
            _print_next_step("apply", "start applying to pending jobs")
        else:
            console.print("\n[yellow]No jobs imported (empty window or missing credentials).[/yellow]")
            _print_next_step("login", "verify credentials & API base URL, then re-run discover")

    except Exception as e:
        msg = str(e)
        # When SyncClient produced its own classified, multi-line "Next step:"
        # block, render it as-is without the generic panel below it.
        if "Authentication failed against all WBL API candidates" in msg:
            console.print("\n[red]Discovery failed: WBL login failed.[/red]")
            for line in msg.splitlines()[1:]:  # skip the leading "WBL login failed." line
                console.print(line)
        else:
            console.print(f"\n[red]Discovery failed: {e}[/red]")
            _print_next_step("login", "fix credentials / API base URL, then re-run discover")
    finally:
        session.close()


@app.command()
def open_dashboard() -> None:
    """Open Whitebox Learning dashboard in an interactive browser window."""
    console.print("[bold cyan]Opening Dashboard[/bold cyan]\n")
    
    config = get_config()
    _require_wbl_credentials_for_discovery(config)
    ensure_configured(config)
    
    db = get_database()
    session = db.get_session()
    
    try:
        discoverer = WboxDiscoverer(session, config=config)
        discoverer.open_interactive()
    except KeyboardInterrupt:
        console.print("\n[yellow]Browser closed.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Failed to open dashboard: {e}[/red]")
    finally:
        session.close()


@app.command()
def scan(
    portal_config: str = typer.Option(
        "config/portals.example.yml",
        "--config",
        "-c",
        help="Path to portals configuration YAML",
    )
) -> None:
    """Scan configured ATS portals for open jobs."""
    console.print("[bold cyan]ATS Zero-Token Scanner[/bold cyan]\n")
    
    import yaml
    from jobcli.orchestration.scanner import ATSScanner
    from jobcli.storage.repositories import JobRepository
    
    try:
        with open(portal_config, "r") as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        return
        
    portals = config_data.get("portals", [])
    if not portals:
        console.print("[yellow]No portals configured to scan.[/yellow]")
        return
        
    scanner = ATSScanner()
    db = get_database()
    session = db.get_session()
    job_repo = JobRepository(session)
    
    total_added = 0
    with console.status("[bold green]Scanning portals..."):
        for portal in portals:
            name = portal.get("name")
            ats = portal.get("ats")
            company_id = portal.get("company_id")
            
            if not all([name, ats, company_id]):
                continue
                
            console.print(f"Scanning {name} ({ats})...")
            
            jobs = []
            if ats == "greenhouse":
                jobs = scanner.scan_greenhouse(company_id)
            elif ats == "lever":
                jobs = scanner.scan_lever(company_id)
            elif ats == "ashby":
                jobs = scanner.scan_ashby(company_id)
            elif ats == "bamboo_hr":
                jobs = scanner.scan_bamboohr(company_id)
                
            added = 0
            for job in jobs:
                if not job_repo.get_by_url(job.url):
                    job_repo.create(job)
                    added += 1
            
            if added:
                console.print(f"  [green]✓ Found {added} new jobs![/green]")
            total_added += added
            
    session.close()
    console.print(f"\n[bold green]Scan complete. Added {total_added} new jobs to database.[/bold green]")


@app.command("doctor")
def doctor_cmd(
    wbox_smoke: bool = typer.Option(
        False,
        "--wbox-smoke",
        help="Load Whitebox login page with Playwright (needs JOBCLI_USERNAME / JOBCLI_PASSWORD)",
    ),
) -> None:
    """Validate Playwright, SQLite, config, and resume JSON."""
    from jobcli.cli.doctor import run_doctor

    raise typer.Exit(run_doctor(console, wbox_smoke=wbox_smoke))


@app.command("sync")
def sync_cmd() -> None:
    """Sync learned knowledge and job activity with the central server."""
    db = get_database()
    with db.get_session() as session:
        from jobcli.sync.manager import SyncManager
        manager = SyncManager(session)
        
        console.print("[bold cyan]JobCLI Synchronization[/bold cyan]")
        console.print("Syncing knowledge and application activity with central server...\n")
        
        try:
            results = manager.perform_sync()
            
            if results["status"] == "success":
                # Knowledge Sync Results
                if results.get("uploaded_answers") or results.get("uploaded_locators"):
                    console.print(f"  [green]✓[/green] Uploaded {results['uploaded_answers']} field patterns")
                    console.print(f"  [green]✓[/green] Uploaded {results['uploaded_locators']} locators")
                
                if results.get("downloaded_updates", 0) > 0:
                    console.print(f"  [green]✓[/green] Downloaded {results['downloaded_updates']} global updates")
                else:
                    console.print("  [blue]i[/blue] Knowledge patterns are up to date.")
                
                # Activity Sync Results
                if results.get("activity_sync_status") == "success":
                    console.print(f"  [green]✓[/green] Synced {results['activity_count']} job applications to dashboard")
                elif results.get("activity_sync_status") == "skipped":
                    console.print("  [blue]i[/blue] No new application activity to sync.")
                elif results.get("activity_sync_status") == "failed":
                    console.print(f"  [yellow]⚠[/yellow] Activity sync failed: {results.get('activity_error')}")

                console.print("\n[bold green]✓ Synchronization complete[/bold green]")
            else:
                console.print(f"[red]Sync failed: {results['error']}[/red]")
        except Exception as e:
            console.print(f"[red]Sync error: {e}[/red]")



@app.command()
def server() -> None:
    """Start the JobCLI web UI server."""
    import uvicorn
    def _env_bool(key: str, default: bool) -> bool:
        raw = os.getenv(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

    host = os.getenv("JOBCLI_API_HOST", "0.0.0.0")
    port = int(os.getenv("JOBCLI_API_PORT", "8000"))
    reload = _env_bool("JOBCLI_API_RELOAD", True)

    console.print("[bold cyan]Starting JobCLI Web UI...[/bold cyan]")
    dashboard_host = "localhost" if host in {"0.0.0.0", "::"} else host
    console.print(f"Access the dashboard at: [green]http://{dashboard_host}:{port}[/green]")
    uvicorn.run("jobcli.api.main:app", host=host, port=port, reload=reload)

@app.command()
def agent(
    prompt: str = typer.Argument(..., help="The task you want the agent to perform"),
    max_steps: int = typer.Option(12, help="Maximum number of steps the agent can take"),
) -> None:
    """Launch the autonomous coding agent."""
    from jobcli.agents.coder.agent import CodingAgent
    
    console.print(f"[bold cyan]JobCLI Autonomous Coder[/bold cyan]\n")
    
    config = get_config()
    ensure_configured(config, require_job_board=False)
    
    if not config.default_llm_provider:
        console.print("[red]No default LLM provider configured. Run [cyan]login[/cyan] to set one.[/red]")
        raise typer.Exit(1)
        
    try:
        agent = CodingAgent(config)
        agent.run(prompt, max_steps=max_steps)
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal Error: {e}[/red]")


@app.command("reset")
def cli_reset(
    force: bool = typer.Option(False, "--force", "-f", help="Same as jobcli db reset --force"),
) -> None:
    """Alias for ``jobcli db reset`` — full local SQLite database wipe (keeps ~/.jobcli logs)."""
    _run_db_reset(force)


if __name__ == "__main__":
    app()
