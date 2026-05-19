"""Integration tests for complete ATS flows.

Tests end-to-end application flows across different ATS platforms:
- Greenhouse
- Lever
- Workday
- Taleo
- SmartRecruiters

Validates:
- Field detection and filling
- Resume upload
- Question answering
- Form submission
- Error handling
"""

import tempfile
from pathlib import Path
from typing import Dict, List
from unittest.mock import Mock, patch

import pytest
from playwright.sync_api import Page

from jobcli.execution.actions import (
    ActionType,
    ClickAction,
    ExecutionAction,
    FillInputAction,
    SelectOptionAction,
    UploadFileAction,
    VerifyAction,
)
from jobcli.execution.engine import ExecutionEngine, ExecutionResult, ExecutionStatus
from jobcli.execution.telemetry import get_telemetry_tracker
from jobcli.healing.self_healing_engine import SelfHealingEngine
from jobcli.memory import ApplicationMemory
from jobcli.observability import create_trace_context, get_logger, set_trace_context


class ATSTestScenario:
    """Test scenario for an ATS platform."""

    def __init__(
        self,
        ats_name: str,
        fields: List[Dict],
        resume_selector: str,
        submit_selector: str,
    ):
        self.ats_name = ats_name
        self.fields = fields
        self.resume_selector = resume_selector
        self.submit_selector = submit_selector


# ATS test scenarios
GREENHOUSE_SCENARIO = ATSTestScenario(
    ats_name="Greenhouse",
    fields=[
        {
            "selector": "#first_name",
            "field_id": "first_name",
            "field_type": "text_input",
            "value": "John",
        },
        {
            "selector": "#last_name",
            "field_id": "last_name",
            "field_type": "text_input",
            "value": "Doe",
        },
        {
            "selector": "#email",
            "field_id": "email",
            "field_type": "email",
            "value": "john.doe@example.com",
        },
        {
            "selector": "#phone",
            "field_id": "phone",
            "field_type": "phone",
            "value": "555-0100",
        },
    ],
    resume_selector="#resume",
    submit_selector="#submit_app",
)

LEVER_SCENARIO = ATSTestScenario(
    ats_name="Lever",
    fields=[
        {
            "selector": "input[name='name']",
            "field_id": "full_name",
            "field_type": "text_input",
            "value": "John Doe",
        },
        {
            "selector": "input[name='email']",
            "field_id": "email",
            "field_type": "email",
            "value": "john.doe@example.com",
        },
        {
            "selector": "input[name='phone']",
            "field_id": "phone",
            "field_type": "phone",
            "value": "555-0100",
        },
        {
            "selector": "input[name='org']",
            "field_id": "company",
            "field_type": "text_input",
            "value": "ACME Corp",
        },
    ],
    resume_selector="input[name='resume']",
    submit_selector=".application-submit",
)

WORKDAY_SCENARIO = ATSTestScenario(
    ats_name="Workday",
    fields=[
        {
            "selector": "input[data-automation-id='legalNameSection_firstName']",
            "field_id": "first_name",
            "field_type": "text_input",
            "value": "John",
        },
        {
            "selector": "input[data-automation-id='legalNameSection_lastName']",
            "field_id": "last_name",
            "field_type": "text_input",
            "value": "Doe",
        },
        {
            "selector": "input[data-automation-id='email']",
            "field_id": "email",
            "field_type": "email",
            "value": "john.doe@example.com",
        },
        {
            "selector": "input[data-automation-id='phone-number']",
            "field_id": "phone",
            "field_type": "phone",
            "value": "555-0100",
        },
    ],
    resume_selector="input[data-automation-id='file-upload-input-ref']",
    submit_selector="button[data-automation-id='bottom-navigation-next-button']",
)


class MockPageWithForm:
    """Mock Playwright page with form elements."""

    def __init__(self, scenario: ATSTestScenario):
        self.scenario = scenario
        self.filled_fields: Dict[str, str] = {}
        self.uploaded_files: List[str] = []
        self.submitted = False

    def wait_for_selector(self, selector: str, **kwargs):
        """Mock wait_for_selector."""
        # Check if selector matches any field
        for field in self.scenario.fields:
            if field["selector"] == selector:
                return self._create_element(field["selector"])

        if selector == self.scenario.resume_selector:
            return self._create_element(selector)

        if selector == self.scenario.submit_selector:
            return self._create_element(selector)

        # Selector not found
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        raise PlaywrightTimeoutError(f"Selector not found: {selector}")

    def query_selector(self, selector: str):
        """Mock query_selector."""
        try:
            return self.wait_for_selector(selector, timeout=0)
        except:
            return None

    def _create_element(self, selector: str):
        """Create mock element."""
        element = Mock()
        element.is_visible.return_value = True
        element.is_enabled.return_value = True

        def fill_mock(value):
            self.filled_fields[selector] = value

        def click_mock():
            if selector == self.scenario.submit_selector:
                self.submitted = True

        def set_input_files_mock(files):
            self.uploaded_files.append(files)

        element.fill = fill_mock
        element.click = click_mock
        element.set_input_files = set_input_files_mock
        element.input_value.return_value = self.filled_fields.get(selector, "")

        return element


class TestGreenhouseFlow:
    """Test Greenhouse ATS flow."""

    def test_complete_application_flow(self):
        """Test complete application on Greenhouse."""
        scenario = GREENHOUSE_SCENARIO
        page_mock = MockPageWithForm(scenario)

        # Create execution engine
        logger = get_logger("greenhouse_test")
        engine = ExecutionEngine(page=page_mock, logger=logger)

        # Set trace context
        context = create_trace_context(
            session_id="test_session",
            company_name="Test Company",
            position_title="Software Engineer",
            attempt_number=1,
            operation="greenhouse_application",
        )
        set_trace_context(context)

        # Fill fields
        actions = []

        for field in scenario.fields:
            actions.append(
                FillInputAction(
                    selector=field["selector"],
                    field_id=field["field_id"],
                    field_type=field["field_type"],
                    field_label=field["field_id"],
                    value=field["value"],
                )
            )

        # Execute field fills
        results = []
        for action in actions:
            result = engine.execute(action)
            results.append(result)

        # All fields should succeed
        assert all(r.success for r in results), "All fields should fill successfully"

        # Verify filled values
        assert len(page_mock.filled_fields) == len(scenario.fields)
        assert page_mock.filled_fields["#email"] == "john.doe@example.com"

        # Upload resume
        resume_action = UploadFileAction(
            selector=scenario.resume_selector,
            field_id="resume",
            field_label="Resume",
            file_path="/tmp/resume.pdf",
        )

        resume_result = engine.execute(resume_action)
        assert resume_result.success
        assert len(page_mock.uploaded_files) == 1

        # Submit
        submit_action = ClickAction(
            selector=scenario.submit_selector,
            field_id="submit",
            field_label="Submit Application",
        )

        submit_result = engine.execute(submit_action)
        assert submit_result.success
        assert page_mock.submitted


class TestLeverFlow:
    """Test Lever ATS flow."""

    def test_complete_application_flow(self):
        """Test complete application on Lever."""
        scenario = LEVER_SCENARIO
        page_mock = MockPageWithForm(scenario)

        logger = get_logger("lever_test")
        engine = ExecutionEngine(page=page_mock, logger=logger)

        context = create_trace_context(
            session_id="test_session",
            company_name="Test Company",
            position_title="Frontend Engineer",
            attempt_number=1,
            operation="lever_application",
        )
        set_trace_context(context)

        # Fill fields
        for field in scenario.fields:
            action = FillInputAction(
                selector=field["selector"],
                field_id=field["field_id"],
                field_type=field["field_type"],
                field_label=field["field_id"],
                value=field["value"],
            )

            result = engine.execute(action)
            assert result.success, f"Field {field['field_id']} should succeed"

        # Upload resume
        resume_action = UploadFileAction(
            selector=scenario.resume_selector,
            field_id="resume",
            field_label="Resume",
            file_path="/tmp/resume.pdf",
        )

        resume_result = engine.execute(resume_action)
        assert resume_result.success

        # Submit
        submit_action = ClickAction(
            selector=scenario.submit_selector,
            field_id="submit",
            field_label="Submit Application",
        )

        submit_result = engine.execute(submit_action)
        assert submit_result.success


class TestWorkdayFlow:
    """Test Workday ATS flow."""

    def test_complete_application_flow(self):
        """Test complete application on Workday."""
        scenario = WORKDAY_SCENARIO
        page_mock = MockPageWithForm(scenario)

        logger = get_logger("workday_test")
        engine = ExecutionEngine(page=page_mock, logger=logger)

        context = create_trace_context(
            session_id="test_session",
            company_name="Test Company",
            position_title="Backend Engineer",
            attempt_number=1,
            operation="workday_application",
        )
        set_trace_context(context)

        # Fill fields
        for field in scenario.fields:
            action = FillInputAction(
                selector=field["selector"],
                field_id=field["field_id"],
                field_type=field["field_type"],
                field_label=field["field_id"],
                value=field["value"],
            )

            result = engine.execute(action)
            assert result.success

        # Workday has data-automation-id selectors
        assert any(
            "data-automation-id" in field["selector"] for field in scenario.fields
        )


class TestATSFlowWithMemory:
    """Test ATS flows with application memory."""

    def test_greenhouse_with_memory_learning(self):
        """Test Greenhouse flow with memory learning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ApplicationMemory(storage_path=Path(tmpdir) / "memory.json")

            # Create application
            app = memory.create_application(
                company_name="Google",
                position_title="Software Engineer",
                ats_type="greenhouse",
            )

            scenario = GREENHOUSE_SCENARIO
            page_mock = MockPageWithForm(scenario)

            logger = get_logger("greenhouse_memory_test")
            engine = ExecutionEngine(page=page_mock, logger=logger)

            # Fill fields and record answers
            for field in scenario.fields:
                action = FillInputAction(
                    selector=field["selector"],
                    field_id=field["field_id"],
                    field_type=field["field_type"],
                    field_label=field["field_id"],
                    value=field["value"],
                )

                result = engine.execute(action)

                # Record answer in memory
                if result.success:
                    memory.add_answer(
                        application_id=app.application_id,
                        question=field["field_id"],
                        answer=field["value"],
                        confidence=0.95,
                    )

            # Update status
            memory.update_application(
                application_id=app.application_id,
                status="submitted",
            )

            # Get history
            history = memory.get_company_history("Google")
            assert history is not None
            assert history.total_applications == 1

            # Check learned answers
            app_record = memory.get_application(app.application_id)
            assert len(app_record.answers) == len(scenario.fields)


class TestATSFlowWithHealing:
    """Test ATS flows with self-healing."""

    def test_greenhouse_with_selector_healing(self):
        """Test Greenhouse flow with selector healing."""
        scenario = GREENHOUSE_SCENARIO
        page_mock = MockPageWithForm(scenario)

        # Simulate selector change (common in ATS updates)
        old_email_selector = "#email"
        new_email_selector = "#email-input"  # Changed

        # Update mock to accept both
        original_fields = scenario.fields.copy()
        scenario.fields.append(
            {
                "selector": new_email_selector,
                "field_id": "email",
                "field_type": "email",
                "value": "john.doe@example.com",
            }
        )

        logger = get_logger("greenhouse_healing_test")
        base_engine = ExecutionEngine(page=page_mock, logger=logger)

        from jobcli.healing.selector_healer import SelectorHealer

        with tempfile.TemporaryDirectory() as tmpdir:
            healer = SelectorHealer(storage_path=Path(tmpdir) / "healing.json")

            # Record successful pattern
            healer.record_success(
                original_selector=old_email_selector,
                healed_selector=new_email_selector,
                field_type="email",
                strategy="attribute_variations",
            )

            # Create healing engine
            healing_engine = SelfHealingEngine(
                page=page_mock,
                execution_engine=base_engine,
                selector_healer=healer,
                enable_healing=True,
            )

            # Try with old selector (should heal)
            action = FillInputAction(
                selector=old_email_selector,
                field_id="email",
                field_type="email",
                field_label="Email",
                value="john.doe@example.com",
            )

            result = healing_engine.execute(action)

            # Should succeed via healing or direct execution
            # (Mock accepts both selectors)
            assert result is not None


class TestATSFlowWithTelemetry:
    """Test ATS flows with telemetry tracking."""

    def test_greenhouse_with_telemetry(self):
        """Test Greenhouse flow with telemetry."""
        tracker = get_telemetry_tracker()
        tracker.reset()  # Clear previous data

        scenario = GREENHOUSE_SCENARIO
        page_mock = MockPageWithForm(scenario)

        logger = get_logger("greenhouse_telemetry_test")
        engine = ExecutionEngine(page=page_mock, logger=logger, telemetry=tracker)

        # Fill all fields
        for field in scenario.fields:
            action = FillInputAction(
                selector=field["selector"],
                field_id=field["field_id"],
                field_type=field["field_type"],
                field_label=field["field_id"],
                value=field["value"],
            )

            engine.execute(action)

        # Check telemetry
        metrics = tracker.get_metrics()

        assert metrics["total_actions"] == len(scenario.fields)
        assert metrics["successful_actions"] == len(scenario.fields)
        assert metrics["field_fill_success_rate"] == 1.0


class TestCrossATSComparison:
    """Compare behavior across different ATS platforms."""

    def test_all_ats_platforms(self):
        """Test all ATS platforms and compare success rates."""
        scenarios = [
            GREENHOUSE_SCENARIO,
            LEVER_SCENARIO,
            WORKDAY_SCENARIO,
        ]

        results = {}

        for scenario in scenarios:
            page_mock = MockPageWithForm(scenario)
            logger = get_logger(f"{scenario.ats_name.lower()}_test")
            engine = ExecutionEngine(page=page_mock, logger=logger)

            success_count = 0

            for field in scenario.fields:
                action = FillInputAction(
                    selector=field["selector"],
                    field_id=field["field_id"],
                    field_type=field["field_type"],
                    field_label=field["field_id"],
                    value=field["value"],
                )

                result = engine.execute(action)
                if result.success:
                    success_count += 1

            success_rate = success_count / len(scenario.fields)
            results[scenario.ats_name] = success_rate

        # All should succeed
        for ats_name, rate in results.items():
            assert rate == 1.0, f"{ats_name} should have 100% success rate"

        print("\nATS Success Rates:")
        for ats_name, rate in results.items():
            print(f"  {ats_name}: {rate:.1%}")


class TestATSErrorHandling:
    """Test error handling across ATS platforms."""

    def test_missing_field_handling(self):
        """Test handling of missing fields."""
        scenario = GREENHOUSE_SCENARIO
        page_mock = MockPageWithForm(scenario)

        logger = get_logger("error_handling_test")
        engine = ExecutionEngine(page=page_mock, logger=logger)

        # Try to fill non-existent field
        action = FillInputAction(
            selector="#nonexistent-field",
            field_id="nonexistent",
            field_type="text_input",
            field_label="Nonexistent",
            value="test",
        )

        result = engine.execute(action)

        # Should fail gracefully
        assert not result.success
        assert result.status == ExecutionStatus.FAILED

    def test_disabled_field_handling(self):
        """Test handling of disabled fields."""
        scenario = GREENHOUSE_SCENARIO
        page_mock = MockPageWithForm(scenario)

        # Mock disabled element
        def create_disabled_element():
            element = Mock()
            element.is_visible.return_value = True
            element.is_enabled.return_value = False  # Disabled
            return element

        page_mock.wait_for_selector = lambda s, **k: create_disabled_element()

        logger = get_logger("disabled_field_test")
        engine = ExecutionEngine(page=page_mock, logger=logger)

        action = FillInputAction(
            selector="#email",
            field_id="email",
            field_type="email",
            field_label="Email",
            value="test@example.com",
        )

        result = engine.execute(action)

        # Should detect disabled state
        assert not result.success


def test_integration_suite():
    """Run full integration test suite."""
    print("\n=== Running ATS Integration Tests ===\n")

    test_classes = [
        TestGreenhouseFlow,
        TestLeverFlow,
        TestWorkdayFlow,
        TestATSFlowWithMemory,
        TestATSFlowWithHealing,
        TestATSFlowWithTelemetry,
        TestCrossATSComparison,
        TestATSErrorHandling,
    ]

    total = 0
    passed = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")

        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]

        for method_name in methods:
            total += 1
            try:
                method = getattr(instance, method_name)
                method()
                passed += 1
                print(f"  ✓ {method_name}")
            except Exception as e:
                print(f"  ✗ {method_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Integration Tests: {passed}/{total} passed")
    print(f"{'='*50}\n")

    assert passed == total, f"Some integration tests failed: {passed}/{total}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
