"""Trace context for strict observability.

Every application run has a hierarchy of IDs:
- session_id: User session (may contain multiple jobs)
- application_id: Single job application
- job_id: Specific job posting
- attempt_id: Retry attempt number
- trace_id: Individual operation trace

All actions are traceable through this hierarchy.
"""

import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TraceContext(BaseModel):
    """Complete trace context for an operation.

    Hierarchy:
    session_id → application_id → job_id → attempt_id → trace_id
    """

    # Identity hierarchy
    session_id: str = Field(..., description="User session ID")
    application_id: str = Field(..., description="Application instance ID")
    job_id: str = Field(..., description="Job posting ID")
    attempt_id: str = Field(..., description="Attempt number for this application")
    trace_id: str = Field(..., description="Unique trace ID for this operation")

    # Context
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    operation: Optional[str] = Field(None, description="Operation being traced")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Parent trace (for nested operations)
    parent_trace_id: Optional[str] = None

    def model_dump_ids(self) -> Dict[str, str]:
        """Get just the ID fields as dict.

        Returns:
            Dict with all ID fields
        """
        return {
            "session_id": self.session_id,
            "application_id": self.application_id,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "trace_id": self.trace_id,
        }

    def with_new_trace(self, operation: Optional[str] = None) -> "TraceContext":
        """Create child trace context.

        Args:
            operation: Operation name

        Returns:
            New TraceContext with new trace_id but same parent IDs
        """
        return TraceContext(
            session_id=self.session_id,
            application_id=self.application_id,
            job_id=self.job_id,
            attempt_id=self.attempt_id,
            trace_id=generate_trace_id(),
            operation=operation,
            parent_trace_id=self.trace_id,
            metadata=self.metadata.copy(),
        )

    def with_attempt(self, attempt_number: int) -> "TraceContext":
        """Create trace context for a new attempt.

        Args:
            attempt_number: Attempt number

        Returns:
            New TraceContext with new attempt_id and trace_id
        """
        return TraceContext(
            session_id=self.session_id,
            application_id=self.application_id,
            job_id=self.job_id,
            attempt_id=f"{self.application_id}_attempt_{attempt_number}",
            trace_id=generate_trace_id(),
            metadata=self.metadata.copy(),
        )


# Context variable for current trace
_current_trace: ContextVar[Optional[TraceContext]] = ContextVar(
    "current_trace", default=None
)


def generate_trace_id() -> str:
    """Generate a unique trace ID.

    Returns:
        Trace ID string
    """
    return f"trace_{uuid.uuid4().hex[:16]}"


def generate_session_id() -> str:
    """Generate a unique session ID.

    Returns:
        Session ID string
    """
    return f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def generate_application_id(session_id: str) -> str:
    """Generate an application ID.

    Args:
        session_id: Parent session ID

    Returns:
        Application ID string
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"app_{timestamp}_{uuid.uuid4().hex[:8]}"


def generate_job_id(company_name: str, position_title: str) -> str:
    """Generate a job ID.

    Args:
        company_name: Company name
        position_title: Position title

    Returns:
        Job ID string
    """
    import hashlib

    # Create deterministic ID from company + position
    combined = f"{company_name.lower()}_{position_title.lower()}"
    hash_part = hashlib.md5(combined.encode()).hexdigest()[:8]

    return f"job_{hash_part}"


def generate_attempt_id(application_id: str, attempt_number: int) -> str:
    """Generate an attempt ID.

    Args:
        application_id: Parent application ID
        attempt_number: Attempt number

    Returns:
        Attempt ID string
    """
    return f"{application_id}_attempt_{attempt_number}"


def create_trace_context(
    session_id: str,
    company_name: str,
    position_title: str,
    attempt_number: int = 1,
    operation: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TraceContext:
    """Create a complete trace context.

    Args:
        session_id: Session ID
        company_name: Company name
        position_title: Position title
        attempt_number: Attempt number
        operation: Operation name
        metadata: Additional metadata

    Returns:
        TraceContext
    """
    application_id = generate_application_id(session_id)
    job_id = generate_job_id(company_name, position_title)
    attempt_id = generate_attempt_id(application_id, attempt_number)
    trace_id = generate_trace_id()

    return TraceContext(
        session_id=session_id,
        application_id=application_id,
        job_id=job_id,
        attempt_id=attempt_id,
        trace_id=trace_id,
        operation=operation,
        metadata=metadata or {},
    )


def set_trace_context(context: TraceContext) -> None:
    """Set current trace context.

    Args:
        context: TraceContext to set
    """
    _current_trace.set(context)


def get_trace_context() -> Optional[TraceContext]:
    """Get current trace context.

    Returns:
        Current TraceContext or None
    """
    return _current_trace.get()


def clear_trace_context() -> None:
    """Clear current trace context."""
    _current_trace.set(None)


def with_trace_context(context: TraceContext):
    """Context manager for trace context.

    Usage:
        with with_trace_context(context):
            # Operations here have access to context
            pass
    """

    class TraceContextManager:
        def __enter__(self):
            self.token = _current_trace.set(context)
            return context

        def __exit__(self, *args):
            _current_trace.reset(self.token)

    return TraceContextManager()


def ensure_trace_context(
    operation: Optional[str] = None,
) -> TraceContext:
    """Ensure trace context exists, create if missing.

    Args:
        operation: Operation name if creating new context

    Returns:
        TraceContext (existing or newly created)
    """
    context = get_trace_context()

    if context is None:
        # Create minimal context
        session_id = generate_session_id()
        context = create_trace_context(
            session_id=session_id,
            company_name="unknown",
            position_title="unknown",
            operation=operation,
        )
        set_trace_context(context)

    return context


def trace_operation(operation_name: str):
    """Decorator to trace an operation.

    Usage:
        @trace_operation("fill_field")
        def fill_field(field_id, value):
            # Operation is automatically traced
            pass
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            context = ensure_trace_context(operation_name)

            # Create child trace for this operation
            child_context = context.with_new_trace(operation_name)

            # Execute with child context
            with with_trace_context(child_context):
                return func(*args, **kwargs)

        return wrapper

    return decorator
