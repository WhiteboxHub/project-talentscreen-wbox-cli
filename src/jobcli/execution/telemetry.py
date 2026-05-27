"""Structured telemetry system for execution tracking.

All operations emit structured events for monitoring, debugging, and learning.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from jobcli.profile.schemas import ATSType


class EventType(str, Enum):
    """Types of telemetry events."""

    # Field detection events
    FIELD_DETECTED = "field_detected"
    FIELD_CLASSIFIED = "field_classified"
    FIELD_MAPPED = "field_mapped"

    # Execution events
    ACTION_STARTED = "action_started"
    ACTION_SUCCEEDED = "action_succeeded"
    ACTION_FAILED = "action_failed"
    ACTION_RETRYING = "action_retrying"

    # Validation events
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"

    # Fill-specific events
    FIELD_FILL_STARTED = "field_fill_started"
    FIELD_FILL_SUCCEEDED = "field_fill_succeeded"
    FIELD_FILL_FAILED = "field_fill_failed"

    # Human interaction events
    HUMAN_OVERRIDE_REQUESTED = "human_override_requested"
    HUMAN_OVERRIDE_PROVIDED = "human_override_provided"
    HUMAN_CORRECTION = "human_correction"

    # Selector events
    SELECTOR_FOUND = "selector_found"
    SELECTOR_NOT_FOUND = "selector_not_found"
    SELECTOR_FALLBACK = "selector_fallback"

    # ATS events
    ATS_DETECTED = "ats_detected"
    ATS_PATTERN_MATCHED = "ats_pattern_matched"


class TelemetryEvent(BaseModel):
    """Structured telemetry event.

    Example:
        {
            "event": "field_fill_failed",
            "field": "phone_number",
            "reason": "validation_error",
            "ats": "workday",
            "confidence": 0.42,
            "timestamp": "2026-05-18T12:34:56Z",
            "metadata": {...}
        }
    """

    # Core fields
    event: EventType = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    field: Optional[str] = Field(None, description="Field ID")
    ats: Optional[ATSType] = Field(None, description="ATS platform")
    session_id: Optional[str] = Field(None, description="Application session ID")

    # Outcome
    success: Optional[bool] = Field(None, description="Did operation succeed?")
    reason: Optional[str] = Field(None, description="Reason for failure/success")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    # Metrics
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score")
    retry_count: int = Field(0, description="Number of retries")
    duration_ms: Optional[int] = Field(None, description="Operation duration in ms")

    # Additional data
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra context")

    model_config = {"arbitrary_types_allowed": True}


class TelemetryTracker:
    """Track and aggregate telemetry events.

    Responsibilities:
    - Emit structured events
    - Aggregate metrics
    - Track success rates
    - Calculate ATS reliability
    - Monitor confidence accuracy
    """

    def __init__(self):
        """Initialize tracker."""
        self.events: List[TelemetryEvent] = []
        self._metrics_cache: Dict[str, Any] = {}

    def emit(self, event: TelemetryEvent) -> None:
        """Emit a telemetry event.

        Args:
            event: Structured telemetry event
        """
        self.events.append(event)
        # Invalidate metrics cache
        self._metrics_cache.clear()

    def emit_field_detected(
        self,
        field_id: str,
        semantic_type: str,
        confidence: float,
        ats: ATSType,
        session_id: Optional[str] = None,
    ) -> None:
        """Convenience: Emit field detected event."""
        self.emit(
            TelemetryEvent(
                event=EventType.FIELD_DETECTED,
                field=field_id,
                ats=ats,
                session_id=session_id,
                confidence=confidence,
                success=True,
                metadata={"semantic_type": semantic_type},
            )
        )

    def emit_field_fill_succeeded(
        self,
        field_id: str,
        value: str,
        confidence: float,
        duration_ms: int,
        ats: ATSType,
        session_id: Optional[str] = None,
    ) -> None:
        """Convenience: Emit field fill success."""
        self.emit(
            TelemetryEvent(
                event=EventType.FIELD_FILL_SUCCEEDED,
                field=field_id,
                ats=ats,
                session_id=session_id,
                success=True,
                confidence=confidence,
                duration_ms=duration_ms,
                metadata={"value_length": len(value)},
            )
        )

    def emit_field_fill_failed(
        self,
        field_id: str,
        reason: str,
        confidence: float,
        ats: ATSType,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        session_id: Optional[str] = None,
    ) -> None:
        """Convenience: Emit field fill failure."""
        self.emit(
            TelemetryEvent(
                event=EventType.FIELD_FILL_FAILED,
                field=field_id,
                ats=ats,
                session_id=session_id,
                success=False,
                reason=reason,
                error_message=error_message,
                confidence=confidence,
                retry_count=retry_count,
            )
        )

    def emit_human_override(
        self,
        field_id: str,
        original_value: Optional[str],
        provided_value: str,
        confidence: float,
        ats: ATSType,
        session_id: Optional[str] = None,
    ) -> None:
        """Convenience: Emit human override event."""
        self.emit(
            TelemetryEvent(
                event=EventType.HUMAN_OVERRIDE_PROVIDED,
                field=field_id,
                ats=ats,
                session_id=session_id,
                success=True,
                confidence=0.95,  # Human override = high confidence
                metadata={
                    "original_value": original_value,
                    "provided_value": provided_value,
                    "original_confidence": confidence,
                },
            )
        )

    def emit_selector_not_found(
        self,
        field_id: str,
        selector: str,
        ats: ATSType,
        session_id: Optional[str] = None,
    ) -> None:
        """Convenience: Emit selector not found."""
        self.emit(
            TelemetryEvent(
                event=EventType.SELECTOR_NOT_FOUND,
                field=field_id,
                ats=ats,
                session_id=session_id,
                success=False,
                reason="selector_not_found",
                metadata={"selector": selector},
            )
        )

    # ── Metrics Aggregation ──────────────────────────────────────────────────

    def get_field_detection_rate(self, ats: Optional[ATSType] = None) -> float:
        """Calculate field detection success rate.

        Args:
            ats: Filter by ATS type (optional)

        Returns:
            Detection rate [0.0, 1.0]
        """
        events = self._filter_events(EventType.FIELD_DETECTED, ats=ats)
        if not events:
            return 0.0

        detected = sum(1 for e in events if e.confidence and e.confidence >= 0.6)
        return detected / len(events)

    def get_fill_success_rate(self, ats: Optional[ATSType] = None) -> float:
        """Calculate field fill success rate.

        Args:
            ats: Filter by ATS type

        Returns:
            Success rate [0.0, 1.0]
        """
        succeeded = self._filter_events(EventType.FIELD_FILL_SUCCEEDED, ats=ats)
        failed = self._filter_events(EventType.FIELD_FILL_FAILED, ats=ats)

        total = len(succeeded) + len(failed)
        if total == 0:
            return 0.0

        return len(succeeded) / total

    def get_retry_statistics(self, ats: Optional[ATSType] = None) -> Dict[str, float]:
        """Get retry statistics.

        Returns:
            {
                "avg_retries": float,
                "max_retries": int,
                "fields_requiring_retry": int
            }
        """
        failed_events = self._filter_events(EventType.FIELD_FILL_FAILED, ats=ats)

        if not failed_events:
            return {"avg_retries": 0.0, "max_retries": 0, "fields_requiring_retry": 0}

        retry_counts = [e.retry_count for e in failed_events if e.retry_count > 0]

        return {
            "avg_retries": sum(retry_counts) / len(retry_counts) if retry_counts else 0.0,
            "max_retries": max(retry_counts) if retry_counts else 0,
            "fields_requiring_retry": len(retry_counts),
        }

    def get_ats_reliability(self) -> Dict[ATSType, float]:
        """Calculate reliability score per ATS.

        Reliability = (successful fills) / (total attempts)

        Returns:
            {ATSType.GREENHOUSE: 0.95, ...}
        """
        reliability: Dict[ATSType, float] = {}

        for ats in ATSType:
            rate = self.get_fill_success_rate(ats=ats)
            if rate > 0:
                reliability[ats] = rate

        return reliability

    def get_selector_failure_rate(self, ats: Optional[ATSType] = None) -> float:
        """Calculate selector not found rate.

        Returns:
            Failure rate [0.0, 1.0]
        """
        found = self._filter_events(EventType.SELECTOR_FOUND, ats=ats)
        not_found = self._filter_events(EventType.SELECTOR_NOT_FOUND, ats=ats)

        total = len(found) + len(not_found)
        if total == 0:
            return 0.0

        return len(not_found) / total

    def get_human_override_rate(self, ats: Optional[ATSType] = None) -> float:
        """Calculate human override rate.

        Returns:
            Override rate [0.0, 1.0]
        """
        overrides = self._filter_events(EventType.HUMAN_OVERRIDE_PROVIDED, ats=ats)
        all_fields = self._filter_events(EventType.FIELD_DETECTED, ats=ats)

        if not all_fields:
            return 0.0

        return len(overrides) / len(all_fields)

    def get_confidence_accuracy(self, ats: Optional[ATSType] = None) -> Dict[str, float]:
        """Analyze confidence score accuracy.

        Compare predicted confidence vs. actual success rate.

        Returns:
            {
                "high_confidence_accuracy": 0.95,  # conf >= 0.8
                "medium_confidence_accuracy": 0.75,  # conf 0.6-0.8
                "low_confidence_accuracy": 0.40,  # conf < 0.6
            }
        """
        succeeded = self._filter_events(EventType.FIELD_FILL_SUCCEEDED, ats=ats)
        failed = self._filter_events(EventType.FIELD_FILL_FAILED, ats=ats)

        all_events = succeeded + failed

        # Group by confidence tier
        high = [e for e in all_events if e.confidence and e.confidence >= 0.8]
        medium = [e for e in all_events if e.confidence and 0.6 <= e.confidence < 0.8]
        low = [e for e in all_events if e.confidence and e.confidence < 0.6]

        def accuracy(events: List[TelemetryEvent]) -> float:
            if not events:
                return 0.0
            succeeded_count = sum(1 for e in events if e.success)
            return succeeded_count / len(events)

        return {
            "high_confidence_accuracy": accuracy(high),
            "medium_confidence_accuracy": accuracy(medium),
            "low_confidence_accuracy": accuracy(low),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get complete telemetry summary.

        Returns:
            Dictionary with all metrics
        """
        return {
            "total_events": len(self.events),
            "field_detection_rate": self.get_field_detection_rate(),
            "fill_success_rate": self.get_fill_success_rate(),
            "retry_statistics": self.get_retry_statistics(),
            "ats_reliability": {
                ats.value: score for ats, score in self.get_ats_reliability().items()
            },
            "selector_failure_rate": self.get_selector_failure_rate(),
            "human_override_rate": self.get_human_override_rate(),
            "confidence_accuracy": self.get_confidence_accuracy(),
        }

    def _filter_events(
        self,
        event_type: EventType,
        ats: Optional[ATSType] = None,
    ) -> List[TelemetryEvent]:
        """Filter events by type and optional ATS.

        Args:
            event_type: Event type to filter
            ats: Optional ATS filter

        Returns:
            List of matching events
        """
        filtered = [e for e in self.events if e.event == event_type]

        if ats:
            filtered = [e for e in filtered if e.ats == ats]

        return filtered


# Global telemetry tracker instance
_global_tracker = TelemetryTracker()


def get_telemetry_tracker() -> TelemetryTracker:
    """Get global telemetry tracker instance."""
    return _global_tracker
