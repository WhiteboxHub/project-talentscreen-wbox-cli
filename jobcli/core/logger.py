"""Structured logging system with JSON output."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog
from playwright.sync_api import Page

from jobcli.core.schemas import ExecutionPhase, LogEntry


class JobLogger:
    """Structured logger for job applications."""

    def __init__(
        self,
        job_id: int,
        log_directory: str = "logs",
        enable_screenshots: bool = True,
        on_event: Optional[Any] = None,
    ) -> None:
        """Initialize job logger."""
        self.job_id = job_id
        self.log_directory = Path(log_directory)
        self.enable_screenshots = enable_screenshots
        self.on_event = on_event

        # Create job-specific log directory
        self.job_log_dir = self.log_directory / f"job_{job_id}"
        self.job_log_dir.mkdir(parents=True, exist_ok=True)

        # Create screenshots directory
        self.screenshots_dir = self.job_log_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)

        # Create DOM snapshots directory
        self.dom_dir = self.job_log_dir / "dom_snapshots"
        self.dom_dir.mkdir(exist_ok=True)

        # Setup structlog
        self._setup_logger()

        self.screenshot_counter = 0
        self.dom_counter = 0

    def _setup_logger(self) -> None:
        """Setup structlog with JSON output."""
        log_file = self.job_log_dir / "application.jsonl"

        # Configure structlog
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.WriteLoggerFactory(
                file=open(log_file, "a", encoding="utf-8")
            ),
            cache_logger_on_first_use=True,
        )

        self.logger = structlog.get_logger()
        
        # Add a rich console for user-facing output
        from rich.console import Console
        self.console = Console()

    def log(
        self,
        level: str,
        message: str,
        phase: Optional[ExecutionPhase] = None,
        **metadata: Any,
    ) -> None:
        """Log a message with metadata."""
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(
            message,
            job_id=self.job_id,
            phase=phase.value if phase else None,
            **metadata,
        )
        
        # Mirror important info to terminal for monitoring
        if level.lower() in ["info", "warning", "error", "critical"]:
            self._print_to_console(level, message, phase, **metadata)

    def _print_to_console(self, level: str, message: str, phase: Optional[ExecutionPhase], **metadata: Any) -> None:
        """Helper to format and print logs to console for user visibility."""
        if not hasattr(self, "console"):
            return
            
        color = "white"
        if level.lower() == "warning": color = "yellow"
        elif level.lower() == "error": color = "red"
        elif level.lower() == "critical": color = "bold red"
        elif level.lower() == "info": color = "cyan"
        
        prefix = f"[{color}][{level.upper()}][/{color}]"
        if phase:
            prefix += f" [dim]({phase.value})[/dim]"
            
        # Format actions specifically
        if "action" in metadata:
            msg = f"{prefix} [bold]AI Action:[/bold] {metadata['action']}"
            if "selector" in metadata: msg += f" on {metadata['selector']}"
            if "value" in metadata: msg += f" -> [green]{metadata['value']}[/green]"
            # Keep the actual error/info message — otherwise failures
            # (e.g. raised exceptions) show up as useless "AI Action: click
            # on Yes" lines with no root cause attached.
            if message and level.lower() in ("error", "warning", "critical"):
                msg += f"  [dim]— {message}[/dim]"
            self.console.print(msg)
        elif "success" in metadata:
             status = "[green][OK][/green]" if metadata.get("success", True) else "[red][X][/red]"
             self.console.print(f"{prefix} {status} {message}")
        else:
            self.console.print(f"{prefix} {message}")


    def debug(
        self, message: str, phase: Optional[ExecutionPhase] = None, **metadata: Any
    ) -> None:
        """Log debug message."""
        self.log("debug", message, phase, **metadata)

    def info(
        self, message: str, phase: Optional[ExecutionPhase] = None, **metadata: Any
    ) -> None:
        """Log info message."""
        self.log("info", message, phase, **metadata)

    def warning(
        self, message: str, phase: Optional[ExecutionPhase] = None, **metadata: Any
    ) -> None:
        """Log warning message."""
        self.log("warning", message, phase, **metadata)

    def emit_event(self, data: Any) -> None:
        """Forward an event to the callback."""
        if self.on_event:
            self.on_event(data)

    def error(
        self, message: str, phase: Optional[ExecutionPhase] = None, **metadata: Any
    ) -> None:
        """Log error message."""
        self.log("error", message, phase, **metadata)

    def critical(
        self, message: str, phase: Optional[ExecutionPhase] = None, **metadata: Any
    ) -> None:
        """Log critical message."""
        self.log("critical", message, phase, **metadata)

    def capture_screenshot(
        self,
        page: Page,
        name: str = "screenshot",
        phase: Optional[ExecutionPhase] = None,
    ) -> Optional[str]:
        """Capture screenshot and return path."""
        if not self.enable_screenshots:
            return None

        try:
            self.screenshot_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.screenshot_counter:03d}_{timestamp}_{name}.png"
            filepath = self.screenshots_dir / filename

            page.screenshot(path=str(filepath), full_page=True)

            self.info(
                "Screenshot captured",
                phase=phase,
                screenshot_path=str(filepath),
                name=name,
            )

            return str(filepath)
        except Exception as e:
            self.error("Failed to capture screenshot", phase=phase, error=str(e))
            return None

    def save_dom_snapshot(
        self,
        page: Page,
        name: str = "snapshot",
        phase: Optional[ExecutionPhase] = None,
    ) -> Optional[str]:
        """Save DOM snapshot and return path."""
        try:
            self.dom_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.dom_counter:03d}_{timestamp}_{name}.html"
            filepath = self.dom_dir / filename

            content = page.content()
            filepath.write_text(content, encoding="utf-8")

            self.info(
                "DOM snapshot saved",
                phase=phase,
                dom_path=str(filepath),
                name=name,
            )

            return str(filepath)
        except Exception as e:
            self.error("Failed to save DOM snapshot", phase=phase, error=str(e))
            return None

    def save_structured_dom(
        self,
        dom_data: dict[str, Any],
        name: str = "structured",
        phase: Optional[ExecutionPhase] = None,
    ) -> Optional[str]:
        """Save structured DOM data as JSON."""
        try:
            self.dom_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.dom_counter:03d}_{timestamp}_{name}.json"
            filepath = self.dom_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(dom_data, f, indent=2)

            self.info(
                "Structured DOM saved",
                phase=phase,
                dom_path=str(filepath),
                name=name,
            )

            return str(filepath)
        except Exception as e:
            self.error("Failed to save structured DOM", phase=phase, error=str(e))
            return None

    def log_action(
        self,
        action: str,
        success: bool,
        phase: ExecutionPhase,
        selector: Optional[str] = None,
        error: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        """Log a browser action."""
        self.info(
            f"Action: {action}",
            phase=phase,
            action=action,
            success=success,
            selector=selector,
            error=error,
            **metadata,
        )

    def log_phase_start(self, phase: ExecutionPhase) -> None:
        """Log start of execution phase."""
        self.info(f"Starting phase: {phase.value}", phase=phase)

    def log_phase_end(self, phase: ExecutionPhase, success: bool) -> None:
        """Log end of execution phase."""
        self.info(
            f"Completed phase: {phase.value}",
            phase=phase,
            success=success,
        )

    def get_log_summary(self) -> dict[str, Any]:
        """Get summary of log directory."""
        return {
            "job_id": self.job_id,
            "log_directory": str(self.job_log_dir),
            "screenshots_count": self.screenshot_counter,
            "dom_snapshots_count": self.dom_counter,
            "log_file": str(self.job_log_dir / "application.jsonl"),
        }


class GlobalLogger:
    """Global application logger."""

    _instance: Optional["GlobalLogger"] = None
    _logger: Optional[structlog.BoundLogger] = None

    def __new__(cls) -> "GlobalLogger":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize global logger."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "jobcli.jsonl"

        # Configure structlog
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.WriteLoggerFactory(
                file=open(log_file, "a", encoding="utf-8")
            ),
            cache_logger_on_first_use=True,
        )

        self._logger = structlog.get_logger()

    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger instance."""
        if self._logger is None:
            self._initialize()
        return self._logger  # type: ignore

    def info(self, message: str, **metadata: Any) -> None:
        """Log info message."""
        self.logger.info(message, **metadata)

    def error(self, message: str, **metadata: Any) -> None:
        """Log error message."""
        self.logger.error(message, **metadata)

    def warning(self, message: str, **metadata: Any) -> None:
        """Log warning message."""
        self.logger.warning(message, **metadata)

    def debug(self, message: str, **metadata: Any) -> None:
        """Log debug message."""
        self.logger.debug(message, **metadata)


# Global logger instance
global_logger = GlobalLogger()
