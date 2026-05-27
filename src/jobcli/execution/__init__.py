"""Strict execution layer with structured actions, retries, validation, and telemetry.

This module provides a deterministic execution engine that:
- Executes simple, structured actions (fill_input, click_button, etc.)
- Validates before and after execution
- Retries with exponential backoff
- Emits structured telemetry events
- Tracks state across execution
"""

from jobcli.execution.actions import (
    ClickAction,
    ExecutionAction,
    FillInputAction,
    SelectOptionAction,
    UploadFileAction,
)
from jobcli.execution.engine import ExecutionEngine, ExecutionResult
from jobcli.execution.telemetry import TelemetryEvent, TelemetryTracker

__all__ = [
    "ExecutionAction",
    "FillInputAction",
    "ClickAction",
    "SelectOptionAction",
    "UploadFileAction",
    "ExecutionEngine",
    "ExecutionResult",
    "TelemetryEvent",
    "TelemetryTracker",
]
