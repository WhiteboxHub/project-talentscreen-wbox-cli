"""Strict execution engine with retries, validation, telemetry, and state tracking."""

import random
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from pydantic import BaseModel, Field

from jobcli.execution.actions import (
    ClickAction,
    ExecutionAction,
    FillInputAction,
    SelectOptionAction,
    UploadFileAction,
    WaitAction,
)
from jobcli.execution.telemetry import (
    EventType,
    TelemetryEvent,
    TelemetryTracker,
    get_telemetry_tracker,
)
from jobcli.profile.schemas import ATSType


class ExecutionStatus(str, Enum):
    """Execution result status."""

    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class ExecutionResult(BaseModel):
    """Result of executing an action.

    Example:
        {
            "status": "success",
            "action_target": "candidate_email",
            "attempts": 1,
            "duration_ms": 234,
            "verified": true,
            "error": null
        }
    """

    status: ExecutionStatus
    action_target: str = Field(..., description="Target field ID")
    attempts: int = Field(1, description="Number of attempts")
    duration_ms: int = Field(..., description="Total execution time")
    verified: bool = Field(False, description="Was action verified?")
    verified_value: Optional[str] = Field(None, description="Value read back after fill")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionEngine:
    """Strict execution engine with retries, validation, and telemetry.

    Responsibilities:
    - Execute structured actions deterministically
    - Retry with exponential backoff + jitter
    - Validate before execution (element exists, visible)
    - Verify after execution (read back value, check state)
    - Emit structured telemetry for all operations
    - Track execution state
    """

    # Retry configuration
    BASE_RETRY_DELAY_MS = 500  # Start at 500ms
    MAX_RETRY_DELAY_MS = 5000  # Cap at 5s
    JITTER_FACTOR = 0.3  # ±30% jitter

    def __init__(
        self,
        page: Page,
        ats_type: ATSType,
        session_id: Optional[str] = None,
        telemetry_tracker: Optional[TelemetryTracker] = None,
    ):
        """Initialize execution engine.

        Args:
            page: Playwright Page instance
            ats_type: ATS platform type
            session_id: Application session ID
            telemetry_tracker: Custom telemetry tracker (or use global)
        """
        self.page = page
        self.ats_type = ats_type
        self.session_id = session_id
        self.telemetry = telemetry_tracker or get_telemetry_tracker()

        # State tracking
        self.executed_actions: List[ExecutionResult] = []
        self.failed_actions: List[ExecutionResult] = []

    def execute(self, action: ExecutionAction) -> ExecutionResult:
        """Execute an action with retries, validation, and telemetry.

        Algorithm:
        1. Emit action_started event
        2. Validate pre-conditions (element exists, visible)
        3. Execute action
        4. If verify_after: verify success
        5. Retry on failure with exponential backoff
        6. Emit success/failure event
        7. Return ExecutionResult

        Args:
            action: Structured execution action

        Returns:
            ExecutionResult with status, attempts, duration
        """
        start_time = time.time()

        # Emit started event
        self.telemetry.emit(
            TelemetryEvent(
                event=EventType.ACTION_STARTED,
                field=action.target,
                ats=self.ats_type,
                session_id=self.session_id,
                metadata={"action_type": action.action.value, "selector": action.selector},
            )
        )

        # Execute with retries
        for attempt in range(1, action.retry_count + 1):
            try:
                # Pre-validation
                if not self._validate_preconditions(action):
                    if attempt < action.retry_count:
                        self._wait_retry(attempt)
                        continue
                    else:
                        return self._build_failed_result(
                            action,
                            "Pre-validation failed: element not found or not visible",
                            attempt,
                            start_time,
                        )

                # Execute action
                self._execute_action(action)

                # Post-verification
                if action.verify_after:
                    verified, verified_value = self._verify_action(action)
                    if not verified:
                        if attempt < action.retry_count:
                            self.telemetry.emit(
                                TelemetryEvent(
                                    event=EventType.ACTION_RETRYING,
                                    field=action.target,
                                    ats=self.ats_type,
                                    session_id=self.session_id,
                                    retry_count=attempt,
                                    reason="verification_failed",
                                )
                            )
                            self._wait_retry(attempt)
                            continue
                        else:
                            return self._build_failed_result(
                                action,
                                f"Verification failed (expected: {getattr(action, 'value', 'N/A')})",
                                attempt,
                                start_time,
                            )
                else:
                    verified = False
                    verified_value = None

                # Success!
                return self._build_success_result(
                    action, attempt, start_time, verified, verified_value
                )

            except PlaywrightError as e:
                if attempt < action.retry_count:
                    self.telemetry.emit(
                        TelemetryEvent(
                            event=EventType.ACTION_RETRYING,
                            field=action.target,
                            ats=self.ats_type,
                            session_id=self.session_id,
                            retry_count=attempt,
                            reason="playwright_error",
                            error_message=str(e),
                        )
                    )
                    self._wait_retry(attempt)
                    continue
                else:
                    return self._build_failed_result(action, str(e), attempt, start_time)

            except Exception as e:
                # Unexpected error, fail immediately
                return self._build_failed_result(action, f"Unexpected error: {e}", attempt, start_time)

        # Should never reach here
        return self._build_failed_result(action, "Max retries exceeded", action.retry_count, start_time)

    def execute_batch(self, actions: List[ExecutionAction]) -> List[ExecutionResult]:
        """Execute a batch of actions sequentially.

        Args:
            actions: List of actions to execute

        Returns:
            List of ExecutionResults
        """
        results: List[ExecutionResult] = []

        for action in actions:
            result = self.execute(action)
            results.append(result)

            # Stop on first failure if action is critical
            if result.status == ExecutionStatus.FAILED and action.verify_after:
                break

        return results

    # ── Private Methods ───────────────────────────────────────────────────────

    def _validate_preconditions(self, action: ExecutionAction) -> bool:
        """Validate that element exists and is ready for interaction.

        Args:
            action: Action to validate

        Returns:
            True if preconditions met
        """
        try:
            locator = self.page.locator(action.selector).first

            # Check exists
            if locator.count() == 0:
                self.telemetry.emit_selector_not_found(
                    action.target, action.selector, self.ats_type, self.session_id
                )
                return False

            # Check visible (unless it's a file input)
            if not isinstance(action, UploadFileAction):
                if not locator.is_visible(timeout=action.timeout_ms):
                    return False

            # Success
            self.telemetry.emit(
                TelemetryEvent(
                    event=EventType.SELECTOR_FOUND,
                    field=action.target,
                    ats=self.ats_type,
                    session_id=self.session_id,
                    success=True,
                    metadata={"selector": action.selector},
                )
            )
            return True

        except PlaywrightError:
            return False

    def _execute_action(self, action: ExecutionAction) -> None:
        """Execute the actual action (fill, click, select, upload).

        Args:
            action: Action to execute

        Raises:
            PlaywrightError: If action fails
        """
        locator = self.page.locator(action.selector).first

        if isinstance(action, FillInputAction):
            if action.clear_first:
                locator.clear(timeout=action.timeout_ms)
            locator.fill(action.value, timeout=action.timeout_ms)

        elif isinstance(action, ClickAction):
            locator.click(timeout=action.timeout_ms)
            if action.wait_for_navigation:
                self.page.wait_for_load_state("networkidle", timeout=action.timeout_ms)

        elif isinstance(action, SelectOptionAction):
            if action.match_strategy == "exact":
                locator.select_option(label=action.value, timeout=action.timeout_ms)
            elif action.match_strategy == "contains":
                # Find option containing value
                options = locator.evaluate(
                    """el => Array.from(el.options).map(o => o.text)"""
                )
                matching = [opt for opt in options if action.value.lower() in opt.lower()]
                if matching:
                    locator.select_option(label=matching[0], timeout=action.timeout_ms)
                else:
                    raise ValueError(f"No option contains '{action.value}'")
            else:  # fuzzy
                # Implement fuzzy matching if needed
                locator.select_option(label=action.value, timeout=action.timeout_ms)

        elif isinstance(action, UploadFileAction):
            locator.set_input_files(action.file_path, timeout=action.timeout_ms)

        elif isinstance(action, WaitAction):
            if action.wait_type == "appear":
                locator.wait_for(state="visible", timeout=action.timeout_ms)
            elif action.wait_type == "disappear":
                locator.wait_for(state="hidden", timeout=action.timeout_ms)
            elif action.wait_type == "time":
                time.sleep(action.timeout_ms / 1000.0)

    def _verify_action(self, action: ExecutionAction) -> tuple[bool, Optional[str]]:
        """Verify action succeeded by reading back value/state.

        Args:
            action: Action to verify

        Returns:
            (verified, value_read_back)
        """
        try:
            locator = self.page.locator(action.selector).first

            if isinstance(action, FillInputAction):
                # Read back value
                actual_value = locator.input_value(timeout=1000)
                expected_value = action.value

                # Normalize for comparison
                actual_normalized = actual_value.strip()
                expected_normalized = expected_value.strip()

                verified = actual_normalized == expected_normalized

                if verified:
                    self.telemetry.emit(
                        TelemetryEvent(
                            event=EventType.VERIFICATION_PASSED,
                            field=action.target,
                            ats=self.ats_type,
                            session_id=self.session_id,
                            success=True,
                        )
                    )
                else:
                    self.telemetry.emit(
                        TelemetryEvent(
                            event=EventType.VERIFICATION_FAILED,
                            field=action.target,
                            ats=self.ats_type,
                            session_id=self.session_id,
                            success=False,
                            reason="value_mismatch",
                            metadata={
                                "expected": expected_normalized,
                                "actual": actual_normalized,
                            },
                        )
                    )

                return verified, actual_value

            elif isinstance(action, SelectOptionAction):
                # Verify selected option
                selected = locator.evaluate(
                    "el => el.selectedOptions[0]?.text || null"
                )
                verified = selected and action.value.lower() in selected.lower()
                return verified, selected

            elif isinstance(action, UploadFileAction):
                # Verify file was set
                files = locator.evaluate("el => el.files ? el.files.length : 0")
                verified = files > 0
                return verified, str(files) if files else None

            else:
                # Other actions don't have verifiable state
                return True, None

        except PlaywrightError:
            return False, None

    def _wait_retry(self, attempt: int) -> None:
        """Wait before retry with exponential backoff + jitter.

        Args:
            attempt: Current attempt number (1-indexed)
        """
        # Exponential backoff: base * 2^(attempt-1)
        delay_ms = min(
            self.BASE_RETRY_DELAY_MS * (2 ** (attempt - 1)),
            self.MAX_RETRY_DELAY_MS,
        )

        # Add jitter: ±30%
        jitter = delay_ms * self.JITTER_FACTOR * (2 * random.random() - 1)
        final_delay_ms = max(0, delay_ms + jitter)

        time.sleep(final_delay_ms / 1000.0)

    def _build_success_result(
        self,
        action: ExecutionAction,
        attempts: int,
        start_time: float,
        verified: bool,
        verified_value: Optional[str],
    ) -> ExecutionResult:
        """Build success result and emit telemetry.

        Args:
            action: Executed action
            attempts: Number of attempts
            start_time: Start timestamp
            verified: Was verification successful?
            verified_value: Value read back (if applicable)

        Returns:
            ExecutionResult
        """
        duration_ms = int((time.time() - start_time) * 1000)

        # Emit success event
        if isinstance(action, FillInputAction):
            self.telemetry.emit_field_fill_succeeded(
                action.target,
                action.value,
                confidence=1.0,  # Successful execution = high confidence
                duration_ms=duration_ms,
                ats=self.ats_type,
                session_id=self.session_id,
            )
        else:
            self.telemetry.emit(
                TelemetryEvent(
                    event=EventType.ACTION_SUCCEEDED,
                    field=action.target,
                    ats=self.ats_type,
                    session_id=self.session_id,
                    success=True,
                    duration_ms=duration_ms,
                    retry_count=attempts - 1,
                    metadata={"action_type": action.action.value},
                )
            )

        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            action_target=action.target,
            attempts=attempts,
            duration_ms=duration_ms,
            verified=verified,
            verified_value=verified_value,
        )

        self.executed_actions.append(result)
        return result

    def _build_failed_result(
        self,
        action: ExecutionAction,
        error_message: str,
        attempts: int,
        start_time: float,
    ) -> ExecutionResult:
        """Build failed result and emit telemetry.

        Args:
            action: Failed action
            error_message: Error description
            attempts: Number of attempts
            start_time: Start timestamp

        Returns:
            ExecutionResult
        """
        duration_ms = int((time.time() - start_time) * 1000)

        # Emit failure event
        if isinstance(action, FillInputAction):
            self.telemetry.emit_field_fill_failed(
                action.target,
                reason="execution_error",
                confidence=0.0,
                ats=self.ats_type,
                error_message=error_message,
                retry_count=attempts - 1,
                session_id=self.session_id,
            )
        else:
            self.telemetry.emit(
                TelemetryEvent(
                    event=EventType.ACTION_FAILED,
                    field=action.target,
                    ats=self.ats_type,
                    session_id=self.session_id,
                    success=False,
                    reason="execution_error",
                    error_message=error_message,
                    duration_ms=duration_ms,
                    retry_count=attempts - 1,
                    metadata={"action_type": action.action.value},
                )
            )

        result = ExecutionResult(
            status=ExecutionStatus.FAILED,
            action_target=action.target,
            attempts=attempts,
            duration_ms=duration_ms,
            verified=False,
            error=error_message,
        )

        self.failed_actions.append(result)
        return result

    # ── State Tracking ────────────────────────────────────────────────────────

    def get_success_rate(self) -> float:
        """Get overall success rate for this session.

        Returns:
            Success rate [0.0, 1.0]
        """
        total = len(self.executed_actions) + len(self.failed_actions)
        if total == 0:
            return 0.0
        return len(self.executed_actions) / total

    def get_failed_targets(self) -> List[str]:
        """Get list of failed action targets.

        Returns:
            List of target field IDs that failed
        """
        return [r.action_target for r in self.failed_actions]
