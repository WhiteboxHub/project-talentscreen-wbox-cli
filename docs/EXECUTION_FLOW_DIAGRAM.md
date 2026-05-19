# Execution Flow Diagram

Visual representation of the execution layer architecture and flow.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                          │
│  (Semantic Engine, ATS Handlers, Canonical Model)               │
│                                                                  │
│  • Detects fields                                               │
│  • Maps to canonical model                                      │
│  • Generates ExecutionActions                                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ Emits structured actions
                     │ (FillInput, Click, Select, Upload)
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Execution Engine                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │ 1. Pre-Validation                                   │       │
│  │    • Element exists? (count > 0)                    │       │
│  │    • Element visible? (unless file input)           │       │
│  │    • Emit selector_found / selector_not_found       │       │
│  └─────────────────────────────────────────────────────┘       │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │ 2. Execute Action                                   │       │
│  │    • fill_input: clear → fill                       │       │
│  │    • click_button: click (→ wait navigation)        │       │
│  │    • select_option: select with match strategy      │       │
│  │    • upload_file: set_input_files                   │       │
│  │    • wait: wait for appear/disappear/time           │       │
│  └─────────────────────────────────────────────────────┘       │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │ 3. Post-Verification (if verify_after=true)         │       │
│  │    • Read back value from DOM                       │       │
│  │    • Compare with expected                          │       │
│  │    • Emit verification_passed / verification_failed │       │
│  └─────────────────────────────────────────────────────┘       │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │ 4. Retry on Failure                                 │       │
│  │    • Exponential backoff: 500ms → 5000ms            │       │
│  │    • Jitter: ±30%                                   │       │
│  │    • Max retry_count attempts                       │       │
│  │    • Emit action_retrying events                    │       │
│  └─────────────────────────────────────────────────────┘       │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │ 5. Return ExecutionResult                           │       │
│  │    • status: success / failed                       │       │
│  │    • attempts: number of tries                      │       │
│  │    • duration_ms: total time                        │       │
│  │    • verified: was verification successful?         │       │
│  │    • error: error message if failed                 │       │
│  └─────────────────────────────────────────────────────┘       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ Uses
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Playwright Page (Browser)                      │
│                                                                  │
│  • DOM manipulation (fill, click, select)                       │
│  • Element queries (locator, count, visible)                    │
│  • State inspection (input_value, selectedOptions)              │
└─────────────────────────────────────────────────────────────────┘

                     ┌──────────────────┐
                     │                  │
                     │  Telemetry       │
                     │  Tracker         │
                     │                  │
                     │  • Events        │
                     │  • Metrics       │
                     │  • Analytics     │
                     │                  │
                     └──────────────────┘
                     (Global, all operations emit events)
```

## Retry Flow

```
attempt = 1

  ┌─────────────────────────────────────┐
  │  Execute Action                     │
  └──────────┬──────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────┐
  │  Success?                           │
  └──────────┬──────────────────────────┘
             │
             ├─ YES ─────────────────────────────► Return Success
             │
             └─ NO ───► Is attempt < retry_count?
                        │
                        ├─ YES ─────────────────┐
                        │                        │
                        │  ┌─────────────────────▼──────────────┐
                        │  │  Wait with Exponential Backoff     │
                        │  │                                     │
                        │  │  delay = min(500 * 2^(attempt-1),  │
                        │  │              5000)                  │
                        │  │  jitter = delay * 0.3 * random()   │
                        │  │  sleep(delay + jitter)             │
                        │  └─────────────────────┬──────────────┘
                        │                        │
                        │                        │
                        │  ┌─────────────────────▼──────────────┐
                        │  │  attempt++                         │
                        │  └─────────────────────┬──────────────┘
                        │                        │
                        │                        │
                        └────────────────────────┴──────────► Loop
                        │
                        └─ NO ─────────────────────────────► Return Failed
```

**Retry Delays:**
- Attempt 1 → 2: ~500ms (350-650ms with jitter)
- Attempt 2 → 3: ~1000ms (700-1300ms)
- Attempt 3 → 4: ~2000ms (1400-2600ms)
- Attempt 4+: ~5000ms (3500-6500ms, capped)

## Telemetry Event Flow

```
┌────────────────────┐
│ action_started     │  ← Emitted at start of execution
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ selector_found     │  ← Emitted during pre-validation
│ (or not_found)     │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ action_retrying    │  ← Emitted on retry (if needed)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ verification_      │  ← Emitted during post-verification
│ passed/failed      │    (if verify_after=true)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ action_succeeded   │  ← Emitted at end (success or failure)
│ (or failed)        │
└────────────────────┘

All events include:
• field: target field ID
• ats: ATS platform type
• session_id: application session
• timestamp: UTC timestamp
• duration_ms: operation duration
• confidence: confidence score
• metadata: additional context
```

## Batch Execution Flow

```
actions = [action1, action2, action3, ...]

  ┌─────────────────────────────────────┐
  │  For each action in batch:          │
  └──────────┬──────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────┐
  │  result = engine.execute(action)    │
  └──────────┬──────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────┐
  │  Add result to results list         │
  └──────────┬──────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────┐
  │  If result.status == FAILED AND     │
  │     action.verify_after == True:    │
  │                                      │
  │    → STOP (critical failure)        │
  └──────────┬──────────────────────────┘
             │
             └─ Continue to next action

Return all results
```

**Early Stopping:**
- Non-critical actions (`verify_after=false`): continue on failure
- Critical actions (`verify_after=true`): stop batch on failure

## Action Type Decision Tree

```
What do you want to do?

├─ Fill text? ────────────────────────► FillInputAction
│                                         • Email, phone, name
│                                         • Text areas
│                                         • Any text input
│
├─ Click element? ────────────────────► ClickAction
│                                         • Buttons
│                                         • Links
│                                         • Checkboxes
│
├─ Select from dropdown? ─────────────► SelectOptionAction
│                                         • Country, state
│                                         • Industry, role
│                                         • Any <select>
│
├─ Upload file? ──────────────────────► UploadFileAction
│                                         • Resume (PDF, DOCX)
│                                         • Cover letter
│                                         • Portfolio files
│
└─ Wait for something? ───────────────► WaitAction
                                          • Loading spinner
                                          • Modal appears
                                          • Dynamic content
```

## State Machine

```
ExecutionEngine State:

┌──────────────────┐
│  IDLE            │
│  (initialized)   │
└────────┬─────────┘
         │
         │ execute(action)
         ▼
┌──────────────────┐
│  VALIDATING      │  ← Pre-validation
│  (checking DOM)  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  EXECUTING       │  ← Action execution
│  (fill/click/etc)│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  VERIFYING       │  ← Post-verification
│  (read back)     │    (if verify_after=true)
└────────┬─────────┘
         │
         ├─ Success ────────► executed_actions.append(result)
         │                    └─► IDLE
         │
         └─ Failure ───┬───► retry? ──YES──► VALIDATING (retry loop)
                       │
                       └───► retry? ──NO───► failed_actions.append(result)
                                             └─► IDLE
```

## Telemetry Aggregation

```
Raw Events (TelemetryTracker.events)
  │
  │ Filter by event_type, ats, session_id
  ▼
Filtered Events
  │
  │ Aggregate
  ▼
Metrics:

├─ Field Detection Rate
│    = (events with confidence ≥ 0.6) / total field_detected events
│
├─ Fill Success Rate
│    = field_fill_succeeded / (field_fill_succeeded + field_fill_failed)
│
├─ Retry Statistics
│    = avg(retry_count), max(retry_count), count(retry_count > 0)
│
├─ ATS Reliability
│    = {ATSType: fill_success_rate} for each ATS
│
├─ Selector Failure Rate
│    = selector_not_found / (selector_found + selector_not_found)
│
├─ Human Override Rate
│    = human_override_provided / field_detected
│
└─ Confidence Accuracy
     = {
       high (≥0.8): success_rate,
       medium (0.6-0.8): success_rate,
       low (<0.6): success_rate
     }
```

## Data Flow

```
User Resume Data
  │
  ▼
┌─────────────────┐
│ Canonical Model │  ← Field ID, semantic type, value
└────────┬────────┘
         │
         │ Map to selectors
         ▼
┌─────────────────┐
│ ExecutionAction │  ← target, selector, value, config
└────────┬────────┘
         │
         │ Pass to engine
         ▼
┌─────────────────┐
│ ExecutionEngine │  ← Executes with retries, validation
└────────┬────────┘
         │
         │ Returns result
         ▼
┌─────────────────┐
│ ExecutionResult │  ← status, attempts, duration, verified, error
└────────┬────────┘
         │
         └─► Application logic (continue / stop / retry)

Side effects:
├─► Telemetry events emitted
├─► Engine state updated (executed_actions, failed_actions)
└─► DOM modified (fields filled, buttons clicked)
```

## Integration Example

```
                    ┌───────────────┐
                    │ Job Posting   │
                    │ (URL)         │
                    └───────┬───────┘
                            │
                            │ page.goto()
                            ▼
                    ┌───────────────┐
                    │ Browser Page  │
                    │ (Playwright)  │
                    └───────┬───────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
┌────────────────┐  ┌──────────────┐  ┌──────────────┐
│ ATS Detector   │  │ Semantic     │  │ Canonical    │
│                │  │ Engine       │  │ Model        │
│ → ATSType      │  │              │  │              │
└────────┬───────┘  │ → Fields     │  │ → Fields     │
         │          │ → Types      │  │ → Selectors  │
         │          └──────┬───────┘  └──────┬───────┘
         │                 │                 │
         │                 └────────┬────────┘
         │                          │
         └──────────────────────────┼──────────────────┐
                                    │                  │
                                    ▼                  │
                          ┌─────────────────┐          │
                          │ Generate        │          │
                          │ ExecutionActions│          │
                          └────────┬────────┘          │
                                   │                   │
                                   ▼                   ▼
                          ┌─────────────────┐  ┌──────────────┐
                          │ ExecutionEngine │  │ Telemetry    │
                          │                 │  │ Tracker      │
                          │ → execute()     │──┤ → emit()     │
                          │ → verify()      │  │ → metrics()  │
                          └────────┬────────┘  └──────────────┘
                                   │
                                   │ Results
                                   ▼
                          ┌─────────────────┐
                          │ Application     │
                          │ Logic           │
                          │                 │
                          │ → Success?      │
                          │ → Retry?        │
                          │ → Human input?  │
                          └─────────────────┘
```

---

**Summary**: The execution layer provides a clean separation between **what to do** (actions) and **how to do it** (engine), with comprehensive telemetry for learning and debugging.
