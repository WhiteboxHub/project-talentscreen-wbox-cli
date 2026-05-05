"""Interactive TUI for WboxCLI — polished, smooth, Claude Code-style.

Brand colors from Whitebox Learning:
  Primary: #7C3AED (violet)  |  Accent: #f0abfc (pink)  |  #e9d5ff (lavender)
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
from rich.columns import Columns
from rich import box
from rich.rule import Rule
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text
from rich.align import Align

console = Console()

# ── Brand Colors ──────────────────────────────────────────────────────
C = {
    "pink":     "#f0abfc",
    "hot":      "#e879f9",
    "mag":      "#d946ef",
    "deep":     "#c026d3",
    "lav":      "#e9d5ff",
    "purp":     "#c084fc",
    "soft":     "#a78bfa",
    "vio":      "#7c3aed",
    "dark":     "#581c87",
    "muted":    "#6b7280",
    "dim":      "#4b5563",
    "faint":    "#374151",
}

# ── Tips (shown randomly below the prompt) ────────────────────────────
TIPS = [
    f"[{C['dim']}]💡 Tip: Press [{C['pink']}]Tab[/{C['pink']}] to autocomplete commands[/]",
    f"[{C['dim']}]💡 Tip: Use [{C['pink']}]apply --batch[/{C['pink']}] to apply to all pending jobs[/]",
    f"[{C['dim']}]💡 Tip: Run [{C['pink']}]doctor[/{C['pink']}] to check your setup[/]",
    f"[{C['dim']}]💡 Tip: [{C['pink']}]discover[/{C['pink']}] scrapes new jobs from the dashboard[/]",
    f"[{C['dim']}]💡 Tip: [{C['pink']}]sync[/{C['pink']}] shares your learned patterns with the team[/]",
    f"[{C['dim']}]💡 Tip: Use ↑/↓ arrows to browse command history[/]",
    f"[{C['dim']}]💡 Tip: [{C['pink']}]jobs[/{C['pink']}] shows all your pending applications[/]",
    f"[{C['dim']}]💡 Tip: [{C['pink']}]status[/{C['pink']}] shows your current config at a glance[/]",
]

# ── Commands ──────────────────────────────────────────────────────────
COMMANDS = {
    "setup":     {"cli": ["setup"],          "desc": "One-shot setup from .env",        "cat": "setup"},
    "apply":     {"cli": None,               "desc": "Apply to jobs (--batch / --url)", "cat": "core"},
    "discover":  {"cli": ["discover"],       "desc": "Discover jobs from dashboard",    "cat": "core"},
    "jobs":      {"cli": None,               "desc": "List pending jobs",               "cat": "core"},
    "status":    {"cli": None,               "desc": "Show current status",             "cat": "info"},
    "doctor":    {"cli": ["doctor"],         "desc": "Health check",                    "cat": "info"},
    "login":     {"cli": ["login"],          "desc": "Configure credentials",           "cat": "setup"},
    "resume":    {"cli": None,               "desc": "Upload resume PDF + JSON",        "cat": "setup"},
    "config":    {"cli": ["config-cmd"],     "desc": "View/edit configuration",         "cat": "setup"},
    "questions": {"cli": ["questions"],      "desc": "Pre-fill common answers",         "cat": "setup"},
    "scan":      {"cli": ["scan"],           "desc": "Scan ATS portals for openings",   "cat": "core"},
    "sync":      {"cli": ["sync"],           "desc": "Sync knowledge with server",      "cat": "core"},
    "server":    {"cli": ["server"],         "desc": "Start the web UI dashboard",      "cat": "extra"},
    "dashboard": {"cli": ["open-dashboard"], "desc": "Open Whitebox dashboard",         "cat": "extra"},
    "clear":     {"cli": None,               "desc": "Clear the screen",                "cat": "util"},
    "help":      {"cli": None,               "desc": "Show all commands",               "cat": "util"},
    "exit":      {"cli": None,               "desc": "Exit WboxCLI",                    "cat": "util"},
}

COMMAND_NAMES = list(COMMANDS.keys())


# ── Readline Setup ────────────────────────────────────────────────────
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


# ── Banner Animation ─────────────────────────────────────────────────
def _animate_banner():
    """Print the banner with a smooth character-by-character reveal."""
    lines = [
        f"[bold {C['pink']}] ██╗    ██╗[/][bold {C['hot']}]██████╗  [/][bold {C['mag']}]██████╗ [/][bold {C['deep']}]██╗  ██╗[/]     [bold {C['lav']}]██████╗[/] [bold {C['purp']}]██╗     [/][bold {C['soft']}]██╗[/]",
        f"[bold {C['pink']}] ██║    ██║[/][bold {C['hot']}]██╔══██╗ [/][bold {C['mag']}]██╔═══██╗[/][bold {C['deep']}]╚██╗██╔╝[/]    [bold {C['lav']}]██╔════╝[/] [bold {C['purp']}]██║     [/][bold {C['soft']}]██║[/]",
        f"[bold {C['pink']}] ██║ █╗ ██║[/][bold {C['hot']}]██████╔╝ [/][bold {C['mag']}]██║   ██║[/][bold {C['deep']}] ╚███╔╝ [/]    [bold {C['lav']}]██║     [/] [bold {C['purp']}]██║     [/][bold {C['soft']}]██║[/]",
        f"[bold {C['pink']}] ██║███╗██║[/][bold {C['hot']}]██╔══██╗ [/][bold {C['mag']}]██║   ██║[/][bold {C['deep']}] ██╔██╗ [/]    [bold {C['lav']}]██║     [/] [bold {C['purp']}]██║     [/][bold {C['soft']}]██║[/]",
        f"[bold {C['pink']}] ╚███╔███╔╝[/][bold {C['hot']}]██████╔╝ [/][bold {C['mag']}]╚██████╔╝[/][bold {C['deep']}]██╔╝ ██╗[/]    [bold {C['lav']}]╚██████╗[/] [bold {C['purp']}]███████╗[/][bold {C['soft']}]██║[/]",
        f"[bold {C['pink']}]  ╚══╝╚══╝ [/][bold {C['hot']}]╚═════╝  [/][bold {C['mag']}] ╚═════╝ [/][bold {C['deep']}]╚═╝  ╚═╝[/]     [bold {C['lav']}]╚═════╝[/] [bold {C['purp']}]╚══════╝[/][bold {C['soft']}]╚═╝[/]",
    ]
    console.print()
    for line in lines:
        console.print(line)
        time.sleep(0.04)

    console.print()
    console.print(f"[dim {C['soft']}]       Autonomous Job Application Engine[/]", justify="center")
    time.sleep(0.1)
    console.print(f"[dim {C['muted']}]v0.1.0  •  Whitebox Learning[/]", justify="center")
    console.print()


# ── Panels ────────────────────────────────────────────────────────────
def _get_greeting() -> str:
    """Get a personalized greeting based on time of day and user name."""
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    try:
        from jobcli.cli.main import get_database
        from jobcli.storage.repositories import UserDataRepository
        db = get_database()
        session = db.get_session()
        resume = UserDataRepository(session).get_resume()
        session.close()
        if resume and resume.personal.first_name:
            return f"{greeting}, [{C['pink']}]{resume.personal.first_name}[/]"
    except Exception:
        pass

    return greeting


def _get_status_dashboard() -> Panel:
    from jobcli.cli.main import get_config, get_database
    from jobcli.storage.repositories import JobRepository, UserDataRepository

    config = get_config()
    db = get_database()
    session = db.get_session()
    job_repo = JobRepository(session)
    user_data_repo = UserDataRepository(session)

    has_llm = bool(config.openai_api_key or config.anthropic_api_key or config.gemini_api_key)
    llm_provider = config.default_llm_provider if has_llm else None
    has_wbox = bool(config.job_board_username and config.job_board_password)
    resume = user_data_repo.get_resume()
    pending_jobs = job_repo.list_pending()
    session.close()

    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2), expand=True)
    table.add_column("Key", style=C["soft"], width=20)
    table.add_column("Value")

    ok  = f"[{C['purp']}]✓[/]"
    bad = "[red]✗[/]"
    wrn = "[yellow]⚠[/]"

    table.add_row("LLM Provider",  f"{ok} {llm_provider}" if has_llm else f"{bad} Not configured — run [bold]login[/]")
    table.add_row("Whitebox Login", f"{ok} {config.job_board_username}" if has_wbox else f"{wrn} Not set — run [bold]login[/]")
    if resume:
        table.add_row("Resume", f"{ok} {resume.personal.first_name} {resume.personal.last_name}")
    else:
        table.add_row("Resume", f"{bad} Not uploaded — run [bold]resume[/]")
    table.add_row("Pending Jobs", f"[bold {C['hot']}]{len(pending_jobs)}[/] jobs ready")
    table.add_row("Browser", f"[{C['purp']}]Visible[/]" if not config.headless else f"[{C['muted']}]Headless[/]")

    return Panel(table, title=f"[bold {C['lav']}]⚡ Status[/]", border_style=C["vio"], padding=(1, 2))


def _get_quick_actions() -> Panel:
    """Show categorized commands in a clean layout."""
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1), expand=True)
    table.add_column("Cmd", width=14)
    table.add_column("Desc", style=C["muted"])

    # Group by category for visual structure
    categories = [
        ("🚀 Core",  "core"),
        ("⚙️  Setup", "setup"),
        ("📡 More",  "extra"),
        ("🔧 Utils", "util"),
    ]

    for cat_label, cat_key in categories:
        table.add_row(f"[bold {C['dim']}]{cat_label}[/]", "")
        for name, info in COMMANDS.items():
            if info.get("cat") == cat_key:
                table.add_row(f"  [{C['pink']}]{name}[/]", info["desc"])
        table.add_row("", "")  # spacer

    return Panel(table, title=f"[bold {C['lav']}]💡 Commands[/]", border_style=C["dark"], padding=(1, 2))


def _print_welcome():
    _animate_banner()

    greeting = _get_greeting()
    console.print(f"  {greeting}! [{C['dim']}]What would you like to do?[/]")
    console.print()

    try:
        status = _get_status_dashboard()
        actions = _get_quick_actions()
        # Side-by-side if terminal is wide enough, stacked if narrow
        term_width = shutil.get_terminal_size().columns
        if term_width >= 120:
            console.print(Columns([status, actions], expand=True, padding=(0, 2)))
        else:
            console.print(status)
            console.print(actions)
    except Exception:
        console.print(_get_quick_actions())

    console.print()


# ── Command Execution ─────────────────────────────────────────────────
def _find_jobcli_bin() -> str:
    venv_dir = os.path.join(os.path.expanduser("~"), ".jobcli", "venv")
    candidate = os.path.join(venv_dir, "Scripts" if os.name == "nt" else "bin", "jobcli.exe" if os.name == "nt" else "jobcli")
    if os.path.exists(candidate):
        return candidate
    return shutil.which("jobcli") or "jobcli"


def _exec_jobcli(args: list[str], label: str = ""):
    """Execute a jobcli subcommand with a spinner and streamed output."""
    jobcli = _find_jobcli_bin()
    display = label or " ".join(args)

    console.print()
    console.print(f"  [{C['dim']}]▸[/] [{C['purp']}]{display}[/]")
    console.print(Rule(style=C["faint"]))

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
        console.print(Rule(style=C["faint"]))

        if proc.returncode == 0:
            console.print(f"  [{C['purp']}]✓[/] [{C['muted']}]Done[/]")
        else:
            console.print(f"  [red]✗[/] [{C['muted']}]Exited with code {proc.returncode}[/]")

    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        console.print(f"\n  [yellow]⚠ Cancelled[/]")
    except FileNotFoundError:
        try:
            subprocess.run([sys.executable, "-m", "jobcli"] + args, cwd=os.getcwd())
        except KeyboardInterrupt:
            console.print(f"\n  [yellow]⚠ Cancelled[/]")

    console.print()


# ── Internal Handlers ─────────────────────────────────────────────────
def _cmd_status():
    console.print()
    try:
        console.print(_get_status_dashboard())
    except Exception as e:
        console.print(f"  [red]Error: {e}[/]")
    console.print()


def _cmd_jobs():
    try:
        from jobcli.cli.main import get_database
        from jobcli.storage.repositories import JobRepository

        # Show a loading spinner while fetching
        with console.status(f"[{C['purp']}]Loading jobs...", spinner="dots", spinner_style=C["pink"]):
            db = __import__("jobcli.cli.main", fromlist=["get_database"]).get_database()
            session = db.get_session()
            pending = JobRepository(session).list_pending()
            session.close()
            time.sleep(0.3)  # brief pause so spinner is visible

        if not pending:
            console.print(f"\n  [{C['muted']}]No pending jobs. Run [{C['pink']}]discover[/] to find some.[/]\n")
            return

        table = Table(
            title=f"[bold {C['lav']}]Pending Jobs ({len(pending)})[/]",
            box=box.ROUNDED,
            border_style=C["dark"],
            padding=(0, 1),
            show_lines=False,
        )
        table.add_column("#", style=C["muted"], width=4, justify="right")
        table.add_column("Title", style=C["purp"], max_width=40, no_wrap=True)
        table.add_column("Company", style=C["pink"], max_width=20, no_wrap=True)
        table.add_column("ATS", style=C["dim"], width=12)
        table.add_column("URL", style=C["faint"], max_width=45, no_wrap=True)

        for i, job in enumerate(pending, 1):
            url_short = job.url[:43] + "…" if len(job.url) > 43 else job.url
            ats = getattr(job, "ats_type", "") or "—"
            table.add_row(str(i), job.title or "—", job.company or "—", ats, url_short)

        console.print()
        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"  [red]Error: {e}[/]")


def _cmd_help():
    console.print()
    console.print(_get_quick_actions())
    console.print()


def _cmd_clear():
    os.system("cls" if os.name == "nt" else "clear")
    _print_welcome()


# ── Dispatcher ────────────────────────────────────────────────────────
def _dispatch(raw: str):
    parts = raw.strip().split()
    if not parts:
        return

    cmd = parts[0].lower()
    args = parts[1:]

    # Internal
    handlers = {"help": _cmd_help, "status": _cmd_status, "jobs": _cmd_jobs, "clear": _cmd_clear, "cls": _cmd_clear}
    if cmd in handlers:
        handlers[cmd]()
        return
    if cmd in ("exit", "quit", "q"):
        return

    # Apply (needs args)
    if cmd == "apply":
        if not args:
            console.print(f"\n  [{C['muted']}]Usage:[/] [{C['pink']}]apply --batch[/]  [{C['dim']}]or[/]  [{C['pink']}]apply --url <url>[/]\n")
            return
        _exec_jobcli(["apply"] + args, label=f"apply {' '.join(args)}")
        return

    # Resume alias
    if cmd == "resume":
        _exec_jobcli(["resume-upload"] + args, label="resume-upload")
        return

    # Standard CLI
    if cmd in COMMANDS and COMMANDS[cmd]["cli"] is not None:
        _exec_jobcli(COMMANDS[cmd]["cli"] + args, label=cmd)
        return

    # Unknown — fuzzy suggest
    matches = [c for c in COMMAND_NAMES if c.startswith(cmd[:2])]
    if matches:
        suggestions = "  ".join(f"[{C['pink']}]{m}[/]" for m in matches[:4])
        console.print(f"\n  [red]✗[/] Unknown command: [{C['dim']}]{cmd}[/]")
        console.print(f"  [{C['muted']}]Did you mean:[/]  {suggestions}\n")
    else:
        console.print(f"\n  [red]✗[/] Unknown command: [{C['dim']}]{cmd}[/]")
        console.print(f"  [{C['muted']}]Type [{C['pink']}]help[/] to see available commands.\n")


# ── Prompt ────────────────────────────────────────────────────────────
_tip_counter = 0

def _prompt() -> str:
    global _tip_counter
    # ANSI colors for input() (Rich can't style readline input)
    P = "\033[1;38;2;192;132;252m"  # bold purple
    D = "\033[38;2;75;85;99m"       # dim
    R = "\033[0m"                    # reset

    # Show a rotating tip every 3rd prompt
    _tip_counter += 1
    if _tip_counter % 3 == 0:
        tip = random.choice(TIPS)
        console.print(f"  {tip}")

    try:
        return input(f"{P}wboxcli{R} {D}❯{R} ").strip()
    except EOFError:
        return "exit"


# ── Main Session ──────────────────────────────────────────────────────
def interactive_session():
    """Main interactive REPL — polished, smooth, Claude Code-style."""

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
                    _goodbye()
                    break

                _dispatch(user_input)

            except KeyboardInterrupt:
                console.print(f"\n  [{C['dim']}]Interrupted. Type [{C['pink']}]exit[/] or Ctrl+D to quit.[/]")

    finally:
        try:
            readline.write_history_file(history_path)
        except Exception:
            pass


def _goodbye():
    """Smooth animated exit."""
    console.print()
    msgs = ["Saving session...", "See you next time! 👋"]
    for msg in msgs:
        console.print(f"  [{C['soft']}]{msg}[/]")
        time.sleep(0.2)
    console.print()
