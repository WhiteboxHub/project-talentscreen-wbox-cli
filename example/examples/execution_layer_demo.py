#!/usr/bin/env python3
"""
Execution Layer Demo

Demonstrates the strict execution layer with structured actions,
retries, validation, and telemetry.

Usage:
    python examples/execution_layer_demo.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from playwright.sync_api import sync_playwright

from jobcli.execution import (
    ClickAction,
    ExecutionEngine,
    FillInputAction,
    SelectOptionAction,
    UploadFileAction,
)
from jobcli.execution.telemetry import get_telemetry_tracker
from jobcli.profile.schemas import ATSType


def demo_basic_execution():
    """Demo 1: Basic action execution with validation."""
    print("=" * 70)
    print("DEMO 1: Basic Execution")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to a test form
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        # Initialize execution engine
        engine = ExecutionEngine(
            page=page,
            ats_type=ATSType.GREENHOUSE,
            session_id="demo-session-1",
        )

        # Execute fill actions
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
        ]

        print("\nExecuting actions...")
        for action in actions:
            result = engine.execute(action)
            print(f"\n  {action.target}:")
            print(f"    Status: {result.status}")
            print(f"    Attempts: {result.attempts}")
            print(f"    Duration: {result.duration_ms}ms")
            print(f"    Verified: {result.verified}")
            if result.verified:
                print(f"    Value: {result.verified_value}")

        # Show engine state
        print(f"\n  Overall success rate: {engine.get_success_rate():.2%}")
        print(f"  Failed targets: {engine.get_failed_targets()}")

        input("\nPress Enter to close browser...")
        browser.close()


def demo_retry_logic():
    """Demo 2: Retry logic with exponential backoff."""
    print("\n" + "=" * 70)
    print("DEMO 2: Retry Logic")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        engine = ExecutionEngine(
            page=page,
            ats_type=ATSType.LEVER,
            session_id="demo-session-2",
        )

        # Try to fill a field that doesn't exist (will retry)
        print("\nAttempting to fill non-existent field (will retry 3 times)...")
        action = FillInputAction(
            target="nonexistent_field",
            selector="input[name='does_not_exist']",
            value="test",
            retry_count=3,
            verify_after=False,
        )

        result = engine.execute(action)

        print(f"\n  Status: {result.status}")
        print(f"  Attempts: {result.attempts}")
        print(f"  Error: {result.error}")

        input("\nPress Enter to close browser...")
        browser.close()


def demo_batch_execution():
    """Demo 3: Batch execution with early stopping."""
    print("\n" + "=" * 70)
    print("DEMO 3: Batch Execution")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        engine = ExecutionEngine(
            page=page,
            ats_type=ATSType.WORKDAY,
            session_id="demo-session-3",
        )

        # Batch of actions
        actions = [
            FillInputAction(
                target="first_name",
                selector="input[name='fname']",
                value="Jane",
                verify_after=True,  # Critical
            ),
            FillInputAction(
                target="last_name",
                selector="input[name='lname']",
                value="Smith",
                verify_after=True,  # Critical
            ),
            FillInputAction(
                target="email",
                selector="input[name='email']",  # Doesn't exist
                value="jane@example.com",
                verify_after=True,  # Critical - will fail and stop batch
                retry_count=1,
            ),
            FillInputAction(
                target="phone",  # Won't execute due to previous failure
                selector="input[name='phone']",
                value="555-1234",
                verify_after=False,
            ),
        ]

        print("\nExecuting batch (will stop on first critical failure)...")
        results = engine.execute_batch(actions)

        print(f"\n  Executed {len(results)}/{len(actions)} actions")
        for result in results:
            print(f"    {result.action_target}: {result.status}")

        input("\nPress Enter to close browser...")
        browser.close()


def demo_telemetry():
    """Demo 4: Telemetry tracking and metrics."""
    print("\n" + "=" * 70)
    print("DEMO 4: Telemetry & Metrics")
    print("=" * 70)

    # Get global telemetry tracker
    telemetry = get_telemetry_tracker()

    # Clear previous events for clean demo
    telemetry.events.clear()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        # Execute on multiple "ATS platforms" to show metrics
        for ats_type in [ATSType.GREENHOUSE, ATSType.LEVER]:
            engine = ExecutionEngine(
                page=page,
                ats_type=ats_type,
                session_id=f"demo-session-{ats_type.value}",
            )

            # Execute some actions
            actions = [
                FillInputAction(
                    target="fname",
                    selector="input[name='fname']",
                    value=f"Test-{ats_type.value}",
                    verify_after=True,
                ),
                FillInputAction(
                    target="lname",
                    selector="input[name='lname']",
                    value="User",
                    verify_after=True,
                ),
            ]

            for action in actions:
                engine.execute(action)

        # Show telemetry metrics
        print("\nTelemetry Summary:")
        print("-" * 70)

        summary = telemetry.get_summary()

        print(f"  Total events: {summary['total_events']}")
        print(f"  Field detection rate: {summary['field_detection_rate']:.2%}")
        print(f"  Fill success rate: {summary['fill_success_rate']:.2%}")
        print(f"  Selector failure rate: {summary['selector_failure_rate']:.2%}")
        print(f"  Human override rate: {summary['human_override_rate']:.2%}")

        print("\n  Retry Statistics:")
        retry_stats = summary["retry_statistics"]
        print(f"    Average retries: {retry_stats['avg_retries']:.2f}")
        print(f"    Max retries: {retry_stats['max_retries']}")
        print(f"    Fields requiring retry: {retry_stats['fields_requiring_retry']}")

        print("\n  ATS Reliability:")
        for ats, score in summary["ats_reliability"].items():
            print(f"    {ats}: {score:.2%}")

        print("\n  Confidence Accuracy:")
        conf_accuracy = summary["confidence_accuracy"]
        print(f"    High confidence (≥0.8): {conf_accuracy['high_confidence_accuracy']:.2%}")
        print(f"    Medium confidence (0.6-0.8): {conf_accuracy['medium_confidence_accuracy']:.2%}")
        print(f"    Low confidence (<0.6): {conf_accuracy['low_confidence_accuracy']:.2%}")

        # Show raw events
        print("\n  Recent Events:")
        for event in telemetry.events[-5:]:
            print(f"    {event.event}: {event.field} (success={event.success})")

        input("\nPress Enter to close browser...")
        browser.close()


def demo_error_handling():
    """Demo 5: Comprehensive error handling."""
    print("\n" + "=" * 70)
    print("DEMO 5: Error Handling")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.w3schools.com/html/html_forms.asp")

        engine = ExecutionEngine(
            page=page,
            ats_type=ATSType.GREENHOUSE,
            session_id="demo-session-5",
        )

        # Test different failure scenarios
        scenarios = [
            ("Element not found", "input[name='does_not_exist']", "test"),
            ("Wrong value verified", "input[name='fname']", "John"),
        ]

        for scenario_name, selector, value in scenarios:
            print(f"\nScenario: {scenario_name}")
            print("-" * 50)

            action = FillInputAction(
                target=f"test_{scenario_name.lower().replace(' ', '_')}",
                selector=selector,
                value=value,
                verify_after=True,
                retry_count=2,
            )

            result = engine.execute(action)

            print(f"  Status: {result.status}")
            print(f"  Attempts: {result.attempts}")
            print(f"  Duration: {result.duration_ms}ms")

            if result.error:
                print(f"  Error: {result.error}")

            # Check telemetry for details
            telemetry = get_telemetry_tracker()
            failed_events = [
                e
                for e in telemetry.events
                if e.field == result.action_target and not e.success
            ]

            if failed_events:
                print(f"  Telemetry captured {len(failed_events)} failure events:")
                for event in failed_events:
                    print(f"    - {event.event}: {event.reason}")

        input("\nPress Enter to close browser...")
        browser.close()


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print(" " * 20 + "EXECUTION LAYER DEMO")
    print("=" * 70)
    print("\nThis demo showcases the strict execution layer with:")
    print("  • Structured actions (fill, click, select, upload)")
    print("  • Automatic retries with exponential backoff")
    print("  • Pre-validation and post-verification")
    print("  • Comprehensive telemetry tracking")
    print("  • State management and error handling")
    print("\n" + "=" * 70)

    demos = [
        ("1", "Basic Execution", demo_basic_execution),
        ("2", "Retry Logic", demo_retry_logic),
        ("3", "Batch Execution", demo_batch_execution),
        ("4", "Telemetry & Metrics", demo_telemetry),
        ("5", "Error Handling", demo_error_handling),
    ]

    print("\nAvailable demos:")
    for num, name, _ in demos:
        print(f"  {num}. {name}")
    print("  0. Run all demos")

    choice = input("\nSelect demo (0-5): ").strip()

    if choice == "0":
        for _, _, demo_func in demos:
            demo_func()
    else:
        for num, _, demo_func in demos:
            if choice == num:
                demo_func()
                break
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
