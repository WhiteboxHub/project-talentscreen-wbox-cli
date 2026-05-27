"""Execution timeline tracking for debugging and analysis."""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TimelineEventType(str, Enum):
    """Types of timeline events."""

    # Session events
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"

    # Action events
    ACTION_STARTED = "action_started"
    ACTION_COMPLETED = "action_completed"
    ACTION_FAILED = "action_failed"
    ACTION_RETRYING = "action_retrying"
    ACTION_SKIPPED = "action_skipped"

    # Validation events
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"

    # Verification events
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"

    # AI/Semantic events
    AI_INFERENCE_STARTED = "ai_inference_started"
    AI_INFERENCE_COMPLETED = "ai_inference_completed"
    FIELD_DETECTED = "field_detected"
    FIELD_CLASSIFIED = "field_classified"

    # Human interaction
    HUMAN_INPUT_REQUESTED = "human_input_requested"
    HUMAN_INPUT_PROVIDED = "human_input_provided"

    # Navigation
    PAGE_LOADED = "page_loaded"
    PAGE_NAVIGATED = "page_navigated"

    # Snapshots
    SNAPSHOT_CAPTURED = "snapshot_captured"

    # Errors
    ERROR_OCCURRED = "error_occurred"


class TimelineEvent(BaseModel):
    """A single event in the execution timeline."""

    event_id: str = Field(..., description="Unique event ID")
    event_type: TimelineEventType = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    relative_time_ms: int = Field(0, description="Time since session start (ms)")

    # Context
    action_target: Optional[str] = Field(None, description="Target field ID")
    session_id: Optional[str] = Field(None, description="Session ID")

    # Outcome
    success: Optional[bool] = Field(None, description="Did operation succeed?")
    duration_ms: Optional[int] = Field(None, description="Operation duration")

    # Details
    message: Optional[str] = Field(None, description="Human-readable message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional data")

    def to_console_log(self) -> str:
        """Format event as console log line."""
        timestamp_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        relative_str = f"+{self.relative_time_ms}ms"

        status = ""
        if self.success is True:
            status = "✓"
        elif self.success is False:
            status = "✗"

        parts = [
            timestamp_str,
            f"[{relative_str:>8}]",
            status,
            self.event_type.value,
        ]

        if self.action_target:
            parts.append(f"→ {self.action_target}")

        if self.message:
            parts.append(f": {self.message}")

        if self.duration_ms:
            parts.append(f"({self.duration_ms}ms)")

        return " ".join(parts)


class ExecutionTimeline:
    """Timeline of execution events for debugging and analysis."""

    def __init__(self):
        """Initialize timeline."""
        self.events: List[TimelineEvent] = []
        self.start_time: Optional[datetime] = None
        self._event_counter = 0

    def add_event(
        self,
        event_type: TimelineEventType,
        action_target: Optional[str] = None,
        session_id: Optional[str] = None,
        success: Optional[bool] = None,
        duration_ms: Optional[int] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        """Add an event to the timeline.

        Args:
            event_type: Type of event
            action_target: Target field ID
            session_id: Session ID
            success: Did operation succeed?
            duration_ms: Operation duration
            message: Human-readable message
            metadata: Additional data

        Returns:
            Created TimelineEvent
        """
        now = datetime.utcnow()

        # Set start time on first event
        if self.start_time is None:
            self.start_time = now

        # Calculate relative time
        relative_time_ms = int((now - self.start_time).total_seconds() * 1000)

        # Generate event ID
        self._event_counter += 1
        event_id = f"event_{self._event_counter:04d}"

        # Create event
        event = TimelineEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=now,
            relative_time_ms=relative_time_ms,
            action_target=action_target,
            session_id=session_id,
            success=success,
            duration_ms=duration_ms,
            message=message,
            metadata=metadata or {},
        )

        self.events.append(event)
        return event

    def get_events_by_type(self, event_type: TimelineEventType) -> List[TimelineEvent]:
        """Get all events of a specific type.

        Args:
            event_type: Event type to filter

        Returns:
            List of matching events
        """
        return [e for e in self.events if e.event_type == event_type]

    def get_events_by_target(self, target: str) -> List[TimelineEvent]:
        """Get all events for a specific target.

        Args:
            target: Target field ID

        Returns:
            List of events for target
        """
        return [e for e in self.events if e.action_target == target]

    def get_failed_events(self) -> List[TimelineEvent]:
        """Get all failed events.

        Returns:
            List of events with success=False
        """
        return [e for e in self.events if e.success is False]

    def get_total_duration_ms(self) -> int:
        """Get total timeline duration.

        Returns:
            Duration in milliseconds
        """
        if not self.events:
            return 0
        return self.events[-1].relative_time_ms

    def get_action_durations(self) -> Dict[str, List[int]]:
        """Get durations for each action target.

        Returns:
            Dict of {target: [duration1, duration2, ...]}
        """
        durations: Dict[str, List[int]] = {}

        for event in self.events:
            if event.action_target and event.duration_ms:
                if event.action_target not in durations:
                    durations[event.action_target] = []
                durations[event.action_target].append(event.duration_ms)

        return durations

    def get_statistics(self) -> Dict[str, Any]:
        """Get timeline statistics.

        Returns:
            Dict with stats (total events, success rate, duration, etc.)
        """
        total_events = len(self.events)
        success_events = [e for e in self.events if e.success is True]
        failed_events = [e for e in self.events if e.success is False]

        action_started = len(self.get_events_by_type(TimelineEventType.ACTION_STARTED))
        action_completed = len(self.get_events_by_type(TimelineEventType.ACTION_COMPLETED))
        action_failed = len(self.get_events_by_type(TimelineEventType.ACTION_FAILED))
        action_retrying = len(self.get_events_by_type(TimelineEventType.ACTION_RETRYING))

        return {
            "total_events": total_events,
            "total_duration_ms": self.get_total_duration_ms(),
            "success_count": len(success_events),
            "failed_count": len(failed_events),
            "success_rate": len(success_events) / total_events if total_events > 0 else 0.0,
            "actions": {
                "started": action_started,
                "completed": action_completed,
                "failed": action_failed,
                "retrying": action_retrying,
            },
        }

    def print_summary(self) -> None:
        """Print timeline summary to console."""
        stats = self.get_statistics()

        print("\n" + "=" * 70)
        print("TIMELINE SUMMARY")
        print("=" * 70)
        print(f"  Total events: {stats['total_events']}")
        print(f"  Total duration: {stats['total_duration_ms']}ms")
        print(f"  Success count: {stats['success_count']}")
        print(f"  Failed count: {stats['failed_count']}")
        print(f"  Success rate: {stats['success_rate']:.2%}")
        print("\n  Actions:")
        print(f"    Started: {stats['actions']['started']}")
        print(f"    Completed: {stats['actions']['completed']}")
        print(f"    Failed: {stats['actions']['failed']}")
        print(f"    Retrying: {stats['actions']['retrying']}")
        print("=" * 70)

    def print_timeline(self, max_events: Optional[int] = None) -> None:
        """Print timeline events to console.

        Args:
            max_events: Maximum events to print (None = all)
        """
        print("\n" + "=" * 70)
        print("EXECUTION TIMELINE")
        print("=" * 70)

        events_to_print = self.events[:max_events] if max_events else self.events

        for event in events_to_print:
            print(event.to_console_log())

        if max_events and len(self.events) > max_events:
            print(f"  ... ({len(self.events) - max_events} more events)")

        print("=" * 70)

    def save(self, file_path: Path) -> None:
        """Save timeline to JSON file.

        Args:
            file_path: Path to save timeline
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "total_duration_ms": self.get_total_duration_ms(),
            "statistics": self.get_statistics(),
            "events": [e.model_dump() for e in self.events],
        }

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls, file_path: Path) -> "ExecutionTimeline":
        """Load timeline from JSON file.

        Args:
            file_path: Path to timeline file

        Returns:
            ExecutionTimeline instance
        """
        with open(file_path) as f:
            data = json.load(f)

        timeline = cls()
        timeline.start_time = (
            datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None
        )

        for event_data in data.get("events", []):
            event = TimelineEvent(**event_data)
            timeline.events.append(event)

        return timeline

    def export_to_html(self, output_path: Path) -> None:
        """Export timeline as interactive HTML visualization.

        Args:
            output_path: Path to save HTML file
        """
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Execution Timeline</title>
    <style>
        body {{
            font-family: 'Monaco', 'Menlo', monospace;
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            margin: 0;
        }}
        .header {{
            border-bottom: 2px solid #444;
            padding-bottom: 20px;
            margin-bottom: 20px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #2d2d2d;
            border: 1px solid #444;
            padding: 15px;
            border-radius: 5px;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #4ec9b0;
        }}
        .stat-label {{
            color: #858585;
            font-size: 14px;
        }}
        .timeline {{
            background: #2d2d2d;
            border: 1px solid #444;
            padding: 20px;
            border-radius: 5px;
        }}
        .event {{
            padding: 10px;
            margin: 5px 0;
            border-left: 3px solid #444;
            padding-left: 15px;
        }}
        .event.success {{
            border-left-color: #4ec9b0;
        }}
        .event.failed {{
            border-left-color: #f48771;
        }}
        .event-time {{
            color: #858585;
            font-size: 12px;
        }}
        .event-type {{
            color: #dcdcaa;
            font-weight: bold;
        }}
        .event-target {{
            color: #4fc1ff;
        }}
        .event-message {{
            color: #ce9178;
            margin-top: 5px;
        }}
        .event-metadata {{
            color: #858585;
            font-size: 11px;
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Execution Timeline</h1>
        <p>Total Duration: {self.get_total_duration_ms()}ms</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{len(self.events)}</div>
            <div class="stat-label">Total Events</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{len([e for e in self.events if e.success is True])}</div>
            <div class="stat-label">Successful</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{len([e for e in self.events if e.success is False])}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{self.get_total_duration_ms()}ms</div>
            <div class="stat-label">Duration</div>
        </div>
    </div>

    <div class="timeline">
"""

        for event in self.events:
            status_class = ""
            if event.success is True:
                status_class = "success"
            elif event.success is False:
                status_class = "failed"

            html_content += f"""
        <div class="event {status_class}">
            <div class="event-time">
                [{event.relative_time_ms:>6}ms] {event.timestamp.strftime("%H:%M:%S.%f")[:-3]}
            </div>
            <div>
                <span class="event-type">{event.event_type.value}</span>
"""

            if event.action_target:
                html_content += f"""
                <span class="event-target">→ {event.action_target}</span>
"""

            if event.duration_ms:
                html_content += f"""
                <span class="event-metadata">({event.duration_ms}ms)</span>
"""

            if event.message:
                html_content += f"""
            </div>
            <div class="event-message">{event.message}</div>
"""

            if event.metadata:
                metadata_str = json.dumps(event.metadata, indent=2)
                html_content += f"""
            <div class="event-metadata">{metadata_str}</div>
"""

            html_content += """
        </div>
"""

        html_content += """
    </div>
</body>
</html>
"""

        output_path.write_text(html_content)
