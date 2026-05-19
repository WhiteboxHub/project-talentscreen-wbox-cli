

# Replay + Debugging System

Complete debugging toolkit for understanding failures, inspecting AI decisions, and visualizing execution.

## Overview

The debug system provides 6 critical capabilities:

1. **DOM Snapshot Capture** - Save complete page state before/after actions
2. **Action Replay** - Re-execute actions with step-through debugging
3. **Execution Timeline** - Visual timeline of all events
4. **Field Overlay Debugger** - Visual overlay showing fields on page
5. **AI Reasoning Inspector** - Inspect LLM prompts, responses, decisions
6. **Failure Inspection** - Diagnose failures with context and suggestions

---

## 1. DOM Snapshot Capture

Captures complete page state for later analysis.

### What's Captured

- Complete HTML source
- Viewport size and scroll position
- Full page & viewport screenshots (optional)
- Individual element snapshots (position, visibility, value, styles)
- Page metadata (forms, inputs, buttons)

### Usage

```python
from playwright.sync_api import sync_playwright
from jobcli.debug import SnapshotCapture

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://jobs.lever.co/...")
    
    # Initialize snapshot capture
    capture = SnapshotCapture(page)
    
    # Capture before action
    before_snapshot = capture.capture_before_action(
        action_target="email_field",
        action_selector="input[name='email']"
    )
    
    # Execute action
    page.fill("input[name='email']", "test@example.com")
    
    # Capture after action
    after_snapshot = capture.capture_after_action(
        action_target="email_field",
        action_selector="input[name='email']"
    )
    
    # Save snapshots
    from pathlib import Path
    snapshots_dir = Path("debug_snapshots")
    before_snapshot.save(snapshots_dir)
    after_snapshot.save(snapshots_dir)
```

### Snapshot Structure

```python
snapshot = DOMSnapshot(
    snapshot_id="snapshot_20260519_123456_a1b2c3d4",
    timestamp=datetime.utcnow(),
    url="https://jobs.lever.co/company/position",
    title="Software Engineer - Company",
    
    # DOM
    html="<html>...</html>",
    viewport_width=1920,
    viewport_height=1080,
    scroll_x=0.0,
    scroll_y=250.0,
    
    # Screenshots (base64 encoded)
    full_screenshot="iVBORw0KG...",
    viewport_screenshot="iVBORw0KG...",
    
    # Element snapshots
    elements={
        "email_field": ElementSnapshot(
            selector="input[name='email']",
            exists=True,
            visible=True,
            enabled=True,
            tag_name="input",
            type="email",
            value="",
            x=100.5,
            y=200.3,
            width=300.0,
            height=40.0,
            display="block",
            visibility="visible",
            screenshot_data="iVBORw0KG..."
        )
    },
    
    # Metadata
    form_count=1,
    input_count=15,
    button_count=3,
    capture_duration_ms=234
)
```

### Saved Files

```
debug_snapshots/
  snapshot_20260519_123456_a1b2c3d4.json    # Complete snapshot
  snapshot_20260519_123456_a1b2c3d4.html    # HTML source
  snapshot_20260519_123456_a1b2c3d4_full.png   # Full page screenshot
  snapshot_20260519_123456_a1b2c3d4_viewport.png  # Viewport screenshot
```

---

## 2. Action Replay

Re-execute actions with full debugging, step-through, and snapshot capture.

### Replay Modes

- **NORMAL** - Execute with snapshots and logging
- **STEP** - Pause after each action (interactive)
- **FAST** - Skip waits and screenshots (quick validation)
- **INSPECT** - Capture maximum debug info (failure analysis)

### Usage

```python
from playwright.sync_api import sync_playwright
from jobcli.debug import ActionReplayer, ReplayMode
from jobcli.execution import FillInputAction, ClickAction
from jobcli.profile.schemas import ATSType

actions = [
    FillInputAction(
        target="email",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=True
    ),
    FillInputAction(
        target="phone",
        selector="input[name='phone']",
        value="555-1234",
        verify_after=True
    ),
    ClickAction(
        target="submit",
        selector="button[type='submit']",
        wait_for_navigation=True
    )
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://jobs.lever.co/...")
    
    # Initialize replayer
    replayer = ActionReplayer(
        page=page,
        ats_type=ATSType.LEVER,
        mode=ReplayMode.INSPECT,
        snapshots_dir=Path("debug_snapshots")
    )
    
    # Replay sequence
    session = replayer.replay_sequence(
        actions,
        stop_on_failure=True
    )
    
    # Inspect results
    print(f"Success rate: {session.get_success_rate():.2%}")
    print(f"Failed steps: {len(session.get_failed_steps())}")
    
    # Inspect specific failure
    for step in session.get_failed_steps():
        report = replayer.inspect_failure(step)
        print(f"Failure: {report['diagnosis']}")
```

### Quick Replay

```python
from jobcli.debug import quick_replay

session = quick_replay(
    page=page,
    actions=actions,
    ats_type=ATSType.GREENHOUSE,
    mode=ReplayMode.NORMAL
)
```

### Replay Output

```
======================================================================
REPLAY SESSION: replay_20260519123456
  Mode: inspect
  ATS: lever
  Actions: 3
  Snapshots: debug_snapshots/20260519_123456
======================================================================

======================================================================
STEP 1: fill_input → email
  Selector: input[name='email']
======================================================================
  Capturing before snapshot...
  Executing action...
  ✓ SUCCESS (attempts=1, duration=234ms)
    Verified value: test@example.com
  Capturing after snapshot...

======================================================================
STEP 2: fill_input → phone
  Selector: input[name='phone']
======================================================================
  Capturing before snapshot...
  Executing action...
  ✗ FAILED (attempts=3, duration=1543ms)
    Error: Pre-validation failed: element not found or not visible
  Capturing failure snapshot...

  ⚠ Stopping on failure at step 2

======================================================================
REPLAY SUMMARY
======================================================================
  Total actions: 2
  Successful: 1
  Failed: 1
  Success rate: 50.00%
  Duration: 1777ms
  Snapshots: debug_snapshots/20260519_123456
======================================================================

  Session saved: debug_sessions/replay_20260519123456.json
```

---

## 3. Execution Timeline

Visual timeline of all events during execution.

### Timeline Events

- **Session**: started, ended, paused, resumed
- **Action**: started, completed, failed, retrying, skipped
- **Validation**: started, passed, failed
- **Verification**: started, passed, failed
- **AI/Semantic**: inference started/completed, field detected/classified
- **Human**: input requested/provided
- **Navigation**: page loaded/navigated
- **Snapshots**: captured
- **Errors**: occurred

### Usage

```python
from jobcli.debug import ExecutionTimeline, TimelineEventType

# Create timeline
timeline = ExecutionTimeline()

# Add events
timeline.add_event(
    TimelineEventType.ACTION_STARTED,
    action_target="email",
    metadata={"selector": "input[name='email']"}
)

timeline.add_event(
    TimelineEventType.ACTION_COMPLETED,
    action_target="email",
    success=True,
    duration_ms=234
)

# Get statistics
stats = timeline.get_statistics()
print(f"Total events: {stats['total_events']}")
print(f"Success rate: {stats['success_rate']:.2%}")

# Print timeline
timeline.print_timeline(max_events=20)

# Save timeline
timeline.save(Path("timeline.json"))

# Export as HTML
timeline.export_to_html(Path("timeline.html"))
```

### Timeline Output

```
======================================================================
EXECUTION TIMELINE
======================================================================
08:15:23.123 [    +0ms]   session_started
08:15:23.234 [  +111ms] ✓ action_started → email
08:15:23.456 [  +333ms] ✓ action_completed → email (234ms)
08:15:23.567 [  +444ms]   action_started → phone
08:15:24.789 [ +1666ms] ✗ action_failed → phone
08:15:24.890 [ +1767ms]   session_ended
======================================================================
```

### HTML Timeline

Opens in browser with interactive visualization, color-coded events, and statistics.

---

## 4. Field Overlay Debugger

Visual overlay on page showing detected fields, confidence, and status.

### Usage

```python
from playwright.sync_api import sync_playwright
from jobcli.debug import OverlayDebugger, FieldOverlay

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://jobs.lever.co/...")
    
    # Initialize overlay
    overlay = OverlayDebugger(page)
    
    # Highlight a field
    overlay.highlight_field(
        field_id="email",
        selector="input[name='email']",
        status="pending",
        label="email (0.95)"
    )
    
    # Execute action
    page.fill("input[name='email']", "test@example.com")
    
    # Update status
    overlay.update_field_status(
        field_id="email",
        status="success",
        label="email (0.95) ✓"
    )
    
    # Show fields panel
    fields = [
        FieldOverlay(
            field_id="email",
            selector="input[name='email']",
            semantic_type="email",
            confidence=0.95,
            status="success"
        ),
        FieldOverlay(
            field_id="phone",
            selector="input[name='phone']",
            semantic_type="phone",
            confidence=0.78,
            status="failed",
            error="Element not found"
        )
    ]
    
    overlay.show_fields_panel(fields)
    
    input("Press Enter to close...")
    
    # Clear overlays
    overlay.clear_overlays()
```

### Visual Output

The overlay renders:
- **Colored borders** around fields (yellow=pending, green=success, red=failed)
- **Labels** above fields showing field_id and confidence
- **Panel** in top-right corner listing all fields with status

---

## 5. AI Reasoning Inspector

Inspect LLM prompts, responses, decisions, and confidence calibration.

### Usage

```python
from jobcli.debug import get_ai_inspector, AITaskType

# Get global inspector
inspector = get_ai_inspector()

# Record AI reasoning
reasoning = inspector.record_reasoning(
    task_type=AITaskType.FIELD_CLASSIFICATION,
    prompt="Classify this field: <input name='email' ...>",
    response="This is an email field based on name attribute",
    decision="email",
    confidence=0.95,
    model="gpt-4",
    reasoning_steps=[
        "1. Check name attribute: 'email'",
        "2. Check type attribute: None",
        "3. Strong match on name → email field"
    ],
    tokens_used=150,
    latency_ms=450
)

# After execution, validate
inspector.validate_reasoning(
    reasoning.reasoning_id,
    validation_result="Field was correctly classified",
    correct=True,
    ground_truth="email"
)

# Get confidence calibration
calibration = inspector.get_confidence_calibration()
print(inspector.generate_calibration_report())

# Get task performance
performance = inspector.get_task_performance()
print(inspector.generate_task_performance_report())

# Print specific reasoning
inspector.print_reasoning(reasoning.reasoning_id)

# Export all reasonings
inspector.export_reasonings(Path("ai_reasonings.json"))
```

### Calibration Report

```
======================================================================
AI CONFIDENCE CALIBRATION REPORT
======================================================================
Total Validated: 45

high (≥0.8):
  Count: 20
  Accuracy: 95.00%
  Avg Confidence: 92.00%
  Calibration Error: 3.00%
  ✓ Well calibrated

medium (0.6-0.8):
  Count: 15
  Accuracy: 73.33%
  Avg Confidence: 70.00%
  Calibration Error: 3.33%
  ✓ Well calibrated

low (<0.6):
  Count: 10
  Accuracy: 40.00%
  Avg Confidence: 52.00%
  Calibration Error: 12.00%
  ⚠ Overconfident (reduce confidence)

======================================================================
```

### Task Performance Report

```
======================================================================
AI TASK PERFORMANCE REPORT
======================================================================

field_classification:
  Total: 45
  Validated: 45
  Accuracy: 91.11%
  Avg Confidence: 85.00%
  Avg Latency: 380ms

selector_generation:
  Total: 30
  Validated: 30
  Accuracy: 86.67%
  Avg Confidence: 78.00%
  Avg Latency: 520ms

======================================================================
```

---

## 6. Failure Inspection

Diagnose failures with complete context, root cause analysis, and suggested fixes.

### Usage

```python
from jobcli.debug import get_failure_inspector

# Get global inspector
inspector = get_failure_inspector()

# Record failure
failure = inspector.record_failure(
    result=execution_result,
    action_type="fill_input",
    selector="input[name='phone']",
    before_snapshot=before_snapshot,
    after_snapshot=after_snapshot,
    failure_snapshot=failure_snapshot,
    ai_reasonings=[reasoning1, reasoning2],
    timeline_events=timeline.get_events_by_target("phone")
)

# Print failure details
inspector.print_failure(failure.failure_id, verbose=True)

# Get failures by root cause
selector_failures = inspector.get_failures_by_root_cause("selector_not_found")

# Get statistics
stats = inspector.get_failure_statistics()
print(inspector.generate_failure_summary())

# Export failures
inspector.generate_failure_report(Path("failures.json"))
inspector.export_failures_html(Path("failures.html"))
```

### Failure Output

```
======================================================================
FAILURE INSPECTION: failure_0001
======================================================================
Action: fill_input → phone
Selector: input[name='phone']
Error: Pre-validation failed: element not found or not visible
Attempts: 3

--- DIAGNOSIS ---
  • Element not found with selector

Root Cause: selector_not_found
Suggested Fix: Update selector or verify page state

--- SNAPSHOTS ---
Before: snapshot_20260519_123456_a1b2c3d4
After: snapshot_20260519_123457_b2c3d4e5
Failure: failure_20260519_123458_c3d4e5f6

--- AI REASONING ---
  • reasoning_0042

======================================================================
```

### Failure Summary

```
======================================================================
FAILURE SUMMARY
======================================================================
Total Failures: 8
Avg Attempts: 2.4

Failures by Root Cause:
  selector_not_found: 3
  element_not_visible: 2
  value_unchanged: 2
  timeout: 1

Failures by Action Type:
  fill_input: 5
  click_button: 2
  select_option: 1

======================================================================
```

---

## Complete Debugging Workflow

### 1. Capture Everything

```python
from playwright.sync_api import sync_playwright
from jobcli.debug import *
from jobcli.execution import ExecutionEngine, FillInputAction
from jobcli.profile.schemas import ATSType

# Setup
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://jobs.lever.co/...")
    
    # Initialize all debug tools
    snapshot_capture = SnapshotCapture(page)
    overlay = OverlayDebugger(page)
    timeline = ExecutionTimeline()
    ai_inspector = get_ai_inspector()
    failure_inspector = get_failure_inspector()
    
    # Initialize execution engine
    engine = ExecutionEngine(page, ats_type=ATSType.LEVER)
```

### 2. Execute with Debug Instrumentation

```python
action = FillInputAction(
    target="email",
    selector="input[name='email']",
    value="test@example.com",
    verify_after=True
)

# Timeline: started
timeline.add_event(
    TimelineEventType.ACTION_STARTED,
    action_target=action.target
)

# Overlay: highlight field
overlay.highlight_field(
    field_id=action.target,
    selector=action.selector,
    status="pending"
)

# Snapshot: before
before_snapshot = snapshot_capture.capture_before_action(
    action.target, action.selector
)

# Execute
result = engine.execute(action)

# Snapshot: after
after_snapshot = snapshot_capture.capture_after_action(
    action.target, action.selector
)

# Timeline: completed/failed
if result.status == "success":
    timeline.add_event(
        TimelineEventType.ACTION_COMPLETED,
        action_target=action.target,
        success=True,
        duration_ms=result.duration_ms
    )
    
    # Overlay: success
    overlay.update_field_status(action.target, "success")
    
else:
    timeline.add_event(
        TimelineEventType.ACTION_FAILED,
        action_target=action.target,
        success=False,
        duration_ms=result.duration_ms
    )
    
    # Overlay: failed
    overlay.update_field_status(action.target, "failed")
    
    # Snapshot: failure
    failure_snapshot = snapshot_capture.capture_failure(
        action.target, action.selector, result.error
    )
    
    # Record failure
    failure = failure_inspector.record_failure(
        result=result,
        action_type=action.action.value,
        selector=action.selector,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        failure_snapshot=failure_snapshot
    )
    
    print(failure_inspector.generate_failure_summary())
```

### 3. Inspect and Analyze

```python
# Timeline analysis
timeline.print_summary()
timeline.export_to_html(Path("debug/timeline.html"))

# AI reasoning analysis
print(ai_inspector.generate_calibration_report())
print(ai_inspector.generate_task_performance_report())
ai_inspector.export_reasonings(Path("debug/ai_reasonings.json"))

# Failure analysis
print(failure_inspector.generate_failure_summary())
failure_inspector.export_failures_html(Path("debug/failures.html"))

# Save snapshots
from pathlib import Path
snapshots_dir = Path("debug/snapshots")
snapshots_dir.mkdir(parents=True, exist_ok=True)

before_snapshot.save(snapshots_dir)
after_snapshot.save(snapshots_dir)
if failure_snapshot:
    failure_snapshot.save(snapshots_dir)
```

---

## Integration with Execution Layer

The debug system integrates seamlessly with the execution layer:

```python
from jobcli.execution import ExecutionEngine
from jobcli.debug import SnapshotCapture, ExecutionTimeline

# Extend ExecutionEngine with debug capabilities
class DebugExecutionEngine(ExecutionEngine):
    def __init__(self, page, ats_type, **kwargs):
        super().__init__(page, ats_type, **kwargs)
        self.snapshot_capture = SnapshotCapture(page)
        self.timeline = ExecutionTimeline()
    
    def execute(self, action):
        # Capture before
        before_snapshot = self.snapshot_capture.capture_before_action(
            action.target, action.selector
        )
        
        # Timeline: started
        self.timeline.add_event(
            TimelineEventType.ACTION_STARTED,
            action_target=action.target
        )
        
        # Execute
        result = super().execute(action)
        
        # Capture after
        after_snapshot = self.snapshot_capture.capture_after_action(
            action.target, action.selector
        )
        
        # Timeline: completed/failed
        self.timeline.add_event(
            TimelineEventType.ACTION_COMPLETED if result.status == "success"
            else TimelineEventType.ACTION_FAILED,
            action_target=action.target,
            success=result.status == "success",
            duration_ms=result.duration_ms
        )
        
        return result
```

---

## Output Files

Complete debug session generates:

```
debug/
  snapshots/
    before_email_20260519_123456.json
    before_email_20260519_123456.html
    before_email_20260519_123456_viewport.png
    after_email_20260519_123457.json
    after_email_20260519_123457.html
    after_email_20260519_123457_viewport.png
    failure_phone_20260519_123458.json
    failure_phone_20260519_123458.html
    failure_phone_20260519_123458_full.png
  
  replay_20260519123456.json
  timeline_20260519123456.json
  timeline.html
  
  ai_reasonings.json
  
  failures.json
  failures.html
```

---

## Best Practices

### 1. Enable Debug Mode for New ATS Platforms

When adding support for a new ATS:
- Use `ReplayMode.INSPECT` for maximum capture
- Enable field overlays to visualize detection
- Record all AI reasoning for calibration
- Capture failures for root cause analysis

### 2. Replay Failed Sessions

If a job application fails in production:
- Capture the failed actions sequence
- Replay in `ReplayMode.STEP` to inspect each action
- Use snapshots to compare before/after state
- Check AI reasoning for classification errors

### 3. Monitor AI Confidence Calibration

Regularly check if AI confidence matches actual accuracy:
- Export AI reasonings after batch runs
- Generate calibration report
- Adjust confidence thresholds if overconfident/underconfident

### 4. Analyze Failure Patterns

After multiple runs:
- Group failures by root cause
- Identify common selector failures
- Update selectors or add fallbacks
- Improve pre-validation logic

### 5. Use Overlay for Manual Testing

When testing a new form manually:
- Highlight all inputs with `overlay.highlight_all_inputs()`
- Verify field detection visually
- Check that selectors match expected elements

---

**The debug system is production-ready and integrates seamlessly with the execution layer.**