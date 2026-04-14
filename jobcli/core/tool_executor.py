"""Safe tool execution layer for browser actions."""

from typing import Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import (
    ActionType,
    BrowserAction,
    ExecutionPhase,
    LLMActionResponse,
    SelectorType,
)


class ToolExecutor:
    """Execute browser actions safely with validation."""

    def __init__(self, page: Page, logger: Optional[JobLogger] = None) -> None:
        """Initialize executor."""
        self.page = page
        self.logger = logger

    def execute_action(self, action: BrowserAction) -> bool:
        """Execute a single browser action."""
        if self.logger:
            self.logger.info(
                f"Executing {action.action.value} action",
                phase=ExecutionPhase.LLM,
                selector=action.selector,
                field_label=action.field_label,
            )

        try:
            # Route to appropriate action handler
            if action.action == ActionType.CLICK:
                return self._execute_click(action)
            elif action.action == ActionType.TYPE:
                return self._execute_type(action)
            elif action.action == ActionType.SELECT:
                return self._execute_select(action)
            elif action.action == ActionType.UPLOAD:
                return self._execute_upload(action)
            elif action.action == ActionType.SCROLL:
                return self._execute_scroll(action)
            elif action.action == ActionType.WAIT:
                return self._execute_wait(action)
            else:
                if self.logger:
                    self.logger.error(
                        f"Unknown action type: {action.action}",
                        phase=ExecutionPhase.LLM,
                    )
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Action execution failed: {e}",
                    phase=ExecutionPhase.LLM,
                    action=action.action.value,
                    selector=action.selector,
                    error=str(e),
                )
            return False

    def execute_actions(self, llm_response: LLMActionResponse) -> dict[str, bool]:
        """Execute a sequence of actions from LLM."""
        if llm_response.requires_human:
            if self.logger:
                self.logger.warning(
                    "LLM requested human intervention",
                    phase=ExecutionPhase.LLM,
                    reasoning=llm_response.reasoning,
                )
            return {"requires_human": True}

        results: dict[str, bool] = {}

        for i, action in enumerate(llm_response.actions):
            # Check confidence threshold
            if action.confidence < 0.7:
                if self.logger:
                    self.logger.warning(
                        f"Skipping low confidence action ({action.confidence})",
                        phase=ExecutionPhase.LLM,
                        action=action.action.value,
                    )
                results[f"action_{i}"] = False
                continue

            # Execute action
            success = self.execute_action(action)
            results[f"action_{i}_{action.action.value}"] = success

            if not success:
                if self.logger:
                    self.logger.warning(
                        f"Action {i} failed, stopping execution",
                        phase=ExecutionPhase.LLM,
                    )
                break

        return results

    def _get_selector(self, action: BrowserAction) -> str:
        """Get formatted selector based on type."""
        if action.selector_type == SelectorType.CSS:
            return action.selector
        elif action.selector_type == SelectorType.XPATH:
            return f"xpath={action.selector}"
        elif action.selector_type == SelectorType.TEXT:
            return f"text={action.selector}"
        elif action.selector_type == SelectorType.ROLE:
            return f"role={action.selector}"
        elif action.selector_type == SelectorType.ARIA_LABEL:
            return f"aria-label={action.selector}"
        else:
            return action.selector

    def _execute_click(self, action: BrowserAction) -> bool:
        """Execute click action with safety fallback and context intercepts."""
        selector = self._get_selector(action)

        # Verify element exists
        element = self.page.query_selector(selector)
        if not element:
            if self.logger:
                self.logger.error("Element not found for click", phase=ExecutionPhase.LLM, selector=selector)
            return False

        if not element.is_visible():
            if self.logger:
                self.logger.warning("Element not visible, attempting to scroll", phase=ExecutionPhase.LLM, selector=selector)
            element.scroll_into_view_if_needed()

        context = self.page.context
        try:
            with context.expect_page(timeout=5000) as new_page_info:
                # Click with standard timeout
                self.page.click(selector, timeout=action.timeout or 3000)
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded")
            if self.logger:
                self.logger.info("Click resolved to new page context", phase=ExecutionPhase.LLM)
        except TimeoutError:
            # Did not trigger a new page. Check if standard click failed entirely
            try:
                self.page.click(selector, force=True, timeout=action.timeout or 3000)
            except Exception as e:
                if self.logger:
                    self.logger.error("Click intercepted, resolving via force=True fallback", phase=ExecutionPhase.LLM, error=str(e))
                self.page.evaluate(f'document.querySelector("{selector}").click()')

        if self.logger:
            self.logger.info("Click executed successfully", phase=ExecutionPhase.LLM, selector=selector)

        return True

    def _execute_type(self, action: BrowserAction) -> bool:
        """Execute type action."""
        if not action.value:
            if self.logger:
                self.logger.error(
                    "No value provided for type action",
                    phase=ExecutionPhase.LLM,
                )
            return False

        selector = self._get_selector(action)

        # Verify element exists
        element = self.page.query_selector(selector)
        if not element:
            if self.logger:
                self.logger.error(
                    "Element not found for type",
                    phase=ExecutionPhase.LLM,
                    selector=selector,
                )
            return False

        # Fill with timeout
        self.page.fill(selector, action.value, timeout=action.timeout)

        if self.logger:
            self.logger.info(
                "Type executed successfully",
                phase=ExecutionPhase.LLM,
                selector=selector,
                value_length=len(action.value),
            )

        return True

    def _execute_select(self, action: BrowserAction) -> bool:
        """Execute select dropdown action."""
        if not action.value:
            if self.logger:
                self.logger.error(
                    "No value provided for select action",
                    phase=ExecutionPhase.LLM,
                )
            return False

        selector = self._get_selector(action)

        # Verify element exists
        element = self.page.query_selector(selector)
        if not element:
            if self.logger:
                self.logger.error(
                    "Element not found for select",
                    phase=ExecutionPhase.LLM,
                    selector=selector,
                )
            return False

        # Select option
        self.page.select_option(selector, action.value, timeout=action.timeout)

        if self.logger:
            self.logger.info(
                "Select executed successfully",
                phase=ExecutionPhase.LLM,
                selector=selector,
                value=action.value,
            )

        return True

    def _execute_upload(self, action: BrowserAction) -> bool:
        """Execute file upload action."""
        if not action.value:
            if self.logger:
                self.logger.error(
                    "No file path provided for upload action",
                    phase=ExecutionPhase.LLM,
                )
            return False

        selector = self._get_selector(action)

        # Verify element exists and is file input
        element = self.page.query_selector(selector)
        if not element:
            if self.logger:
                self.logger.error(
                    "Element not found for upload",
                    phase=ExecutionPhase.LLM,
                    selector=selector,
                )
            return False

        # Upload file
        self.page.set_input_files(selector, action.value, timeout=action.timeout)

        if self.logger:
            self.logger.info(
                "Upload executed successfully",
                phase=ExecutionPhase.LLM,
                selector=selector,
                file=action.value,
            )

        return True

    def _execute_scroll(self, action: BrowserAction) -> bool:
        """Execute scroll action."""
        selector = self._get_selector(action)

        if selector:
            # Scroll to specific element
            element = self.page.query_selector(selector)
            if element:
                element.scroll_into_view_if_needed()
            else:
                return False
        else:
            # Scroll by amount (value should be pixels)
            scroll_amount = int(action.value) if action.value else 500
            self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")

        if self.logger:
            self.logger.info(
                "Scroll executed successfully",
                phase=ExecutionPhase.LLM,
                selector=selector,
            )

        return True

    def _execute_wait(self, action: BrowserAction) -> bool:
        """Execute wait action."""
        wait_time = int(action.value) if action.value else action.timeout

        if action.selector:
            # Wait for specific element
            selector = self._get_selector(action)
            try:
                self.page.wait_for_selector(selector, timeout=wait_time)
            except Exception:
                return False
        else:
            # Wait for specified time
            self.page.wait_for_timeout(wait_time)

        if self.logger:
            self.logger.info(
                "Wait executed successfully",
                phase=ExecutionPhase.LLM,
                duration=wait_time,
            )

        return True

    def validate_action(self, action: BrowserAction) -> tuple[bool, Optional[str]]:
        """Validate action before execution."""
        # Check confidence
        if action.confidence < 0.5:
            return False, f"Confidence too low: {action.confidence}"

        # Check required fields based on action type
        if action.action in [ActionType.TYPE, ActionType.SELECT, ActionType.UPLOAD]:
            if not action.value:
                return False, f"Value required for {action.action.value} action"

        # Check selector
        if not action.selector and action.action != ActionType.SCROLL:
            return False, "Selector required for this action"

        return True, None
