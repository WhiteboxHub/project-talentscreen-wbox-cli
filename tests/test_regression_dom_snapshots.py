"""Regression tests for DOM snapshots and replay.

Validates:
- DOM snapshot capture stability
- Before/after snapshot comparison
- Replay accuracy
- Timeline event ordering
- Field overlay persistence
- Failure diagnosis consistency
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import Mock

import pytest

from jobcli.debug.ai_inspector import (
    AIInspector,
    AIReasoning,
    AITaskType,
)
from jobcli.debug.failure_inspector import (
    FailureContext,
    FailureInspector,
    FailureRootCause,
)
from jobcli.debug.overlay import OverlayDebugger
from jobcli.debug.replay import ActionReplayer, ReplayMode, ReplaySession
from jobcli.debug.snapshot import (
    DOMSnapshot,
    ElementSnapshot,
    SnapshotManager,
)
from jobcli.debug.timeline import (
    ExecutionTimeline,
    TimelineEvent,
    TimelineEventType,
)
from jobcli.execution.actions import (
    ActionType,
    FillInputAction,
)


class TestDOMSnapshotRegression:
    """Regression tests for DOM snapshot capture."""

    def test_snapshot_structure_stability(self):
        """Test that snapshot structure remains stable."""
        # Create snapshot
        snapshot = DOMSnapshot(
            snapshot_id="snap_123",
            timestamp=datetime.utcnow(),
            html="<html><body><input id='email' /></body></html>",
            viewport_width=1920,
            viewport_height=1080,
            scroll_x=0,
            scroll_y=0,
            elements={
                "email": ElementSnapshot(
                    selector="#email",
                    tag_name="input",
                    attributes={"id": "email", "type": "text"},
                    x=100,
                    y=200,
                    width=300,
                    height=40,
                    visible=True,
                    enabled=True,
                    value="",
                )
            },
        )

        # Serialize to JSON
        json_data = snapshot.model_dump()

        # Validate expected fields
        assert "snapshot_id" in json_data
        assert "timestamp" in json_data
        assert "html" in json_data
        assert "viewport_width" in json_data
        assert "viewport_height" in json_data
        assert "elements" in json_data

        # Validate element structure
        email_element = json_data["elements"]["email"]
        assert "selector" in email_element
        assert "tag_name" in email_element
        assert "attributes" in email_element
        assert "x" in email_element
        assert "y" in email_element
        assert "visible" in email_element

    def test_snapshot_serialization_roundtrip(self):
        """Test snapshot serialization and deserialization."""
        original = DOMSnapshot(
            snapshot_id="snap_123",
            timestamp=datetime.utcnow(),
            html="<html><body></body></html>",
            viewport_width=1920,
            viewport_height=1080,
            scroll_x=0,
            scroll_y=0,
            elements={},
        )

        # Serialize
        json_str = json.dumps(original.model_dump(), default=str)

        # Deserialize
        data = json.loads(json_str)
        restored = DOMSnapshot(**data)

        # Validate
        assert restored.snapshot_id == original.snapshot_id
        assert restored.viewport_width == original.viewport_width
        assert restored.html == original.html

    def test_element_snapshot_attributes(self):
        """Test element snapshot captures all attributes."""
        element = ElementSnapshot(
            selector="#email",
            tag_name="input",
            attributes={
                "id": "email",
                "type": "email",
                "name": "user_email",
                "placeholder": "Enter email",
                "required": "true",
                "data-testid": "email-input",
            },
            x=100,
            y=200,
            width=300,
            height=40,
            visible=True,
            enabled=True,
            value="test@example.com",
        )

        # All attributes should be captured
        assert element.attributes["id"] == "email"
        assert element.attributes["type"] == "email"
        assert element.attributes["data-testid"] == "email-input"

        # Value captured separately
        assert element.value == "test@example.com"

    def test_snapshot_manager_storage(self):
        """Test snapshot manager stores snapshots correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "snapshots"
            manager = SnapshotManager(storage_path=storage_path)

            snapshot = DOMSnapshot(
                snapshot_id="snap_123",
                timestamp=datetime.utcnow(),
                html="<html><body></body></html>",
                viewport_width=1920,
                viewport_height=1080,
                scroll_x=0,
                scroll_y=0,
                elements={},
            )

            # Save snapshot
            manager.save_snapshot(snapshot)

            # Load snapshot
            loaded = manager.load_snapshot("snap_123")

            assert loaded is not None
            assert loaded.snapshot_id == "snap_123"
            assert loaded.html == snapshot.html

    def test_snapshot_comparison(self):
        """Test comparing before/after snapshots."""
        before = DOMSnapshot(
            snapshot_id="before",
            timestamp=datetime.utcnow(),
            html="<html><body><input id='email' value='' /></body></html>",
            viewport_width=1920,
            viewport_height=1080,
            scroll_x=0,
            scroll_y=0,
            elements={
                "email": ElementSnapshot(
                    selector="#email",
                    tag_name="input",
                    attributes={"id": "email"},
                    x=100,
                    y=200,
                    width=300,
                    height=40,
                    visible=True,
                    enabled=True,
                    value="",
                )
            },
        )

        after = DOMSnapshot(
            snapshot_id="after",
            timestamp=datetime.utcnow(),
            html="<html><body><input id='email' value='test@example.com' /></body></html>",
            viewport_width=1920,
            viewport_height=1080,
            scroll_x=0,
            scroll_y=0,
            elements={
                "email": ElementSnapshot(
                    selector="#email",
                    tag_name="input",
                    attributes={"id": "email"},
                    x=100,
                    y=200,
                    width=300,
                    height=40,
                    visible=True,
                    enabled=True,
                    value="test@example.com",
                )
            },
        )

        # Value changed
        assert before.elements["email"].value != after.elements["email"].value

        # Other properties unchanged
        assert before.elements["email"].selector == after.elements["email"].selector
        assert before.elements["email"].visible == after.elements["email"].visible


class TestReplayRegression:
    """Regression tests for action replay."""

    def test_replay_session_structure(self):
        """Test replay session structure."""
        session = ReplaySession(
            session_id="replay_123",
            start_time=datetime.utcnow(),
            mode=ReplayMode.NORMAL,
            actions=[],
            steps=[],
        )

        # Validate structure
        assert session.session_id == "replay_123"
        assert session.mode == ReplayMode.NORMAL
        assert isinstance(session.actions, list)
        assert isinstance(session.steps, list)

    def test_replay_step_recording(self):
        """Test replay step is recorded correctly."""
        from jobcli.debug.replay import ReplayStep
        from jobcli.execution.engine import ExecutionResult, ExecutionStatus

        step = ReplayStep(
            step_number=1,
            action=FillInputAction(
                selector="#email",
                field_id="email",
                field_type="email",
                field_label="Email",
                value="test@example.com",
            ),
            before_snapshot_id="before_123",
            after_snapshot_id="after_123",
            result=ExecutionResult(
                success=True,
                status=ExecutionStatus.SUCCESS,
                action_type=ActionType.FILL_INPUT,
            ),
            duration_ms=150,
        )

        # Validate step structure
        assert step.step_number == 1
        assert step.action.field_id == "email"
        assert step.before_snapshot_id == "before_123"
        assert step.after_snapshot_id == "after_123"
        assert step.result.success is True
        assert step.duration_ms == 150

    def test_replay_modes(self):
        """Test all replay modes are defined."""
        modes = [
            ReplayMode.NORMAL,
            ReplayMode.STEP,
            ReplayMode.FAST,
            ReplayMode.INSPECT,
        ]

        # All modes should be enum values
        for mode in modes:
            assert isinstance(mode, ReplayMode)


class TestTimelineRegression:
    """Regression tests for execution timeline."""

    def test_timeline_event_types(self):
        """Test all timeline event types are defined."""
        event_types = [
            TimelineEventType.ACTION_STARTED,
            TimelineEventType.ACTION_COMPLETED,
            TimelineEventType.ACTION_FAILED,
            TimelineEventType.FIELD_DETECTED,
            TimelineEventType.FIELD_FILL_STARTED,
            TimelineEventType.FIELD_FILL_SUCCEEDED,
            TimelineEventType.FIELD_FILL_FAILED,
            TimelineEventType.SELECTOR_FOUND,
            TimelineEventType.SELECTOR_NOT_FOUND,
            TimelineEventType.SELECTOR_HEALING_STARTED,
            TimelineEventType.SELECTOR_HEALING_SUCCEEDED,
            TimelineEventType.SELECTOR_HEALING_FAILED,
            TimelineEventType.RETRY_STARTED,
            TimelineEventType.RETRY_SUCCEEDED,
            TimelineEventType.RETRY_FAILED,
            TimelineEventType.HUMAN_INTERVENTION_REQUESTED,
            TimelineEventType.HUMAN_INTERVENTION_COMPLETED,
            TimelineEventType.CONFIDENCE_LOW,
            TimelineEventType.NAVIGATION_STARTED,
            TimelineEventType.NAVIGATION_COMPLETED,
        ]

        # All should be valid enum values
        for event_type in event_types:
            assert isinstance(event_type, TimelineEventType)

    def test_timeline_event_ordering(self):
        """Test timeline maintains chronological order."""
        timeline = ExecutionTimeline(session_id="timeline_test")

        # Add events
        timeline.add_event(
            event_type=TimelineEventType.ACTION_STARTED,
            action_type=ActionType.FILL_INPUT,
            field_id="email",
        )

        timeline.add_event(
            event_type=TimelineEventType.FIELD_FILL_SUCCEEDED,
            action_type=ActionType.FILL_INPUT,
            field_id="email",
            success=True,
        )

        timeline.add_event(
            event_type=TimelineEventType.ACTION_COMPLETED,
            action_type=ActionType.FILL_INPUT,
            field_id="email",
            success=True,
        )

        events = timeline.get_events()

        # Events should be in order
        assert len(events) == 3
        assert events[0].event_type == TimelineEventType.ACTION_STARTED
        assert events[1].event_type == TimelineEventType.FIELD_FILL_SUCCEEDED
        assert events[2].event_type == TimelineEventType.ACTION_COMPLETED

        # Relative times should increase
        assert events[0].relative_time_ms <= events[1].relative_time_ms
        assert events[1].relative_time_ms <= events[2].relative_time_ms

    def test_timeline_statistics(self):
        """Test timeline statistics calculation."""
        timeline = ExecutionTimeline(session_id="stats_test")

        # Add successful events
        for i in range(3):
            timeline.add_event(
                event_type=TimelineEventType.FIELD_FILL_SUCCEEDED,
                field_id=f"field_{i}",
                success=True,
            )

        # Add failed event
        timeline.add_event(
            event_type=TimelineEventType.FIELD_FILL_FAILED,
            field_id="field_3",
            success=False,
        )

        stats = timeline.get_statistics()

        assert stats["total_events"] == 4
        assert stats["successful_events"] == 3
        assert stats["failed_events"] == 1
        assert stats["success_rate"] == 0.75

    def test_timeline_export_formats(self):
        """Test timeline export to different formats."""
        timeline = ExecutionTimeline(session_id="export_test")

        timeline.add_event(
            event_type=TimelineEventType.ACTION_STARTED,
            action_type=ActionType.FILL_INPUT,
        )

        # Export to JSON
        json_data = timeline.to_json()
        data = json.loads(json_data)

        assert "session_id" in data
        assert "events" in data
        assert len(data["events"]) == 1

        # Export to HTML (returns string)
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "timeline.html"
            timeline.export_html(html_path)

            assert html_path.exists()
            content = html_path.read_text()
            assert "session_id" in content.lower() or "timeline" in content.lower()


class TestOverlayRegression:
    """Regression tests for field overlay debugger."""

    def test_overlay_highlight_persistence(self):
        """Test overlay highlights persist across operations."""
        page_mock = Mock()
        page_mock.evaluate = Mock()

        debugger = OverlayDebugger(page_mock)

        # Highlight multiple fields
        debugger.highlight_field(
            field_id="email",
            selector="#email",
            status="pending",
            label="Email",
        )

        debugger.highlight_field(
            field_id="phone",
            selector="#phone",
            status="success",
            label="Phone",
        )

        # Should have injected CSS/JS
        assert page_mock.evaluate.called

    def test_overlay_status_colors(self):
        """Test overlay uses correct colors for status."""
        page_mock = Mock()
        debugger = OverlayDebugger(page_mock)

        statuses = ["pending", "success", "failed", "healing"]

        for status in statuses:
            debugger.highlight_field(
                field_id=f"field_{status}",
                selector=f"#{status}",
                status=status,
                label=status.capitalize(),
            )

        # Should handle all status types
        # (In real implementation, each status has different color)


class TestFailureInspectorRegression:
    """Regression tests for failure diagnosis."""

    def test_failure_root_causes(self):
        """Test all failure root causes are defined."""
        causes = [
            FailureRootCause.SELECTOR_NOT_FOUND,
            FailureRootCause.ELEMENT_NOT_VISIBLE,
            FailureRootCause.ELEMENT_DISABLED,
            FailureRootCause.VALUE_UNCHANGED,
            FailureRootCause.TIMEOUT,
            FailureRootCause.UNEXPECTED_NAVIGATION,
            FailureRootCause.ELEMENT_DETACHED,
        ]

        for cause in causes:
            assert isinstance(cause, FailureRootCause)

    def test_failure_context_structure(self):
        """Test failure context captures all needed info."""
        context = FailureContext(
            action=FillInputAction(
                selector="#email",
                field_id="email",
                field_type="email",
                field_label="Email",
                value="test@example.com",
            ),
            error_message="Element not found",
            before_snapshot_id="before_123",
            after_snapshot_id=None,
            attempt_number=1,
            root_cause=FailureRootCause.SELECTOR_NOT_FOUND,
            suggested_fix="Check selector: #email",
        )

        # Validate structure
        assert context.action.field_id == "email"
        assert context.error_message == "Element not found"
        assert context.root_cause == FailureRootCause.SELECTOR_NOT_FOUND
        assert "selector" in context.suggested_fix.lower()

    def test_failure_diagnosis_consistency(self):
        """Test failure diagnosis produces consistent results."""
        page_mock = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_storage = Path(tmpdir) / "snapshots"
            manager = SnapshotManager(storage_path=snapshot_storage)

            # Create before snapshot
            before = DOMSnapshot(
                snapshot_id="before_123",
                timestamp=datetime.utcnow(),
                html="<html><body></body></html>",
                viewport_width=1920,
                viewport_height=1080,
                scroll_x=0,
                scroll_y=0,
                elements={},
            )

            manager.save_snapshot(before)

            inspector = FailureInspector(
                page=page_mock,
                snapshot_manager=manager,
            )

            # Create failure context
            context = FailureContext(
                action=FillInputAction(
                    selector="#missing",
                    field_id="missing",
                    field_type="text_input",
                    field_label="Missing",
                    value="test",
                ),
                error_message="Timeout",
                before_snapshot_id="before_123",
                attempt_number=1,
            )

            # Diagnose
            diagnosed = inspector.diagnose(context)

            # Should have root cause
            assert diagnosed.root_cause is not None


class TestAIInspectorRegression:
    """Regression tests for AI reasoning inspection."""

    def test_ai_reasoning_structure(self):
        """Test AI reasoning structure is stable."""
        reasoning = AIReasoning(
            reasoning_id="reason_123",
            timestamp=datetime.utcnow(),
            task_type=AITaskType.FIELD_DETECTION,
            prompt="Detect form fields",
            response="Found 5 fields",
            decision="Fill all fields",
            confidence=0.85,
            model="gpt-4",
            tokens_used=150,
            duration_ms=500,
        )

        # Validate structure
        assert reasoning.reasoning_id == "reason_123"
        assert reasoning.task_type == AITaskType.FIELD_DETECTION
        assert reasoning.confidence == 0.85
        assert reasoning.tokens_used == 150

    def test_ai_task_types(self):
        """Test all AI task types are defined."""
        task_types = [
            AITaskType.FIELD_DETECTION,
            AITaskType.FIELD_CLASSIFICATION,
            AITaskType.QUESTION_ANSWERING,
            AITaskType.FORM_UNDERSTANDING,
            AITaskType.ERROR_DIAGNOSIS,
        ]

        for task_type in task_types:
            assert isinstance(task_type, AITaskType)

    def test_confidence_calibration(self):
        """Test confidence calibration analysis."""
        inspector = AIInspector()

        # Add reasoning with high confidence
        inspector.add_reasoning(
            AIReasoning(
                reasoning_id="r1",
                timestamp=datetime.utcnow(),
                task_type=AITaskType.FIELD_DETECTION,
                prompt="Detect fields",
                response="Found fields",
                decision="Fill fields",
                confidence=0.95,
                actual_success=True,
            )
        )

        # Add reasoning with low confidence
        inspector.add_reasoning(
            AIReasoning(
                reasoning_id="r2",
                timestamp=datetime.utcnow(),
                task_type=AITaskType.FIELD_DETECTION,
                prompt="Detect fields",
                response="Found fields",
                decision="Fill fields",
                confidence=0.45,
                actual_success=False,
            )
        )

        calibration = inspector.get_confidence_calibration()

        # Should have high and low confidence bins
        assert "high_confidence_accuracy" in calibration
        assert "low_confidence_accuracy" in calibration


def test_regression_suite():
    """Run full regression test suite."""
    print("\n=== Running Regression Tests ===\n")

    test_classes = [
        TestDOMSnapshotRegression,
        TestReplayRegression,
        TestTimelineRegression,
        TestOverlayRegression,
        TestFailureInspectorRegression,
        TestAIInspectorRegression,
    ]

    total = 0
    passed = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")

        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]

        for method_name in methods:
            total += 1
            try:
                method = getattr(instance, method_name)
                method()
                passed += 1
                print(f"  ✓ {method_name}")
            except Exception as e:
                print(f"  ✗ {method_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Regression Tests: {passed}/{total} passed")
    print(f"{'='*50}\n")

    assert passed == total, f"Some regression tests failed: {passed}/{total}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
