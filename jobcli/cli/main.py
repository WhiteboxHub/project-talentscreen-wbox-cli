"""Main CLI application using Typer."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Fix UnicodeEncodeError on Windows terminals when printing checkmarks/symbols
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from jobcli.core.engine import ApplicationEngine
from jobcli.core.schemas import ApplicationStatus, CommonQuestions, Config, InteractionMode, Job, ResumeData
from jobcli.storage.models import Database
from jobcli.core.wbox_discoverer import WboxDiscoverer
from jobcli.storage.repositories import (
    ConfigRepository,
    JobRepository,
    UserDataRepository,
)

app = typer.Typer(
    name="jobcli",
    help="Production-grade CLI for automated job applications",
)

console = Console()

# Default config directory
CONFIG_DIR = Path.home() / ".jobcli"
CONFIG_FILE = CONFIG_DIR / "config.json"
DATABASE_FILE = CONFIG_DIR / "jobcli.db"


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


def get_config() -> Config:
    """Load configuration, with ``.env`` always winning over the SQLite DB.

    Order of precedence (highest first):
      1. Environment variables loaded from ``.env`` (or the real shell env).
      2. Values previously persisted to the SQLite ``config`` table.
      3. Schema defaults.

    This means rotating an API key in ``.env`` takes effect on the very next
    run — no need to re-run ``jobcli login`` or hand-edit the DB.
    """
    from dotenv import load_dotenv
    # override=True so a freshly-edited .env beats stale shell env vars too.
    load_dotenv(override=True)

    db = get_database()
    session = db.get_session()
    config_repo = ConfigRepository(session)

    try:
        config = config_repo.get_all()
    except Exception:
        config = Config()

    # ── .env overrides ──────────────────────────────────────────────
    # Anything present and non-empty in the environment wins.
    env_overrides: list[tuple[str, str]] = [
        ("OPENAI_API_KEY", "openai_api_key"),
        ("ANTHROPIC_API_KEY", "anthropic_api_key"),
        ("GEMINI_API_KEY", "gemini_api_key"),
        ("DEFAULT_LLM_PROVIDER", "default_llm_provider"),
        ("RESUME_PDF_PATH", "resume_pdf_path"),
        ("RESUME_JSON_PATH", "resume_json_path"),
        ("EXTENSION_PATH", "extension_path"),
        ("DATABASE_PATH", "database_path"),
        ("LOG_DIRECTORY", "log_directory"),
        ("JOBCLI_USERNAME", "job_board_username"),
        ("JOBCLI_PASSWORD", "job_board_password"),
        ("LINKEDIN_USERNAME", "linkedin_username"),
        ("LINKEDIN_PASSWORD", "linkedin_password"),
    ]
    for env_key, attr in env_overrides:
        val = os.getenv(env_key)
        if val and hasattr(config, attr):
            try:
                setattr(config, attr, val)
            except Exception:
                pass

    env_headless = os.getenv("HEADLESS")
    if env_headless is not None:
        config.headless = env_headless.lower() == "true"

    session.close()
    return config


def save_config(config: Config) -> None:
    """Save configuration."""
    db = get_database()
    session = db.get_session()
    config_repo = ConfigRepository(session)
    config_repo.save_config(config)
    session.close()


def ensure_configured(config: Config, require_job_board: bool = True) -> None:
    """Ensure the user has logged in and configured required credentials."""
    if require_job_board and (not config.job_board_username or not config.job_board_password):
        console.print("[yellow]Warning: Missing job board credentials.[/yellow]")
        console.print("Run [cyan]jobcli login[/cyan] if you need to discover jobs of view Whitebox-hosted listings.")
        
    has_llm = config.openai_api_key or config.anthropic_api_key or config.gemini_api_key
    if not has_llm:
        console.print("\n[yellow]Warning: No LLM API keys configured. Phase 2 (Autonomous Reasoning) will be disabled.[/yellow]")
        console.print("Run [cyan]jobcli login[/cyan] to unlock full AI automation capabilities.\n")


@app.command()
def setup() -> None:
    """Initialize JobCLI configuration and database."""
    console.print("[bold cyan]JobCLI Setup[/bold cyan]\n")

    ensure_config_dir()

    # Create database
    db = get_database()
    console.print(f"✓ Database created at: {DATABASE_FILE}")

    # Initialize config
    config = Config()
    save_config(config)
    console.print(f"✓ Configuration saved to: {CONFIG_FILE}")

    console.print("\n[bold green]Setup completed successfully![/bold green]")
    console.print("\nNext steps:")
    console.print("1. Run [cyan]jobcli login[/cyan] to add credentials")
    console.print("2. Run [cyan]jobcli resume upload[/cyan] to upload your resume")
    console.print("3. Run [cyan]jobcli questions[/cyan] to pre-fill common answers")
    console.print("4. Run [cyan]jobcli apply[/cyan] to start applying to jobs")


@app.command()
def login() -> None:
    """Configure credentials for job boards and LLM APIs."""
    console.print("[bold cyan]JobCLI Login[/bold cyan]\n")

    config = get_config()

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


@app.command()
def config_cmd(
    key: Optional[str] = typer.Option(None, help="Configuration key to view"),
    set_value: Optional[str] = typer.Option(None, "--set", help="Set configuration value"),
) -> None:
    """View or modify configuration."""
    config = get_config()

    if key and set_value:
        # Set configuration
        if hasattr(config, key):
            setattr(config, key, set_value)
            save_config(config)
            console.print(f"[green]✓ Set {key} = {set_value}[/green]")
        else:
            console.print(f"[red]Unknown configuration key: {key}[/red]")

    elif key:
        # View specific key
        if hasattr(config, key):
            value = getattr(config, key)
            console.print(f"{key}: {value}")
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


@app.command()
def resume_upload(
    pdf: str = typer.Option(..., help="Path to resume PDF"),
    json_file: str = typer.Option(..., "--json", help="Path to resume JSON"),
) -> None:
    """Upload resume in PDF and JSON formats."""
    console.print("[bold cyan]Resume Upload[/bold cyan]\n")

    # Validate PDF
    pdf_path = Path(pdf)
    if not pdf_path.exists():
        console.print(f"[red]PDF file not found: {pdf}[/red]")
        raise typer.Exit(1)

    # Validate and parse JSON
    json_path = Path(json_file)
    if not json_path.exists():
        console.print(f"[red]JSON file not found: {json_file}[/red]")
        raise typer.Exit(1)

    try:
        with open(json_path) as f:
            resume_data = json.load(f)

        # Validate with Pydantic
        resume = ResumeData(**resume_data)

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


@app.command()
def apply(
    url: Optional[str] = typer.Option(None, help="Single job URL to apply"),
    batch: bool = typer.Option(False, help="Apply to all pending jobs"),
    mode: str = typer.Option(
        "supervised",
        "--mode", "-m",
        help="Interaction mode: auto (fully autonomous), supervised (AI + human checkpoints, default), manual (pause at every step)",
    ),
) -> None:
    """Apply to jobs.

    The --mode flag controls how tightly you are integrated into the agent loop:

      auto       – fully autonomous; only stops for CAPTCHA / fatal errors.
      supervised – (default) AI drives, but pauses for submission confirmation,
                   missing fields, and failed actions — like Claude Code.
      manual     – pauses before every action batch for explicit approval.
    """
    console.print("[bold cyan]Job Application[/bold cyan]\n")

    config = get_config()
    ensure_configured(config, require_job_board=False)

    # Apply interaction mode
    try:
        config.interaction_mode = InteractionMode(mode)
    except ValueError:
        console.print(f"[red]Invalid mode '{mode}'. Choose from: auto, supervised, manual[/red]")
        raise typer.Exit(1)

    console.print(f"Mode: [cyan]{config.interaction_mode.value}[/cyan]\n")

    db = get_database()
    session = db.get_session()

    user_data_repo = UserDataRepository(session)
    job_repo = JobRepository(session)

    resume = user_data_repo.get_resume()
    if not resume:
        console.print("[red]No resume uploaded. Run 'jobcli resume upload' first.[/red]")
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

    elif batch:
        jobs = job_repo.list_pending()
        if not jobs:
            console.print("[yellow]No pending jobs found.[/yellow]")
            raise typer.Exit(0)

    else:
        console.print("[red]Provide either --url or --batch[/red]")
        raise typer.Exit(1)

    console.print(f"Applying to {len(jobs)} job(s)...\n")

    engine = ApplicationEngine(config, resume, db)

    for i, job in enumerate(jobs, 1):
        console.print(f"[bold]Job {i}/{len(jobs)}[/bold]: {job.url}")
        try:
            status = engine.apply_to_job(job)
            console.print(f"Status: [green]{status.value}[/green]\n")
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]\n")
            continue

    session.close()
    console.print("[bold green]Application process completed[/bold green]")


@app.command()
def discover(
    headless: bool = typer.Option(True, help="Run browser in headless mode"),
) -> None:
    """Discover jobs from Whitebox Learning dashboard."""
    console.print("[bold cyan]Job Discovery[/bold cyan]\n")

    config = get_config()
    ensure_configured(config)

    db = get_database()
    session = db.get_session()

    try:
        discoverer = WboxDiscoverer(session)
        with console.status("[bold green]Discovering jobs from Wbox dashboard..."):
            new_jobs = discoverer.discover(headless=headless)

        if new_jobs:
            console.print(f"\n[bold green]✓ Discovered {len(new_jobs)} new jobs![/bold green]")
            table = Table(title="New Jobs")
            table.add_column("Title", style="cyan")
            table.add_column("Company", style="green")
            table.add_column("URL", style="blue")

            for job in new_jobs:
                table.add_row(job.title, job.company or "Unknown", job.url)
            console.print(table)
            console.print("\nRun [cyan]jobcli apply --batch[/cyan] to start applying.")
        else:
            console.print("\n[yellow]No new jobs found.[/yellow]")

    except Exception as e:
        console.print(f"\n[red]Discovery failed: {e}[/red]")
    finally:
        session.close()


@app.command()
def open_dashboard() -> None:
    """Open Whitebox Learning dashboard in an interactive browser window."""
    console.print("[bold cyan]Opening Dashboard[/bold cyan]\n")
    
    config = get_config()
    ensure_configured(config)
    
    db = get_database()
    session = db.get_session()
    
    try:
        discoverer = WboxDiscoverer(session)
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
    from jobcli.core.scanner import ATSScanner
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
    """Sync learned field answers and locators with the central server."""
    console.print("[bold cyan]JobCLI Knowledge Sync[/bold cyan]\n")
    
    db = get_database()
    session = db.get_session()
    
    try:
        from jobcli.storage.repositories import SyncMetadataRepository
        sync_repo = SyncMetadataRepository(session)
        metadata = sync_repo.get_metadata()
        
        apps_since_sync = metadata.apps_since_sync if metadata else 0
        
        if apps_since_sync > 0:
            console.print(f"You have {apps_since_sync} applications worth of new data.")
        
        do_sync = Confirm.ask("New improvements available. Sync now?", default=True)
        if not do_sync:
            console.print("[yellow]Sync cancelled.[/yellow]")
            return
            
        with console.status("[bold green]Extracting and uploading local knowledge..."):
            from jobcli.sync.extractor import extract_field_answers, extract_locators
            from jobcli.sync.client import upload_knowledge, download_updates
            from jobcli.sync.sqlite_merger import merge_server_updates
            from datetime import datetime
            
            field_answers = extract_field_answers(session)
            locators = extract_locators(session)
            
            payload = {
                "field_answers": field_answers,
                "locators": locators
            }
            
            # 1. Upload
            upload_resp = upload_knowledge(payload)
            
            # 2. Download
            current_version = metadata.last_version if metadata else "0.0.0"
            download_resp = download_updates(current_version)
            
            new_version = download_resp.get("version", current_version)
            field_answers_down = len(download_resp.get("field_answers", []))
            locators_down = len(download_resp.get("locators", []))
            
            # 3. Merge
            merge_server_updates(session, download_resp)
            
            # 4. Update metadata
            if hasattr(sync_repo, "record_sync_success"):
                sync_repo.record_sync_success(new_version)
            elif metadata:
                metadata.last_version = new_version
                metadata.last_sync_at = datetime.now()
                metadata.apps_since_sync = 0
                session.commit()
                
            console.print(f"[bold green]✓ Downloaded {field_answers_down} field answers and {locators_down} locators.[/bold green]")
            console.print(f"[bold green]✓ Updated to version {new_version}.[/bold green]")
            
    except Exception as e:
        console.print(f"\n[red]Sync failed: {e}[/red]")
    finally:
        session.close()



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
    """Launch the autonomous coding agent (Claude Code style)."""
    from jobcli.coder.agent import CodingAgent
    
    console.print(f"[bold cyan]JobCLI Autonomous Coder[/bold cyan]\n")
    
    config = get_config()
    ensure_configured(config, require_job_board=False)
    
    if not config.default_llm_provider:
        console.print("[red]No default LLM provider configured. Run 'jobcli login' to set one.[/red]")
        raise typer.Exit(1)
        
    try:
        agent = CodingAgent(config)
        agent.run(prompt, max_steps=max_steps)
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal Error: {e}[/red]")


if __name__ == "__main__":
    app()
