"""Replay and debugging system for JobCLI.

Complete debugging toolkit with:
- DOM snapshot capture (before/after/failure)
- Action replay with step-through
- Execution timeline tracking
- Field overlay visualization
- AI reasoning inspection
- Failure diagnosis and analysis
"""

from .ai_inspector import AIInspector, AIReasoning, AITaskType, get_ai_inspector
from .failure_inspector import FailureContext, FailureInspector, get_failure_inspector
from .overlay import FieldOverlay, OverlayDebugger, create_overlay_from_canonical
from .replay import ActionReplayer, ReplayMode, ReplaySession, ReplayStep, quick_replay
from .snapshot import DOMSnapshot, ElementSnapshot, SnapshotCapture
from .timeline import (
    ExecutionTimeline,
    TimelineEvent,
    TimelineEventType,
)

__all__ = [
    # Snapshot
    "DOMSnapshot",
    "ElementSnapshot",
    "SnapshotCapture",
    # Replay
    "ActionReplayer",
    "ReplayMode",
    "ReplaySession",
    "ReplayStep",
    "quick_replay",
    # Timeline
    "ExecutionTimeline",
    "TimelineEvent",
    "TimelineEventType",
    # Overlay
    "OverlayDebugger",
    "FieldOverlay",
    "create_overlay_from_canonical",
    # AI Inspector
    "AIInspector",
    "AIReasoning",
    "AITaskType",
    "get_ai_inspector",
    # Failure Inspector
    "FailureInspector",
    "FailureContext",
    "get_failure_inspector",
]
