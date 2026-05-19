#!/usr/bin/env python3
"""
Debug System Demo

Comprehensive demonstration of the replay and debugging system.

Usage:
    python examples/debug_system_demo.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from playwright.sync_api import sync_playwright

from jobcli.debug import (
    ActionReplayer,
    AITaskType,
    ExecutionTimeline,
    OverlayDebugger,
    FieldOverlay,
    ReplayMode,
    SnapshotCapture,
    TimelineEventType,
    get_ai_inspector,
    get_failure_inspector,
)
from jobcli.execution import (
    ClickAction,
    ExecutionEngine,
    FillInputAction,
    SelectOptionAction,
)
from jobcli.profile.schemas import ATSType


def demo_snapshot_capture():
    """Demo 1: DOM Snapshot Capture"""
    print("\n" + "=" * 70)
    print("DEMO 1: DOM Snapshot Capture")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        # Initialize snapshot capture
        capture = SnapshotCapture(page)

        # Capture before filling
        print("\nCapturing before snapshot...")
        before_snapshot = capture.capture_before_action(
            action_target="first_name",
            action_selector="input[name='fname']",
        )

        print(f"  Snapshot ID: {before_snapshot.snapshot_id}")
        print(f"  URL: {before_snapshot.url}")
        print(f"  Inputs: {before_snapshot.input_count}")
        print(f"  Elements captured: {len(before_snapshot.elements)}")

        # Fill the field
        page.fill("input[name='fname']", "John")

        # Capture after filling
        print("\nCapturing after snapshot...")
        after_snapshot = capture.capture_after_action(
            action_target="first_name",
            action_selector="input[name='fname']",
        )

        # Compare before/after
        before_elem = before_snapshot.elements.get("first_name")
        after_elem = after_snapshot.elements.get("first_name")

        if before_elem and after_elem:
            print("\n  Before value:", before_elem.value)
            print("  After value:", after_elem.value)
            print("  Value changed:", before_elem.value != after_elem.value)

        # Save snapshots
        snapshots_dir = Path("debug_snapshots")
        snapshots_dir.mkdir(exist_ok=True)

        before_file = before_snapshot.save(snapshots_dir)
        after_file = after_snapshot.save(snapshots_dir)

        print(f"\n  Snapshots saved:")
        print(f"    Before: {before_file}")
        print(f"    After: {after_file}")

        input("\nPress Enter to continue...")
        browser.close()


def demo_field_overlay():
    """Demo 2: Field Overlay Debugger"""
    print("\n" + "=" * 70)
    print("DEMO 2: Field Overlay Debugger")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        # Initialize overlay
        overlay = OverlayDebugger(page)

        # Highlight all inputs first
        print("\nHighlighting all inputs on page...")
        overlay.highlight_all_inputs()

        input("\nPress Enter to continue...")

        # Clear and highlight specific fields
        overlay.clear_overlays()

        print("\nHighlighting specific fields with status...")

        fields = [
            FieldOverlay(
                field_id="first_name",
                selector="input[name='fname']",
                semantic_type="first_name",
                confidence=0.95,
                required=True,
                status="pending",
            ),
            FieldOverlay(
                field_id="last_name",
                selector="input[name='lname']",
                semantic_type="last_name",
                confidence=0.92,
                required=True,
                status="pending",
            ),
        ]

        for field in fields:
            overlay.highlight_field(
                field_id=field.field_id,
                selector=field.selector,
                status=field.status,
                label=f"{field.field_id} ({field.confidence:.0%})",
            )

        # Show panel
        overlay.show_fields_panel(fields)

        input("\nPress Enter to fill fields...")

        # Fill first field
        page.fill("input[name='fname']", "John")
        overlay.update_field_status("first_name", "success", "first_name (0.95) ✓")

        # Update panel
        fields[0].status = "success"
        overlay.show_fields_panel(fields)

        input("\nPress Enter to fill second field...")

        # Fill second field
        page.fill("input[name='lname']", "Doe")
        overlay.update_field_status("last_name", "success", "last_name (0.92) ✓")

        # Update panel
        fields[1].status = "success"
        overlay.show_fields_panel(fields)

        input("\nPress Enter to close...")
        browser.close()


def demo_execution_timeline():
    """Demo 3: Execution Timeline"""
    print("\n" + "=" * 70)
    print("DEMO 3: Execution Timeline")
    print("=" * 70)

    # Create timeline
    timeline = ExecutionTimeline()

    print("\nRecording events...")

    # Simulate execution events
    timeline.add_event(
        TimelineEventType.SESSION_STARTED,
        metadata={"total_actions": 3},
    )

    timeline.add_event(
        TimelineEventType.ACTION_STARTED,
        action_target="email",
        metadata={"selector": "input[name='email']"},
    )

    timeline.add_event(
        TimelineEventType.ACTION_COMPLETED,
        action_target="email",
        success=True,
        duration_ms=234,
    )

    timeline.add_event(
        TimelineEventType.ACTION_STARTED,
        action_target="phone",
        metadata={"selector": "input[name='phone']"},
    )

    timeline.add_event(
        TimelineEventType.ACTION_RETRYING,
        action_target="phone",
        metadata={"attempt": 2},
    )

    timeline.add_event(
        TimelineEventType.ACTION_FAILED,
        action_target="phone",
        success=False,
        duration_ms=1543,
        metadata={"error": "Element not found"},
    )

    timeline.add_event(
        TimelineEventType.SESSION_ENDED,
        metadata={"success_rate": 0.5},
    )

    # Print timeline
    timeline.print_timeline()

    # Print summary
    timeline.print_summary()

    # Save timeline
    timeline_file = Path("debug_timeline.json")
    timeline.save(timeline_file)
    print(f"\nTimeline saved: {timeline_file}")

    # Export HTML
    timeline_html = Path("debug_timeline.html")
    timeline.export_to_html(timeline_html)
    print(f"HTML timeline: {timeline_html}")


def demo_ai_inspector():
    """Demo 4: AI Reasoning Inspector"""
    print("\n" + "=" * 70)
    print("DEMO 4: AI Reasoning Inspector")
    print("=" * 70)

    inspector = get_ai_inspector()

    print("\nRecording AI reasoning...")

    # Record field classification
    reasoning1 = inspector.record_reasoning(
        task_type=AITaskType.FIELD_CLASSIFICATION,
        prompt="Classify this field: <input name='email' type='email'>",
        response="This is an email field based on name and type attributes",
        decision="email",
        confidence=0.95,
        model="gpt-4",
        reasoning_steps=[
            "1. Check name attribute: 'email'",
            "2. Check type attribute: 'email'",
            "3. Strong match → email field",
        ],
        tokens_used=150,
        latency_ms=380,
    )

    # Validate it
    inspector.validate_reasoning(
        reasoning1.reasoning_id,
        validation_result="Correctly classified",
        correct=True,
        ground_truth="email",
    )

    # Record another reasoning (selector generation)
    reasoning2 = inspector.record_reasoning(
        task_type=AITaskType.SELECTOR_GENERATION,
        prompt="Generate selector for phone field",
        response="input[name='phone']",
        decision="input[name='phone']",
        confidence=0.78,
        model="gpt-4",
        reasoning_steps=[
            "1. Look for name='phone' attribute",
            "2. Found input with name='phone'",
            "3. Generate selector",
        ],
        tokens_used=120,
        latency_ms=420,
    )

    # Validate it (failed this time)
    inspector.validate_reasoning(
        reasoning2.reasoning_id,
        validation_result="Selector not found on page",
        correct=False,
        ground_truth="input[type='tel']",
    )

    # Record more for calibration demo
    for i in range(10):
        r = inspector.record_reasoning(
            task_type=AITaskType.FIELD_CLASSIFICATION,
            prompt=f"Test field {i}",
            response=f"Decision {i}",
            decision=f"field_{i}",
            confidence=0.85,
            model="gpt-4",
            latency_ms=400,
        )
        inspector.validate_reasoning(
            r.reasoning_id,
            validation_result="Test",
            correct=i % 3 != 0,  # Fail every 3rd
        )

    # Print specific reasoning
    print("\n" + "-" * 70)
    inspector.print_reasoning(reasoning1.reasoning_id)

    # Print reports
    print(inspector.generate_calibration_report())
    print(inspector.generate_task_performance_report())

    # Export
    ai_export = Path("debug_ai_reasonings.json")
    inspector.export_reasonings(ai_export)
    print(f"\nAI reasonings exported: {ai_export}")


def demo_failure_inspection():
    """Demo 5: Failure Inspection"""
    print("\n" + "=" * 70)
    print("DEMO 5: Failure Inspection")
    print("=" * 70)

    failure_inspector = get_failure_inspector()

    print("\nSimulating failure...")

    # Create mock execution result
    from jobcli.execution.engine import ExecutionResult, ExecutionStatus

    result = ExecutionResult(
        status=ExecutionStatus.FAILED,
        action_target="phone",
        attempts=3,
        duration_ms=1543,
        verified=False,
        error="Pre-validation failed: element not found or not visible",
    )

    # Record failure
    failure = failure_inspector.record_failure(
        result=result,
        action_type="fill_input",
        selector="input[name='phone']",
    )

    # Print failure
    failure_inspector.print_failure(failure.failure_id)

    # Print summary
    print(failure_inspector.generate_failure_summary())

    # Export
    failures_json = Path("debug_failures.json")
    failure_inspector.generate_failure_report(failures_json)
    print(f"\nFailures exported: {failures_json}")

    failures_html = Path("debug_failures.html")
    failure_inspector.export_failures_html(failures_html)
    print(f"Failures HTML: {failures_html}")


def demo_action_replay():
    """Demo 6: Action Replay"""
    print("\n" + "=" * 70)
    print("DEMO 6: Action Replay")
    print("=" * 70)

    # Define actions
    actions = [
        FillInputAction(
            target="first_name",
            selector="input[name='fname']",
            value="John",
            verify_after=True,
        ),
        FillInputAction(
            target="last_name",
            selector="input[name='lname']",
            value="Doe",
            verify_after=True,
        ),
        FillInputAction(
            target="nonexistent",
            selector="input[name='does_not_exist']",
            value="test",
            verify_after=True,
            retry_count=1,  # Fail fast for demo
        ),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        # Initialize replayer
        replayer = ActionReplayer(
            page=page,
            ats_type=ATSType.GREENHOUSE,
            mode=ReplayMode.INSPECT,
            snapshots_dir=Path("debug_snapshots_replay"),
        )

        # Replay sequence
        session = replayer.replay_sequence(
            actions,
            stop_on_failure=True,
        )

        # Inspect failed steps
        for step in session.get_failed_steps():
            print("\n" + "=" * 70)
            print("FAILURE INSPECTION")
            print("=" * 70)

            report = replayer.inspect_failure(step)

            print(f"Step: {report['step_number']}")
            print(f"Target: {report['target']}")
            print(f"Selector: {report['selector']}")
            print(f"Error: {report['error']}")
            print(f"Attempts: {report['attempts']}")
            print(f"Diagnosis: {report['diagnosis']}")

        input("\nPress Enter to close...")
        browser.close()


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print(" " * 20 + "DEBUG SYSTEM DEMO")
    print("=" * 70)
    print("\nThis demo showcases the complete replay and debugging system.")
    print("\nDemos:")
    print("  1. DOM Snapshot Capture")
    print("  2. Field Overlay Debugger")
    print("  3. Execution Timeline")
    print("  4. AI Reasoning Inspector")
    print("  5. Failure Inspection")
    print("  6. Action Replay")
    print("  0. Run all demos")

    choice = input("\nSelect demo (0-6): ").strip()

    demos = {
        "1": demo_snapshot_capture,
        "2": demo_field_overlay,
        "3": demo_execution_timeline,
        "4": demo_ai_inspector,
        "5": demo_failure_inspection,
        "6": demo_action_replay,
    }

    if choice == "0":
        for demo_func in demos.values():
            demo_func()
    elif choice in demos:
        demos[choice]()
    else:
        print("Invalid choice. Exiting.")

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError running demo: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
