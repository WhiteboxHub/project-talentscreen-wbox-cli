"""Unit tests for observability system.

Tests:
- Trace context creation and propagation
- Structured logging with context injection
- Trace analysis and statistics
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest

from jobcli.observability import (
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
    trace_operation,
    LogLevel,
    StructuredLogEntry,
    StructuredLogger,
    LoggerFactory,
    get_logger,
    TraceAnalyzer,
    SessionStatistics,
)


class TestTraceContext:
    """Test trace context management."""

    def test_generate_ids(self):
        """Test ID generation functions."""
        session_id = generate_session_id()
        assert session_id.startswith("session_")
        assert len(session_id) > len("session_")

        app_id = generate_application_id(session_id)
        assert app_id.startswith("app_")

        job_id = generate_job_id("Google", "Software Engineer")
        assert job_id.startswith("job_")

        # Deterministic job_id
        job_id_2 = generate_job_id("Google", "Software Engineer")
        assert job_id == job_id_2

        # Different companies = different job_id
        job_id_3 = generate_job_id("Meta", "Software Engineer")
        assert job_id != job_id_3

        attempt_id = generate_attempt_id(app_id, 1)
        assert attempt_id.endswith("_attempt_1")

        trace_id = generate_trace_id()
        assert trace_id.startswith("trace_")

    def test_create_trace_context(self):
        """Test trace context creation."""
        context = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
            attempt_number=1,
            operation="test_op",
        )

        assert context.session_id == "session_test"
        assert context.application_id.startswith("app_")
        assert context.job_id.startswith("job_")
        assert context.attempt_id.endswith("_attempt_1")
        assert context.trace_id.startswith("trace_")
        assert context.operation == "test_op"
        assert context.parent_trace_id is None

    def test_context_propagation(self):
        """Test context get/set."""
        context = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
        )

        # Initially None
        assert get_trace_context() is None

        # Set context
        set_trace_context(context)
        retrieved = get_trace_context()
        assert retrieved is not None
        assert retrieved.session_id == "session_test"

        # Clear context
        clear_trace_context()
        assert get_trace_context() is None

    def test_context_manager(self):
        """Test context manager."""
        context = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
        )

        # Before context manager
        assert get_trace_context() is None

        # Inside context manager
        with with_trace_context(context):
            retrieved = get_trace_context()
            assert retrieved is not None
            assert retrieved.session_id == "session_test"

        # After context manager (restored)
        assert get_trace_context() is None

    def test_nested_context_managers(self):
        """Test nested context managers."""
        parent_context = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
            operation="parent",
        )

        child_context = parent_context.with_new_trace("child")

        with with_trace_context(parent_context):
            assert get_trace_context().operation == "parent"

            with with_trace_context(child_context):
                current = get_trace_context()
                assert current.operation == "child"
                assert current.parent_trace_id == parent_context.trace_id

            # Restored to parent
            assert get_trace_context().operation == "parent"

        # Restored to None
        assert get_trace_context() is None

    def test_with_new_trace(self):
        """Test creating child trace."""
        parent = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
        )

        child = parent.with_new_trace("child_op")

        # Same parent IDs
        assert child.session_id == parent.session_id
        assert child.application_id == parent.application_id
        assert child.job_id == parent.job_id
        assert child.attempt_id == parent.attempt_id

        # New trace_id
        assert child.trace_id != parent.trace_id

        # Parent link
        assert child.parent_trace_id == parent.trace_id

        # Operation
        assert child.operation == "child_op"

    def test_with_attempt(self):
        """Test creating retry context."""
        context = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
            attempt_number=1,
        )

        retry = context.with_attempt(2)

        # Same parent IDs
        assert retry.session_id == context.session_id
        assert retry.application_id == context.application_id
        assert retry.job_id == context.job_id

        # New attempt_id
        assert retry.attempt_id != context.attempt_id
        assert retry.attempt_id.endswith("_attempt_2")

        # New trace_id
        assert retry.trace_id != context.trace_id

    def test_trace_operation_decorator(self):
        """Test trace_operation decorator."""
        context = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
        )

        set_trace_context(context)

        @trace_operation("test_function")
        def test_func():
            # Inside function, should have child context
            current = get_trace_context()
            assert current.operation == "test_function"
            assert current.parent_trace_id == context.trace_id
            return "result"

        result = test_func()
        assert result == "result"

        # After function, context restored
        current = get_trace_context()
        assert current.trace_id == context.trace_id

        clear_trace_context()


class TestStructuredLogger:
    """Test structured logging."""

    def test_log_entry_creation(self):
        """Test log entry model."""
        entry = StructuredLogEntry(
            level=LogLevel.INFO,
            message="Test message",
            session_id="session_123",
            application_id="app_123",
            component="test_component",
        )

        assert entry.level == LogLevel.INFO
        assert entry.message == "Test message"
        assert entry.session_id == "session_123"
        assert entry.component == "test_component"

    def test_log_entry_to_json(self):
        """Test JSON serialization."""
        entry = StructuredLogEntry(
            level=LogLevel.INFO,
            message="Test message",
            session_id="session_123",
        )

        json_str = entry.to_json()
        data = json.loads(json_str)

        assert data["level"] == "info"
        assert data["message"] == "Test message"
        assert data["session_id"] == "session_123"
        assert "timestamp" in data

    def test_logger_with_context(self):
        """Test logger with trace context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create context
            context = create_trace_context(
                session_id="session_test",
                company_name="Google",
                position_title="SWE",
            )
            set_trace_context(context)

            # Create logger
            logger = StructuredLogger(
                component="test_component",
                log_file=log_file,
                console_output=False,
            )

            # Log message
            logger.info("Test message", field_id="email")

            logger.close()

            # Read log file
            with open(log_file) as f:
                line = f.read().strip()
                data = json.loads(line)

            assert data["level"] == "info"
            assert data["message"] == "Test message"
            assert data["session_id"] == "session_test"
            assert data["application_id"] == context.application_id
            assert data["trace_id"] == context.trace_id
            assert data["component"] == "test_component"
            assert data["data"]["field_id"] == "email"

            clear_trace_context()

    def test_logger_all_levels(self):
        """Test all log levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = StructuredLogger(
                component="test",
                log_file=log_file,
                console_output=False,
            )

            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")

            logger.close()

            # Read all lines
            with open(log_file) as f:
                lines = f.readlines()

            assert len(lines) == 5

            levels = [json.loads(line)["level"] for line in lines]
            assert levels == ["debug", "info", "warning", "error", "critical"]

    def test_logger_with_error(self):
        """Test logging with exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            logger = StructuredLogger(
                component="test",
                log_file=log_file,
                console_output=False,
            )

            try:
                raise ValueError("Test error")
            except Exception as e:
                logger.error("Operation failed", error=e)

            logger.close()

            # Read log
            with open(log_file) as f:
                data = json.loads(f.read())

            assert data["level"] == "error"
            assert data["error_type"] == "ValueError"
            assert data["error_message"] == "Test error"
            assert "stack_trace" in data
            assert data["stack_trace"] is not None

    def test_logger_factory(self):
        """Test logger factory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            LoggerFactory.configure(
                log_dir=Path(tmpdir),
                console_output=False,
            )

            logger1 = get_logger("component1")
            logger2 = get_logger("component2")
            logger3 = get_logger("component1")  # Same as logger1

            assert logger1 is logger3  # Cached
            assert logger1 is not logger2

            logger1.info("Message 1")
            logger2.info("Message 2")

            LoggerFactory.close_all()

            # Check log files created
            log1 = Path(tmpdir) / "component1.log"
            log2 = Path(tmpdir) / "component2.log"

            assert log1.exists()
            assert log2.exists()


class TestTraceAnalyzer:
    """Test trace analysis."""

    def _create_log_entries(self, log_file: Path) -> None:
        """Create sample log entries."""
        context1 = create_trace_context(
            session_id="session_test",
            company_name="Google",
            position_title="SWE",
            attempt_number=1,
        )

        context2 = create_trace_context(
            session_id="session_test",
            company_name="Meta",
            position_title="Frontend",
            attempt_number=1,
        )

        entries = [
            # Application 1: Success
            StructuredLogEntry(
                level=LogLevel.INFO,
                message="Starting application",
                session_id=context1.session_id,
                application_id=context1.application_id,
                job_id=context1.job_id,
                attempt_id=context1.attempt_id,
                trace_id=context1.trace_id,
                operation="apply",
            ),
            StructuredLogEntry(
                level=LogLevel.INFO,
                message="Filled field",
                session_id=context1.session_id,
                application_id=context1.application_id,
                job_id=context1.job_id,
                attempt_id=context1.attempt_id,
                trace_id=context1.trace_id,
            ),
            StructuredLogEntry(
                level=LogLevel.INFO,
                message="Application submitted",
                session_id=context1.session_id,
                application_id=context1.application_id,
                job_id=context1.job_id,
                attempt_id=context1.attempt_id,
                trace_id=context1.trace_id,
            ),
            # Application 2: Failure
            StructuredLogEntry(
                level=LogLevel.INFO,
                message="Starting application",
                session_id=context2.session_id,
                application_id=context2.application_id,
                job_id=context2.job_id,
                attempt_id=context2.attempt_id,
                trace_id=context2.trace_id,
                operation="apply",
            ),
            StructuredLogEntry(
                level=LogLevel.ERROR,
                message="Field not found",
                session_id=context2.session_id,
                application_id=context2.application_id,
                job_id=context2.job_id,
                attempt_id=context2.attempt_id,
                trace_id=context2.trace_id,
                error_type="SelectorNotFoundError",
                error_message="Could not find #email",
            ),
        ]

        # Write to file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as f:
            for entry in entries:
                f.write(entry.to_json() + "\n")

    def test_load_entries(self):
        """Test loading log entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            self._create_log_entries(log_file)

            analyzer = TraceAnalyzer(log_file)

            assert len(analyzer.entries) == 5

    def test_session_statistics(self):
        """Test session statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            self._create_log_entries(log_file)

            analyzer = TraceAnalyzer(log_file)
            stats = analyzer.get_session_statistics("session_test")

            assert stats is not None
            assert stats.session_id == "session_test"
            assert stats.total_applications == 2
            assert stats.successful_applications == 1
            assert stats.failed_applications == 1
            assert stats.total_log_entries == 5
            assert stats.error_count == 1
            assert stats.total_traces == 2

    def test_trace_statistics(self):
        """Test trace statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            self._create_log_entries(log_file)

            analyzer = TraceAnalyzer(log_file)
            stats = analyzer.get_session_statistics("session_test")

            # Check traces
            assert len(stats.traces) == 2

            # First trace (success)
            trace1 = stats.traces[0]
            assert trace1.success is True
            assert trace1.error_count == 0
            assert trace1.info_count == 3

            # Second trace (failure)
            trace2 = stats.traces[1]
            assert trace2.success is False
            assert trace2.error_count == 1
            assert len(trace2.errors) == 1

    def test_find_failed_applications(self):
        """Test finding failed applications."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            self._create_log_entries(log_file)

            analyzer = TraceAnalyzer(log_file)
            failed = analyzer.find_failed_applications()

            assert len(failed) == 1
            # Should contain Meta application_id

    def test_error_summary(self):
        """Test error summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            self._create_log_entries(log_file)

            analyzer = TraceAnalyzer(log_file)
            summary = analyzer.get_error_summary()

            assert summary["total_errors"] == 1
            assert "SelectorNotFoundError" in summary["by_type"]
            assert summary["most_common_error"] == "SelectorNotFoundError"

    def test_reconstruct_execution_flow(self):
        """Test execution flow reconstruction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            # Create context
            context = create_trace_context(
                session_id="session_test",
                company_name="Google",
                position_title="SWE",
            )

            # Create entries with timestamps
            base_time = datetime.utcnow()
            entries = [
                StructuredLogEntry(
                    timestamp=base_time,
                    level=LogLevel.INFO,
                    message="Step 1",
                    trace_id=context.trace_id,
                ),
                StructuredLogEntry(
                    timestamp=base_time + timedelta(seconds=1),
                    level=LogLevel.INFO,
                    message="Step 2",
                    trace_id=context.trace_id,
                ),
                StructuredLogEntry(
                    timestamp=base_time + timedelta(seconds=2),
                    level=LogLevel.INFO,
                    message="Step 3",
                    trace_id=context.trace_id,
                ),
            ]

            # Write to file
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "w") as f:
                for entry in entries:
                    f.write(entry.to_json() + "\n")

            # Reconstruct flow
            analyzer = TraceAnalyzer(log_file)
            flow = analyzer.reconstruct_execution_flow(context.trace_id)

            assert len(flow) == 3
            assert flow[0].message == "Step 1"
            assert flow[1].message == "Step 2"
            assert flow[2].message == "Step 3"

            # Should be in chronological order
            assert flow[0].timestamp < flow[1].timestamp < flow[2].timestamp

    def test_export_session_report(self):
        """Test session report export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            report_file = Path(tmpdir) / "report.txt"

            self._create_log_entries(log_file)

            analyzer = TraceAnalyzer(log_file)
            analyzer.export_session_report("session_test", report_file)

            # Check report created
            assert report_file.exists()

            # Check content
            content = report_file.read_text()
            assert "SESSION REPORT: session_test" in content
            assert "Applications: 2" in content
            assert "Successful: 1" in content
            assert "Failed: 1" in content


class TestIntegration:
    """Integration tests for full observability flow."""

    def test_full_application_trace(self):
        """Test complete application with tracing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Configure logging
            LoggerFactory.configure(
                log_dir=Path(tmpdir),
                console_output=False,
            )

            # Create session
            session_id = generate_session_id()

            # Create application context
            context = create_trace_context(
                session_id=session_id,
                company_name="Google",
                position_title="Software Engineer",
                attempt_number=1,
                operation="apply",
            )

            set_trace_context(context)

            # Get logger
            logger = get_logger("application_engine")

            # Simulate application flow
            logger.info("Starting application")
            logger.debug("Detected ATS", ats_type="greenhouse")
            logger.info("Filling basic info")
            logger.info("Uploading resume")
            logger.info("Application submitted")

            # Create child trace for sub-operation
            child_context = context.with_new_trace("fill_questions")
            with with_trace_context(child_context):
                logger.info("Filling questions", count=3)

            LoggerFactory.close_all()

            # Analyze logs
            log_file = Path(tmpdir) / "application_engine.log"
            analyzer = TraceAnalyzer(log_file)

            stats = analyzer.get_session_statistics(session_id)
            assert stats is not None
            assert stats.total_log_entries == 6
            assert stats.error_count == 0
            assert stats.total_traces == 2  # Parent + child

            clear_trace_context()

    def test_multi_application_session(self):
        """Test session with multiple applications."""
        with tempfile.TemporaryDirectory() as tmpdir:
            LoggerFactory.configure(
                log_dir=Path(tmpdir),
                console_output=False,
            )

            session_id = generate_session_id()
            logger = get_logger("batch_processor")

            companies = [
                ("Google", "SWE"),
                ("Meta", "Frontend"),
                ("Amazon", "Backend"),
            ]

            for company, position in companies:
                context = create_trace_context(
                    session_id=session_id,
                    company_name=company,
                    position_title=position,
                    attempt_number=1,
                )

                set_trace_context(context)
                logger.info("Application started", company=company)
                logger.info("Application submitted", company=company)

            LoggerFactory.close_all()

            # Analyze
            log_file = Path(tmpdir) / "batch_processor.log"
            analyzer = TraceAnalyzer(log_file)

            stats = analyzer.get_session_statistics(session_id)
            assert stats.total_applications == 3
            assert stats.total_log_entries == 6

            clear_trace_context()

    def test_retry_with_new_attempt(self):
        """Test retry with new attempt context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            LoggerFactory.configure(
                log_dir=Path(tmpdir),
                console_output=False,
            )

            session_id = generate_session_id()
            logger = get_logger("retry_handler")

            # Initial attempt
            context = create_trace_context(
                session_id=session_id,
                company_name="Google",
                position_title="SWE",
                attempt_number=1,
            )

            set_trace_context(context)
            logger.info("Attempt 1")
            logger.error("Attempt 1 failed", error_type="TimeoutError")

            # Retry
            retry_context = context.with_attempt(2)
            set_trace_context(retry_context)
            logger.info("Attempt 2")
            logger.info("Attempt 2 succeeded")

            LoggerFactory.close_all()

            # Analyze
            log_file = Path(tmpdir) / "retry_handler.log"
            analyzer = TraceAnalyzer(log_file)

            # Both attempts should be under same application
            stats = analyzer.get_session_statistics(session_id)
            assert stats.total_log_entries == 4
            assert stats.error_count == 1

            # Should have 2 traces (one per attempt)
            assert stats.total_traces == 2

            clear_trace_context()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
