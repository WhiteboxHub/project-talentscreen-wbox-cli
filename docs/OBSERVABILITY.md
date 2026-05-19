# Observability System

Complete traceability for every application run through structured logging and hierarchical trace IDs.

## Overview

Every action in JobCLI is traceable through a 5-level ID hierarchy:

```
session_id → application_id → job_id → attempt_id → trace_id
```

This enables:
- Full execution reconstruction
- Failure analysis across applications
- Performance metrics per ATS
- Session-level success tracking
- Individual operation debugging

## Architecture

### 1. Trace Context (`trace_context.py`)

Manages the ID hierarchy and propagates context through execution.

#### ID Hierarchy

```python
class TraceContext:
    session_id: str       # User session (multiple applications)
    application_id: str   # Single job application
    job_id: str          # Specific job posting
    attempt_id: str      # Retry attempt number
    trace_id: str        # Individual operation
    parent_trace_id: str # For nested operations
```

**ID Generation**:
- `session_id`: `session_20260519_123456_abc12345`
- `application_id`: `app_20260519_120000_abc12345`
- `job_id`: `job_a1b2c3d4` (deterministic from company + position)
- `attempt_id`: `app_20260519_120000_abc12345_attempt_1`
- `trace_id`: `trace_1234567890abcdef`

#### Context Propagation

Context is stored in a `ContextVar`, automatically propagating through async operations and threads.

```python
from jobcli.observability import (
    create_trace_context,
    set_trace_context,
    get_trace_context,
)

# Create context
context = create_trace_context(
    session_id="session_20260519_123456",
    company_name="Google",
    position_title="Software Engineer",
    attempt_number=1,
    operation="fill_application_form"
)

# Set as current
set_trace_context(context)

# Get current context
current = get_trace_context()
print(current.trace_id)  # trace_1234567890abcdef
```

#### Context Manager

Use `with_trace_context()` for scoped context:

```python
from jobcli.observability import with_trace_context

with with_trace_context(context):
    # All operations here have this context
    logger.info("Inside context")
    # Logs include: session_id, application_id, job_id, attempt_id, trace_id
```

#### Operation Tracing Decorator

Automatically create child traces for operations:

```python
from jobcli.observability import trace_operation, get_logger

logger = get_logger("form_filler")

@trace_operation("fill_field")
def fill_field(field_id: str, value: str):
    """Automatically traced with child context."""
    logger.info("Filling field", field_id=field_id)
    # Creates child trace: parent_trace_id = current trace_id
    # New trace_id generated for this operation
```

#### Child Traces

Create nested operations:

```python
# Parent operation
parent_context = get_trace_context()

# Create child trace
child_context = parent_context.with_new_trace("fill_email_field")

with with_trace_context(child_context):
    logger.info("Filling email")
    # child_context.parent_trace_id == parent_context.trace_id
```

#### Retry Attempts

Create new context for retry attempts:

```python
# First attempt
context = create_trace_context(
    session_id="session_123",
    company_name="Google",
    position_title="SWE",
    attempt_number=1
)

# Retry (attempt 2)
retry_context = context.with_attempt(2)
# New attempt_id: app_xxx_attempt_2
# New trace_id
```

### 2. Structured Logger (`structured_logger.py`)

Logs with automatic trace context injection.

#### Log Entry Format

```python
class StructuredLogEntry:
    timestamp: datetime
    level: LogLevel  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message: str
    
    # Trace context (auto-injected)
    session_id: str
    application_id: str
    job_id: str
    attempt_id: str
    trace_id: str
    
    # Operation context
    operation: str
    component: str
    
    # Additional data
    data: Dict[str, Any]
    
    # Error info
    error_type: str
    error_message: str
    stack_trace: str
```

#### Logger Usage

```python
from jobcli.observability import get_logger

logger = get_logger("execution_engine")

# Info log
logger.info("Starting application", company="Google")

# Debug log
logger.debug("Found form field", field_id="email", selector="#email-input")

# Warning log
logger.warning("Low confidence", confidence=0.65, field="phone")

# Error log
try:
    fill_field()
except Exception as e:
    logger.error("Field fill failed", error=e, field_id="email")

# Critical log
logger.critical("Session aborted", reason="timeout", elapsed_ms=30000)
```

#### JSON Output

Logs are written in JSON format (one per line):

```json
{
  "timestamp": "2026-05-19T12:34:56.789000",
  "level": "info",
  "message": "Starting application",
  "session_id": "session_20260519_123456",
  "application_id": "app_20260519_120000_abc123",
  "job_id": "job_a1b2c3d4",
  "attempt_id": "app_20260519_120000_abc123_attempt_1",
  "trace_id": "trace_1234567890abcdef",
  "component": "execution_engine",
  "operation": "fill_application_form",
  "data": {
    "company": "Google"
  }
}
```

#### Logger Configuration

```python
from jobcli.observability import LoggerFactory
from pathlib import Path

# Configure all loggers
LoggerFactory.configure(
    log_dir=Path("logs"),           # Directory for log files
    console_output=True,             # Print to console?
    json_format=False                # Human-readable console output
)

# Get component-specific logger
logger = get_logger("form_filler")
# Logs to: logs/form_filler.log

# Close all loggers
LoggerFactory.close_all()
```

#### Human-Readable Console Output

When `json_format=False`:

```
12:34:56.789 [INFO] [execution_engine] [trace_1234567890abcdef] [fill_form] Starting application
  Data: {"company": "Google"}
12:34:57.123 [ERROR] [form_filler] [trace_abcdef1234567890] [fill_field] Field not found
  Error: SelectorNotFoundError: Could not find selector #email
```

### 3. Trace Analyzer (`trace_analyzer.py`)

Analyzes structured logs to provide insights.

#### Session Statistics

```python
from jobcli.observability import TraceAnalyzer
from pathlib import Path

analyzer = TraceAnalyzer(Path("logs/application.log"))

# Get session statistics
stats = analyzer.get_session_statistics("session_20260519_123456")

print(f"Session: {stats.session_id}")
print(f"Duration: {stats.total_duration_ms}ms")
print(f"Applications: {stats.total_applications}")
print(f"Successful: {stats.successful_applications}")
print(f"Failed: {stats.failed_applications}")
print(f"Total logs: {stats.total_log_entries}")
print(f"Errors: {stats.error_count}")
print(f"Warnings: {stats.warning_count}")
print(f"Traces: {stats.total_traces}")

# Analyze individual traces
for trace in stats.traces:
    if not trace.success:
        print(f"\nFailed trace: {trace.trace_id}")
        print(f"Operation: {trace.operation}")
        print(f"Duration: {trace.duration_ms}ms")
        print(f"Errors: {trace.error_count}")
        for error in trace.errors:
            print(f"  - {error}")
```

#### Find Failed Applications

```python
# Get all failed application IDs
failed_apps = analyzer.find_failed_applications()

print(f"Failed applications: {len(failed_apps)}")
for app_id in failed_apps:
    print(f"  - {app_id}")
```

#### Find Slow Operations

```python
# Find operations taking >5 seconds
slow_ops = analyzer.find_slow_operations(threshold_ms=5000)

for trace_id, duration_ms, operation in slow_ops:
    print(f"{operation}: {duration_ms}ms (trace: {trace_id})")
```

#### Error Summary

```python
summary = analyzer.get_error_summary()

print(f"Total errors: {summary['total_errors']}")
print(f"Most common: {summary['most_common_error']}")

print("\nBy type:")
for error_type, count in summary['by_type'].items():
    print(f"  {error_type}: {count}")

print("\nBy component:")
for component, count in summary['by_component'].items():
    print(f"  {component}: {count}")

print("\nBy operation:")
for operation, count in summary['by_operation'].items():
    print(f"  {operation}: {count}")
```

#### Reconstruct Execution Flow

```python
# Get all log entries for a trace (sorted by time)
trace_entries = analyzer.reconstruct_execution_flow("trace_1234567890abcdef")

for entry in trace_entries:
    print(f"{entry.timestamp} [{entry.level}] {entry.message}")
    if entry.data:
        print(f"  Data: {entry.data}")
```

#### Export Session Report

```python
# Export human-readable report
analyzer.export_session_report(
    session_id="session_20260519_123456",
    output_file=Path("reports/session_report.txt")
)
```

**Report format**:

```
======================================================================
SESSION REPORT: session_20260519_123456
======================================================================

Duration: 45230ms
Start: 2026-05-19 12:34:56
End: 2026-05-19 12:35:41

Applications: 5
  Successful: 3
  Failed: 2

Log Entries: 342
  Errors: 8
  Warnings: 15

Traces: 47

Failed Traces (2):
  - trace_abc123
    Operation: fill_email_field
    Duration: 3450ms
    Errors: 2
      • Element not found: #email-input
      • Timeout waiting for selector

  - trace_def456
    Operation: upload_resume
    Duration: 12300ms
    Errors: 1
      • File upload failed: Permission denied

Slow Traces (>5s) (3):
  - trace_ghi789
    Operation: wait_for_page_load
    Duration: 8900ms

======================================================================
```

## Usage Examples

### Example 1: Single Application with Tracing

```python
from jobcli.observability import (
    create_trace_context,
    set_trace_context,
    get_logger,
)
from pathlib import Path

# Configure logging
from jobcli.observability import LoggerFactory
LoggerFactory.configure(
    log_dir=Path("logs"),
    console_output=True,
    json_format=False
)

# Create session
session_id = "session_20260519_123456"

# Create trace context for application
context = create_trace_context(
    session_id=session_id,
    company_name="Google",
    position_title="Software Engineer",
    attempt_number=1,
    operation="submit_application"
)

# Set as current context
set_trace_context(context)

# Get logger
logger = get_logger("application_engine")

# Log with automatic trace context
logger.info("Starting application", company="Google", position="Software Engineer")

# Simulate application steps
logger.info("Detected ATS", ats_type="greenhouse")
logger.debug("Found form fields", field_count=12)
logger.info("Filled basic info", fields=["name", "email", "phone"])
logger.warning("Low confidence on field", field="linkedin_url", confidence=0.65)

try:
    # Simulate failure
    raise ValueError("Invalid resume format")
except Exception as e:
    logger.error("Resume upload failed", error=e)

logger.info("Application completed", status="partial")

# Close loggers
LoggerFactory.close_all()
```

### Example 2: Multi-Application Session with Analysis

```python
from jobcli.observability import (
    create_trace_context,
    set_trace_context,
    get_logger,
    TraceAnalyzer,
)
from pathlib import Path

logger = get_logger("batch_processor")
log_file = Path("logs/batch.log")

session_id = "session_20260519_140000"

companies = [
    ("Google", "Software Engineer"),
    ("Meta", "Frontend Engineer"),
    ("Amazon", "Backend Engineer"),
]

# Apply to multiple companies
for company, position in companies:
    context = create_trace_context(
        session_id=session_id,
        company_name=company,
        position_title=position,
        attempt_number=1,
        operation="batch_apply"
    )
    
    set_trace_context(context)
    
    logger.info("Starting application", company=company, position=position)
    
    # Simulate application
    # ... (fill forms, upload resume, etc.)
    
    logger.info("Application submitted", company=company)

# Analyze session
analyzer = TraceAnalyzer(log_file)
stats = analyzer.get_session_statistics(session_id)

print(f"\nSession Summary:")
print(f"  Total applications: {stats.total_applications}")
print(f"  Successful: {stats.successful_applications}")
print(f"  Failed: {stats.failed_applications}")
print(f"  Success rate: {stats.successful_applications / stats.total_applications:.1%}")
print(f"  Total duration: {stats.total_duration_ms}ms")

# Export report
analyzer.export_session_report(
    session_id,
    Path(f"reports/{session_id}_report.txt")
)
```

### Example 3: Retry with New Attempt Context

```python
from jobcli.observability import (
    create_trace_context,
    set_trace_context,
    get_logger,
)

logger = get_logger("retry_handler")

# Initial attempt
context = create_trace_context(
    session_id="session_123",
    company_name="Google",
    position_title="SWE",
    attempt_number=1,
    operation="fill_form"
)

set_trace_context(context)
logger.info("Attempt 1 started")

# Simulate failure
logger.error("Attempt 1 failed", reason="timeout")

# Retry with new attempt context
retry_context = context.with_attempt(2)
set_trace_context(retry_context)
logger.info("Attempt 2 started")

# Retry again
retry_context_2 = context.with_attempt(3)
set_trace_context(retry_context_2)
logger.info("Attempt 3 started")
logger.info("Attempt 3 succeeded")

# All three attempts share the same session_id, application_id, job_id
# But have different attempt_id and trace_id
```

### Example 4: Nested Operations with Child Traces

```python
from jobcli.observability import (
    trace_operation,
    get_logger,
    get_trace_context,
)

logger = get_logger("form_filler")

@trace_operation("fill_application_form")
def fill_application_form():
    logger.info("Starting form fill")
    
    fill_basic_info()
    fill_work_experience()
    upload_resume()
    
    logger.info("Form fill complete")

@trace_operation("fill_basic_info")
def fill_basic_info():
    logger.info("Filling basic info")
    # Each call creates a child trace
    # parent_trace_id = fill_application_form's trace_id

@trace_operation("fill_work_experience")
def fill_work_experience():
    logger.info("Filling work experience")

@trace_operation("upload_resume")
def upload_resume():
    logger.info("Uploading resume")
    logger.error("Upload failed", reason="file_too_large")

# When called, creates trace hierarchy:
# trace_123456 (fill_application_form)
#   ├─ trace_234567 (fill_basic_info)
#   ├─ trace_345678 (fill_work_experience)
#   └─ trace_456789 (upload_resume)

fill_application_form()
```

## Integration with Other Systems

### With Execution Engine

```python
from jobcli.execution import ExecutionEngine
from jobcli.observability import (
    create_trace_context,
    set_trace_context,
    get_logger,
)

# Create context
context = create_trace_context(
    session_id="session_123",
    company_name="Google",
    position_title="SWE",
    attempt_number=1,
    operation="execute_application"
)

set_trace_context(context)

# Create engine with traced logger
logger = get_logger("execution_engine")
engine = ExecutionEngine(page, logger)

# All engine operations are now traced
result = engine.execute(action)

# Logs include full trace context
```

### With Self-Healing Engine

```python
from jobcli.healing import SelfHealingEngine
from jobcli.observability import (
    create_trace_context,
    set_trace_context,
    get_logger,
)

context = create_trace_context(
    session_id="session_123",
    company_name="Google",
    position_title="SWE",
    attempt_number=1,
    operation="self_healing_execution"
)

set_trace_context(context)

logger = get_logger("self_healing")
healing_engine = SelfHealingEngine(page, logger)

# Healing attempts are traced
result = healing_engine.execute(action)

# Can trace:
# - Original selector attempt
# - Healing strategy attempts
# - Success/failure of each strategy
```

### With Application Memory

```python
from jobcli.memory import ApplicationMemory
from jobcli.observability import get_trace_context, get_logger

logger = get_logger("memory_system")
memory = ApplicationMemory()

# Get current context
context = get_trace_context()

# Create application record with trace IDs
app = memory.create_application(
    company_name="Google",
    position_title="SWE",
    ats_type="greenhouse"
)

logger.info(
    "Created application record",
    application_id=app.application_id,
    company=app.company_name
)

# Update with outcome
memory.update_application(
    app.application_id,
    status="submitted",
    callback_received=True
)

logger.info(
    "Application outcome recorded",
    application_id=app.application_id,
    status="submitted"
)
```

## Best Practices

### 1. Always Set Context Early

```python
# ✅ GOOD: Set context before any operations
context = create_trace_context(...)
set_trace_context(context)

logger = get_logger("engine")
logger.info("Starting")  # Includes trace context

# ❌ BAD: Log before setting context
logger = get_logger("engine")
logger.info("Starting")  # Missing trace context!

set_trace_context(context)
```

### 2. Use Context Managers for Scoped Operations

```python
# ✅ GOOD: Use context manager
parent_context = get_trace_context()
child_context = parent_context.with_new_trace("sub_operation")

with with_trace_context(child_context):
    # Context is active here
    perform_operation()
# Context is restored here

# ❌ BAD: Manual context switching (error-prone)
parent_context = get_trace_context()
child_context = parent_context.with_new_trace("sub_operation")
set_trace_context(child_context)
perform_operation()
set_trace_context(parent_context)  # Easy to forget!
```

### 3. Use Decorators for Traced Functions

```python
# ✅ GOOD: Use decorator
@trace_operation("fill_field")
def fill_field(field_id, value):
    # Automatically traced
    pass

# ❌ BAD: Manual child trace creation
def fill_field(field_id, value):
    context = get_trace_context()
    child = context.with_new_trace("fill_field")
    with with_trace_context(child):
        # More boilerplate
        pass
```

### 4. Include Rich Context in Logs

```python
# ✅ GOOD: Include relevant data
logger.info(
    "Field filled",
    field_id="email",
    selector="#email-input",
    value_length=25,
    duration_ms=120
)

# ❌ BAD: Vague message
logger.info("Field filled")
```

### 5. Log Errors with Exceptions

```python
# ✅ GOOD: Pass exception for full details
try:
    fill_field()
except Exception as e:
    logger.error("Field fill failed", error=e, field_id="email")
    # Includes error_type, error_message, stack_trace

# ❌ BAD: String-only error
except Exception as e:
    logger.error(f"Error: {e}")
    # No stack trace, no structured error info
```

### 6. Use Different Attempt IDs for Retries

```python
# ✅ GOOD: New attempt context for retries
context = create_trace_context(..., attempt_number=1)
set_trace_context(context)

try:
    apply()
except Exception:
    # Retry with new attempt
    retry_context = context.with_attempt(2)
    set_trace_context(retry_context)
    apply()

# ❌ BAD: Same context for retries (can't distinguish attempts)
context = create_trace_context(..., attempt_number=1)
set_trace_context(context)

try:
    apply()
except Exception:
    apply()  # Same context!
```

## Performance Considerations

### Log File Size

Structured logs in JSON format are verbose. For long sessions:

- Rotate log files daily
- Compress old logs
- Archive after analysis

### Context Propagation Overhead

ContextVar has minimal overhead (~nanoseconds per access). Safe to use in hot paths.

### Analysis Performance

TraceAnalyzer loads entire log file into memory. For very large logs (>100MB):

- Process in chunks
- Use streaming analysis
- Index by session_id/application_id

## Summary

The observability system provides complete traceability for JobCLI:

1. **Trace Context**: 5-level ID hierarchy (session → application → job → attempt → trace)
2. **Structured Logger**: Automatic trace context injection into all logs
3. **Trace Analyzer**: Reconstruct execution, analyze failures, generate reports

**Key features**:
- ✅ Every action is traceable through hierarchical IDs
- ✅ Automatic context propagation via ContextVar
- ✅ Structured JSON logs for easy parsing
- ✅ Session-level and application-level statistics
- ✅ Error analysis and failure diagnosis
- ✅ Execution flow reconstruction
- ✅ Human-readable console output
- ✅ Decorators for automatic operation tracing
- ✅ Context managers for scoped tracing
- ✅ Support for nested operations and retries

This system ensures that every application run is fully observable, debuggable, and analyzable.
