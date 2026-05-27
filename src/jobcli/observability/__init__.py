"""Strict observability for JobCLI.

Every application run has complete traceability through a 5-level ID hierarchy:
- session_id: User session (may contain multiple jobs)
- application_id: Single job application
- job_id: Specific job posting
- attempt_id: Retry attempt number
- trace_id: Individual operation trace

All logs automatically include trace context for full observability.

Usage:
    from jobcli.observability import (
        create_trace_context,
        set_trace_context,
        get_trace_context,
        with_trace_context,
        trace_operation,
        get_logger,
    )

    # Create trace context for a job application
    context = create_trace_context(
        session_id="session_20260519_123456",
        company_name="Google",
        position_title="Software Engineer",
        attempt_number=1,
        operation="fill_application_form"
    )

    # Set as current context
    set_trace_context(context)

    # Get logger (automatically includes trace context)
    logger = get_logger("application_engine")
    logger.info("Starting application", company="Google")
    # Output: {"timestamp":"...","level":"info","session_id":"session_20260519_123456",
    #          "application_id":"app_20260519_120000_abc123","job_id":"job_a1b2c3d4",
    #          "attempt_id":"app_20260519_120000_abc123_attempt_1",
    #          "trace_id":"trace_1234567890abcdef","message":"Starting application",
    #          "data":{"company":"Google"}}

    # Use context manager
    with with_trace_context(context):
        logger.info("Inside context")

    # Trace operations with decorator
    @trace_operation("fill_field")
    def fill_field(field_id, value):
        logger.info("Filling field", field_id=field_id)
        # Automatically creates child trace

    # Analyze logs after execution
    from jobcli.observability import TraceAnalyzer

    analyzer = TraceAnalyzer(Path("logs/application.log"))
    stats = analyzer.get_session_statistics("session_20260519_123456")
    print(f"Applications: {stats.total_applications}")
    print(f"Success rate: {stats.successful_applications / stats.total_applications}")

    # Export session report
    analyzer.export_session_report("session_20260519_123456", Path("report.txt"))
"""

from .trace_context import (
    TraceContext,
    create_trace_context,
    generate_application_id,
    generate_attempt_id,
    generate_job_id,
    generate_session_id,
    generate_trace_id,
    get_trace_context,
    set_trace_context,
    clear_trace_context,
    with_trace_context,
    ensure_trace_context,
    trace_operation,
)
from .structured_logger import (
    LogLevel,
    StructuredLogEntry,
    StructuredLogger,
    LoggerFactory,
    get_logger,
)
from .trace_analyzer import (
    TraceStatistics,
    SessionStatistics,
    TraceAnalyzer,
)

__all__ = [
    # Trace Context
    "TraceContext",
    "create_trace_context",
    "generate_session_id",
    "generate_application_id",
    "generate_job_id",
    "generate_attempt_id",
    "generate_trace_id",
    "get_trace_context",
    "set_trace_context",
    "clear_trace_context",
    "with_trace_context",
    "ensure_trace_context",
    "trace_operation",
    # Structured Logging
    "LogLevel",
    "StructuredLogEntry",
    "StructuredLogger",
    "LoggerFactory",
    "get_logger",
    # Trace Analysis
    "TraceStatistics",
    "SessionStatistics",
    "TraceAnalyzer",
]
