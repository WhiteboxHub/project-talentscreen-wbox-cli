

# Self-Healing Automation System

Automatic recovery from selector failures with support for modern web technologies.

## Overview

The self-healing system provides **5 critical capabilities**:

1. **Selector Healing** - Automatically fix broken selectors using semantic matching, DOM similarity, and historical patterns
2. **Modern Web Handling** - Support React SPAs, Shadow DOM, delayed hydration, dynamic rendering
3. **Adaptive Retry** - Intelligent retry with exponential backoff and confidence-based escalation
4. **Historical Learning** - Learn from successful patterns and reuse them
5. **Confidence Escalation** - Escalate to human verification when confidence is low

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SelfHealingEngine                            │
│                                                                  │
│  Wraps ExecutionEngine with healing capabilities                │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ├──► ExecutionEngine (standard execution)
               │
               ├──► SelectorHealer
               │    • Semantic matching (labels, aria, data-*)
               │    • Historical patterns
               │    • DOM similarity
               │    • Attribute variations
               │    • Positional matching
               │
               ├──► ModernWebHandler
               │    • React/Vue/Angular detection
               │    • Hydration waiting
               │    • Shadow DOM piercing
               │    • SPA navigation handling
               │
               └──► AdaptiveRetry
                    • Exponential backoff with jitter
                    • Confidence-based delays
                    • Escalation triggers
                    • Failure tracking
```

---

## 1. Selector Healing

Automatically fixes broken selectors using 5 fallback strategies.

### Strategies (in order of confidence)

#### 1. Semantic Matching (confidence: 0.70-0.85)

Looks for semantic attributes that match the field type:

```python
# For field_type="email", tries:
input[name*='email' i]
input[id*='email' i]
input[placeholder*='email' i]
input[aria-label*='email' i]
input[data-field*='email' i]
input[data-testid*='email' i]
```

**Patterns per field type:**
- `email` → ["email", "e-mail", "mail"]
- `phone` → ["phone", "telephone", "tel", "mobile"]
- `first_name` → ["first name", "firstname", "fname"]
- `last_name` → ["last name", "lastname", "lname"]
- `address`, `city`, `state`, `zip`, `country` → similar patterns

#### 2. Historical Patterns (confidence: 0.80-0.95)

Uses selectors that worked previously for this field type:

```python
# If "input[name='applicantEmail']" worked 10 times for "email" fields,
# it gets higher confidence than untested selectors
```

Patterns are stored with:
- Field type
- Success count
- Last used timestamp
- ATS type (optional)

#### 3. DOM Similarity (confidence: 0.60-0.75)

Relaxes the original selector:

```python
# Original: input[name='email'][class='form-control']
# Tries:
input[name='email']          # Drop class
input[name*='email']         # Name contains
input[class='form-control']  # Drop name
```

#### 4. Attribute Variations (confidence: 0.55-0.70)

Tries common attribute name variations:

```python
# For field_type="email", tries:
input[name='email']
input[name='Email']           # Capital
input[name='userEmail']       # Prefix
input[name='user_email']      # Snake case
input[name='emailAddress']    # Suffix
```

#### 5. Positional Matching (confidence: 0.50-0.80)

Uses labels or position in form:

```python
# By label:
label:has-text('Email') + input
label:has-text('Email') ~ input
label:has-text('Email') input

# By position (email is often first):
form input:nth-child(1)
```

### Usage

```python
from playwright.sync_api import sync_playwright
from jobcli.healing import SelectorHealer

with sync_playwright() as p:
    page = p.chromium.launch().new_page()
    page.goto("https://jobs.lever.co/...")

    healer = SelectorHealer(page)

    # Try healing broken selector
    result = healer.heal_selector(
        original_selector="input[name='email']",
        field_type="email",
        semantic_context={
            "label_text": "Email Address",
            "expected_value": "test@example.com"
        }
    )

    if result.success:
        print(f"Healed selector: {result.healed_selector}")
        print(f"Confidence: {result.confidence:.2%}")
        print(f"Strategy: {result.strategy}")

        # Use healed selector
        page.fill(result.healed_selector, "test@example.com")

        # Record success for future use
        healer.record_success(
            result.healed_selector,
            "email",
            ats_type="lever"
        )
```

### Historical Patterns

Patterns are automatically learned and stored:

```python
# Patterns stored in JSON:
{
  "field_type": "email",
  "selector": "input[data-qa='email-field']",
  "success_count": 15,
  "last_used": "2026-05-19T12:34:56Z",
  "ats_type": "greenhouse"
}

# View patterns
summary = healer.get_patterns_summary()
print(f"Total patterns: {summary['total_patterns']}")
print(f"Top patterns: {summary['top_patterns']}")
```

---

## 2. Modern Web Handling

Supports React SPAs, Shadow DOM, delayed hydration, and dynamic rendering.

### Framework Detection

Automatically detects:
- **React** (via `window.React`, `data-reactroot`, React Fiber)
- **Vue** (via `window.Vue`, `data-v-`, `__vue__`)
- **Angular** (via `window.ng`, `ng-version`, `ng-app`)

```python
from jobcli.healing import ModernWebHandler

handler = ModernWebHandler(page)

# Detect technologies
info = handler.detect_technologies()

print(f"Framework: {info.framework.value}")           # "react"
print(f"Hydration: {info.hydration_status.value}")    # "hydrated"
print(f"Has Shadow DOM: {info.has_shadow_dom}")       # True/False
print(f"Is SPA: {info.is_spa}")                       # True/False
print(f"Dynamic content: {info.dynamic_content}")     # True/False
```

### Hydration Waiting

Wait for client-side hydration before interacting:

```python
# Wait for React hydration
success = handler.wait_for_hydration(timeout_ms=5000)

# Framework-specific waiting:
# - React: Waits for React Fiber
# - Vue: Waits for __vue__ instance
# - Angular: Waits for ng.probe
# - Generic: Waits for network idle + no loading indicators
```

### Shadow DOM Support

Pierce through Shadow DOM to find elements:

```python
# Find element inside Shadow DOM
locator = handler.find_in_shadow_dom(
    selector="input[name='email']",
    shadow_host_selector="custom-form"
)

if locator:
    locator.fill("test@example.com")

# Returns piercing selector: "custom-form >>> input[name='email']"
```

### SPA Navigation Handling

Handle client-side routing:

```python
# Handle SPA navigation
def click_next():
    page.click("button.next")

success = handler.handle_spa_navigation(click_next)
# Waits for URL change instead of page load
```

### Dynamic Content Waiting

Wait for AJAX-loaded content:

```python
success = handler.wait_for_dynamic_content(
    selector="input[name='email']",
    timeout_ms=5000
)
# Waits for network idle + selector visible
```

### React Fiber Inspection

Extract React component data:

```python
fiber_data = handler.get_react_fiber_data("input[name='email']")

if fiber_data:
    print(f"Component type: {fiber_data['type']}")
    print(f"Props: {fiber_data['props']}")
    print(f"State: {fiber_data['state']}")
```

---

## 3. Adaptive Retry

Intelligent retry with confidence-based escalation.

### Retry Strategies

- **EXPONENTIAL_BACKOFF** - 500ms → 1s → 2s → 4s → 8s (capped at 10s)
- **LINEAR** - 500ms → 1s → 1.5s → 2s → 2.5s
- **FIXED** - 500ms every time
- **ADAPTIVE** - Adjusts based on confidence and failure history

### Confidence-Based Escalation

```python
from jobcli.healing import AdaptiveRetry, RetryConfig, EscalationLevel

config = RetryConfig(
    max_retries=5,
    base_delay_ms=500,
    max_delay_ms=10000,
    strategy="adaptive",
    high_confidence_threshold=0.8,
    low_confidence_threshold=0.5,
    escalate_after_failures=3
)

retry = AdaptiveRetry(config)

# Execute with retry
result = retry.execute_with_retry(
    operation=lambda: page.fill("input[name='email']", "test@example.com"),
    field_id="email",
    confidence=0.42  # Low confidence
)

if result.escalation_triggered:
    print(f"Escalation: {result.escalation_triggered}")
    # EscalationLevel.SELECTOR_HEALING
    # EscalationLevel.HUMAN_VERIFICATION
    # EscalationLevel.SKIP_FIELD
```

### Escalation Triggers

| Condition | Escalation |
|-----------|------------|
| First attempt, confidence < 0.5 | `SELECTOR_HEALING` |
| 2+ attempts, confidence < 0.5 | `HUMAN_VERIFICATION` |
| 3+ attempts, confidence ≥ 0.8 | `HUMAN_VERIFICATION` |
| 3+ attempts, confidence < 0.8 | `SKIP_FIELD` |
| 5+ recent failures | `SKIP_FIELD` |

### Adaptive Delay Calculation

```python
# Base exponential backoff
delay = 500ms * 2^(attempt-1)

# Adjust for confidence
if confidence < 0.5:
    delay *= 1.5  # Wait longer for low confidence
elif confidence >= 0.8:
    delay *= 0.75  # Wait less for high confidence

# Adjust for failure history
if recent_failures > 3:
    delay *= 1.25  # Wait longer for frequent failures

# Add jitter (±30%)
delay += random(-0.3 * delay, +0.3 * delay)

# Cap at max_delay_ms
delay = min(delay, 10000)
```

---

## 4. Integrated Self-Healing Engine

Complete self-healing system combining all components.

### Usage

```python
from playwright.sync_api import sync_playwright
from jobcli.healing import SelfHealingEngine
from jobcli.execution import FillInputAction
from jobcli.profile.schemas import ATSType

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://jobs.lever.co/...")

    # Initialize self-healing engine
    engine = SelfHealingEngine(
        page=page,
        ats_type=ATSType.LEVER,
        enable_healing=True,
        enable_modern_web=True
    )

    # Execute action with automatic healing
    action = FillInputAction(
        target="email",
        selector="input[name='email']",  # May be broken
        value="test@example.com",
        verify_after=True
    )

    result = engine.execute(action)

    if result.status == "success":
        print("✓ Filled successfully")
    else:
        print(f"✗ Failed: {result.error}")

    # Print healing summary
    engine.print_summary()
```

### Output

```
======================================================================
SELF-HEALING ENGINE SUMMARY
======================================================================
  Total actions: 10
  Successful: 9
  Failed: 1
  Success rate: 90.00%

  Selectors healed: 3
  Healing success rate: 30.00%

  Modern web detected:
    Framework: react
    Hydration: hydrated
    Shadow DOM: False
    SPA: True

  Historical patterns: 47
======================================================================
```

### Batch Execution

```python
actions = [
    FillInputAction(target="email", selector="input[name='email']", value="test@example.com"),
    FillInputAction(target="phone", selector="input[name='phone']", value="555-1234"),
    FillInputAction(target="name", selector="input[name='name']", value="John Doe")
]

results = engine.execute_batch(actions, stop_on_failure=False)

for result in results:
    status = "✓" if result.status == "success" else "✗"
    print(f"{status} {result.action_target}: {result.duration_ms}ms")
```

### Fallback Finding

Find element with automatic fallback:

```python
# Try multiple strategies automatically
selector = engine.find_with_fallback(
    primary_selector="input[name='email']",
    field_type="email",
    semantic_context={"label_text": "Email Address"}
)

if selector:
    page.fill(selector, "test@example.com")
```

### Shadow DOM Handling

```python
# Automatic Shadow DOM piercing
selector = engine.handle_shadow_dom(
    selector="input[name='email']",
    shadow_host="custom-form"
)

if selector:
    page.fill(selector, "test@example.com")
```

### SPA Readiness

```python
# Wait for SPA hydration before interacting
success = engine.wait_for_spa_ready(timeout_ms=5000)

if success:
    # SPA is ready, safe to interact
    engine.execute(action)
```

---

## Complete Example

Putting it all together:

```python
from playwright.sync_api import sync_playwright
from jobcli.healing import SelfHealingEngine
from jobcli.execution import FillInputAction, ClickAction
from jobcli.profile.schemas import ATSType
from pathlib import Path

def apply_to_job():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://jobs.lever.co/company/position")

        # Initialize self-healing engine
        engine = SelfHealingEngine(
            page=page,
            ats_type=ATSType.LEVER,
            patterns_file=Path("selector_patterns.json"),
            enable_healing=True,
            enable_modern_web=True
        )

        # Wait for SPA hydration
        engine.wait_for_spa_ready()

        # Define actions
        actions = [
            FillInputAction(
                target="first_name",
                selector="input[name='name']",  # May need healing
                value="John",
                verify_after=True
            ),
            FillInputAction(
                target="email",
                selector="input[name='email']",
                value="john@example.com",
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

        # Execute with automatic healing
        results = engine.execute_batch(actions, stop_on_failure=True)

        # Report
        engine.print_summary()

        # Check modern web info
        web_info = engine.get_modern_web_info()
        if web_info:
            print(f"\nDetected: {web_info.framework.value} SPA")

        browser.close()

if __name__ == "__main__":
    apply_to_job()
```

---

## Healing Metrics

```python
metrics = engine.get_healing_metrics()

print(f"Total actions: {metrics.total_actions}")
print(f"Successful: {metrics.successful_actions}")
print(f"Failed: {metrics.failed_actions}")
print(f"Selectors healed: {metrics.selectors_healed}")
print(f"Healing success rate: {metrics.healing_success_rate:.2%}")
print(f"Modern web patterns: {metrics.modern_web_detections}")
```

---

## Configuration

### RetryConfig

```python
from jobcli.healing import RetryConfig

config = RetryConfig(
    max_retries=5,                      # Max retry attempts
    base_delay_ms=500,                  # Base delay
    max_delay_ms=10000,                 # Max delay (cap)
    jitter_factor=0.3,                  # Jitter (±30%)
    strategy="adaptive",                # Strategy
    high_confidence_threshold=0.8,      # High confidence
    low_confidence_threshold=0.5,       # Low confidence
    escalate_after_failures=3,          # Escalate after N failures
    escalate_on_low_confidence=True     # Escalate on low confidence
)
```

### SelfHealingEngine Options

```python
engine = SelfHealingEngine(
    page=page,
    ats_type=ATSType.LEVER,
    session_id="custom-session-id",          # Optional
    patterns_file=Path("patterns.json"),     # Historical patterns
    retry_config=retry_config,               # Retry config
    enable_healing=True,                     # Enable selector healing
    enable_modern_web=True                   # Enable modern web handling
)
```

---

## Best Practices

### 1. Enable Healing for New ATS Platforms

When adding support for a new ATS:
- Enable both healing and modern web handling
- Start with low confidence thresholds
- Monitor which selectors get healed
- Review historical patterns after testing

### 2. Tune Retry Configuration

For stable platforms:
```python
RetryConfig(
    max_retries=3,
    base_delay_ms=300,
    high_confidence_threshold=0.9
)
```

For flaky platforms:
```python
RetryConfig(
    max_retries=7,
    base_delay_ms=1000,
    high_confidence_threshold=0.7,
    escalate_after_failures=5
)
```

### 3. Monitor Healing Success Rate

```python
if metrics.healing_success_rate < 0.3:
    # Low healing rate - selectors may be fundamentally wrong
    print("⚠ Review selectors manually")
elif metrics.healing_success_rate > 0.8:
    # High healing rate - primary selectors are unreliable
    print("⚠ Update primary selectors with healed ones")
```

### 4. Use Semantic Context

Provide context to improve healing:

```python
result = healer.heal_selector(
    "input[name='email']",
    "email",
    semantic_context={
        "label_text": "Email Address",
        "placeholder": "Enter your email",
        "expected_value": "test@example.com"
    }
)
```

### 5. Review Historical Patterns

Periodically review and clean up patterns:

```python
summary = healer.get_patterns_summary()

# Promote high-success patterns to primary selectors
for pattern in summary['top_patterns']:
    if pattern['success_count'] > 20:
        print(f"Consider using: {pattern['selector']}")
```

---

## Limitations

### What Healing Can't Fix

1. **CAPTCHA challenges** - Requires human interaction
2. **Complex multi-step workflows** - Healing is per-field
3. **Completely redesigned forms** - All selectors change
4. **Authentication barriers** - Login still required

### When to Escalate to Human

- Persistent failures after healing (3+ attempts)
- Very low confidence (< 0.3) on critical fields
- Multiple related fields failing
- Security-sensitive fields (passwords, SSN)

---

## Integration with Execution Layer

The healing system wraps the execution layer:

```python
# Standard execution (no healing)
from jobcli.execution import ExecutionEngine

engine = ExecutionEngine(page, ats_type)
result = engine.execute(action)

# Self-healing execution
from jobcli.healing import SelfHealingEngine

healing_engine = SelfHealingEngine(page, ats_type, enable_healing=True)
result = healing_engine.execute(action)
# Automatically tries healing on failure
```

---

**The self-healing system is production-ready and dramatically improves reliability across different ATS platforms.**
