"""Rich-based progress tracking for job applications."""

from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from jobcli.core.schemas import ApplicationState, ExecutionPhase


class ApplicationProgressTracker:
    """Track and display job application progress using Rich."""

    def __init__(self, console: Optional[Console] = None) -> None:
        """Initialize progress tracker."""
        self.console = console or Console()

        # Create progress bars
        self.overall_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )

        self.phase_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        )

        self.overall_task: Optional[TaskID] = None
        self.phase_task: Optional[TaskID] = None

        self.current_job_url: str = ""
        self.current_phase: ExecutionPhase = ExecutionPhase.RULES
        self.phase_status: dict[ExecutionPhase, str] = {}

    def start_batch(self, total_jobs: int) -> None:
        """Start batch processing."""
        self.overall_task = self.overall_progress.add_task(
            "Processing jobs",
            total=total_jobs,
        )

    def start_job(self, job_url: str, job_number: int, total_jobs: int) -> None:
        """Start processing a single job."""
        self.current_job_url = job_url
        self.phase_status = {}

        if self.overall_task is not None:
            self.overall_progress.update(
                self.overall_task,
                description=f"Job {job_number}/{total_jobs}: {job_url[:50]}...",
            )

    def start_phase(self, phase: ExecutionPhase) -> None:
        """Start an execution phase."""
        self.current_phase = phase
        self.phase_status[phase] = "🔄 In Progress"

        phase_names = {
            ExecutionPhase.RULES: "Phase 1: Rule-based locators",
            ExecutionPhase.LLM: "Phase 2: LLM reasoning",
            ExecutionPhase.HUMAN: "Phase 3: Human assistance",
        }

        if self.phase_task is not None:
            self.phase_progress.remove_task(self.phase_task)

        self.phase_task = self.phase_progress.add_task(
            phase_names.get(phase, phase.value),
        )

    def end_phase(self, phase: ExecutionPhase, success: bool) -> None:
        """End an execution phase."""
        self.phase_status[phase] = "✅ Success" if success else "❌ Failed"

        if self.phase_task is not None:
            self.phase_progress.remove_task(self.phase_task)
            self.phase_task = None

    def update_action(self, action: str, details: str = "") -> None:
        """Update current action."""
        if self.phase_task is not None:
            description = f"{action}"
            if details:
                description += f" - {details}"
            self.phase_progress.update(
                self.phase_task,
                description=description,
            )

    def end_job(self, success: bool) -> None:
        """End processing a job."""
        if self.overall_task is not None:
            self.overall_progress.advance(self.overall_task)

        if self.phase_task is not None:
            self.phase_progress.remove_task(self.phase_task)
            self.phase_task = None

    def get_summary_panel(self, state: ApplicationState) -> Panel:
        """Get summary panel for current state."""
        # Create status table
        table = Table.grid(padding=(0, 2))
        table.add_column("Phase", style="bold")
        table.add_column("Status")

        for phase in [ExecutionPhase.RULES, ExecutionPhase.LLM, ExecutionPhase.HUMAN]:
            status = self.phase_status.get(phase, "⏸️ Pending")
            table.add_row(phase.value.title(), status)

        # Additional info
        table.add_row("", "")
        table.add_row("Current URL", Text(state.current_url[:60] + "...", style="dim"))
        table.add_row("Step Count", str(state.step_count))
        table.add_row("Attempts", str(state.attempts))

        if state.detected_ats:
            table.add_row("Detected ATS", state.detected_ats.value.title())

        return Panel(
            table,
            title=f"[bold]Job Application Progress[/bold]",
            border_style="blue",
        )

    def display(self) -> Live:
        """Get Live display context manager."""
        layout = Table.grid()
        layout.add_row(self.overall_progress)
        layout.add_row(self.phase_progress)

        return Live(layout, console=self.console, refresh_per_second=4)


class SimpleProgressBar:
    """Simple progress bar for quick operations."""

    def __init__(self, console: Optional[Console] = None) -> None:
        """Initialize simple progress bar."""
        self.console = console or Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        )

    def track(self, sequence, description: str = "Processing..."):
        """Track a sequence with progress bar."""
        return self.progress.track(sequence, description=description)


def create_status_table(
    jobs_processed: int,
    jobs_successful: int,
    jobs_failed: int,
    jobs_skipped: int,
) -> Table:
    """Create summary status table."""
    table = Table(title="Application Summary", show_header=True, header_style="bold magenta")

    table.add_column("Status", style="cyan", width=20)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Percentage", justify="right", style="yellow")

    total = jobs_processed
    if total == 0:
        total = 1  # Avoid division by zero

    table.add_row(
        "Total Processed",
        str(jobs_processed),
        f"{100.0:.1f}%",
    )

    table.add_row(
        "✅ Successful",
        str(jobs_successful),
        f"{jobs_successful / total * 100:.1f}%",
    )

    table.add_row(
        "❌ Failed",
        str(jobs_failed),
        f"{jobs_failed / total * 100:.1f}%",
    )

    table.add_row(
        "⏭️ Skipped",
        str(jobs_skipped),
        f"{jobs_skipped / total * 100:.1f}%",
    )

    return table
