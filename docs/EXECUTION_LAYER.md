# Strict Execution Layer

The execution layer provides a deterministic, reliable way to interact with browser automation in JobCLI. All browser actions go through structured schemas with automatic retries, validation, and telemetry.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      High-Level Controller                   │
│              (Semantic Engine / ATS Handler)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Emits ExecutionActions
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     ExecutionEngine                          │
│  • Pre-validation (element exists, visible)                 │
│  • Execute action (fill, click, select, upload)             │
│  • Post-verification (read back, verify state)              │
│  • Retry with exponential backoff + jitter                  │
│  • Emit structured telemetry                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Uses
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   Playwright Page                            │
│                   (Browser DOM)                              │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Execution Actions (`jobcli/execution/actions.py`)

Structured schemas that define **what** to do, not **how** to do it.

```python
from jobcli.execution import FillInputAction, ClickAction, SelectOptionAction

# Fill an input field
action = FillInputAction(
    action="fill_input",
    target="candidate_email",              # Canonical field ID
    selector="input[name='email']",        # CSS/XPath selector
    value="user@email.com",                # Value to fill
    verify_after=True,                     # Read back and verify?
    timeout_ms=5000,                       # Timeout per attempt
    retry_count=3,                         # Max retry attempts
    clear_first=True                       # Clear existing value first?
)

# Click a button
action = ClickAction(
    action="click_button",
    target="submit_button",
    selector="button[type='submit']",
    wait_for_navigation=True,              # Wait for page load?
    verify_after=False
)

# Select from dropdown
action = SelectOptionAction(
    action="select_option",
    target="country_field",
    selector="select[name='country']",
    value="United States",
    match_strategy="exact",                # "exact", "contains", "fuzzy"
    verify_after=True
)
```

### 2. Execution Engine (`jobcli/execution/engine.py`)

The engine executes actions with retries, validation, and telemetry.

```python
from playwright.sync_api import sync_playwright
from jobcli.execution import ExecutionEngine, FillInputAction
from jobcli.profile.schemas import ATSType

# Initialize engine
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    
    engine = ExecutionEngine(
        page=page,
        ats_type=ATSType.GREENHOUSE,
        session_id="app-session-123"
    )
    
    # Execute single action
    action = FillInputAction(
        target="email",
        selector="input#email",
        value="test@example.com"
    )
    
    result = engine.execute(action)
    
    print(f"Status: {result.status}")           # "success" or "failed"
    print(f"Attempts: {result.attempts}")       # Number of tries
    print(f"Duration: {result.duration_ms}ms")  # Total time
    print(f"Verified: {result.verified}")       # Was value verified?
    print(f"Error: {result.error}")             # Error message if failed
```

### 3. Telemetry System (`jobcli/execution/telemetry.py`)

All operations emit structured events for monitoring and learning.

```python
from jobcli.execution.telemetry import get_telemetry_tracker, EventType

# Access global telemetry tracker
telemetry = get_telemetry_tracker()

# Events are automatically emitted by ExecutionEngine
# You can also emit custom events:
telemetry.emit_field_detected(
    field_id="email_field",
    semantic_type="email",
    confidence=0.95,
    ats=ATSType.GREENHOUSE
)

# Get metrics
print(f"Fill success rate: {telemetry.get_fill_success_rate():.2%}")
print(f"Detection rate: {telemetry.get_field_detection_rate():.2%}")
print(f"Retry stats: {telemetry.get_retry_statistics()}")
print(f"ATS reliability: {telemetry.get_ats_reliability()}")
print(f"Human override rate: {telemetry.get_human_override_rate():.2%}")
print(f"Confidence accuracy: {telemetry.get_confidence_accuracy()}")

# Get complete summary
summary = telemetry.get_summary()
```

## Event Types

All telemetry events follow this structure:

```json
{
  "event": "field_fill_failed",
  "field": "phone_number",
  "reason": "validation_error",
  "ats": "workday",
  "confidence": 0.42,
  "timestamp": "2026-05-19T12:34:56Z",
  "session_id": "app-123",
  "retry_count": 2,
  "duration_ms": 1543,
  "metadata": {...}
}
```

### Event Categories

**Field Detection:**
- `field_detected` - Field found and classified
- `field_classified` - Semantic type assigned
- `field_mapped` - Mapped to canonical model

**Execution:**
- `action_started` - Action execution began
- `action_succeeded` - Action completed successfully
- `action_failed` - Action failed after retries
- `action_retrying` - Retry attempt in progress

**Validation:**
- `validation_passed` - Pre-execution validation succeeded
- `validation_failed` - Pre-execution validation failed
- `verification_passed` - Post-execution verification succeeded
- `verification_failed` - Post-execution verification failed

**Field Fill (specific):**
- `field_fill_started` - Fill operation started
- `field_fill_succeeded` - Fill succeeded and verified
- `field_fill_failed` - Fill failed

**Human Interaction:**
- `human_override_requested` - System needs human input
- `human_override_provided` - Human provided value
- `human_correction` - Human corrected AI decision

**Selectors:**
- `selector_found` - CSS selector matched element
- `selector_not_found` - CSS selector failed
- `selector_fallback` - Fell back to alternative selector

**ATS:**
- `ats_detected` - ATS platform identified
- `ats_pattern_matched` - ATS-specific pattern recognized

## Execution Algorithm

For each action, the engine follows this flow:

```
1. Emit action_started event
2. FOR attempt = 1 to retry_count:
   a. Pre-validation:
      - Check element exists (count > 0)
      - Check element visible (unless file input)
      - Emit selector_found or selector_not_found
   b. Execute action:
      - fill_input: clear + fill
      - click_button: click (+ wait for navigation)
      - select_option: select with match strategy
      - upload_file: set_input_files
      - wait: wait for appear/disappear/time
   c. Post-verification (if verify_after=true):
      - Read back value from DOM
      - Compare with expected value
      - Emit verification_passed or verification_failed
   d. On failure:
      - If attempt < retry_count: wait with exponential backoff
      - Else: emit failure event and return failed result
3. Emit success/failure event
4. Return ExecutionResult
```

### Retry Strategy

Exponential backoff with jitter:

```python
# Base delay: 500ms
# Max delay: 5000ms
# Jitter: ±30%

delay = min(500 * 2^(attempt-1), 5000)
jitter = delay * 0.3 * (random() - 0.5) * 2
final_delay = delay + jitter

# Attempt 1: ~500ms (350-650ms)
# Attempt 2: ~1000ms (700-1300ms)
# Attempt 3: ~2000ms (1400-2600ms)
# Attempt 4+: ~5000ms (3500-6500ms)
```

## Usage Patterns

### Pattern 1: Sequential Execution

```python
engine = ExecutionEngine(page, ats_type=ATSType.LEVER)

# Execute actions one by one
result1 = engine.execute(FillInputAction(...))
if result1.status == "failed":
    print(f"Failed: {result1.error}")
    return

result2 = engine.execute(ClickAction(...))
```

### Pattern 2: Batch Execution

```python
actions = [
    FillInputAction(target="email", ...),
    FillInputAction(target="phone", ...),
    FillInputAction(target="name", ...),
    ClickAction(target="submit", verify_after=True)  # Critical action
]

results = engine.execute_batch(actions)

# Batch stops on first critical failure (verify_after=True)
for result in results:
    print(f"{result.action_target}: {result.status}")
```

### Pattern 3: Conditional Execution

```python
# Try primary selector, fallback to secondary
action1 = FillInputAction(
    target="email",
    selector="input[name='email']",
    value="test@example.com",
    retry_count=1  # Fail fast
)

result1 = engine.execute(action1)

if result1.status == "failed":
    # Try fallback selector
    action2 = FillInputAction(
        target="email",
        selector="input[type='email']",  # Different selector
        value="test@example.com"
    )
    result2 = engine.execute(action2)
```

### Pattern 4: State Tracking

```python
# Execute multiple fields
for field_id, selector, value in fields:
    action = FillInputAction(target=field_id, selector=selector, value=value)
    engine.execute(action)

# Check overall success
success_rate = engine.get_success_rate()
failed_fields = engine.get_failed_targets()

print(f"Success rate: {success_rate:.2%}")
print(f"Failed fields: {failed_fields}")
```

## Integration with Canonical Model

The execution layer integrates with the canonical model:

```python
from jobcli.canonical import CanonicalFormModel, CanonicalField
from jobcli.execution import ExecutionEngine, FillInputAction

# Canonical model defines WHAT to fill
canonical = CanonicalFormModel(
    form_id="greenhouse-app-123",
    fields=[
        CanonicalField(
            field_id="email",
            semantic_type="email",
            selector="input[name='email']",
            required=True
        )
    ]
)

# Execution engine defines HOW to fill
engine = ExecutionEngine(page, ats_type=ATSType.GREENHOUSE)

for field in canonical.fields:
    if field.selector and field.value:
        action = FillInputAction(
            target=field.field_id,
            selector=field.selector,
            value=field.value,
            verify_after=field.required  # Verify required fields
        )
        result = engine.execute(action)
```

## Error Handling

```python
result = engine.execute(action)

if result.status == ExecutionStatus.SUCCESS:
    print(f"✓ Filled {result.action_target} in {result.duration_ms}ms")
    if result.verified:
        print(f"  Verified value: {result.verified_value}")
else:
    print(f"✗ Failed to fill {result.action_target}")
    print(f"  Error: {result.error}")
    print(f"  Attempts: {result.attempts}")
    
    # Check telemetry for details
    failed_events = [
        e for e in telemetry.events 
        if e.field == result.action_target and not e.success
    ]
    for event in failed_events:
        print(f"  {event.event}: {event.reason}")
```

## Metrics You Should Track

### Per-Session Metrics
```python
engine = ExecutionEngine(...)

# After execution
print(f"Success rate: {engine.get_success_rate():.2%}")
print(f"Failed targets: {engine.get_failed_targets()}")
```

### Global Metrics
```python
telemetry = get_telemetry_tracker()

# Field detection
detection_rate = telemetry.get_field_detection_rate()
detection_rate_by_ats = telemetry.get_field_detection_rate(ats=ATSType.WORKDAY)

# Fill success
fill_rate = telemetry.get_fill_success_rate()
fill_rate_by_ats = telemetry.get_fill_success_rate(ats=ATSType.LEVER)

# Retries
retry_stats = telemetry.get_retry_statistics()
# => {"avg_retries": 1.2, "max_retries": 3, "fields_requiring_retry": 5}

# ATS reliability (which platforms work best)
reliability = telemetry.get_ats_reliability()
# => {ATSType.GREENHOUSE: 0.95, ATSType.LEVER: 0.88, ...}

# Selector health
selector_failure_rate = telemetry.get_selector_failure_rate()

# Human intervention
override_rate = telemetry.get_human_override_rate()

# Confidence calibration
confidence_accuracy = telemetry.get_confidence_accuracy()
# => {
#   "high_confidence_accuracy": 0.95,   # conf >= 0.8
#   "medium_confidence_accuracy": 0.75, # conf 0.6-0.8
#   "low_confidence_accuracy": 0.40     # conf < 0.6
# }
```

## Best Practices

### 1. Use verify_after for critical fields
```python
# Critical fields (email, resume) should be verified
FillInputAction(
    target="email",
    value="test@example.com",
    verify_after=True  # ✓ Read back and verify
)

# Non-critical fields can skip verification
FillInputAction(
    target="linkedin_url",
    value="https://linkedin.com/in/john",
    verify_after=False  # Fast path
)
```

### 2. Set appropriate retry_count
```python
# Fast-fail for selector validation
FillInputAction(
    target="optional_field",
    retry_count=1  # Give up quickly if selector wrong
)

# Resilient for important fields
FillInputAction(
    target="resume_upload",
    retry_count=5  # Try harder for file uploads
)
```

### 3. Use clear_first judiciously
```python
# Clear for user-facing inputs (may have default values)
FillInputAction(
    target="email",
    value="new@email.com",
    clear_first=True  # Remove any pre-filled value
)

# Don't clear for append-only fields
FillInputAction(
    target="additional_info",
    value="Extra context",
    clear_first=False  # Append to existing
)
```

### 4. Monitor telemetry to improve selectors
```python
# After a job run
telemetry = get_telemetry_tracker()

# Find failing selectors
for event in telemetry.events:
    if event.event == EventType.SELECTOR_NOT_FOUND:
        print(f"Bad selector: {event.metadata['selector']} for {event.field}")
        # Update selector in ATS handler or canonical model
```

### 5. Emit custom events for learning
```python
# When AI makes a decision
telemetry.emit_field_detected(
    field_id="custom_question_1",
    semantic_type="years_of_experience",
    confidence=0.78,
    ats=ATSType.GREENHOUSE
)

# When human corrects AI
telemetry.emit_human_override(
    field_id="custom_question_1",
    original_value="5",
    provided_value="7",
    confidence=0.78,
    ats=ATSType.GREENHOUSE
)

# Later, analyze: where is AI weak?
low_confidence_fields = [
    e for e in telemetry.events
    if e.event == EventType.HUMAN_OVERRIDE_PROVIDED
]
```

## Testing

Run execution engine tests:

```bash
pytest tests/test_execution_engine.py -v
```

Test coverage includes:
- ✓ All action types (fill, click, select, upload, wait)
- ✓ Pre-validation (element exists, visible)
- ✓ Post-verification (value read-back)
- ✓ Retry logic with exponential backoff
- ✓ Batch execution with early stopping
- ✓ State tracking (success rate, failed targets)
- ✓ Telemetry event emission
- ✓ Error handling (Playwright errors, unexpected errors)

## Future Enhancements

- [ ] **Parallel execution**: Execute independent actions concurrently
- [ ] **Smart selectors**: Auto-generate fallback selectors using AI
- [ ] **Visual verification**: Screenshot comparison for visual fields
- [ ] **Performance optimization**: Cache element handles
- [ ] **Telemetry export**: Push events to external monitoring (Datadog, etc.)
- [ ] **Confidence-based retry**: Retry more aggressively for high-confidence actions
- [ ] **Selector healing**: Auto-fix broken selectors using page analysis

---

**Summary**: The execution layer provides a production-ready, deterministic way to interact with browser automation. It handles all the complexity (retries, validation, telemetry) so higher-level code can focus on business logic.
