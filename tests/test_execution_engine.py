"""Tests for execution engine with retries, validation, and telemetry."""

import time
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from playwright.sync_api import Error as PlaywrightError

from jobcli.execution.actions import (
    ActionType,
    ClickAction,
    FillInputAction,
    SelectOptionAction,
    UploadFileAction,
    WaitAction,
)
from jobcli.execution.engine import ExecutionEngine, ExecutionResult, ExecutionStatus
from jobcli.execution.telemetry import EventType, TelemetryTracker
from jobcli.profile.schemas import ATSType


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_page():
    """Create a mock Playwright Page."""
    page = MagicMock()
    locator = MagicMock()

    # Setup default successful behaviors
    locator.count.return_value = 1
    locator.is_visible.return_value = True
    locator.input_value.return_value = "test@example.com"

    page.locator.return_value.first = locator

    return page


@pytest.fixture
def telemetry_tracker():
    """Create a fresh telemetry tracker."""
    return TelemetryTracker()


@pytest.fixture
def execution_engine(mock_page, telemetry_tracker):
    """Create execution engine with mocks."""
    return ExecutionEngine(
        page=mock_page,
        ats_type=ATSType.GREENHOUSE,
        session_id="test-session-123",
        telemetry_tracker=telemetry_tracker,
    )


# ── FillInputAction Tests ─────────────────────────────────────────────────────


def test_fill_input_success(execution_engine, mock_page):
    """Test successful fill input action."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=True,
    )

    # Mock locator to return the value we filled
    mock_page.locator.return_value.first.input_value.return_value = "test@example.com"

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.action_target == "email_field"
    assert result.attempts == 1
    assert result.verified is True
    assert result.verified_value == "test@example.com"
    assert result.error is None


def test_fill_input_without_verification(execution_engine, mock_page):
    """Test fill input without post-verification."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=False,
    )

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.verified is False
    assert result.verified_value is None


def test_fill_input_verification_mismatch(execution_engine, mock_page):
    """Test fill input with verification mismatch."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=True,
        retry_count=1,  # Only 1 attempt to speed up test
    )

    # Mock returns different value than what we tried to fill
    mock_page.locator.return_value.first.input_value.return_value = "wrong@example.com"

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.FAILED
    assert result.verified is False
    assert "Verification failed" in result.error


def test_fill_input_clear_first(execution_engine, mock_page):
    """Test fill input with clear_first flag."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        clear_first=True,
        verify_after=False,
    )

    locator = mock_page.locator.return_value.first

    execution_engine.execute(action)

    # Should call clear before fill
    locator.clear.assert_called_once()
    locator.fill.assert_called_once_with("test@example.com", timeout=5000)


# ── ClickAction Tests ─────────────────────────────────────────────────────────


def test_click_action_success(execution_engine, mock_page):
    """Test successful click action."""
    action = ClickAction(
        target="submit_button",
        selector="button[type='submit']",
        verify_after=False,
    )

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.action_target == "submit_button"
    mock_page.locator.return_value.first.click.assert_called_once()


def test_click_with_navigation(execution_engine, mock_page):
    """Test click with navigation wait."""
    action = ClickAction(
        target="submit_button",
        selector="button[type='submit']",
        wait_for_navigation=True,
        verify_after=False,
    )

    execution_engine.execute(action)

    mock_page.locator.return_value.first.click.assert_called_once()
    mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=5000)


# ── SelectOptionAction Tests ──────────────────────────────────────────────────


def test_select_option_exact(execution_engine, mock_page):
    """Test select option with exact match."""
    action = SelectOptionAction(
        target="country_field",
        selector="select[name='country']",
        value="United States",
        match_strategy="exact",
        verify_after=False,
    )

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    mock_page.locator.return_value.first.select_option.assert_called_once_with(
        label="United States", timeout=5000
    )


def test_select_option_contains(execution_engine, mock_page):
    """Test select option with contains match."""
    action = SelectOptionAction(
        target="country_field",
        selector="select[name='country']",
        value="States",
        match_strategy="contains",
        verify_after=False,
    )

    # Mock evaluate to return available options
    mock_page.locator.return_value.first.evaluate.return_value = [
        "United States",
        "Canada",
        "Mexico",
    ]

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    # Should match "United States" since it contains "States"
    mock_page.locator.return_value.first.select_option.assert_called_once()


def test_select_option_contains_no_match(execution_engine, mock_page):
    """Test select option contains with no matching option."""
    action = SelectOptionAction(
        target="country_field",
        selector="select[name='country']",
        value="NonExistent",
        match_strategy="contains",
        verify_after=False,
        retry_count=1,
    )

    mock_page.locator.return_value.first.evaluate.return_value = [
        "United States",
        "Canada",
    ]

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.FAILED
    assert "No option contains" in result.error


# ── UploadFileAction Tests ────────────────────────────────────────────────────


def test_upload_file_success(execution_engine, mock_page):
    """Test successful file upload."""
    action = UploadFileAction(
        target="resume_upload",
        selector="input[type='file']",
        file_path="/path/to/resume.pdf",
        verify_after=False,
    )

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    mock_page.locator.return_value.first.set_input_files.assert_called_once_with(
        "/path/to/resume.pdf", timeout=5000
    )


def test_upload_file_with_verification(execution_engine, mock_page):
    """Test file upload with verification."""
    action = UploadFileAction(
        target="resume_upload",
        selector="input[type='file']",
        file_path="/path/to/resume.pdf",
        verify_after=True,
    )

    # Mock that file was uploaded
    mock_page.locator.return_value.first.evaluate.return_value = 1

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.verified is True


# ── WaitAction Tests ──────────────────────────────────────────────────────────


def test_wait_for_appear(execution_engine, mock_page):
    """Test wait for element to appear."""
    action = WaitAction(
        target="loading_spinner",
        selector=".spinner",
        wait_type="appear",
        timeout_ms=3000,
    )

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    mock_page.locator.return_value.first.wait_for.assert_called_once_with(
        state="visible", timeout=3000
    )


def test_wait_for_disappear(execution_engine, mock_page):
    """Test wait for element to disappear."""
    action = WaitAction(
        target="loading_spinner",
        selector=".spinner",
        wait_type="disappear",
        timeout_ms=3000,
    )

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    mock_page.locator.return_value.first.wait_for.assert_called_once_with(
        state="hidden", timeout=3000
    )


def test_wait_for_time(execution_engine, mock_page):
    """Test wait for fixed time."""
    action = WaitAction(
        target="delay",
        selector="body",
        wait_type="time",
        timeout_ms=100,  # 100ms for fast test
    )

    start = time.time()
    result = execution_engine.execute(action)
    elapsed_ms = (time.time() - start) * 1000

    assert result.status == ExecutionStatus.SUCCESS
    assert elapsed_ms >= 100
    assert elapsed_ms < 200  # Should be close to 100ms


# ── Pre-validation Tests ──────────────────────────────────────────────────────


def test_prevalidation_element_not_found(execution_engine, mock_page):
    """Test pre-validation fails when element not found."""
    action = FillInputAction(
        target="missing_field",
        selector="input[name='missing']",
        value="test",
        retry_count=1,
    )

    # Element doesn't exist
    mock_page.locator.return_value.first.count.return_value = 0

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.FAILED
    assert "Pre-validation failed" in result.error


def test_prevalidation_element_not_visible(execution_engine, mock_page):
    """Test pre-validation fails when element not visible."""
    action = FillInputAction(
        target="hidden_field",
        selector="input[name='hidden']",
        value="test",
        retry_count=1,
    )

    locator = mock_page.locator.return_value.first
    locator.count.return_value = 1
    locator.is_visible.return_value = False

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.FAILED
    assert "Pre-validation failed" in result.error


# ── Retry Logic Tests ─────────────────────────────────────────────────────────


def test_retry_on_playwright_error(execution_engine, mock_page):
    """Test retry on Playwright error."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        retry_count=3,
        verify_after=False,
    )

    locator = mock_page.locator.return_value.first

    # Fail twice, succeed on third attempt
    locator.fill.side_effect = [
        PlaywrightError("Timeout"),
        PlaywrightError("Timeout"),
        None,  # Success
    ]

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.attempts == 3
    assert locator.fill.call_count == 3


def test_retry_exhausted(execution_engine, mock_page):
    """Test all retries exhausted."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        retry_count=2,
        verify_after=False,
    )

    locator = mock_page.locator.return_value.first
    locator.fill.side_effect = PlaywrightError("Timeout")

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.FAILED
    assert result.attempts == 2
    assert "Timeout" in result.error


def test_exponential_backoff_timing(execution_engine, mock_page):
    """Test exponential backoff delays increase."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        retry_count=3,
        verify_after=False,
    )

    locator = mock_page.locator.return_value.first
    locator.fill.side_effect = [
        PlaywrightError("Timeout"),
        PlaywrightError("Timeout"),
        None,
    ]

    start = time.time()
    result = execution_engine.execute(action)
    elapsed_ms = (time.time() - start) * 1000

    assert result.status == ExecutionStatus.SUCCESS
    # First retry: ~500ms, second retry: ~1000ms
    # With jitter, should be at least 1000ms total
    assert elapsed_ms >= 1000


# ── Telemetry Tests ───────────────────────────────────────────────────────────


def test_telemetry_action_started(execution_engine, telemetry_tracker):
    """Test action_started event is emitted."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=False,
    )

    execution_engine.execute(action)

    started_events = [e for e in telemetry_tracker.events if e.event == EventType.ACTION_STARTED]
    assert len(started_events) == 1
    assert started_events[0].field == "email_field"


def test_telemetry_field_fill_succeeded(execution_engine, telemetry_tracker):
    """Test field_fill_succeeded event on success."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=False,
    )

    execution_engine.execute(action)

    success_events = [e for e in telemetry_tracker.events if e.event == EventType.FIELD_FILL_SUCCEEDED]
    assert len(success_events) == 1
    assert success_events[0].field == "email_field"
    assert success_events[0].success is True


def test_telemetry_field_fill_failed(execution_engine, telemetry_tracker, mock_page):
    """Test field_fill_failed event on failure."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        retry_count=1,
        verify_after=False,
    )

    mock_page.locator.return_value.first.fill.side_effect = PlaywrightError("Timeout")

    execution_engine.execute(action)

    failed_events = [e for e in telemetry_tracker.events if e.event == EventType.FIELD_FILL_FAILED]
    assert len(failed_events) == 1
    assert failed_events[0].field == "email_field"
    assert failed_events[0].success is False


def test_telemetry_verification_passed(execution_engine, telemetry_tracker, mock_page):
    """Test verification_passed event when verification succeeds."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=True,
    )

    mock_page.locator.return_value.first.input_value.return_value = "test@example.com"

    execution_engine.execute(action)

    verify_events = [e for e in telemetry_tracker.events if e.event == EventType.VERIFICATION_PASSED]
    assert len(verify_events) == 1


def test_telemetry_verification_failed(execution_engine, telemetry_tracker, mock_page):
    """Test verification_failed event when verification fails."""
    action = FillInputAction(
        target="email_field",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=True,
        retry_count=1,
    )

    mock_page.locator.return_value.first.input_value.return_value = "wrong@example.com"

    execution_engine.execute(action)

    verify_events = [e for e in telemetry_tracker.events if e.event == EventType.VERIFICATION_FAILED]
    assert len(verify_events) == 1


def test_telemetry_selector_not_found(execution_engine, telemetry_tracker, mock_page):
    """Test selector_not_found event when element missing."""
    action = FillInputAction(
        target="missing_field",
        selector="input[name='missing']",
        value="test",
        retry_count=1,
    )

    mock_page.locator.return_value.first.count.return_value = 0

    execution_engine.execute(action)

    not_found_events = [e for e in telemetry_tracker.events if e.event == EventType.SELECTOR_NOT_FOUND]
    assert len(not_found_events) >= 1


# ── Batch Execution Tests ─────────────────────────────────────────────────────


def test_execute_batch_all_success(execution_engine, mock_page):
    """Test batch execution with all successful actions."""
    actions = [
        FillInputAction(
            target="email",
            selector="input[name='email']",
            value="test@example.com",
            verify_after=False,
        ),
        FillInputAction(
            target="name",
            selector="input[name='name']",
            value="John Doe",
            verify_after=False,
        ),
    ]

    results = execution_engine.execute_batch(actions)

    assert len(results) == 2
    assert all(r.status == ExecutionStatus.SUCCESS for r in results)


def test_execute_batch_stop_on_critical_failure(execution_engine, mock_page):
    """Test batch execution stops on critical failure."""
    actions = [
        FillInputAction(
            target="email",
            selector="input[name='email']",
            value="test@example.com",
            verify_after=True,  # Critical (verify_after=True)
            retry_count=1,
        ),
        FillInputAction(
            target="name",
            selector="input[name='name']",
            value="John Doe",
            verify_after=False,
        ),
    ]

    # First action fails verification
    mock_page.locator.return_value.first.input_value.return_value = "wrong@example.com"

    results = execution_engine.execute_batch(actions)

    # Should only execute first action (critical failure stops batch)
    assert len(results) == 1
    assert results[0].status == ExecutionStatus.FAILED


# ── State Tracking Tests ──────────────────────────────────────────────────────


def test_state_tracking_executed_actions(execution_engine):
    """Test executed_actions list is populated."""
    action = FillInputAction(
        target="email",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=False,
    )

    execution_engine.execute(action)

    assert len(execution_engine.executed_actions) == 1
    assert execution_engine.executed_actions[0].action_target == "email"


def test_state_tracking_failed_actions(execution_engine, mock_page):
    """Test failed_actions list is populated."""
    action = FillInputAction(
        target="email",
        selector="input[name='email']",
        value="test@example.com",
        retry_count=1,
        verify_after=False,
    )

    mock_page.locator.return_value.first.fill.side_effect = PlaywrightError("Timeout")

    execution_engine.execute(action)

    assert len(execution_engine.failed_actions) == 1
    assert execution_engine.failed_actions[0].action_target == "email"


def test_get_success_rate(execution_engine, mock_page):
    """Test success rate calculation."""
    # Execute 3 successful actions
    for i in range(3):
        action = FillInputAction(
            target=f"field_{i}",
            selector=f"input[name='field_{i}']",
            value="test",
            verify_after=False,
        )
        execution_engine.execute(action)

    # Execute 1 failed action
    action = FillInputAction(
        target="failed_field",
        selector="input[name='failed']",
        value="test",
        retry_count=1,
        verify_after=False,
    )
    mock_page.locator.return_value.first.fill.side_effect = PlaywrightError("Timeout")
    execution_engine.execute(action)

    success_rate = execution_engine.get_success_rate()
    assert success_rate == 0.75  # 3/4 = 0.75


def test_get_failed_targets(execution_engine, mock_page):
    """Test getting list of failed targets."""
    # One successful
    action1 = FillInputAction(
        target="email",
        selector="input[name='email']",
        value="test@example.com",
        verify_after=False,
    )
    execution_engine.execute(action1)

    # Two failed
    for target in ["field1", "field2"]:
        action = FillInputAction(
            target=target,
            selector=f"input[name='{target}']",
            value="test",
            retry_count=1,
            verify_after=False,
        )
        mock_page.locator.return_value.first.fill.side_effect = PlaywrightError("Timeout")
        execution_engine.execute(action)

    failed_targets = execution_engine.get_failed_targets()
    assert len(failed_targets) == 2
    assert "field1" in failed_targets
    assert "field2" in failed_targets


# ── Edge Cases ────────────────────────────────────────────────────────────────


def test_unexpected_error_fails_immediately(execution_engine, mock_page):
    """Test unexpected errors fail without retries."""
    action = FillInputAction(
        target="email",
        selector="input[name='email']",
        value="test@example.com",
        retry_count=3,
        verify_after=False,
    )

    # Unexpected error (not PlaywrightError)
    mock_page.locator.return_value.first.fill.side_effect = RuntimeError("Unexpected")

    result = execution_engine.execute(action)

    assert result.status == ExecutionStatus.FAILED
    assert result.attempts == 1  # No retries on unexpected errors
    assert "Unexpected error" in result.error


def test_empty_batch(execution_engine):
    """Test executing empty batch."""
    results = execution_engine.execute_batch([])
    assert len(results) == 0


def test_custom_timeout(execution_engine, mock_page):
    """Test custom timeout is respected."""
    action = FillInputAction(
        target="email",
        selector="input[name='email']",
        value="test@example.com",
        timeout_ms=10000,
        verify_after=False,
    )

    execution_engine.execute(action)

    mock_page.locator.return_value.first.fill.assert_called_once_with(
        "test@example.com", timeout=10000
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
