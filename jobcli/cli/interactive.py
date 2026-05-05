"""Interactive TUI for WboxCLI — clean, minimal, Claude Code-style.

Just a clean prompt. No heavy panels. Information when you need it.
"""

import os
import sys
import time
import readline
import subprocess
import random
import shutil
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.rule import Rule

console = Console(highlight=False)

# ── Colors ────────────────────────────────────────────────────────────
P = "#c084fc"   # purple (primary)
K = "#f0abfc"   # pink (accent)
D = "#6b7280"   # dim
F = "#4b5563"   # faint
V = "#7c3aed"   # violet


# ── Commands ──────────────────────────────────────────────────────────
COMMANDS = {
    "setup":     ["setup"],
    "apply":     None,
    "discover":  ["discover"],
    "jobs":      None,
    "status":    None,
    "doctor":    ["doctor"],
    "login":     ["login"],
    "resume":    None,
    "config":    ["config-cmd"],
    "questions": ["questions"],
    "scan":      ["scan"],
    "sync":      ["sync"],
    "server":    ["server"],
    "dashboard": ["open-dashboard"],
    "clear":     None,
    "help":      None,
    "exit":      None,
}

COMMAND_NAMES = list(COMMANDS.keys())


# ── Readline ──────────────────────────────────────────────────────────
class _Completer:
    def __init__(self):
        self.matches = []

    def complete(self, text, state):
        if state == 0:
            self.matches = [c + " " for c in COMMAND_NAMES if c.startswith(text.lower())] if text else []
        return self.matches[state] if state < len(self.matches) else None


def _setup_readline():
    history_path = os.path.join(os.path.expanduser("~"), ".jobcli", "history")
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    try:
        readline.read_history_file(history_path)
    except (FileNotFoundError, PermissionError, OSError):
        pass
    readline.set_history_length(500)
    readline.set_completer(_Completer().complete)
    readline.parse_and_bind("tab: complete")
    if hasattr(readline, "__doc__") and readline.__doc__ and "libedit" in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    return history_path


# ── Welcome ───────────────────────────────────────────────────────────
def _animate_banner():
    """Claude Code style welcome: boxed title + block ASCII banner."""
    # The small boxed welcome at the top left
    welcome_box = Panel(
        "[bold #f0abfc]◈ Welcome to WboxCLI[/]", 
        box=box.ROUNDED, 
        border_style="#c084fc",
        padding=(0, 1),
        expand=False
    )
    console.print()
    console.print(welcome_box)
    console.print()

    # Huge block ASCII art for "WBOXCLI" on one line
    block_ascii = [
        f"[bold #f0abfc]██╗    ██╗██████╗  ██████╗ ██╗  ██╗ ██████╗██╗     ██╗[/]",
        f"[bold #e879f9]██║    ██║██╔══██╗██╔═══██╗╚██╗██╔╝██╔════╝██║     ██║[/]",
        f"[bold #d946ef]██║ █╗ ██║██████╔╝██║   ██║ ╚███╔╝ ██║     ██║     ██║[/]",
        f"[bold #c026d3]██║███╗██║██╔══██╗██║   ██║ ██╔██╗ ██║     ██║     ██║[/]",
        f"[bold #a78bfa]╚███╔███╔╝██████╔╝╚██████╔╝██╔╝ ██╗╚██████╗███████╗██║[/]",
        f"[bold #7c3aed] ╚══╝╚══╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝[/]"
    ]
    
    for line in block_ascii:
        console.print(line)
        time.sleep(0.04)

    console.print()
    console.print(f"[{D}]WboxCLI is an exclusive autonomous agent. It works ONLY with[/]")
    console.print(f"[{D}]Whitebox Learning (https://whiteboxlearning.com) and will[/]")
    console.print(f"[{D}]not apply on any other external job boards.[/]")
    console.print()


def _validate_llm(provider: str, api_key: str) -> bool:
    """Validate LLM API key with a quick test call."""
    try:
        from litellm import completion
        model = "gpt-3.5-turbo" if provider == "openai" else "claude-3-haiku-20240307" if provider == "anthropic" else "gemini/gemini-1.5-flash"
        completion(model=model, messages=[{"role": "user", "content": "hi"}], api_key=api_key, max_tokens=1)
        return True
    except Exception:
        return False


def _validate_wbox(email: str, password: str) -> bool:
    """Validate Whitebox Learning credentials."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://whitebox-learning.com/login")
            page.fill('input[name="email"]', email)
            page.fill('input[name="password"]', password)
            page.click('button:has-text("Login")')
            page.wait_for_url("**/user_dashboard**", timeout=5000)
            browser.close()
            return True
    except Exception:
        return False


def _run_onboarding(force: bool = False):
    """Claude Code style interactive onboarding selection."""
    try:
        from jobcli.cli.main import get_config, get_database
        from jobcli.storage.repositories import ConfigRepository
        import getpass
        
        config = get_config()
        has_llm = bool(config.openai_api_key or config.anthropic_api_key or config.gemini_api_key)
        has_wbox = bool(config.job_board_username and config.job_board_password)
        
        db = get_database()
        session = db.get_session()
        
        from jobcli.storage.repositories import UserDataRepository
        resume_data = UserDataRepository(session).get_resume()
        has_resume = resume_data is not None
        
        if force or not has_llm or not has_wbox or not has_resume:
            console.print("[bold]Select LLM Provider for Automation:[/bold]")
            console.print()
            console.print(f"[{K}]> 1. OpenAI (Recommended)[/]")
            console.print(f"  [{D}]Requires OPENAI_API_KEY[/]")
            console.print(f"  2. Anthropic")
            console.print(f"  3. Gemini")
            console.print()
            
            PURP = "\033[1;38;2;192;132;252m"
            RST = "\033[0m"
            
            repo = ConfigRepository(session)
            db_config = repo.get_all()
            
            choice = ""
            while True:
                choice = input(f"{PURP}Select provider (1-3) > {RST}").strip()
                if choice not in ("1", "2", "3"):
                    continue
                    
                provider = "openai" if choice == "1" else "anthropic" if choice == "2" else "gemini"
                prompt_name = "OpenAI" if choice == "1" else "Anthropic" if choice == "2" else "Gemini"
                
                api_key = input(f"{PURP}Enter {prompt_name} API Key: {RST}").strip()
                
                with console.status(f"[{D}]Validating API key...[/]", spinner="dots", spinner_style="#e879f9"):
                    is_valid = _validate_llm(provider, api_key)
                
                if is_valid:
                    db_config.default_llm_provider = provider
                    if provider == "openai":
                        db_config.openai_api_key = api_key
                    elif provider == "anthropic":
                        db_config.anthropic_api_key = api_key
                    elif provider == "gemini":
                        db_config.gemini_api_key = api_key
                    console.print(f"[bold white on #d946ef] ✓ [/] [green]API key successfully verified[/green]")
                    break
                else:
                    console.print(f"[bold white on #c026d3] ✗ [/] [red]Invalid {prompt_name} API key. Please try again.[/red]")
                    
            console.print()
            console.print("[bold]Whitebox Learning Credentials:[/bold]")
            if force or not db_config.job_board_username or not db_config.job_board_password:
                while True:
                    email = input(f"{PURP}Whitebox Email: {RST}").strip()
                    password = getpass.getpass(f"{PURP}Whitebox Password: {RST}").strip()
                    
                    with console.status(f"[{D}]Connecting to whitebox-learning.com...[/]", spinner="dots", spinner_style="#e879f9"):
                        is_valid = _validate_wbox(email, password)
                    
                    if is_valid:
                        db_config.job_board_username = email
                        db_config.job_board_password = password
                        console.print(f"[bold white on #d946ef] ✓ [/] [green]Credentials verified successfully[/green]")
                        break
                    else:
                        console.print(f"[bold white on #c026d3] ✗ [/] [red]Invalid email or password. Please try again.[/red]")
                
            repo.save_config(db_config)
            session.commit()
            
            console.print()
            console.print("[bold]Resume Upload:[/bold]")
            if force or not has_resume:
                pdf_path = input(f"{PURP}Path to Resume PDF: {RST}").strip()
                json_path = input(f"{PURP}Path to Resume JSON: {RST}").strip()
                session.close() # Close session before running subprocess
                
                # Use absolute paths and expand ~
                pdf_path = os.path.abspath(os.path.expanduser(pdf_path))
                json_path = os.path.abspath(os.path.expanduser(json_path))
                
                console.print(f"\n[{D}]Uploading resume...[/]")
                _exec(["resume-upload", "--pdf", pdf_path, "--json", json_path])
            else:
                session.close()
            
            console.print(f"\n[{K}]✓ Setup complete! You are ready to apply to jobs.[/]\n")
    except Exception as e:
        console.print(f"[red]Error during setup: {e}[/red]")


def _print_welcome():
    """Claude Code-style welcome and onboarding."""
    _animate_banner()
    _run_onboarding()

    # Greeting
    hour = datetime.now().hour
    name = ""
    pending_count = 0

    try:
        from jobcli.cli.main import get_config, get_database
        from jobcli.storage.repositories import JobRepository, UserDataRepository
        config = get_config()
        db = get_database()
        session = db.get_session()
        resume = UserDataRepository(session).get_resume()
        pending_count = len(JobRepository(session).list_pending())
        session.close()
        if resume and resume.personal.first_name:
            name = resume.personal.first_name
    except Exception:
        pass

    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    greeting_str = f"{greeting}, {name}" if name else greeting

    console.print(f"  {greeting_str}. [{D}]You have[/] [{K}]{pending_count}[/] [{D}]pending jobs.[/]")
    console.print(f"  [{D}]Type a command to get started, or[/] [{K}]help[/] [{D}]to see options.[/]")
    console.print(f"  [{D}]Use[/] [{K}]Tab[/] [{D}]to autocomplete,[/] [{K}]↑↓[/] [{D}]for history.[/]")
    console.print()


# ── Helpers ───────────────────────────────────────────────────────────
def _find_jobcli_bin() -> str:
    venv_dir = os.path.join(os.path.expanduser("~"), ".jobcli", "venv")
    candidate = os.path.join(venv_dir, "Scripts" if os.name == "nt" else "bin", "jobcli.exe" if os.name == "nt" else "jobcli")
    if os.path.exists(candidate):
        return candidate
    return shutil.which("jobcli") or "jobcli"


def _exec(args: list[str]):
    """Run a jobcli subcommand, streaming output."""
    jobcli = _find_jobcli_bin()

    console.print(f"\n  [{D}]$ jobcli {' '.join(args)}[/]")
    console.print()

    try:
        proc = subprocess.Popen(
            [jobcli] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),
            text=True,
            bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
        proc.wait()
        console.print()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        console.print(f"\n  [{D}]cancelled[/]\n")
    except FileNotFoundError:
        try:
            subprocess.run([sys.executable, "-m", "jobcli"] + args, cwd=os.getcwd())
        except KeyboardInterrupt:
            console.print(f"\n  [{D}]cancelled[/]\n")


# ── Internal Commands ─────────────────────────────────────────────────
def _cmd_help():
    console.print()
    console.print(f"  [{K}]Commands:[/]")
    console.print()

    groups = [
        ("Getting started", [
            ("setup",     "One-shot setup from .env"),
            ("login",     "Configure credentials"),
            ("resume",    "Upload resume PDF + JSON"),
            ("config",    "View/edit configuration"),
            ("questions", "Pre-fill common answers"),
        ]),
        ("Running", [
            ("apply --batch",  "Apply to all pending jobs"),
            ("apply --url URL","Apply to a specific URL"),
            ("discover",       "Discover jobs from dashboard"),
            ("scan",           "Scan ATS portals for openings"),
        ]),
        ("Info", [
            ("status",    "Show current status"),
            ("jobs",      "List pending jobs"),
            ("doctor",    "Health check"),
            ("sync",      "Sync learned patterns with server"),
        ]),
        ("Other", [
            ("server",    "Start web UI dashboard"),
            ("dashboard", "Open Whitebox dashboard in browser"),
            ("clear",     "Clear the screen"),
            ("exit",      "Exit"),
        ]),
    ]

    for group_name, cmds in groups:
        console.print(f"  [{D}]{group_name}[/]")
        for cmd_name, desc in cmds:
            console.print(f"    [{K}]{cmd_name:<20}[/] [{D}]{desc}[/]")
        console.print()


def _cmd_status():
    try:
        from jobcli.cli.main import get_config, get_database
        from jobcli.storage.repositories import JobRepository, UserDataRepository

        config = get_config()
        db = get_database()
        session = db.get_session()
        has_llm = bool(config.openai_api_key or config.anthropic_api_key or config.gemini_api_key)
        has_wbox = bool(config.job_board_username and config.job_board_password)
        resume = UserDataRepository(session).get_resume()
        pending = len(JobRepository(session).list_pending())
        session.close()

        console.print()
        items = [
            ("LLM",       f"[green]✓[/] {config.default_llm_provider}" if has_llm else "[red]✗[/] not configured"),
            ("Login",     f"[green]✓[/] {config.job_board_username}" if has_wbox else "[yellow]⚠[/] not set"),
            ("Resume",    f"[green]✓[/] {resume.personal.first_name} {resume.personal.last_name}" if resume else "[red]✗[/] not uploaded"),
            ("Jobs",      f"[{K}]{pending}[/] pending"),
            ("Browser",   f"visible" if not config.headless else "headless"),
        ]
        for label, val in items:
            console.print(f"  [{D}]{label:<12}[/] {val}")
        console.print()

    except Exception as e:
        console.print(f"  [red]error: {e}[/]\n")


def _cmd_jobs():
    try:
        from jobcli.cli.main import get_database
        from jobcli.storage.repositories import JobRepository

        with console.status(f"[{D}]loading...", spinner="dots", spinner_style=P):
            db = __import__("jobcli.cli.main", fromlist=["get_database"]).get_database()
            session = db.get_session()
            pending = JobRepository(session).list_pending()
            session.close()

        if not pending:
            console.print(f"\n  [{D}]No pending jobs. Run[/] [{K}]discover[/] [{D}]to find some.[/]\n")
            return

        console.print()
        for i, job in enumerate(pending, 1):
            title = job.title or "untitled"
            url = job.url[:60] + "…" if len(job.url) > 60 else job.url
            console.print(f"  [{D}]{i:>3}.[/]  [{K}]{title}[/]")
            console.print(f"       [{F}]{url}[/]")
        console.print(f"\n  [{D}]{len(pending)} jobs pending[/]\n")

    except Exception as e:
        console.print(f"  [red]error: {e}[/]\n")


# ── Dispatch ──────────────────────────────────────────────────────────
def _dispatch(raw: str):
    parts = raw.strip().split()
    if not parts:
        return

    cmd = parts[0].lower()
    args = parts[1:]

    # Internal
    if cmd == "help":
        _cmd_help()
        return
    if cmd == "status":
        _cmd_status()
        return
    if cmd == "jobs":
        _cmd_jobs()
        return
    if cmd in ("clear", "cls"):
        os.system("cls" if os.name == "nt" else "clear")
        _print_welcome()
        return
    if cmd in ("exit", "quit", "q"):
        return

    # Apply
    if cmd == "apply":
        if not args:
            console.print(f"\n  [{D}]usage:[/]  [{K}]apply --batch[/]  [{D}]or[/]  [{K}]apply --url <url>[/]\n")
            return
        _exec(["apply"] + args)
        return

    # Resume alias
    if cmd == "resume":
        _exec(["resume-upload"] + args)
        return

    # Login / Setup mapping
    if cmd in ("login", "setup"):
        _run_onboarding(force=True)
        return

    # Standard
    if cmd in COMMANDS and COMMANDS[cmd] is not None:
        _exec(COMMANDS[cmd] + args)
        return

    # Unknown
    close = [c for c in COMMAND_NAMES if c.startswith(cmd[:2]) and c != cmd]
    if close:
        suggestions = ", ".join(f"[{K}]{c}[/]" for c in close[:3])
        console.print(f"\n  [{D}]unknown command:[/] {cmd}  [{D}]— did you mean {suggestions}?[/]\n")
    else:
        console.print(f"\n  [{D}]unknown command:[/] {cmd}  [{D}]— type[/] [{K}]help[/] [{D}]for options[/]\n")


# ── Prompt ────────────────────────────────────────────────────────────
def _prompt() -> str:
    # ANSI codes (Rich can't style input/readline)
    PURP = "\033[1;38;2;192;132;252m"
    RST = "\033[0m"

    try:
        return input(f"  {PURP}>{RST} ").strip()
    except EOFError:
        return "exit"


# ── Session ───────────────────────────────────────────────────────────
def interactive_session():
    os.system("cls" if os.name == "nt" else "clear")
    history_path = _setup_readline()
    _print_welcome()

    try:
        while True:
            try:
                user_input = _prompt()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    console.print(f"\n  [{D}]goodbye[/]\n")
                    break
                _dispatch(user_input)
            except KeyboardInterrupt:
                console.print(f"  [{D}]^C[/]")

    finally:
        try:
            readline.write_history_file(history_path)
        except (PermissionError, OSError):
            pass
