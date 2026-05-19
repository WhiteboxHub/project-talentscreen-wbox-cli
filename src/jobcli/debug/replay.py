"""Action replay system for debugging and testing.

Replays recorded actions with detailed logging and inspection.
"""

import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page
from pydantic import BaseModel, Field

from jobcli.execution.actions import ExecutionAction
from jobcli.execution.engine import ExecutionEngine, ExecutionResult, ExecutionStatus
from jobcli.profile.schemas import ATSType

from .snapshot import DOMSnapshot, SnapshotCapture
from .timeline import ExecutionTimeline, TimelineEvent, TimelineEventType


class ReplayMode(str, Enum):
    """Replay execution mode."""

    NORMAL = "normal"  # Execute actions normally
    STEP = "step"  # Pause after each action (interactive)
    FAST = "fast"  # Skip waits, no screenshots
    INSPECT = "inspect"  # Capture maximum debug info


class ReplayStep(BaseModel):
    """A single step in a replay sequence."""

    step_number: int
    action: ExecutionAction
    before_snapshot: Optional[DOMSnapshot] = None
    after_snapshot: Optional[DOMSnapshot] = None
    result: Optional[ExecutionResult] = None
    timeline_events: List[TimelineEvent] = Field(default_factory=list)
    duration_ms: int = 0


class ReplaySession(BaseModel):
    """A complete replay session with all steps and debug info."""

    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    mode: ReplayMode
    ats_type: ATSType

    # Actions and results
    steps: List[ReplayStep] = Field(default_factory=list)
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0

    # Timeline
    timeline: ExecutionTimeline = Field(default_factory=ExecutionTimeline)

    # Snapshots directory
    snapshots_dir: Optional[str] = None

    def add_step(self, step: ReplayStep) -> None:
        """Add a replay step."""
        self.steps.append(step)
        self.total_actions += 1

        if step.result:
            if step.result.status == ExecutionStatus.SUCCESS:
                self.successful_actions += 1
            elif step.result.status == ExecutionStatus.FAILED:
                self.failed_actions += 1

    def finalize(self) -> None:
        """Finalize session (set end time)."""
        self.end_time = datetime.utcnow()

    def get_success_rate(self) -> float:
        """Get overall success rate."""
        if self.total_actions == 0:
            return 0.0
        return self.successful_actions / self.total_actions

    def get_failed_steps(self) -> List[ReplayStep]:
        """Get all failed steps."""
        return [step for step in self.steps if step.result and step.result.status == ExecutionStatus.FAILED]

    def save(self, directory: Path) -> Path:
        """Save replay session to directory.

        Args:
            directory: Directory to save session

        Returns:
            Path to saved session file
        """
        directory.mkdir(parents=True, exist_ok=True)

        # Save session JSON
        session_file = directory / f"replay_{self.session_id}.json"
        with open(session_file, "w") as f:
            import json

            json.dump(self.model_dump(), f, indent=2, default=str)

        # Save timeline
        timeline_file = directory / f"timeline_{self.session_id}.json"
        self.timeline.save(timeline_file)

        # Snapshots are already saved in snapshots_dir
        return session_file


class ActionReplayer:
    """Replay actions with comprehensive debugging."""

    def __init__(
        self,
        page: Page,
        ats_type: ATSType,
        mode: ReplayMode = ReplayMode.NORMAL,
        snapshots_dir: Optional[Path] = None,
    ):
        """Initialize replayer.

        Args:
            page: Playwright Page instance
            ats_type: ATS platform type
            mode: Replay mode
            snapshots_dir: Directory to save snapshots (auto-created if None)
        """
        self.page = page
        self.ats_type = ats_type
        self.mode = mode

        # Setup snapshots directory
        if snapshots_dir is None:
            snapshots_dir = Path("debug_snapshots") / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.snapshots_dir = snapshots_dir
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.snapshot_capture = SnapshotCapture(page)
        self.timeline = ExecutionTimeline()
        self.engine = ExecutionEngine(
            page=page,
            ats_type=ats_type,
            session_id=f"replay_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        )

        # Session
        self.session = ReplaySession(
            session_id=self.engine.session_id,
            start_time=datetime.utcnow(),
            mode=mode,
            ats_type=ats_type,
            snapshots_dir=str(self.snapshots_dir),
        )

    def replay_action(
        self,
        action: ExecutionAction,
        step_number: int,
        pause_after: bool = False,
    ) -> ReplayStep:
        """Replay a single action with full debugging.

        Args:
            action: Action to execute
            step_number: Step number in sequence
            pause_after: Pause after execution (for interactive mode)

        Returns:
            ReplayStep with results and debug info
        """
        step_start_time = time.time()

        # Log step start
        print(f"\n{'=' * 70}")
        print(f"STEP {step_number}: {action.action.value} → {action.target}")
        print(f"  Selector: {action.selector}")
        print(f"{'=' * 70}")

        # Timeline: step started
        self.timeline.add_event(
            TimelineEventType.ACTION_STARTED,
            action_target=action.target,
            metadata={
                "step_number": step_number,
                "action_type": action.action.value,
                "selector": action.selector,
            },
        )

        # Capture before snapshot
        before_snapshot = None
        if self.mode in [ReplayMode.NORMAL, ReplayMode.INSPECT]:
            print("  Capturing before snapshot...")
            before_snapshot = self.snapshot_capture.capture_before_action(
                action.target, action.selector
            )
            before_snapshot.save(self.snapshots_dir)

        # Execute action
        print(f"  Executing action...")
        result = self.engine.execute(action)

        # Log result
        if result.status == ExecutionStatus.SUCCESS:
            print(f"  ✓ SUCCESS (attempts={result.attempts}, duration={result.duration_ms}ms)")
            if result.verified:
                print(f"    Verified value: {result.verified_value}")
        else:
            print(f"  ✗ FAILED (attempts={result.attempts}, duration={result.duration_ms}ms)")
            print(f"    Error: {result.error}")

        # Timeline: step completed
        self.timeline.add_event(
            TimelineEventType.ACTION_COMPLETED
            if result.status == ExecutionStatus.SUCCESS
            else TimelineEventType.ACTION_FAILED,
            action_target=action.target,
            success=result.status == ExecutionStatus.SUCCESS,
            duration_ms=result.duration_ms,
            metadata={
                "attempts": result.attempts,
                "verified": result.verified,
                "error": result.error,
            },
        )

        # Capture after snapshot
        after_snapshot = None
        if self.mode in [ReplayMode.NORMAL, ReplayMode.INSPECT]:
            print("  Capturing after snapshot...")
            after_snapshot = self.snapshot_capture.capture_after_action(
                action.target, action.selector
            )
            after_snapshot.save(self.snapshots_dir)

        # Capture failure snapshot
        if result.status == ExecutionStatus.FAILED and self.mode == ReplayMode.INSPECT:
            print("  Capturing failure snapshot...")
            failure_snapshot = self.snapshot_capture.capture_failure(
                action.target, action.selector, result.error or "Unknown error"
            )
            failure_snapshot.save(self.snapshots_dir)

        # Calculate step duration
        step_duration_ms = int((time.time() - step_start_time) * 1000)

        # Create replay step
        step = ReplayStep(
            step_number=step_number,
            action=action,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            result=result,
            duration_ms=step_duration_ms,
        )

        # Add to session
        self.session.add_step(step)

        # Pause if requested (interactive mode)
        if pause_after or self.mode == ReplayMode.STEP:
            input("\n  Press Enter to continue...")

        return step

    def replay_sequence(
        self,
        actions: List[ExecutionAction],
        stop_on_failure: bool = True,
    ) -> ReplaySession:
        """Replay a sequence of actions.

        Args:
            actions: List of actions to replay
            stop_on_failure: Stop on first failure?

        Returns:
            ReplaySession with all results
        """
        print(f"\n{'=' * 70}")
        print(f"REPLAY SESSION: {self.session.session_id}")
        print(f"  Mode: {self.mode.value}")
        print(f"  ATS: {self.ats_type.value}")
        print(f"  Actions: {len(actions)}")
        print(f"  Snapshots: {self.snapshots_dir}")
        print(f"{'=' * 70}")

        # Timeline: session started
        self.timeline.add_event(
            TimelineEventType.SESSION_STARTED,
            metadata={
                "total_actions": len(actions),
                "mode": self.mode.value,
                "ats_type": self.ats_type.value,
            },
        )

        # Replay each action
        for i, action in enumerate(actions, start=1):
            step = self.replay_action(action, step_number=i)

            # Stop on failure if requested
            if (
                stop_on_failure
                and step.result
                and step.result.status == ExecutionStatus.FAILED
            ):
                print(f"\n  ⚠ Stopping on failure at step {i}")
                break

        # Finalize session
        self.session.finalize()
        self.session.timeline = self.timeline

        # Timeline: session ended
        self.timeline.add_event(
            TimelineEventType.SESSION_ENDED,
            metadata={
                "total_actions": self.session.total_actions,
                "successful": self.session.successful_actions,
                "failed": self.session.failed_actions,
                "success_rate": self.session.get_success_rate(),
            },
        )

        # Print summary
        print(f"\n{'=' * 70}")
        print(f"REPLAY SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Total actions: {self.session.total_actions}")
        print(f"  Successful: {self.session.successful_actions}")
        print(f"  Failed: {self.session.failed_actions}")
        print(f"  Success rate: {self.session.get_success_rate():.2%}")
        print(f"  Duration: {self.timeline.get_total_duration_ms()}ms")
        print(f"  Snapshots: {self.snapshots_dir}")
        print(f"{'=' * 70}")

        # Save session
        session_file = self.session.save(self.snapshots_dir.parent)
        print(f"\n  Session saved: {session_file}")

        return self.session

    def inspect_failure(self, step: ReplayStep) -> Dict[str, Any]:
        """Inspect a failed step in detail.

        Args:
            step: Failed replay step

        Returns:
            Inspection report with debug information
        """
        report: Dict[str, Any] = {
            "step_number": step.step_number,
            "action": step.action.action.value,
            "target": step.action.target,
            "selector": step.action.selector,
            "error": step.result.error if step.result else "Unknown",
            "attempts": step.result.attempts if step.result else 0,
        }

        # Before state
        if step.before_snapshot:
            before_element = step.before_snapshot.elements.get(step.action.target)
            if before_element:
                report["before_state"] = {
                    "exists": before_element.exists,
                    "visible": before_element.visible,
                    "enabled": before_element.enabled,
                    "value": before_element.value,
                    "position": f"({before_element.x}, {before_element.y})",
                    "size": f"{before_element.width}x{before_element.height}",
                }
            else:
                report["before_state"] = {"exists": False}

        # After state
        if step.after_snapshot:
            after_element = step.after_snapshot.elements.get(step.action.target)
            if after_element:
                report["after_state"] = {
                    "exists": after_element.exists,
                    "visible": after_element.visible,
                    "enabled": after_element.enabled,
                    "value": after_element.value,
                }
            else:
                report["after_state"] = {"exists": False}

        # Diagnose issue
        diagnosis = []

        if report.get("before_state", {}).get("exists") is False:
            diagnosis.append("Element not found with selector")

        if report.get("before_state", {}).get("visible") is False:
            diagnosis.append("Element exists but not visible")

        if report.get("before_state", {}).get("enabled") is False:
            diagnosis.append("Element visible but not enabled")

        before_value = report.get("before_state", {}).get("value")
        after_value = report.get("after_state", {}).get("value")
        if before_value == after_value and step.action.action.value == "fill_input":
            diagnosis.append("Value did not change after fill")

        report["diagnosis"] = diagnosis

        return report


def quick_replay(
    page: Page,
    actions: List[ExecutionAction],
    ats_type: ATSType,
    mode: ReplayMode = ReplayMode.NORMAL,
) -> ReplaySession:
    """Quick replay helper function.

    Args:
        page: Playwright Page
        actions: Actions to replay
        ats_type: ATS type
        mode: Replay mode

    Returns:
        ReplaySession
    """
    replayer = ActionReplayer(page, ats_type, mode)
    return replayer.replay_sequence(actions)
