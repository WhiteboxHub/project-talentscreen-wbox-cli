# Execution Action Reference

Quick reference for all execution action types in JobCLI.

## Action Schema Format

All actions follow this base structure:

```python
{
    "action": "<action_type>",         # Type of action
    "target": "<field_id>",            # Canonical field ID
    "selector": "<css_selector>",      # CSS/XPath selector
    "verify_after": true|false,        # Verify success?
    "timeout_ms": 5000,                # Timeout per attempt
    "retry_count": 3                   # Max retry attempts
}
```

---

## 1. FillInputAction

Fill a text input, textarea, or contenteditable field.

### Schema

```python
{
    "action": "fill_input",
    "target": "candidate_email",
    "selector": "input[name='email']",
    "value": "user@email.com",
    "verify_after": true,
    "clear_first": true,
    "timeout_ms": 5000,
    "retry_count": 3
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | `"fill_input"` | ✓ | - | Action type |
| `target` | `string` | ✓ | - | Field ID from canonical model |
| `selector` | `string` | ✓ | - | CSS/XPath selector |
| `value` | `string` | ✓ | - | Value to fill |
| `verify_after` | `boolean` | | `true` | Read back and verify value? |
| `clear_first` | `boolean` | | `true` | Clear existing value first? |
| `timeout_ms` | `integer` | | `5000` | Timeout per attempt (ms) |
| `retry_count` | `integer` | | `3` | Max retry attempts |

### Use Cases

- Email addresses
- Phone numbers
- Text fields
- Text areas
- Names, addresses
- Any input that accepts text

### Python Example

```python
from jobcli.execution import FillInputAction

action = FillInputAction(
    target="candidate_email",
    selector="input[name='email']",
    value="john.doe@example.com",
    verify_after=True,
    clear_first=True
)

result = engine.execute(action)
```

### Verification

When `verify_after=true`:
1. Reads back value using `.input_value()`
2. Compares with expected value (normalized, trimmed)
3. Emits `verification_passed` or `verification_failed`

---

## 2. ClickAction

Click a button, link, or clickable element.

### Schema

```python
{
    "action": "click_button",
    "target": "submit_button",
    "selector": "button[type='submit']",
    "verify_after": false,
    "wait_for_navigation": true,
    "timeout_ms": 5000,
    "retry_count": 3
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | `"click_button"` | ✓ | - | Action type |
| `target` | `string` | ✓ | - | Field ID from canonical model |
| `selector` | `string` | ✓ | - | CSS/XPath selector |
| `verify_after` | `boolean` | | `false` | Verify click succeeded? |
| `wait_for_navigation` | `boolean` | | `false` | Wait for page load after click? |
| `timeout_ms` | `integer` | | `5000` | Timeout per attempt (ms) |
| `retry_count` | `integer` | | `3` | Max retry attempts |

### Use Cases

- Submit buttons
- "Next" / "Continue" buttons
- Links
- Checkboxes (alternative to fill)
- Radio buttons
- Any clickable element

### Python Example

```python
from jobcli.execution import ClickAction

action = ClickAction(
    target="submit_button",
    selector="button[type='submit']",
    wait_for_navigation=True,
    verify_after=False
)

result = engine.execute(action)
```

### Navigation Wait

When `wait_for_navigation=true`:
1. Clicks the element
2. Waits for `networkidle` state
3. Times out if navigation doesn't complete

---

## 3. SelectOptionAction

Select an option from a `<select>` dropdown.

### Schema

```python
{
    "action": "select_option",
    "target": "country_field",
    "selector": "select[name='country']",
    "value": "United States",
    "match_strategy": "exact",
    "verify_after": true,
    "timeout_ms": 5000,
    "retry_count": 3
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | `"select_option"` | ✓ | - | Action type |
| `target` | `string` | ✓ | - | Field ID from canonical model |
| `selector` | `string` | ✓ | - | CSS/XPath selector for `<select>` |
| `value` | `string` | ✓ | - | Option to select (by label text) |
| `match_strategy` | `"exact"` \| `"contains"` \| `"fuzzy"` | | `"exact"` | How to match option text |
| `verify_after` | `boolean` | | `true` | Verify option is selected? |
| `timeout_ms` | `integer` | | `5000` | Timeout per attempt (ms) |
| `retry_count` | `integer` | | `3` | Max retry attempts |

### Match Strategies

**Exact**: Option text must match exactly
```python
value="United States"  # Matches <option>United States</option>
```

**Contains**: Option text contains the value (case-insensitive)
```python
value="States"  # Matches <option>United States</option>
```

**Fuzzy**: Fuzzy matching (not fully implemented - falls back to exact)

### Use Cases

- Country dropdowns
- State/province selectors
- Industry/role dropdowns
- Any `<select>` element

### Python Example

```python
from jobcli.execution import SelectOptionAction

action = SelectOptionAction(
    target="country",
    selector="select[name='country']",
    value="United States",
    match_strategy="exact",
    verify_after=True
)

result = engine.execute(action)
```

### Verification

When `verify_after=true`:
1. Reads `selectedOptions[0].text`
2. Checks if it contains the value (case-insensitive)
3. Emits `verification_passed` or `verification_failed`

---

## 4. UploadFileAction

Upload a file to an `<input type="file">` element.

### Schema

```python
{
    "action": "upload_file",
    "target": "resume_upload",
    "selector": "input[type='file']",
    "file_path": "/path/to/resume.pdf",
    "verify_after": true,
    "timeout_ms": 10000,
    "retry_count": 3
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | `"upload_file"` | ✓ | - | Action type |
| `target` | `string` | ✓ | - | Field ID from canonical model |
| `selector` | `string` | ✓ | - | CSS/XPath selector for file input |
| `file_path` | `string` | ✓ | - | Absolute path to file |
| `verify_after` | `boolean` | | `true` | Verify file was uploaded? |
| `timeout_ms` | `integer` | | `5000` | Timeout per attempt (ms) |
| `retry_count` | `integer` | | `3` | Max retry attempts |

### Use Cases

- Resume uploads (PDF, DOCX)
- Cover letter uploads
- Portfolio files
- Any file upload

### Python Example

```python
from jobcli.execution import UploadFileAction

action = UploadFileAction(
    target="resume",
    selector="input[type='file'][name='resume']",
    file_path="/Users/john/Documents/resume.pdf",
    verify_after=True,
    timeout_ms=10000  # Longer timeout for large files
)

result = engine.execute(action)
```

### Verification

When `verify_after=true`:
1. Reads `element.files.length`
2. Checks if > 0 (file was set)
3. Emits `verification_passed` or `verification_failed`

### Notes

- File input elements don't need to be visible (pre-validation skips visibility check)
- File path must be absolute
- File must exist and be readable

---

## 5. WaitAction

Wait for an element to appear/disappear or wait for a fixed time.

### Schema

```python
{
    "action": "wait",
    "target": "loading_spinner",
    "selector": ".spinner",
    "wait_type": "disappear",
    "verify_after": false,
    "timeout_ms": 10000,
    "retry_count": 1
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | `"wait"` | ✓ | - | Action type |
| `target` | `string` | ✓ | - | Field ID from canonical model |
| `selector` | `string` | ✓ | - | CSS/XPath selector |
| `wait_type` | `"appear"` \| `"disappear"` \| `"time"` | | `"appear"` | What to wait for |
| `verify_after` | `boolean` | | `false` | Wait actions don't verify |
| `timeout_ms` | `integer` | | `5000` | Timeout for wait (ms) |
| `retry_count` | `integer` | | `3` | Max retry attempts |

### Wait Types

**Appear**: Wait for element to become visible
```python
wait_type="appear"  # Wait for .modal to appear
```

**Disappear**: Wait for element to become hidden
```python
wait_type="disappear"  # Wait for .spinner to disappear
```

**Time**: Wait for fixed duration
```python
wait_type="time"
timeout_ms=2000  # Wait 2 seconds
```

### Use Cases

- Wait for loading spinners to disappear
- Wait for modals to appear
- Wait for dynamic content to load
- Add delay between actions
- Wait for animations to complete

### Python Example

```python
from jobcli.execution import WaitAction

# Wait for spinner to disappear
action = WaitAction(
    target="loading",
    selector=".spinner",
    wait_type="disappear",
    timeout_ms=10000
)

result = engine.execute(action)
```

### Notes

- `verify_after` is always `false` for wait actions
- For `wait_type="time"`, the `timeout_ms` is the duration to wait

---

## 6. VerifyAction

Verify element state without modifying it (not fully implemented).

### Schema

```python
{
    "action": "verify",
    "target": "email_field",
    "selector": "input[name='email']",
    "check_type": "value",
    "expected_value": "user@email.com",
    "verify_after": false,
    "timeout_ms": 5000,
    "retry_count": 1
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | `"verify"` | ✓ | - | Action type |
| `target` | `string` | ✓ | - | Field ID from canonical model |
| `selector` | `string` | ✓ | - | CSS/XPath selector |
| `check_type` | `"exists"` \| `"visible"` \| `"value"` \| `"text"` | | `"exists"` | What to verify |
| `expected_value` | `string` | | `null` | Expected value (for value/text checks) |
| `verify_after` | `boolean` | | `false` | Verify actions don't need verification |
| `timeout_ms` | `integer` | | `5000` | Timeout per attempt (ms) |
| `retry_count` | `integer` | | `3` | Max retry attempts |

### Use Cases

- Verify field was filled by external script (e.g., browser extension)
- Verify page state before proceeding
- Assert expected values

**Note**: This action type is defined but not fully implemented in the execution engine. Use `FillInputAction` with `verify_after=true` for most verification needs.

---

## Common Patterns

### Pattern 1: Fill Critical Field with Verification

```python
FillInputAction(
    target="email",
    selector="input[name='email']",
    value="john@example.com",
    verify_after=True,        # ✓ Verify
    clear_first=True,
    timeout_ms=5000,
    retry_count=3
)
```

### Pattern 2: Fill Optional Field (Fast)

```python
FillInputAction(
    target="linkedin",
    selector="input[name='linkedin']",
    value="https://linkedin.com/in/john",
    verify_after=False,       # Skip verification
    retry_count=1             # Fail fast
)
```

### Pattern 3: Click with Navigation

```python
ClickAction(
    target="next_button",
    selector="button.next",
    wait_for_navigation=True,  # Wait for page load
    timeout_ms=10000           # Longer timeout for navigation
)
```

### Pattern 4: Wait for Loading

```python
# Wait for spinner to disappear before filling
WaitAction(
    target="spinner",
    selector=".loading-spinner",
    wait_type="disappear",
    timeout_ms=10000
)
```

### Pattern 5: Upload Resume

```python
UploadFileAction(
    target="resume",
    selector="input[type='file']",
    file_path="/path/to/resume.pdf",
    verify_after=True,
    timeout_ms=15000,          # Longer timeout for uploads
    retry_count=5              # More retries for critical file
)
```

### Pattern 6: Select with Fuzzy Match

```python
SelectOptionAction(
    target="country",
    selector="select[name='country']",
    value="States",            # Will match "United States"
    match_strategy="contains",
    verify_after=True
)
```

---

## Action Execution Flow

For every action:

```
1. Emit action_started event
2. Loop (attempt = 1 to retry_count):
   a. Pre-validation:
      - Element exists? (count > 0)
      - Element visible? (unless file input)
      → If fails: retry or fail
   b. Execute:
      - Perform action (fill, click, select, upload, wait)
      → If exception: retry or fail
   c. Post-verification (if verify_after=true):
      - Read back value/state
      - Compare with expected
      → If mismatch: retry or fail
   d. Success:
      - Emit success event
      - Return result with status="success"
   e. Failure (attempt < retry_count):
      - Wait with exponential backoff
      - Continue to next attempt
3. Max retries exhausted:
   - Emit failure event
   - Return result with status="failed"
```

---

## Best Practices

### 1. Always verify critical fields

```python
# ✓ Good: Verify email
FillInputAction(target="email", verify_after=True, ...)

# ✗ Bad: Skip verification for critical field
FillInputAction(target="email", verify_after=False, ...)
```

### 2. Use appropriate retry counts

```python
# ✓ Good: More retries for important uploads
UploadFileAction(retry_count=5, ...)

# ✓ Good: Fewer retries for fast selector checks
FillInputAction(retry_count=1, ...)
```

### 3. Set realistic timeouts

```python
# ✓ Good: Longer timeout for file uploads
UploadFileAction(timeout_ms=15000, ...)

# ✓ Good: Shorter timeout for simple fills
FillInputAction(timeout_ms=3000, ...)
```

### 4. Use clear_first judiciously

```python
# ✓ Good: Clear pre-filled email
FillInputAction(target="email", clear_first=True, ...)

# ✓ Good: Don't clear append-only fields
FillInputAction(target="notes", clear_first=False, ...)
```

### 5. Wait before filling dynamic content

```python
# ✓ Good: Wait for modal, then fill
WaitAction(target="modal", wait_type="appear", ...)
FillInputAction(target="field_in_modal", ...)

# ✗ Bad: Fill immediately (field may not exist yet)
FillInputAction(target="field_in_modal", ...)
```

---

## Telemetry Events

Each action emits structured events:

```json
{
  "event": "action_started | action_succeeded | action_failed",
  "field": "candidate_email",
  "ats": "greenhouse",
  "success": true,
  "duration_ms": 234,
  "retry_count": 0,
  "confidence": 1.0,
  "metadata": {"action_type": "fill_input", "selector": "input[name='email']"}
}
```

Track these metrics:
- Fill success rate per ATS
- Average retry count per field
- Selector failure rate
- Action duration percentiles

---

**Next Steps**: See [EXECUTION_LAYER.md](./EXECUTION_LAYER.md) for comprehensive usage guide.
