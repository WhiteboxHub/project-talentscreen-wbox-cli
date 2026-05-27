"""Adaptive retry system with confidence-based escalation.

Adjusts retry strategy based on:
- Failure patterns
- Confidence scores
- Historical success rates
- ATS-specific quirks
"""

import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class RetryStrategy(str, Enum):
    """Retry strategy types."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR = "linear"
    FIXED = "fixed"
    ADAPTIVE = "adaptive"


class EscalationLevel(str, Enum):
    """Confidence escalation levels."""

    NONE = "none"  # No escalation needed
    SELECTOR_HEALING = "selector_healing"  # Try healing selector
    HUMAN_VERIFICATION = "human_verification"  # Ask human to verify
    SKIP_FIELD = "skip_field"  # Skip this field
    ABORT_SESSION = "abort_session"  # Abort entire session


class RetryConfig(BaseModel):
    """Configuration for adaptive retry."""

    max_retries: int = 5
    base_delay_ms: int = 500
    max_delay_ms: int = 10000
    jitter_factor: float = 0.3
    strategy: RetryStrategy = RetryStrategy.ADAPTIVE

    # Confidence thresholds
    high_confidence_threshold: float = 0.8
    low_confidence_threshold: float = 0.5

    # Escalation thresholds
    escalate_after_failures: int = 3
    escalate_on_low_confidence: bool = True


class RetryAttempt(BaseModel):
    """A single retry attempt."""

    attempt_number: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    delay_ms: int
    confidence: float
    reason: Optional[str] = None
    escalation: Optional[EscalationLevel] = None


class RetryResult(BaseModel):
    """Result of retry sequence."""

    success: bool
    attempts: List[RetryAttempt] = Field(default_factory=list)
    total_duration_ms: int
    escalation_triggered: Optional[EscalationLevel] = None
    final_confidence: float = 0.0


class AdaptiveRetry:
    """Adaptive retry system with confidence-based escalation."""

    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize adaptive retry.

        Args:
            config: Retry configuration
        """
        self.config = config or RetryConfig()
        self._failure_history: Dict[str, List[datetime]] = {}

    def execute_with_retry(
        self,
        operation: Callable[[], Any],
        field_id: str,
        confidence: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> RetryResult:
        """Execute operation with adaptive retry.

        Args:
            operation: Function to execute
            field_id: Field identifier
            confidence: Initial confidence score
            context: Additional context

        Returns:
            RetryResult
        """
        start_time = time.time()
        attempts: List[RetryAttempt] = []
        escalation: Optional[EscalationLevel] = None

        for attempt_num in range(1, self.config.max_retries + 1):
            # Calculate delay
            delay_ms = self._calculate_delay(
                attempt_num, confidence, field_id, context or {}
            )

            # Check if escalation needed
            escalation = self._check_escalation(
                attempt_num, confidence, field_id, attempts
            )

            # Record attempt
            attempt = RetryAttempt(
                attempt_number=attempt_num,
                delay_ms=delay_ms,
                confidence=confidence,
                escalation=escalation,
            )
            attempts.append(attempt)

            # Handle escalation
            if escalation and escalation != EscalationLevel.NONE:
                # Escalation triggered, stop retrying
                duration_ms = int((time.time() - start_time) * 1000)
                return RetryResult(
                    success=False,
                    attempts=attempts,
                    total_duration_ms=duration_ms,
                    escalation_triggered=escalation,
                    final_confidence=confidence,
                )

            # Wait before retry
            if attempt_num > 1:
                time.sleep(delay_ms / 1000.0)

            # Execute operation
            try:
                result = operation()

                # Success!
                duration_ms = int((time.time() - start_time) * 1000)

                # Clear failure history
                self._clear_failure_history(field_id)

                return RetryResult(
                    success=True,
                    attempts=attempts,
                    total_duration_ms=duration_ms,
                    final_confidence=confidence,
                )

            except Exception as e:
                # Record failure
                self._record_failure(field_id)

                attempt.reason = str(e)

                # Update confidence based on failure
                confidence = self._adjust_confidence_after_failure(
                    confidence, attempt_num, field_id
                )

        # All retries exhausted
        duration_ms = int((time.time() - start_time) * 1000)

        return RetryResult(
            success=False,
            attempts=attempts,
            total_duration_ms=duration_ms,
            escalation_triggered=escalation,
            final_confidence=confidence,
        )

    def _calculate_delay(
        self,
        attempt: int,
        confidence: float,
        field_id: str,
        context: Dict[str, Any],
    ) -> int:
        """Calculate delay before retry.

        Args:
            attempt: Attempt number
            confidence: Current confidence
            field_id: Field identifier
            context: Additional context

        Returns:
            Delay in milliseconds
        """
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            # Standard exponential backoff
            delay = self.config.base_delay_ms * (2 ** (attempt - 1))

        elif self.config.strategy == RetryStrategy.LINEAR:
            # Linear increase
            delay = self.config.base_delay_ms * attempt

        elif self.config.strategy == RetryStrategy.FIXED:
            # Fixed delay
            delay = self.config.base_delay_ms

        else:  # ADAPTIVE
            # Adaptive based on confidence and failure history
            base_delay = self.config.base_delay_ms * (2 ** (attempt - 1))

            # Adjust based on confidence
            if confidence < self.config.low_confidence_threshold:
                # Low confidence → wait longer
                base_delay *= 1.5
            elif confidence >= self.config.high_confidence_threshold:
                # High confidence → wait less (failure might be temporary)
                base_delay *= 0.75

            # Adjust based on failure history
            recent_failures = self._get_recent_failures(field_id)
            if recent_failures > 3:
                # Frequent failures → wait longer
                base_delay *= 1.25

            delay = int(base_delay)

        # Apply max cap
        delay = min(delay, self.config.max_delay_ms)

        # Add jitter
        import random

        jitter = delay * self.config.jitter_factor * (2 * random.random() - 1)
        delay = max(0, int(delay + jitter))

        return delay

    def _check_escalation(
        self,
        attempt: int,
        confidence: float,
        field_id: str,
        attempts: List[RetryAttempt],
    ) -> EscalationLevel:
        """Check if escalation is needed.

        Args:
            attempt: Current attempt number
            confidence: Current confidence
            field_id: Field identifier
            attempts: Previous attempts

        Returns:
            EscalationLevel
        """
        # Escalate on low confidence
        if (
            self.config.escalate_on_low_confidence
            and confidence < self.config.low_confidence_threshold
        ):
            if attempt == 1:
                # First attempt with low confidence → try healing
                return EscalationLevel.SELECTOR_HEALING
            elif attempt >= 2:
                # Still failing with low confidence → ask human
                return EscalationLevel.HUMAN_VERIFICATION

        # Escalate after multiple failures
        if attempt >= self.config.escalate_after_failures:
            if confidence >= self.config.high_confidence_threshold:
                # High confidence but still failing → ask human
                return EscalationLevel.HUMAN_VERIFICATION
            else:
                # Low confidence and multiple failures → consider skipping
                return EscalationLevel.SKIP_FIELD

        # Check recent failure history
        recent_failures = self._get_recent_failures(field_id)
        if recent_failures >= 5:
            # Persistent failures across sessions → skip field
            return EscalationLevel.SKIP_FIELD

        return EscalationLevel.NONE

    def _adjust_confidence_after_failure(
        self,
        confidence: float,
        attempt: int,
        field_id: str,
    ) -> float:
        """Adjust confidence after failure.

        Args:
            confidence: Current confidence
            attempt: Attempt number
            field_id: Field identifier

        Returns:
            Adjusted confidence
        """
        # Decrease confidence after each failure
        decay_factor = 0.9 ** attempt

        # Check failure history
        recent_failures = self._get_recent_failures(field_id)
        if recent_failures > 0:
            # Additional decay for persistent failures
            history_decay = 0.95 ** recent_failures
            decay_factor *= history_decay

        adjusted = confidence * decay_factor

        # Floor at 0.1
        return max(0.1, adjusted)

    def _record_failure(self, field_id: str) -> None:
        """Record failure for field.

        Args:
            field_id: Field identifier
        """
        if field_id not in self._failure_history:
            self._failure_history[field_id] = []

        self._failure_history[field_id].append(datetime.utcnow())

        # Keep only last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        self._failure_history[field_id] = [
            ts for ts in self._failure_history[field_id] if ts > cutoff
        ]

    def _clear_failure_history(self, field_id: str) -> None:
        """Clear failure history after success.

        Args:
            field_id: Field identifier
        """
        if field_id in self._failure_history:
            del self._failure_history[field_id]

    def _get_recent_failures(self, field_id: str) -> int:
        """Get count of recent failures.

        Args:
            field_id: Field identifier

        Returns:
            Number of recent failures
        """
        if field_id not in self._failure_history:
            return 0

        # Failures in last hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        recent = [ts for ts in self._failure_history[field_id] if ts > cutoff]

        return len(recent)

    def get_failure_statistics(self) -> Dict[str, Any]:
        """Get failure statistics.

        Returns:
            Dict with stats
        """
        total_fields = len(self._failure_history)
        total_failures = sum(len(failures) for failures in self._failure_history.values())

        if total_fields == 0:
            return {
                "total_fields_with_failures": 0,
                "total_failures": 0,
                "avg_failures_per_field": 0.0,
            }

        return {
            "total_fields_with_failures": total_fields,
            "total_failures": total_failures,
            "avg_failures_per_field": total_failures / total_fields,
            "top_failing_fields": self._get_top_failing_fields(),
        }

    def _get_top_failing_fields(self) -> List[Dict[str, Any]]:
        """Get fields with most failures.

        Returns:
            List of top failing fields
        """
        field_counts = [
            {"field_id": field_id, "failure_count": len(failures)}
            for field_id, failures in self._failure_history.items()
        ]

        field_counts.sort(key=lambda x: x["failure_count"], reverse=True)

        return field_counts[:10]


class RetryWithHealing:
    """Retry system integrated with selector healing."""

    def __init__(
        self,
        adaptive_retry: AdaptiveRetry,
        selector_healer: Optional[Any] = None,
    ):
        """Initialize retry with healing.

        Args:
            adaptive_retry: AdaptiveRetry instance
            selector_healer: SelectorHealer instance (optional)
        """
        self.adaptive_retry = adaptive_retry
        self.selector_healer = selector_healer

    def execute_with_healing(
        self,
        operation: Callable[[], Any],
        field_id: str,
        confidence: float,
        selector: str,
        field_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> RetryResult:
        """Execute operation with retry and selector healing.

        Args:
            operation: Function to execute
            field_id: Field identifier
            confidence: Initial confidence
            selector: Original selector
            field_type: Field type
            context: Additional context

        Returns:
            RetryResult
        """
        # First attempt with original selector
        result = self.adaptive_retry.execute_with_retry(
            operation, field_id, confidence, context
        )

        # Check if selector healing triggered
        if (
            not result.success
            and result.escalation_triggered == EscalationLevel.SELECTOR_HEALING
            and self.selector_healer
        ):
            # Try healing selector
            healing_result = self.selector_healer.heal_selector(
                selector, field_type, context
            )

            if healing_result.success and healing_result.healed_selector:
                # Retry with healed selector
                # (operation should be updated to use healed selector)
                result = self.adaptive_retry.execute_with_retry(
                    operation,
                    field_id,
                    healing_result.confidence,
                    {**(context or {}), "healed_selector": healing_result.healed_selector},
                )

        return result
