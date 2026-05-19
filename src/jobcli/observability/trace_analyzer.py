"""Trace analyzer for observability data.

Analyzes structured logs to provide insights:
- Find all traces for a session
- Reconstruct execution flow
- Identify failures
- Calculate performance metrics
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .structured_logger import StructuredLogEntry


class TraceStatistics(BaseModel):
    """Statistics for a trace."""

    trace_id: str
    operation: Optional[str] = None

    # Timing
    start_time: datetime
    end_time: datetime
    duration_ms: int

    # Entries
    total_entries: int
    debug_count: int = 0
    info_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    critical_count: int = 0

    # Status
    success: bool = True
    errors: List[str] = Field(default_factory=list)


class SessionStatistics(BaseModel):
    """Statistics for a session."""

    session_id: str

    # Applications
    application_ids: List[str] = Field(default_factory=list)
    total_applications: int = 0
    successful_applications: int = 0
    failed_applications: int = 0

    # Timing
    start_time: datetime
    end_time: Optional[datetime] = None
    total_duration_ms: Optional[int] = None

    # Logs
    total_log_entries: int = 0
    error_count: int = 0
    warning_count: int = 0

    # Traces
    total_traces: int = 0
    traces: List[TraceStatistics] = Field(default_factory=list)


class TraceAnalyzer:
    """Analyzer for trace and log data."""

    def __init__(self, log_file: Path):
        """Initialize trace analyzer.

        Args:
            log_file: Path to log file
        """
        self.log_file = log_file
        self.entries: List[StructuredLogEntry] = []

        if log_file.exists():
            self._load_entries()

    def _load_entries(self) -> None:
        """Load log entries from file."""
        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        entry = StructuredLogEntry(**data)
                        self.entries.append(entry)
                    except Exception:
                        pass  # Skip malformed entries

    def get_session_statistics(self, session_id: str) -> Optional[SessionStatistics]:
        """Get statistics for a session.

        Args:
            session_id: Session ID

        Returns:
            SessionStatistics or None
        """
        session_entries = [e for e in self.entries if e.session_id == session_id]

        if not session_entries:
            return None

        # Sort by timestamp
        session_entries.sort(key=lambda e: e.timestamp)

        # Collect application IDs
        application_ids = list(
            set(e.application_id for e in session_entries if e.application_id)
        )

        # Calculate timing
        start_time = session_entries[0].timestamp
        end_time = session_entries[-1].timestamp
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Count log levels
        error_count = sum(1 for e in session_entries if e.level == "error")
        warning_count = sum(1 for e in session_entries if e.level == "warning")

        # Analyze traces
        traces = self._analyze_traces_for_session(session_entries)

        # Determine success/failure per application
        successful_apps = 0
        failed_apps = 0

        for app_id in application_ids:
            app_entries = [e for e in session_entries if e.application_id == app_id]
            has_errors = any(e.level in ["error", "critical"] for e in app_entries)

            if has_errors:
                failed_apps += 1
            else:
                successful_apps += 1

        return SessionStatistics(
            session_id=session_id,
            application_ids=application_ids,
            total_applications=len(application_ids),
            successful_applications=successful_apps,
            failed_applications=failed_apps,
            start_time=start_time,
            end_time=end_time,
            total_duration_ms=duration_ms,
            total_log_entries=len(session_entries),
            error_count=error_count,
            warning_count=warning_count,
            total_traces=len(traces),
            traces=traces,
        )

    def _analyze_traces_for_session(
        self, session_entries: List[StructuredLogEntry]
    ) -> List[TraceStatistics]:
        """Analyze traces within session.

        Args:
            session_entries: Log entries for session

        Returns:
            List of TraceStatistics
        """
        # Group by trace_id
        traces_dict: Dict[str, List[StructuredLogEntry]] = defaultdict(list)

        for entry in session_entries:
            if entry.trace_id:
                traces_dict[entry.trace_id].append(entry)

        # Analyze each trace
        traces = []

        for trace_id, trace_entries in traces_dict.items():
            trace_entries.sort(key=lambda e: e.timestamp)

            # Calculate stats
            start_time = trace_entries[0].timestamp
            end_time = trace_entries[-1].timestamp
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Count by level
            debug_count = sum(1 for e in trace_entries if e.level == "debug")
            info_count = sum(1 for e in trace_entries if e.level == "info")
            warning_count = sum(1 for e in trace_entries if e.level == "warning")
            error_count = sum(1 for e in trace_entries if e.level == "error")
            critical_count = sum(1 for e in trace_entries if e.level == "critical")

            # Determine success
            success = error_count == 0 and critical_count == 0

            # Collect errors
            errors = [
                e.error_message
                for e in trace_entries
                if e.error_message and e.level in ["error", "critical"]
            ]

            # Get operation (from first entry with operation)
            operation = None
            for entry in trace_entries:
                if entry.operation:
                    operation = entry.operation
                    break

            traces.append(
                TraceStatistics(
                    trace_id=trace_id,
                    operation=operation,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    total_entries=len(trace_entries),
                    debug_count=debug_count,
                    info_count=info_count,
                    warning_count=warning_count,
                    error_count=error_count,
                    critical_count=critical_count,
                    success=success,
                    errors=errors,
                )
            )

        return traces

    def find_failed_applications(self) -> List[str]:
        """Find all failed application IDs.

        Returns:
            List of application IDs that had errors
        """
        failed_apps = set()

        for entry in self.entries:
            if entry.level in ["error", "critical"] and entry.application_id:
                failed_apps.add(entry.application_id)

        return sorted(failed_apps)

    def find_slow_operations(
        self, threshold_ms: int = 5000
    ) -> List[Tuple[str, int, str]]:
        """Find slow operations.

        Args:
            threshold_ms: Threshold in milliseconds

        Returns:
            List of (trace_id, duration_ms, operation)
        """
        # Group by trace
        traces_dict: Dict[str, List[StructuredLogEntry]] = defaultdict(list)

        for entry in self.entries:
            if entry.trace_id:
                traces_dict[entry.trace_id].append(entry)

        slow_ops = []

        for trace_id, trace_entries in traces_dict.items():
            if not trace_entries:
                continue

            trace_entries.sort(key=lambda e: e.timestamp)
            start = trace_entries[0].timestamp
            end = trace_entries[-1].timestamp
            duration_ms = int((end - start).total_seconds() * 1000)

            if duration_ms >= threshold_ms:
                # Get operation
                operation = "unknown"
                for entry in trace_entries:
                    if entry.operation:
                        operation = entry.operation
                        break

                slow_ops.append((trace_id, duration_ms, operation))

        # Sort by duration
        slow_ops.sort(key=lambda x: x[1], reverse=True)

        return slow_ops

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors.

        Returns:
            Dict with error statistics
        """
        error_entries = [e for e in self.entries if e.level in ["error", "critical"]]

        if not error_entries:
            return {"total_errors": 0}

        # Group by error type
        by_type: Dict[str, int] = defaultdict(int)
        for entry in error_entries:
            error_type = entry.error_type or "unknown"
            by_type[error_type] += 1

        # Group by component
        by_component: Dict[str, int] = defaultdict(int)
        for entry in error_entries:
            component = entry.component or "unknown"
            by_component[component] += 1

        # Group by operation
        by_operation: Dict[str, int] = defaultdict(int)
        for entry in error_entries:
            operation = entry.operation or "unknown"
            by_operation[operation] += 1

        return {
            "total_errors": len(error_entries),
            "by_type": dict(by_type),
            "by_component": dict(by_component),
            "by_operation": dict(by_operation),
            "most_common_error": max(by_type.items(), key=lambda x: x[1])[0]
            if by_type
            else None,
        }

    def reconstruct_execution_flow(self, trace_id: str) -> List[StructuredLogEntry]:
        """Reconstruct execution flow for a trace.

        Args:
            trace_id: Trace ID

        Returns:
            List of StructuredLogEntry sorted by timestamp
        """
        trace_entries = [e for e in self.entries if e.trace_id == trace_id]
        trace_entries.sort(key=lambda e: e.timestamp)

        return trace_entries

    def export_session_report(
        self, session_id: str, output_file: Path
    ) -> None:
        """Export session report to file.

        Args:
            session_id: Session ID
            output_file: Output file path
        """
        stats = self.get_session_statistics(session_id)

        if not stats:
            return

        with open(output_file, "w") as f:
            f.write("=" * 70 + "\n")
            f.write(f"SESSION REPORT: {session_id}\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"Duration: {stats.total_duration_ms}ms\n")
            f.write(f"Start: {stats.start_time}\n")
            f.write(f"End: {stats.end_time}\n\n")

            f.write(f"Applications: {stats.total_applications}\n")
            f.write(f"  Successful: {stats.successful_applications}\n")
            f.write(f"  Failed: {stats.failed_applications}\n\n")

            f.write(f"Log Entries: {stats.total_log_entries}\n")
            f.write(f"  Errors: {stats.error_count}\n")
            f.write(f"  Warnings: {stats.warning_count}\n\n")

            f.write(f"Traces: {stats.total_traces}\n\n")

            # Failed traces
            failed_traces = [t for t in stats.traces if not t.success]
            if failed_traces:
                f.write(f"Failed Traces ({len(failed_traces)}):\n")
                for trace in failed_traces:
                    f.write(f"  - {trace.trace_id}\n")
                    f.write(f"    Operation: {trace.operation}\n")
                    f.write(f"    Duration: {trace.duration_ms}ms\n")
                    f.write(f"    Errors: {trace.error_count}\n")
                    for error in trace.errors:
                        f.write(f"      • {error}\n")
                    f.write("\n")

            # Slow traces
            slow_traces = [t for t in stats.traces if t.duration_ms > 5000]
            if slow_traces:
                f.write(f"\nSlow Traces (>5s) ({len(slow_traces)}):\n")
                for trace in slow_traces:
                    f.write(f"  - {trace.trace_id}\n")
                    f.write(f"    Operation: {trace.operation}\n")
                    f.write(f"    Duration: {trace.duration_ms}ms\n\n")

            f.write("=" * 70 + "\n")
