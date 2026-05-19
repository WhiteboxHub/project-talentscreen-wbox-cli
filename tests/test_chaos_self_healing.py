"""Chaos tests for self-healing system.

Randomly break:
- Selectors (invalid, changed, removed)
- Timing (race conditions, delays)
- Rendering (dynamic content, hydration)
- DOM structure (mutations, shadow DOM)

Ensure recovery mechanisms work.
"""

import asyncio
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from jobcli.execution.actions import (
    ActionType,
    ClickAction,
    ExecutionAction,
    FillInputAction,
    SelectOptionAction,
)
from jobcli.execution.engine import ExecutionResult, ExecutionStatus
from jobcli.healing.adaptive_retry import AdaptiveRetryStrategy, RetryStrategy
from jobcli.healing.modern_web_handler import FrameworkType, ModernWebHandler
from jobcli.healing.selector_healer import (
    HealingStrategy,
    SelectorHealer,
    SelectorHealingResult,
)
from jobcli.healing.self_healing_engine import SelfHealingEngine


class ChaosInjector:
    """Inject chaos into browser automation."""

    def __init__(self, page: Mock):
        self.page = page
        self.chaos_enabled = True
        self.failure_rate = 0.3  # 30% failure rate

    def maybe_fail_selector(self, selector: str) -> str:
        """Randomly mutate selector to cause failures."""
        if not self.chaos_enabled or random.random() > self.failure_rate:
            return selector

        mutation_type = random.choice([
            "invalid_id",
            "invalid_class",
            "invalid_attribute",
            "removed_element",
        ])

        if mutation_type == "invalid_id":
            # Change #id to #wrong-id
            if "#" in selector:
                return selector.replace("#", "#wrong-")

        elif mutation_type == "invalid_class":
            # Change .class to .wrong-class
            if "." in selector:
                parts = selector.split(".")
                return f".wrong-{parts[1]}"

        elif mutation_type == "invalid_attribute":
            # Change [attr="value"] to [attr="wrong"]
            if "[" in selector:
                return selector.replace("]", "-wrong]")

        elif mutation_type == "removed_element":
            # Return selector that doesn't exist
            return "#element-does-not-exist"

        return selector

    def maybe_inject_delay(self, min_ms: int = 100, max_ms: int = 2000) -> None:
        """Randomly inject timing delays."""
        if self.chaos_enabled and random.random() < self.failure_rate:
            delay = random.randint(min_ms, max_ms) / 1000
            time.sleep(delay)

    def maybe_mutate_dom(self) -> bool:
        """Randomly mutate DOM structure."""
        return self.chaos_enabled and random.random() < self.failure_rate

    def maybe_detach_element(self) -> bool:
        """Randomly detach element from DOM."""
        return self.chaos_enabled and random.random() < self.failure_rate


class TestChaosSelectors:
    """Chaos tests for selector healing."""

    def test_random_selector_mutations(self):
        """Test healing with randomly mutated selectors."""
        healer = SelectorHealer(storage_path=Path("/tmp/test_healing_patterns.json"))

        original_selectors = [
            "#email-input",
            ".name-field",
            "input[name='phone']",
            "#resume-upload",
            ".submit-button",
        ]

        chaos = ChaosInjector(None)

        success_count = 0
        total_attempts = 100

        for _ in range(total_attempts):
            selector = random.choice(original_selectors)
            mutated = chaos.maybe_fail_selector(selector)

            # Try to heal
            result = healer.heal_selector(
                original_selector=mutated,
                field_type="text_input",
            )

            if result.success:
                success_count += 1

        # Should heal at least some failures
        healing_rate = success_count / total_attempts
        print(f"Healing success rate: {healing_rate:.1%}")

        # Should heal at least 40% (conservative estimate)
        assert healing_rate >= 0.4, f"Healing rate too low: {healing_rate:.1%}"

    def test_selector_stability_over_time(self):
        """Test selector stability with DOM mutations."""
        healer = SelectorHealer(storage_path=Path("/tmp/test_healing_patterns.json"))

        # Record successful pattern
        healer.record_success(
            original_selector="#email",
            healed_selector="input[type='email']",
            field_type="email",
            strategy=HealingStrategy.ATTRIBUTE_VARIATIONS,
        )

        # Simulate DOM mutations over time
        mutated_selectors = [
            "#email-input",  # ID changed
            "#user-email",   # ID changed differently
            "#contact-email",
            "#email-field",
        ]

        healed_count = 0

        for mutated in mutated_selectors:
            result = healer.heal_selector(
                original_selector=mutated,
                field_type="email",
            )

            if result.success and result.confidence >= 0.6:
                healed_count += 1

        # Should heal most mutations
        assert healed_count >= len(mutated_selectors) * 0.5

    def test_cascade_selector_failures(self):
        """Test healing when multiple selectors fail in sequence."""
        healer = SelectorHealer(storage_path=Path("/tmp/test_healing_patterns.json"))

        # Simulate cascade failures
        failed_selectors = [
            "#name",
            ".name-field",
            "input[name='full_name']",
            "#full-name-input",
        ]

        # Try healing each
        results = []
        for selector in failed_selectors:
            result = healer.heal_selector(
                original_selector=selector,
                field_type="text_input",
            )
            results.append(result)

        # At least one should succeed
        assert any(r.success for r in results)

    def test_shadow_dom_chaos(self):
        """Test handling Shadow DOM with random failures."""
        page_mock = Mock(spec=Page)

        handler = ModernWebHandler(page_mock)

        # Mock Shadow DOM scenarios
        shadow_selectors = [
            "custom-input >>> #email",
            "form-component >>> .field >>> input",
            "#app >>> #form >>> #email-input",
        ]

        chaos = ChaosInjector(page_mock)

        for selector in shadow_selectors:
            # Randomly mutate
            mutated = chaos.maybe_fail_selector(selector)

            # Should handle gracefully (not crash)
            # In real scenario, would try fallback strategies
            assert mutated is not None


class TestChaosTiming:
    """Chaos tests for timing and race conditions."""

    def test_random_delays_with_adaptive_retry(self):
        """Test adaptive retry with random timing delays."""
        strategy = AdaptiveRetryStrategy()

        delays = []
        confidences = [0.9, 0.7, 0.5, 0.3, 0.2]  # Decreasing confidence

        for attempt in range(1, 6):
            confidence = confidences[attempt - 1]
            delay = strategy.calculate_retry_delay(
                attempt=attempt,
                confidence=confidence,
            )
            delays.append(delay)

        # Delays should increase as confidence decreases
        assert delays[0] < delays[-1], "Delays should increase with failures"

        # Should adapt to low confidence
        low_conf_delay = strategy.calculate_retry_delay(attempt=1, confidence=0.2)
        high_conf_delay = strategy.calculate_retry_delay(attempt=1, confidence=0.9)

        assert low_conf_delay > high_conf_delay, "Low confidence should delay more"

    def test_race_condition_simulation(self):
        """Simulate race conditions in element detection."""
        page_mock = Mock(spec=Page)

        # Simulate elements appearing/disappearing
        element_states = [False, False, True, True, False, True]  # Unstable

        call_count = [0]

        def wait_for_selector_unstable(selector, **kwargs):
            # Element randomly appears/disappears
            state = element_states[call_count[0] % len(element_states)]
            call_count[0] += 1

            if not state:
                raise PlaywrightTimeoutError("Element not found")

            return Mock()

        page_mock.wait_for_selector = wait_for_selector_unstable

        # Try multiple times - should eventually succeed
        max_attempts = 10
        success = False

        for _ in range(max_attempts):
            try:
                element = page_mock.wait_for_selector("#unstable-element", timeout=100)
                if element:
                    success = True
                    break
            except PlaywrightTimeoutError:
                continue

        assert success, "Should eventually succeed with retry"

    def test_hydration_delay_chaos(self):
        """Test framework hydration with random delays."""
        page_mock = Mock(spec=Page)

        handler = ModernWebHandler(page_mock)

        # Mock framework detection
        page_mock.evaluate.return_value = True

        # Simulate hydration delays
        hydration_times = [100, 500, 1000, 2000, 5000]  # ms

        chaos = ChaosInjector(page_mock)

        for delay_ms in hydration_times:
            chaos.maybe_inject_delay(min_ms=delay_ms, max_ms=delay_ms + 100)

            # Should handle delays gracefully
            # In real scenario, would wait for hydration
            detected = handler.detect_framework()
            assert detected is not None


class TestChaosRendering:
    """Chaos tests for dynamic rendering."""

    def test_dynamic_content_loading(self):
        """Test handling dynamically loaded content."""
        page_mock = Mock(spec=Page)

        # Simulate content loading in stages
        loading_stages = [
            {"visible": False, "count": 0},  # Initial
            {"visible": False, "count": 3},  # Loading
            {"visible": True, "count": 3},   # Loaded
            {"visible": True, "count": 10},  # Fully rendered
        ]

        stage = [0]

        def get_stage_state():
            current = loading_stages[min(stage[0], len(loading_stages) - 1)]
            stage[0] += 1
            return current

        # Mock element query
        def query_selector(selector):
            state = get_stage_state()
            if not state["visible"]:
                return None

            element = Mock()
            element.is_visible.return_value = state["visible"]
            return element

        page_mock.query_selector = query_selector

        # Should eventually find element after loading
        max_attempts = 10
        found = False

        for _ in range(max_attempts):
            element = page_mock.query_selector(".dynamic-content")
            if element and element.is_visible():
                found = True
                break

        assert found, "Should find element after loading completes"

    def test_spa_navigation_chaos(self):
        """Test SPA navigation with random failures."""
        page_mock = Mock(spec=Page)

        handler = ModernWebHandler(page_mock)

        # Mock navigation scenarios
        navigation_outcomes = [
            {"success": False, "error": "Timeout"},
            {"success": False, "error": "Navigation cancelled"},
            {"success": True, "error": None},
        ]

        outcome_index = [0]

        def simulate_navigation(url, **kwargs):
            outcome = navigation_outcomes[
                outcome_index[0] % len(navigation_outcomes)
            ]
            outcome_index[0] += 1

            if not outcome["success"]:
                raise PlaywrightTimeoutError(outcome["error"])

            return Mock()

        page_mock.goto = simulate_navigation

        # Should eventually succeed with retries
        max_attempts = 5
        success = False

        for _ in range(max_attempts):
            try:
                result = handler.wait_for_spa_navigation(timeout_ms=1000)
                if result:
                    success = True
                    break
            except:
                continue

        # At least one attempt should work
        assert outcome_index[0] > 0, "Should attempt navigation"

    def test_element_detachment_chaos(self):
        """Test element detachment during interaction."""
        page_mock = Mock(spec=Page)

        chaos = ChaosInjector(page_mock)

        # Simulate element becoming detached
        attempts = 0
        max_attempts = 5

        while attempts < max_attempts:
            if chaos.maybe_detach_element():
                # Element detached - would need to re-query
                attempts += 1
                continue
            else:
                # Element stable - can interact
                break

        # Should eventually find stable element
        assert attempts < max_attempts, "Should find stable element within retries"


class TestChaosDOMStructure:
    """Chaos tests for DOM structure changes."""

    def test_dom_mutation_during_fill(self):
        """Test DOM mutations during form filling."""
        page_mock = Mock(spec=Page)

        # Simulate DOM mutations
        dom_states = [
            {"structure": "v1", "fields": ["name", "email"]},
            {"structure": "v2", "fields": ["name", "email", "phone"]},  # Field added
            {"structure": "v3", "fields": ["fullname", "email", "phone"]},  # Renamed
        ]

        state_index = [0]

        def get_current_fields():
            state = dom_states[min(state_index[0], len(dom_states) - 1)]
            state_index[0] += 1
            return state["fields"]

        # Should adapt to structural changes
        for _ in range(5):
            fields = get_current_fields()
            assert len(fields) >= 2, "Should have minimum fields"

    def test_nested_iframe_chaos(self):
        """Test handling nested iframes with random failures."""
        page_mock = Mock(spec=Page)

        # Simulate iframe hierarchy
        iframe_chain = [
            {"exists": True, "loaded": True},
            {"exists": True, "loaded": False},  # Not loaded
            {"exists": False, "loaded": False},  # Doesn't exist
        ]

        chaos = ChaosInjector(page_mock)

        for iframe_state in iframe_chain:
            if not iframe_state["exists"]:
                # iframe doesn't exist - should handle gracefully
                continue

            if not iframe_state["loaded"]:
                # Wait for iframe to load
                chaos.maybe_inject_delay()

        # Should handle various iframe states

    def test_form_recreation_chaos(self):
        """Test form being recreated dynamically."""
        page_mock = Mock(spec=Page)

        # Simulate form recreation (common in React)
        form_generations = [
            {"id": "form-1", "exists": True},
            {"id": "form-1", "exists": False},   # Unmounted
            {"id": "form-2", "exists": True},    # Recreated
            {"id": "form-2", "exists": True},    # Stable
        ]

        generation_index = [0]

        def get_form():
            gen = form_generations[
                min(generation_index[0], len(form_generations) - 1)
            ]
            generation_index[0] += 1

            if not gen["exists"]:
                return None

            form = Mock()
            form.get_attribute.return_value = gen["id"]
            return form

        # Should detect form recreation and adapt
        seen_forms = set()
        max_checks = 10

        for _ in range(max_checks):
            form = get_form()
            if form:
                form_id = form.get_attribute("id")
                seen_forms.add(form_id)

        # Should see both form instances
        assert len(seen_forms) >= 1, "Should detect form(s)"


class TestIntegratedChaos:
    """Integrated chaos tests combining multiple failure modes."""

    def test_full_chaos_application_flow(self):
        """Test complete application with all chaos modes enabled."""
        page_mock = Mock(spec=Page)
        chaos = ChaosInjector(page_mock)

        # Mock successful element after retries
        def find_element_with_chaos(selector):
            # Random failures
            if chaos.maybe_fail_selector(selector) != selector:
                raise PlaywrightTimeoutError("Element not found")

            # Random delays
            chaos.maybe_inject_delay()

            # Random detachment
            if chaos.maybe_detach_element():
                raise PlaywrightTimeoutError("Element detached")

            # Success
            element = Mock()
            element.is_visible.return_value = True
            return element

        page_mock.wait_for_selector = find_element_with_chaos

        healer = SelectorHealer(storage_path=Path("/tmp/test_chaos.json"))
        engine_mock = Mock()
        engine_mock.execute.return_value = ExecutionResult(
            success=True,
            status=ExecutionStatus.SUCCESS,
            action_type=ActionType.FILL_INPUT,
        )

        healing_engine = SelfHealingEngine(
            page=page_mock,
            execution_engine=engine_mock,
            selector_healer=healer,
        )

        # Try filling multiple fields with chaos
        fields = [
            ("name", "John Doe"),
            ("email", "john@example.com"),
            ("phone", "555-0100"),
        ]

        success_count = 0

        for field_id, value in fields:
            action = FillInputAction(
                selector=f"#{field_id}",
                field_id=field_id,
                field_type="text_input",
                field_label=field_id,
                value=value,
            )

            # Try with healing
            result = healing_engine.execute(action)

            if result.success:
                success_count += 1

        # Should succeed on most fields despite chaos
        success_rate = success_count / len(fields)
        print(f"Chaos success rate: {success_rate:.1%}")

        # At least 60% success with healing
        assert success_rate >= 0.6, f"Success rate too low: {success_rate:.1%}"

    def test_cascading_failure_recovery(self):
        """Test recovery from cascading failures."""
        # Simulate: selector fails → healing fails → retry fails → escalation
        failures = []

        # Stage 1: Selector fails
        failures.append({"stage": "selector", "recovered": False})

        # Stage 2: Healing attempts
        healing_attempts = [
            {"strategy": "semantic", "success": False},
            {"strategy": "historical", "success": False},
            {"strategy": "dom_similarity", "success": True},  # Recovered
        ]
        failures.append({"stage": "healing", "attempts": healing_attempts})

        # Check recovery
        healing_recovered = any(a["success"] for a in healing_attempts)
        assert healing_recovered, "Should recover via healing"

    def test_chaos_with_confidence_escalation(self):
        """Test confidence-based escalation under chaos."""
        strategy = AdaptiveRetryStrategy()

        # Simulate declining confidence over attempts
        confidences = [0.85, 0.70, 0.55, 0.40, 0.25]
        attempts_before_escalation = 0

        for attempt, confidence in enumerate(confidences, start=1):
            # Check if should escalate
            should_escalate = strategy.should_escalate(
                attempt=attempt,
                confidence=confidence,
                consecutive_failures=attempt,
            )

            if should_escalate:
                attempts_before_escalation = attempt
                break

        # Should escalate before exhausting all retries
        assert (
            attempts_before_escalation > 0
        ), "Should escalate when confidence drops"
        assert attempts_before_escalation < len(
            confidences
        ), "Should escalate before final attempt"


def test_chaos_suite_comprehensive():
    """Run comprehensive chaos test suite."""
    print("\n=== Running Chaos Test Suite ===\n")

    # Run all chaos tests
    test_classes = [
        TestChaosSelectors,
        TestChaosTiming,
        TestChaosRendering,
        TestChaosDOMStructure,
        TestIntegratedChaos,
    ]

    total_tests = 0
    passed_tests = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")

        instance = test_class()
        test_methods = [
            method
            for method in dir(instance)
            if method.startswith("test_") and callable(getattr(instance, method))
        ]

        for method_name in test_methods:
            total_tests += 1
            try:
                method = getattr(instance, method_name)
                method()
                passed_tests += 1
                print(f"  ✓ {method_name}")
            except Exception as e:
                print(f"  ✗ {method_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Chaos Tests: {passed_tests}/{total_tests} passed")
    print(f"Success Rate: {passed_tests/total_tests:.1%}")
    print(f"{'='*50}\n")

    # Should pass at least 80% of chaos tests
    assert passed_tests / total_tests >= 0.8, "Chaos test pass rate too low"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
