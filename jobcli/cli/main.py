"""Main CLI application using Typer."""

import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from jobcli.core.engine import ApplicationEngine
from jobcli.core.schemas import ApplicationStatus, CommonQuestions, Config, Job, ResumeData
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
    ensure_config_dir()
    db = Database(f"sqlite:///{DATABASE_FILE}")
    db.create_tables()
    return db


def get_config() -> Config:
    """Load configuration, respecting .env overrides."""
    from dotenv import load_dotenv
    load_dotenv()
    
    db = get_database()
    session = db.get_session()
    config_repo = ConfigRepository(session)

    try:
        config = config_repo.get_all()
    except Exception:
        config = Config()

    # Override headless if set in .env
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


def ensure_configured(config: Config) -> None:
    """Ensure the user has logged in and configured required credentials."""
    if not config.job_board_username or not config.job_board_password:
        console.print("[red]Missing job board credentials.[/red]")
        console.print("Please run [cyan]jobcli login[/cyan] first.")
        raise typer.Exit(1)
        
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
) -> None:
    """Apply to jobs."""
    console.print("[bold cyan]Job Application[/bold cyan]\n")

    # Load config and resume
    config = get_config()
    ensure_configured(config)
    
    db = get_database()
    session = db.get_session()

    user_data_repo = UserDataRepository(session)
    job_repo = JobRepository(session)

    resume = user_data_repo.get_resume()
    if not resume:
        console.print("[red]No resume uploaded. Run 'jobcli resume upload' first.[/red]")
        raise typer.Exit(1)

    # Create jobs list
    jobs = []

    if url:
        # Single job
        existing = job_repo.get_by_url(url)
        if existing:
            job = existing
        else:
            job = job_repo.get_by_url(url)
        if not job:
            job = job_repo.create(Job(title="Manual Entry", url=url, status=ApplicationStatus.PENDING))
        
        # In case the user is retrying a previously failed/completed job, reset it to pending
        if job.status != ApplicationStatus.PENDING:
            job_repo.update_status(job.id, ApplicationStatus.PENDING)
            
        jobs = [job]

    elif batch:
        # All pending jobs
        jobs = job_repo.list_pending()
        if not jobs:
            console.print("[yellow]No pending jobs found.[/yellow]")
            raise typer.Exit(0)

    else:
        console.print("[red]Provide either --url or --batch[/red]")
        raise typer.Exit(1)

    console.print(f"Applying to {len(jobs)} job(s)...\n")

    # Initialize engine
    engine = ApplicationEngine(config, resume, db)

    # Apply to each job
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


if __name__ == "__main__":
    app()
