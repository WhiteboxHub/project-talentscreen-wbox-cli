"""Structured logging with trace context.

All log messages include full trace context for traceability.
"""

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .trace_context import TraceContext, get_trace_context


class LogLevel(str, Enum):
    """Log levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StructuredLogEntry(BaseModel):
    """Structured log entry with trace context."""

    # Core fields
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: LogLevel
    message: str

    # Trace context (always included)
    session_id: Optional[str] = None
    application_id: Optional[str] = None
    job_id: Optional[str] = None
    attempt_id: Optional[str] = None
    trace_id: Optional[str] = None

    # Operation context
    operation: Optional[str] = None
    component: Optional[str] = None

    # Additional data
    data: Dict[str, Any] = Field(default_factory=dict)

    # Error info (if error/exception)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_json(self) -> str:
        """Convert to JSON string.

        Returns:
            JSON string
        """
        return json.dumps(self.model_dump(), default=str, separators=(",", ":"))

    def to_pretty_json(self) -> str:
        """Convert to pretty JSON string.

        Returns:
            Pretty JSON string
        """
        return json.dumps(self.model_dump(), default=str, indent=2)


class StructuredLogger:
    """Structured logger with automatic trace context injection."""

    def __init__(
        self,
        component: str,
        log_file: Optional[Path] = None,
        console_output: bool = True,
        json_format: bool = True,
    ):
        """Initialize structured logger.

        Args:
            component: Component name
            log_file: Path to log file (optional)
            console_output: Output to console?
            json_format: Use JSON format for console?
        """
        self.component = component
        self.log_file = log_file
        self.console_output = console_output
        self.json_format = json_format

        # Setup file handler if needed
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            self.file_handler = open(log_file, "a")
        else:
            self.file_handler = None

    def _create_entry(
        self,
        level: LogLevel,
        message: str,
        operation: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> StructuredLogEntry:
        """Create structured log entry.

        Args:
            level: Log level
            message: Log message
            operation: Operation name
            data: Additional data
            error: Exception (if logging error)

        Returns:
            StructuredLogEntry
        """
        # Get trace context
        context = get_trace_context()

        # Create entry
        entry = StructuredLogEntry(
            level=level,
            message=message,
            component=self.component,
            operation=operation,
            data=data or {},
        )

        # Inject trace context
        if context:
            entry.session_id = context.session_id
            entry.application_id = context.application_id
            entry.job_id = context.job_id
            entry.attempt_id = context.attempt_id
            entry.trace_id = context.trace_id

            if not operation and context.operation:
                entry.operation = context.operation

        # Add error info
        if error:
            entry.error_type = type(error).__name__
            entry.error_message = str(error)

            import traceback

            entry.stack_trace = traceback.format_exc()

        return entry

    def _write_entry(self, entry: StructuredLogEntry) -> None:
        """Write log entry to outputs.

        Args:
            entry: StructuredLogEntry
        """
        # Write to file (always JSON)
        if self.file_handler:
            self.file_handler.write(entry.to_json() + "\n")
            self.file_handler.flush()

        # Write to console
        if self.console_output:
            if self.json_format:
                print(entry.to_json())
            else:
                # Human-readable format
                timestamp = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
                level_str = entry.level.value.upper()

                # Color codes
                colors = {
                    "debug": "\033[36m",  # Cyan
                    "info": "\033[32m",  # Green
                    "warning": "\033[33m",  # Yellow
                    "error": "\033[31m",  # Red
                    "critical": "\033[35m",  # Magenta
                }
                reset = "\033[0m"

                color = colors.get(entry.level.value, "")

                parts = [
                    f"{timestamp}",
                    f"{color}[{level_str}]{reset}",
                    f"[{self.component}]",
                ]

                if entry.trace_id:
                    parts.append(f"[{entry.trace_id}]")

                if entry.operation:
                    parts.append(f"[{entry.operation}]")

                parts.append(entry.message)

                print(" ".join(parts))

                # Print data if present
                if entry.data:
                    print(f"  Data: {json.dumps(entry.data, default=str)}")

                # Print error if present
                if entry.error_message:
                    print(f"  Error: {entry.error_type}: {entry.error_message}")

    def debug(
        self,
        message: str,
        operation: Optional[str] = None,
        **data,
    ) -> None:
        """Log debug message.

        Args:
            message: Log message
            operation: Operation name
            **data: Additional data
        """
        entry = self._create_entry(LogLevel.DEBUG, message, operation, data)
        self._write_entry(entry)

    def info(
        self,
        message: str,
        operation: Optional[str] = None,
        **data,
    ) -> None:
        """Log info message.

        Args:
            message: Log message
            operation: Operation name
            **data: Additional data
        """
        entry = self._create_entry(LogLevel.INFO, message, operation, data)
        self._write_entry(entry)

    def warning(
        self,
        message: str,
        operation: Optional[str] = None,
        **data,
    ) -> None:
        """Log warning message.

        Args:
            message: Log message
            operation: Operation name
            **data: Additional data
        """
        entry = self._create_entry(LogLevel.WARNING, message, operation, data)
        self._write_entry(entry)

    def error(
        self,
        message: str,
        error: Optional[Exception] = None,
        operation: Optional[str] = None,
        **data,
    ) -> None:
        """Log error message.

        Args:
            message: Log message
            error: Exception
            operation: Operation name
            **data: Additional data
        """
        entry = self._create_entry(LogLevel.ERROR, message, operation, data, error)
        self._write_entry(entry)

    def critical(
        self,
        message: str,
        error: Optional[Exception] = None,
        operation: Optional[str] = None,
        **data,
    ) -> None:
        """Log critical message.

        Args:
            message: Log message
            error: Exception
            operation: Operation name
            **data: Additional data
        """
        entry = self._create_entry(LogLevel.CRITICAL, message, operation, data, error)
        self._write_entry(entry)

    def close(self) -> None:
        """Close log file handler."""
        if self.file_handler:
            self.file_handler.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()


class LoggerFactory:
    """Factory for creating component-specific loggers."""

    _loggers: Dict[str, StructuredLogger] = {}
    _default_log_dir: Optional[Path] = None
    _console_output: bool = True
    _json_format: bool = False

    @classmethod
    def configure(
        cls,
        log_dir: Optional[Path] = None,
        console_output: bool = True,
        json_format: bool = False,
    ) -> None:
        """Configure logger factory.

        Args:
            log_dir: Default log directory
            console_output: Output to console?
            json_format: Use JSON format for console?
        """
        cls._default_log_dir = log_dir
        cls._console_output = console_output
        cls._json_format = json_format

    @classmethod
    def get_logger(cls, component: str) -> StructuredLogger:
        """Get logger for component.

        Args:
            component: Component name

        Returns:
            StructuredLogger
        """
        if component not in cls._loggers:
            # Create logger
            log_file = None
            if cls._default_log_dir:
                log_file = cls._default_log_dir / f"{component}.log"

            logger = StructuredLogger(
                component=component,
                log_file=log_file,
                console_output=cls._console_output,
                json_format=cls._json_format,
            )

            cls._loggers[component] = logger

        return cls._loggers[component]

    @classmethod
    def close_all(cls) -> None:
        """Close all loggers."""
        for logger in cls._loggers.values():
            logger.close()

        cls._loggers.clear()


def get_logger(component: str) -> StructuredLogger:
    """Get logger for component.

    Args:
        component: Component name

    Returns:
        StructuredLogger
    """
    return LoggerFactory.get_logger(component)
