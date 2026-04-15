"""Safe tool execution layer for browser actions."""

import re
from typing import Optional

from playwright.sync_api import FrameLocator, Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import (
    ActionType,
    BrowserAction,
    ExecutionPhase,
    LLMActionResponse,
    SelectorType,
)

# Known ATS iframe URL patterns to look for
_ATS_IFRAME_PATTERNS = [
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "icims.com",
    "taleo.net",
    "ashby.com",
    "bamboohr.com",
    "smartrecruiters.com",
]


class ToolExecutor:
    """Execute browser actions safely with validation."""

    def __init__(
        self,
        page: Page,
        logger: Optional[JobLogger] = None,
        memory=None,
        synonym_resolver=None,
        ats_type=None,
    ) -> None:
        """Initialize executor."""
        self.page = page
        self.logger = logger
        self.memory = memory
        self.synonym_resolver = synonym_resolver
        self.ats_type = ats_type
        self.last_successful_strategy = None
        self.last_dropdown_options = {}

    def _get_active_content_root(self) -> "Page | FrameLocator":
        """Return the ATS iframe locator if present, otherwise the main page."""
        for pattern in _ATS_IFRAME_PATTERNS:
            try:
                frame_loc = self.page.frame_locator(f"iframe[src*='{pattern}']").first
                if self.page.locator(f"iframe[src*='{pattern}']").count() > 0:
                    if self.logger:
                        self.logger.info(
                            f"Switched to ATS iframe locator: {pattern}",
                            phase=ExecutionPhase.LLM,
                        )
                    return frame_loc
            except Exception:
                pass
        return self.page

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
            elif action.action in (ActionType.TYPE, ActionType.FILL):
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
        self._failed_actions: list[BrowserAction] = []

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
                self._failed_actions.append(action)
                if self.logger:
                    self.logger.warning(
                        f"Action {i} failed, continuing execution",
                        phase=ExecutionPhase.LLM,
                    )
                continue

        return results

    def get_failed_actions(self) -> list[BrowserAction]:
        """Return the list of actions that failed during the last execute_actions call."""
        return getattr(self, '_failed_actions', [])

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
        """Execute click action using Playwright semantic locators."""
        name = action.selector
        selector_type = action.selector_type
        content_root = self._get_active_content_root()

        # For CSS/XPath selectors, use directly
        if selector_type in (SelectorType.CSS, SelectorType.XPATH):
            raw = name if selector_type == SelectorType.CSS else f"xpath={name}"
            try:
                content_root.locator(raw).click(timeout=action.timeout)
                if self.logger:
                    self.logger.info("Click executed via CSS/XPath", phase=ExecutionPhase.LLM, selector=raw)
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Failed to click: {e}", phase=ExecutionPhase.LLM, selector=raw)
                return False

        # For semantic types, try multiple approaches
        locator_attempts = [
            ("get_by_role button", lambda: content_root.get_by_role("button", name=name, exact=False).first),
            ("get_by_role link", lambda: content_root.get_by_role("link", name=name, exact=False).first),
            ("get_by_text", lambda: content_root.get_by_text(name, exact=False).first),
            ("get_by_label", lambda: content_root.get_by_label(name, exact=False).first),
        ]

        for attempt_name, get_locator in locator_attempts:
            try:
                loc = get_locator()
                if loc.is_visible(timeout=2000):
                    try:
                        loc.scroll_into_view_if_needed(timeout=1000)
                        loc.highlight()
                        self.page.wait_for_timeout(300)
                    except Exception:
                        pass
                    loc.click(timeout=action.timeout)
                    if self.logger:
                        self.logger.info(
                            f"Click executed via {attempt_name}",
                            phase=ExecutionPhase.LLM,
                            selector=name,
                        )
                    return True
            except Exception:
                continue

        if self.logger:
            self.logger.error("Element not found for click", phase=ExecutionPhase.LLM, selector=name)
        return False

    def _execute_type(self, action: BrowserAction) -> bool:
        """Execute type/fill action using Playwright semantic locators."""
        if not action.value:
            if self.logger:
                self.logger.error("No value provided for type action", phase=ExecutionPhase.LLM)
            return False

        name = action.selector
        value = action.value
        content_root = self._get_active_content_root()

        # Try in order: get_by_label, get_by_role textbox, get_by_placeholder, CSS
        locator_attempts = [
            ("get_by_label", lambda: content_root.get_by_label(name, exact=False).first),
            ("get_by_role textbox", lambda: content_root.get_by_role("textbox", name=name, exact=False).first),
            ("get_by_placeholder", lambda: content_root.get_by_placeholder(name, exact=False).first),
            ("css label contains", lambda: content_root.locator(f"label:has-text('{name}') + input, label:has-text('{name}') + textarea").first),
        ]

        for attempt_name, get_locator in locator_attempts:
            try:
                loc = get_locator()
                if loc.is_visible(timeout=2000):
                    try:
                        loc.scroll_into_view_if_needed(timeout=1000)
                        loc.highlight()
                        self.page.wait_for_timeout(300) # Give user a chance to see
                    except Exception:
                        pass
                    is_autocomplete = any(kw in name.lower() for kw in ["location", "city", "school", "university", "degree", "company"])
                    if is_autocomplete:
                        loc.fill("")
                        loc.press_sequentially(value, delay=50)
                        self.page.wait_for_timeout(1500) # Wait for network drop-down
                        self.page.keyboard.press("ArrowDown")
                        self.page.wait_for_timeout(200)
                        self.page.keyboard.press("Enter")
                    else:
                        loc.fill(value, timeout=action.timeout)
                    if self.logger:
                        self.logger.info(
                            f"Fill executed via {attempt_name}",
                            phase=ExecutionPhase.LLM,
                            selector=name,
                            value_length=len(value),
                        )
                    return True
            except Exception:
                continue

        if self.logger:
            self.logger.error("Element not found for type", phase=ExecutionPhase.LLM, selector=name)
        return False

    def _execute_select(self, action: BrowserAction) -> bool:
        """Execute select dropdown action, handling both native <select> and custom widget dropdowns."""
        if not action.value:
            if self.logger:
                self.logger.error("No value provided for select action", phase=ExecutionPhase.LLM)
            return False

        name = action.selector
        our_value = action.value
        content_root = self._get_active_content_root()

        # Check memory for a strategy that worked before (TODO: integrate if requested)

        # --- Strategy 1: Native <select> element approaches ---
        native_attempts = [
            ("get_by_label select", lambda: content_root.get_by_label(name, exact=False).first),
            ("get_by_role combobox", lambda: content_root.get_by_role("combobox", name=name, exact=False).first),
            ("css label>select", lambda: content_root.locator(f"label:has-text('{name}')").locator("select").first),
        ]

        for attempt_name, get_locator in native_attempts:
            try:
                loc = get_locator()
                if not loc.is_visible(timeout=1000):
                    continue
                try:
                    loc.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass

                # Extract options for synonym resolution
                options = []
                try:
                    for opt in loc.locator("option").all():
                        text = opt.text_content()
                        if text and text.strip():
                            options.append(text.strip())
                except:
                    pass
                
                # Use synonym resolver to find best match
                best_match = None
                if options and self.synonym_resolver:
                    best_match = self.synonym_resolver.find_best_option(our_value, options)

                try:
                    if best_match:
                        loc.select_option(label=best_match, timeout=1000)
                    else:
                        # Try select by label text first, then by value
                        try:
                            loc.select_option(label=our_value, timeout=1000)
                        except:
                            loc.select_option(value=our_value, timeout=1000)

                    self.last_successful_strategy = f"native_select_{attempt_name}"
                    if self.memory and self.ats_type:
                        self.memory.save_dropdown_strategy(self.ats_type, name, self.last_successful_strategy, options, True)

                    if self.logger:
                        self.logger.info(f"Select executed via {attempt_name}", phase=ExecutionPhase.LLM, selector=name, value=our_value)
                    return True
                except Exception:
                    pass
            except Exception:
                continue

        # --- Strategy 2: Custom dropdown widget (click to open, then click option) ---
        custom_dropdown_attempts = [
            ("custom_label_click", lambda: content_root.get_by_text(name, exact=False).first),
            ("custom_get_by_label", lambda: content_root.get_by_label(name, exact=False).first),
            ("custom_css_sibling", lambda: content_root.locator(f"label:has-text('{name}')").locator("..").locator("select, [role='listbox'], [role='combobox'], .select2-container, [class*='select']").first),
        ]

        for attempt_name, get_trigger in custom_dropdown_attempts:
            try:
                trigger = get_trigger()
                if not trigger.is_visible(timeout=1500):
                    continue

                try:
                    trigger.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass

                # Click to open the dropdown
                trigger.click(timeout=1500)
                self.page.wait_for_timeout(600)  # Wait for options to render

                options = self._extract_dropdown_options(content_root)
                if options:
                    self.last_dropdown_options[name] = options
                
                best_match = our_value
                if options and self.synonym_resolver:
                    found_match = self.synonym_resolver.find_best_option(our_value, options)
                    if found_match:
                        best_match = found_match

                exact_text = re.compile(f"^{re.escape(best_match)}$", re.IGNORECASE)
                option_locators = [
                    content_root.get_by_role("option", name=re.compile(re.escape(best_match), re.IGNORECASE)).first,
                    self.page.get_by_role("option", name=re.compile(re.escape(best_match), re.IGNORECASE)).first,
                    content_root.locator(f"li:has-text('{best_match}')").first,
                    self.page.locator(f"li:has-text('{best_match}')").first,
                    content_root.get_by_text(exact_text).first,
                    self.page.get_by_text(exact_text).first,
                ]

                success = False
                for option_loc in option_locators:
                    try:
                        option_loc.wait_for(state="visible", timeout=1000)
                        option_loc.click(timeout=1000)
                        success = True
                        break
                    except Exception:
                        continue

                if success:
                    self.last_successful_strategy = f"custom_widget_{attempt_name}"
                    if self.memory and self.ats_type:
                        self.memory.save_dropdown_strategy(self.ats_type, name, self.last_successful_strategy, list(options), True)

                    if self.logger:
                        self.logger.info(f"Select executed via {attempt_name}", phase=ExecutionPhase.LLM, selector=name, value=best_match)
                    return True

                # Strategy 3: Keyboard navigation
                # Type first letter to jump to matching option
                try:
                    self.page.keyboard.type(best_match[0])
                    self.page.wait_for_timeout(300)
                    self.page.keyboard.press("Enter")
                    
                    self.last_successful_strategy = f"keyboard_nav_{attempt_name}"
                    if self.memory and self.ats_type:
                        self.memory.save_dropdown_strategy(self.ats_type, name, self.last_successful_strategy, list(options), True)

                    if self.logger:
                        self.logger.info(f"Select executed via keyboard navigation", phase=ExecutionPhase.LLM)
                    return True
                except Exception:
                    pass

                # Crucial: Close the dropdown before trying the next trigger attempt
                try:
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(200)
                except Exception:
                    pass
            except Exception:
                continue

        if self.logger:
            self.logger.error("Element not found for select", phase=ExecutionPhase.LLM, selector=name)
        return False

    def _extract_dropdown_options(self, content_root) -> list[str]:
        """Extract ALL visible option texts from an open dropdown."""
        option_locators = [
            content_root.get_by_role("option"),
            self.page.get_by_role("option"),
            content_root.locator("li[role='option'], li[data-value], .select-option"),
            self.page.locator("[role='listbox'] li, [role='listbox'] [role='option']"),
        ]
        
        all_options = set()
        for loc_group in option_locators:
            try:
                count = loc_group.count()
                for i in range(min(count, 50)):
                    text = loc_group.nth(i).text_content(timeout=500)
                    if text and text.strip():
                        all_options.add(text.strip())
            except Exception:
                pass
        
        return sorted(list(all_options))

    def _execute_upload(self, action: BrowserAction) -> bool:
        """Execute file upload action."""
        if not action.value:
            if self.logger:
                self.logger.error("No file path provided for upload action", phase=ExecutionPhase.LLM)
            return False

        name = action.selector
        content_root = self._get_active_content_root()

        locator_attempts = [
            ("get_by_label", lambda: content_root.get_by_label(name, exact=False).first),
            ("css generic input file", lambda: content_root.locator("input[type='file']").first), # Often there's exactly 1 file input
            ("css input file has text", lambda: content_root.locator(f"div:has-text('{name}')").locator("input[type='file']").first),
            ("fallback selector", lambda: content_root.locator(self._get_selector(action)).first),
        ]

        for attempt_name, get_locator in locator_attempts:
            try:
                loc = get_locator()
                loc.set_input_files(action.value, timeout=action.timeout)
                if self.logger:
                    self.logger.info(f"Upload executed via {attempt_name}", phase=ExecutionPhase.LLM, file=action.value)
                return True
            except Exception:
                continue

        if self.logger:
            self.logger.error("Element not found for upload", phase=ExecutionPhase.LLM, selector=name)
        return False

    def _execute_scroll(self, action: BrowserAction) -> bool:
        """Execute scroll action."""
        selector = self._get_selector(action)

        if selector:
            # Scroll to specific element
            element = self.page.query_selector(selector)
            if element:
                element.scroll_into_view_if_needed(timeout=1000)
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
        if action.action in [ActionType.TYPE, ActionType.FILL, ActionType.SELECT, ActionType.UPLOAD]:
            if not action.value:
                return False, f"Value required for {action.action.value} action"

        # Check selector
        if not action.selector and action.action != ActionType.SCROLL:
            return False, "Selector required for this action"

        return True, None
