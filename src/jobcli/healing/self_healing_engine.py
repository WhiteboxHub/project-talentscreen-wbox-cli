"""Integrated self-healing automation engine.

Combines:
- Selector healing
- Modern web handling
- Adaptive retry
- Confidence escalation

Provides a complete self-healing automation system.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page
from pydantic import BaseModel, Field

from jobcli.execution.actions import ExecutionAction, FillInputAction
from jobcli.execution.engine import ExecutionEngine, ExecutionResult, ExecutionStatus
from jobcli.profile.schemas import ATSType

from .adaptive_retry import (
    AdaptiveRetry,
    EscalationLevel,
    RetryConfig,
    RetryWithHealing,
)
from .modern_web_handler import ModernWebHandler, ModernWebInfo
from .selector_healer import SelectorHealer, SelectorHealingResult


class HealingMetrics(BaseModel):
    """Metrics for self-healing system."""

    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0

    # Healing stats
    selectors_healed: int = 0
    healing_success_rate: float = 0.0

    # Escalations
    escalations: Dict[str, int] = Field(default_factory=dict)

    # Modern web
    modern_web_detections: List[str] = Field(default_factory=list)

    # Performance
    avg_action_duration_ms: float = 0.0


class SelfHealingEngine:
    """Self-healing automation engine.

    Wraps ExecutionEngine with healing capabilities:
    - Automatic selector healing on failure
    - Modern web technology handling (React, Shadow DOM, etc.)
    - Adaptive retry with confidence escalation
    - Historical pattern learning
    """

    def __init__(
        self,
        page: Page,
        ats_type: ATSType,
        session_id: Optional[str] = None,
        patterns_file: Optional[Path] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_healing: bool = True,
        enable_modern_web: bool = True,
    ):
        """Initialize self-healing engine.

        Args:
            page: Playwright Page instance
            ats_type: ATS platform type
            session_id: Application session ID
            patterns_file: Path to historical patterns file
            retry_config: Retry configuration
            enable_healing: Enable selector healing?
            enable_modern_web: Enable modern web handling?
        """
        self.page = page
        self.ats_type = ats_type
        self.session_id = session_id or f"healing_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Core execution engine
        self.engine = ExecutionEngine(
            page=page,
            ats_type=ats_type,
            session_id=self.session_id,
        )

        # Healing components
        self.enable_healing = enable_healing
        self.enable_modern_web = enable_modern_web

        if enable_healing:
            self.selector_healer = SelectorHealer(page, patterns_file)
        else:
            self.selector_healer = None

        if enable_modern_web:
            self.modern_web_handler = ModernWebHandler(page)
            self._modern_web_info: Optional[ModernWebInfo] = None
        else:
            self.modern_web_handler = None
            self._modern_web_info = None

        # Adaptive retry
        self.adaptive_retry = AdaptiveRetry(retry_config or RetryConfig())

        if enable_healing and self.selector_healer:
            self.retry_with_healing = RetryWithHealing(
                self.adaptive_retry, self.selector_healer
            )
        else:
            self.retry_with_healing = None

        # Metrics
        self.metrics = HealingMetrics()

    def execute(self, action: ExecutionAction) -> ExecutionResult:
        """Execute action with self-healing capabilities.

        Args:
            action: Action to execute

        Returns:
            ExecutionResult
        """
        self.metrics.total_actions += 1

        # Detect modern web technologies on first action
        if self.enable_modern_web and self._modern_web_info is None:
            self._detect_and_handle_modern_web()

        # Try executing with standard engine
        result = self.engine.execute(action)

        # If successful, record pattern
        if result.status == ExecutionStatus.SUCCESS:
            self.metrics.successful_actions += 1

            if self.enable_healing and self.selector_healer:
                self.selector_healer.record_success(
                    action.selector,
                    action.target,
                    self.ats_type.value,
                )

            return result

        # Failed - try healing
        if self.enable_healing and self.selector_healer:
            healed_result = self._try_healing(action, result)

            if healed_result.status == ExecutionStatus.SUCCESS:
                self.metrics.successful_actions += 1
                self.metrics.selectors_healed += 1
                return healed_result

        # Still failed - record failure
        self.metrics.failed_actions += 1

        return result

    def execute_batch(
        self,
        actions: List[ExecutionAction],
        stop_on_failure: bool = True,
    ) -> List[ExecutionResult]:
        """Execute batch of actions with healing.

        Args:
            actions: List of actions
            stop_on_failure: Stop on first failure?

        Returns:
            List of ExecutionResults
        """
        results: List[ExecutionResult] = []

        for action in actions:
            result = self.execute(action)
            results.append(result)

            if stop_on_failure and result.status == ExecutionStatus.FAILED:
                break

        return results

    def _try_healing(
        self,
        action: ExecutionAction,
        failed_result: ExecutionResult,
    ) -> ExecutionResult:
        """Try to heal selector and retry action.

        Args:
            action: Original action
            failed_result: Failed result

        Returns:
            ExecutionResult after healing attempt
        """
        if not self.selector_healer:
            return failed_result

        # Extract context for healing
        context = {}
        if isinstance(action, FillInputAction):
            context["expected_value"] = action.value

        # Try healing selector
        healing_result = self.selector_healer.heal_selector(
            action.selector,
            action.target,
            context,
        )

        if not healing_result.success or not healing_result.healed_selector:
            return failed_result

        # Create new action with healed selector
        healed_action = action.model_copy()
        healed_action.selector = healing_result.healed_selector

        # Retry with healed selector
        healed_exec_result = self.engine.execute(healed_action)

        # Record healing result
        if healed_exec_result.status == ExecutionStatus.SUCCESS:
            # Healing worked! Record it
            self.selector_healer.record_success(
                healing_result.healed_selector,
                action.target,
                self.ats_type.value,
            )

        return healed_exec_result

    def _detect_and_handle_modern_web(self) -> None:
        """Detect and handle modern web technologies."""
        if not self.modern_web_handler:
            return

        # Detect technologies
        self._modern_web_info = self.modern_web_handler.detect_technologies()

        # Record detections
        self.metrics.modern_web_detections = self._modern_web_info.detected_patterns

        # Wait for hydration if needed
        if self._modern_web_info.hydration_status.value == "not_hydrated":
            self.modern_web_handler.wait_for_hydration()

    def get_healing_metrics(self) -> HealingMetrics:
        """Get healing metrics.

        Returns:
            HealingMetrics
        """
        # Update success rate
        if self.metrics.total_actions > 0:
            self.metrics.healing_success_rate = (
                self.metrics.selectors_healed / self.metrics.total_actions
            )

        return self.metrics

    def get_modern_web_info(self) -> Optional[ModernWebInfo]:
        """Get modern web information.

        Returns:
            ModernWebInfo or None
        """
        return self._modern_web_info

    def find_with_fallback(
        self,
        primary_selector: str,
        field_type: str,
        semantic_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Find element with automatic fallback.

        Tries:
        1. Primary selector
        2. Semantic matching
        3. Historical patterns
        4. DOM similarity

        Args:
            primary_selector: Primary selector to try
            field_type: Field type
            semantic_context: Semantic context

        Returns:
            Working selector or None
        """
        # Try primary selector
        try:
            if self.page.locator(primary_selector).count() > 0:
                return primary_selector
        except Exception:
            pass

        # Try healing
        if self.selector_healer:
            healing_result = self.selector_healer.heal_selector(
                primary_selector,
                field_type,
                semantic_context,
            )

            if healing_result.success and healing_result.healed_selector:
                return healing_result.healed_selector

        return None

    def handle_shadow_dom(
        self,
        selector: str,
        shadow_host: Optional[str] = None,
    ) -> Optional[str]:
        """Handle Shadow DOM elements.

        Args:
            selector: Selector inside shadow root
            shadow_host: Shadow host selector

        Returns:
            Working selector with Shadow DOM piercing
        """
        if not self.modern_web_handler:
            return None

        locator = self.modern_web_handler.find_in_shadow_dom(selector, shadow_host)

        if locator:
            # Return piercing selector
            if shadow_host:
                return f"{shadow_host} >>> {selector}"

        return None

    def wait_for_spa_ready(self, timeout_ms: int = 5000) -> bool:
        """Wait for SPA to be ready.

        Args:
            timeout_ms: Maximum wait time

        Returns:
            True if SPA is ready
        """
        if not self.modern_web_handler:
            return True

        return self.modern_web_handler.wait_for_hydration(timeout_ms)

    def print_summary(self) -> None:
        """Print healing summary."""
        metrics = self.get_healing_metrics()

        print("\n" + "=" * 70)
        print("SELF-HEALING ENGINE SUMMARY")
        print("=" * 70)
        print(f"  Total actions: {metrics.total_actions}")
        print(f"  Successful: {metrics.successful_actions}")
        print(f"  Failed: {metrics.failed_actions}")
        print(f"  Success rate: {metrics.successful_actions / metrics.total_actions:.2%}" if metrics.total_actions > 0 else "  Success rate: N/A")

        if self.enable_healing:
            print(f"\n  Selectors healed: {metrics.selectors_healed}")
            print(f"  Healing success rate: {metrics.healing_success_rate:.2%}")

        if self.enable_modern_web and self._modern_web_info:
            print(f"\n  Modern web detected:")
            print(f"    Framework: {self._modern_web_info.framework.value}")
            print(f"    Hydration: {self._modern_web_info.hydration_status.value}")
            print(f"    Shadow DOM: {self._modern_web_info.has_shadow_dom}")
            print(f"    SPA: {self._modern_web_info.is_spa}")

        if self.selector_healer:
            patterns_summary = self.selector_healer.get_patterns_summary()
            print(f"\n  Historical patterns: {patterns_summary.get('total_patterns', 0)}")

        print("=" * 70)
