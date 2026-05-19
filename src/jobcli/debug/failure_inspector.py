"""Failure inspection system for detailed debugging.

Analyzes failures with snapshots, AI reasoning, and execution context.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from jobcli.execution.engine import ExecutionResult, ExecutionStatus

from .ai_inspector import AIReasoning
from .snapshot import DOMSnapshot
from .timeline import TimelineEvent


class FailureContext(BaseModel):
    """Complete context for a failure."""

    # Failure metadata
    failure_id: str
    action_target: str
    action_type: str
    selector: str
    error_message: str
    attempts: int

    # Snapshots
    before_snapshot_id: Optional[str] = None
    after_snapshot_id: Optional[str] = None
    failure_snapshot_id: Optional[str] = None

    # AI reasoning
    ai_reasoning_ids: List[str] = Field(default_factory=list)

    # Timeline events
    timeline_events: List[TimelineEvent] = Field(default_factory=list)

    # Diagnosis
    diagnosis: List[str] = Field(default_factory=list)
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None


class FailureInspector:
    """Inspect and analyze execution failures."""

    def __init__(self):
        """Initialize failure inspector."""
        self.failures: List[FailureContext] = []
        self._failure_counter = 0

    def record_failure(
        self,
        result: ExecutionResult,
        action_type: str,
        selector: str,
        before_snapshot: Optional[DOMSnapshot] = None,
        after_snapshot: Optional[DOMSnapshot] = None,
        failure_snapshot: Optional[DOMSnapshot] = None,
        ai_reasonings: Optional[List[AIReasoning]] = None,
        timeline_events: Optional[List[TimelineEvent]] = None,
    ) -> FailureContext:
        """Record a failure for inspection.

        Args:
            result: Execution result
            action_type: Type of action that failed
            selector: Selector used
            before_snapshot: Snapshot before action
            after_snapshot: Snapshot after action
            failure_snapshot: Snapshot at failure
            ai_reasonings: Related AI reasonings
            timeline_events: Related timeline events

        Returns:
            FailureContext
        """
        self._failure_counter += 1
        failure_id = f"failure_{self._failure_counter:04d}"

        failure = FailureContext(
            failure_id=failure_id,
            action_target=result.action_target,
            action_type=action_type,
            selector=selector,
            error_message=result.error or "Unknown error",
            attempts=result.attempts,
            before_snapshot_id=before_snapshot.snapshot_id if before_snapshot else None,
            after_snapshot_id=after_snapshot.snapshot_id if after_snapshot else None,
            failure_snapshot_id=failure_snapshot.snapshot_id if failure_snapshot else None,
            ai_reasoning_ids=[r.reasoning_id for r in (ai_reasonings or [])],
            timeline_events=timeline_events or [],
        )

        # Diagnose failure
        self._diagnose_failure(failure, before_snapshot, after_snapshot)

        self.failures.append(failure)
        return failure

    def _diagnose_failure(
        self,
        failure: FailureContext,
        before_snapshot: Optional[DOMSnapshot],
        after_snapshot: Optional[DOMSnapshot],
    ) -> None:
        """Diagnose failure and suggest fixes.

        Args:
            failure: Failure context to diagnose
            before_snapshot: Snapshot before action
            after_snapshot: Snapshot after action
        """
        diagnosis = []
        root_cause = None
        suggested_fix = None

        # Check if element existed
        if before_snapshot:
            element = before_snapshot.elements.get(failure.action_target)

            if not element or not element.exists:
                diagnosis.append("Element not found with selector")
                root_cause = "selector_not_found"
                suggested_fix = "Update selector or verify page state"

            elif not element.visible:
                diagnosis.append("Element exists but not visible")
                root_cause = "element_not_visible"
                suggested_fix = "Check CSS display/visibility or wait for element"

                # Additional context
                if element.display == "none":
                    diagnosis.append(f"Element has display: none")
                if element.visibility == "hidden":
                    diagnosis.append(f"Element has visibility: hidden")
                if element.opacity == "0":
                    diagnosis.append(f"Element has opacity: 0")

            elif not element.enabled:
                diagnosis.append("Element visible but not enabled/disabled")
                root_cause = "element_disabled"
                suggested_fix = "Wait for element to become enabled"

            else:
                # Element was accessible, check value change
                if after_snapshot:
                    after_element = after_snapshot.elements.get(failure.action_target)
                    if after_element and element.value == after_element.value:
                        diagnosis.append("Element value did not change")
                        root_cause = "value_unchanged"
                        suggested_fix = "Check if field is readonly or JavaScript prevents change"

        # Check error message patterns
        error_lower = failure.error_message.lower()

        if "timeout" in error_lower:
            diagnosis.append("Operation timed out")
            if not root_cause:
                root_cause = "timeout"
                suggested_fix = "Increase timeout or optimize page load"

        if "navigation" in error_lower:
            diagnosis.append("Page navigation interrupted operation")
            if not root_cause:
                root_cause = "unexpected_navigation"
                suggested_fix = "Handle navigation or adjust timing"

        if "detached" in error_lower or "stale" in error_lower:
            diagnosis.append("Element became detached/stale (DOM changed)")
            if not root_cause:
                root_cause = "element_detached"
                suggested_fix = "Re-query element after DOM changes"

        # Update failure context
        failure.diagnosis = diagnosis
        failure.root_cause = root_cause
        failure.suggested_fix = suggested_fix

    def get_failure(self, failure_id: str) -> Optional[FailureContext]:
        """Get failure by ID.

        Args:
            failure_id: Failure ID

        Returns:
            FailureContext or None
        """
        for f in self.failures:
            if f.failure_id == failure_id:
                return f
        return None

    def get_failures_by_root_cause(self, root_cause: str) -> List[FailureContext]:
        """Get failures by root cause.

        Args:
            root_cause: Root cause to filter

        Returns:
            List of matching failures
        """
        return [f for f in self.failures if f.root_cause == root_cause]

    def get_failure_statistics(self) -> Dict[str, Any]:
        """Get failure statistics.

        Returns:
            Dict with stats (total, by root cause, by action type, etc.)
        """
        total = len(self.failures)
        if total == 0:
            return {"total_failures": 0}

        # Group by root cause
        by_root_cause: Dict[str, int] = {}
        for failure in self.failures:
            cause = failure.root_cause or "unknown"
            by_root_cause[cause] = by_root_cause.get(cause, 0) + 1

        # Group by action type
        by_action_type: Dict[str, int] = {}
        for failure in self.failures:
            by_action_type[failure.action_type] = by_action_type.get(failure.action_type, 0) + 1

        # Average attempts
        avg_attempts = sum(f.attempts for f in self.failures) / total

        return {
            "total_failures": total,
            "by_root_cause": by_root_cause,
            "by_action_type": by_action_type,
            "avg_attempts": avg_attempts,
        }

    def print_failure(self, failure_id: str, verbose: bool = False) -> None:
        """Print failure details to console.

        Args:
            failure_id: Failure ID
            verbose: Include full snapshots and AI reasoning?
        """
        failure = self.get_failure(failure_id)
        if not failure:
            print(f"Failure {failure_id} not found")
            return

        print("\n" + "=" * 70)
        print(f"FAILURE INSPECTION: {failure.failure_id}")
        print("=" * 70)
        print(f"Action: {failure.action_type} → {failure.action_target}")
        print(f"Selector: {failure.selector}")
        print(f"Error: {failure.error_message}")
        print(f"Attempts: {failure.attempts}")

        print("\n--- DIAGNOSIS ---")
        if failure.diagnosis:
            for diag in failure.diagnosis:
                print(f"  • {diag}")
        else:
            print("  (No diagnosis available)")

        if failure.root_cause:
            print(f"\nRoot Cause: {failure.root_cause}")

        if failure.suggested_fix:
            print(f"Suggested Fix: {failure.suggested_fix}")

        print("\n--- SNAPSHOTS ---")
        print(f"Before: {failure.before_snapshot_id or 'N/A'}")
        print(f"After: {failure.after_snapshot_id or 'N/A'}")
        print(f"Failure: {failure.failure_snapshot_id or 'N/A'}")

        if failure.ai_reasoning_ids:
            print("\n--- AI REASONING ---")
            for reasoning_id in failure.ai_reasoning_ids:
                print(f"  • {reasoning_id}")

        if verbose and failure.timeline_events:
            print("\n--- TIMELINE ---")
            for event in failure.timeline_events:
                print(f"  {event.to_console_log()}")

        print("=" * 70)

    def generate_failure_report(self, output_path: Path) -> None:
        """Generate comprehensive failure report.

        Args:
            output_path: Path to save report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        stats = self.get_failure_statistics()

        report = {
            "statistics": stats,
            "failures": [f.model_dump() for f in self.failures],
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

    def generate_failure_summary(self) -> str:
        """Generate human-readable failure summary.

        Returns:
            Summary text
        """
        stats = self.get_failure_statistics()

        summary = "\n" + "=" * 70 + "\n"
        summary += "FAILURE SUMMARY\n"
        summary += "=" * 70 + "\n"

        if stats.get("total_failures", 0) == 0:
            summary += "No failures recorded.\n"
            return summary

        summary += f"Total Failures: {stats['total_failures']}\n"
        summary += f"Avg Attempts: {stats['avg_attempts']:.1f}\n"

        summary += "\nFailures by Root Cause:\n"
        for cause, count in sorted(
            stats["by_root_cause"].items(), key=lambda x: x[1], reverse=True
        ):
            summary += f"  {cause}: {count}\n"

        summary += "\nFailures by Action Type:\n"
        for action_type, count in sorted(
            stats["by_action_type"].items(), key=lambda x: x[1], reverse=True
        ):
            summary += f"  {action_type}: {count}\n"

        summary += "\n" + "=" * 70 + "\n"

        return summary

    def export_failures_html(self, output_path: Path) -> None:
        """Export failures as interactive HTML report.

        Args:
            output_path: Path to save HTML
        """
        stats = self.get_failure_statistics()

        html = """<!DOCTYPE html>
<html>
<head>
    <title>Failure Inspection Report</title>
    <style>
        body {
            font-family: 'Monaco', 'Menlo', monospace;
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            margin: 0;
        }
        .header {
            border-bottom: 2px solid #444;
            padding-bottom: 20px;
            margin-bottom: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #2d2d2d;
            border: 1px solid #444;
            padding: 15px;
            border-radius: 5px;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #f48771;
        }
        .stat-label {
            color: #858585;
            font-size: 14px;
        }
        .failure {
            background: #2d2d2d;
            border: 1px solid #444;
            border-left: 4px solid #f48771;
            padding: 20px;
            margin: 15px 0;
            border-radius: 5px;
        }
        .failure-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .failure-id {
            color: #4fc1ff;
            font-weight: bold;
        }
        .failure-target {
            color: #dcdcaa;
        }
        .failure-error {
            color: #f48771;
            margin: 10px 0;
        }
        .diagnosis {
            background: rgba(255, 255, 255, 0.03);
            padding: 10px;
            margin: 10px 0;
            border-radius: 3px;
        }
        .diagnosis-item {
            color: #ce9178;
            margin: 5px 0;
        }
        .root-cause {
            background: rgba(244, 135, 113, 0.1);
            padding: 10px;
            border-left: 3px solid #f48771;
            margin: 10px 0;
        }
        .suggested-fix {
            background: rgba(78, 201, 176, 0.1);
            padding: 10px;
            border-left: 3px solid #4ec9b0;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Failure Inspection Report</h1>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{total}</div>
            <div class="stat-label">Total Failures</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{avg_attempts:.1f}</div>
            <div class="stat-label">Avg Attempts</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{unique_causes}</div>
            <div class="stat-label">Unique Root Causes</div>
        </div>
    </div>
""".format(
            total=stats.get("total_failures", 0),
            avg_attempts=stats.get("avg_attempts", 0),
            unique_causes=len(stats.get("by_root_cause", {})),
        )

        # Add individual failures
        for failure in self.failures:
            html += f"""
    <div class="failure">
        <div class="failure-header">
            <span class="failure-id">{failure.failure_id}</span>
            <span class="failure-target">{failure.action_type} → {failure.action_target}</span>
        </div>
        <div>Selector: <code>{failure.selector}</code></div>
        <div>Attempts: {failure.attempts}</div>
        <div class="failure-error">Error: {failure.error_message}</div>
"""

            if failure.diagnosis:
                html += """
        <div class="diagnosis">
            <strong>Diagnosis:</strong>
"""
                for diag in failure.diagnosis:
                    html += f"""
            <div class="diagnosis-item">• {diag}</div>
"""
                html += """
        </div>
"""

            if failure.root_cause:
                html += f"""
        <div class="root-cause">
            <strong>Root Cause:</strong> {failure.root_cause}
        </div>
"""

            if failure.suggested_fix:
                html += f"""
        <div class="suggested-fix">
            <strong>Suggested Fix:</strong> {failure.suggested_fix}
        </div>
"""

            html += """
    </div>
"""

        html += """
</body>
</html>
"""

        output_path.write_text(html)


# Global failure inspector instance
_global_failure_inspector = FailureInspector()


def get_failure_inspector() -> FailureInspector:
    """Get global failure inspector instance."""
    return _global_failure_inspector
