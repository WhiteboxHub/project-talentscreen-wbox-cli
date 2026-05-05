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

    # Huge block ASCII art for "WBOX CLI" (like the screenshot)
    block_ascii = [
        f"[bold #f0abfc]██╗    ██╗██████╗  ██████╗ ██╗  ██╗[/]",
        f"[bold #e879f9]██║    ██║██╔══██╗██╔═══██╗╚██╗██╔╝[/]",
        f"[bold #d946ef]██║ █╗ ██║██████╔╝██║   ██║ ╚███╔╝ [/]",
        f"[bold #c026d3]██║███╗██║██╔══██╗██║   ██║ ██╔██╗ [/]",
        f"[bold #a78bfa]╚███╔███╔╝██████╔╝╚██████╔╝██╔╝ ██╗[/]",
        f"[bold #7c3aed] ╚══╝╚══╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝[/]",
        f"",
        f"[bold #f0abfc] ██████╗██╗     ██╗[/]",
        f"[bold #e879f9]██╔════╝██║     ██║[/]",
        f"[bold #d946ef]██║     ██║     ██║[/]",
        f"[bold #c026d3]██║     ██║     ██║[/]",
        f"[bold #a78bfa]╚██████╗███████╗██║[/]",
        f"[bold #7c3aed] ╚═════╝╚══════╝╚═╝[/]"
    ]
    
    for line in block_ascii:
        console.print(line)
        time.sleep(0.04)

    console.print()
    console.print(f"[{D}]WboxCLI can now be used as an autonomous agent to apply to jobs automatically[/]")
    console.print(f"[{D}]using your configured LLM and Whitebox Learning credentials.[/]")
    console.print()


def _run_onboarding():
    """Claude Code style interactive onboarding selection."""
    try:
        from jobcli.cli.main import get_config
        config = get_config()
        has_llm = bool(config.openai_api_key or config.anthropic_api_key or config.gemini_api_key)
        
        if not has_llm:
            console.print("[bold]Select setup method:[/bold]")
            console.print()
            console.print(f"[{K}]> 1. Run quick setup wizard[/]")
            console.print(f"  [{D}]Configure API keys, Whitebox login, and paths - Best for new users[/]")
            console.print()
            console.print(f"  [{D}]2. Continue without setup[/]")
            console.print(f"  [{D}]Explore commands first[/]")
            console.print()
            
            # Simple interaction
            # ANSI codes for input prompt (Rich markup doesn't work in raw input())
            PURP = "\033[1;38;2;192;132;252m"
            RST = "\033[0m"
            choice = ""
            while choice not in ("1", "2"):
                choice = input(f"{PURP}Select an option (1-2) > {RST}")
                if choice == "1":
                    _exec(["setup"])
                    break
                elif choice == "2":
                    break
    except Exception:
        pass


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
