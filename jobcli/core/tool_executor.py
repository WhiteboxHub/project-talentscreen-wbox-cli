"""Safe tool execution layer for browser actions."""

import re
from typing import Optional, List, Union

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
    "paylocity.com",
    "myworkdayjobs.com",
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
        self._failed_actions = []

    def _get_active_content_roots(self) -> List[Union[Page, FrameLocator]]:
        """Return a list of potential content roots (main page + all matching iframes)."""
        roots: List[Union[Page, FrameLocator]] = [self.page]
        
        # Add all frames that might be the ATS form
        for frame in self.page.frames:
            try:
                url = frame.url or ""
                if any(p in url.lower() for p in _ATS_IFRAME_PATTERNS):
                    roots.append(frame.frame_locator(":root"))
            except Exception:
                continue
                
        # Also try explicitly by common iframe IDs/names
        for selector in ["iframe[id*='grnhse']", "iframe[id*='gh_']", "iframe[id*='apply']", "#grnhse_iframe"]:
            try:
                if self.page.locator(selector).count() > 0:
                    roots.append(self.page.frame_locator(selector))
            except Exception:
                continue
                
        return roots

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
                    self.logger.error(f"Unknown action type: {action.action}", phase=ExecutionPhase.LLM)
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Action execution failed: {e}", phase=ExecutionPhase.LLM, action=action.action.value, selector=action.selector)
            return False

    def get_failed_actions(self) -> list[BrowserAction]:
        """Return the list of actions that failed during the last execute_actions call."""
        return getattr(self, '_failed_actions', [])

    def execute_actions(self, llm_response: LLMActionResponse) -> dict[str, bool]:
        """Execute a sequence of actions from LLM."""
        if llm_response.requires_human:
            if self.logger:
                self.logger.warning("LLM requested human intervention", phase=ExecutionPhase.LLM, reasoning=llm_response.reasoning)
            return {"requires_human": True}

        results: dict[str, bool] = {}
        self._failed_actions: list[BrowserAction] = []

        for i, action in enumerate(llm_response.actions):
            if action.confidence < 0.7:
                results[f"action_{i}"] = False
                continue

            success = self.execute_action(action)
            results[f"action_{i}_{action.action.value}"] = success

            if not success:
                self._failed_actions.append(action)
                continue

        return results

    def _execute_click(self, action: BrowserAction) -> bool:
        name = action.selector
        selector_type = action.selector_type

        # SAFETY: Block clicks on upload areas
        upload_keywords = ["upload", "resume", "cv", "attach", "drop or select"]
        if any(kw in name.lower() for kw in upload_keywords):
            if self.logger:
                self.logger.warning(f"Blocking click on '{name}' upload area. Use UPLOAD action instead.", phase=ExecutionPhase.LLM)
            return True

        roots = self._get_active_content_roots()
        
        # Try CSS/XPath first across all roots
        if selector_type in (SelectorType.CSS, SelectorType.XPATH):
            raw = name if selector_type == SelectorType.CSS else f"xpath={name}"
            for root in roots:
                try:
                    loc = root.locator(raw)
                    if loc.count() > 0:
                        loc.first.highlight()
                        loc.first.click(timeout=action.timeout)
                        return True
                except Exception: continue
            return False

        # Try semantic selectors across all roots
        for root in roots:
            attempts = [
                ("role button", lambda r=root: r.get_by_role("button", name=name, exact=False).first),
                ("role link", lambda r=root: r.get_by_role("link", name=name, exact=False).first),
                ("label", lambda r=root: r.get_by_label(name, exact=False).first),
                ("text", lambda r=root: r.get_by_text(name, exact=False).first),
                ("aria-labelledby", lambda r=root: r.locator(f"[aria-labelledby*='{name}']").first),
            ]
            for label, get_loc in attempts:
                try:
                    loc = get_loc()
                    if loc.is_visible(timeout=1000):
                        loc.highlight()
                        loc.click(timeout=action.timeout)
                        if self.logger: self.logger.info(f"Click executed via {label} in frame", phase=ExecutionPhase.LLM)
                        return True
                except Exception: continue
        
        return False

    def _execute_type(self, action: BrowserAction) -> bool:
        if not action.value: return False
        name = action.selector
        roots = self._get_active_content_roots()

        for root in roots:
            attempts = [
                ("label", lambda r=root: r.get_by_label(name, exact=False).first),
                ("placeholder", lambda r=root: r.get_by_placeholder(name, exact=False).first),
                ("css input", lambda r=root: r.locator(f"input[name*='{name}' i]").first),
                ("css textarea", lambda r=root: r.locator(f"textarea[name*='{name}' i]").first),
                ("aria-labelledby", lambda r=root: r.locator(f"[aria-labelledby*='{name}']").first),
            ]
            for label, get_loc in attempts:
                try:
                    loc = get_loc()
                    if loc.is_visible(timeout=1000):
                        loc.highlight()
                        try:
                            loc.fill(action.value, timeout=action.timeout)
                        except Exception:
                            # JS Force Fill Fallback
                            js_code = """(el, val) => {
                                el.value = val;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                el.dispatchEvent(new Event('blur', { bubbles: true }));
                                return true;
                            }"""
                            loc.evaluate(js_code, action.value)
                            
                        if self.logger: self.logger.info(f"Fill executed via {label} in frame", phase=ExecutionPhase.LLM)
                        return True
                except Exception: continue
                
        # Last resort: JS global search and fill
        js_search = f"""(() => {{
            const el = [...document.querySelectorAll('input,textarea')].find(e => 
                e.labels?.[0]?.textContent.toLowerCase().includes('{name.lower()}') || 
                e.placeholder?.toLowerCase().includes('{name.lower()}') ||
                e.name?.toLowerCase().includes('{name.lower()}')
            );
            if (el) {{
                el.value = '{action.value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }})()"""
        try:
            if self.page.evaluate(js_search):
                if self.logger: self.logger.info("Fill executed via global JS search", phase=ExecutionPhase.LLM)
                return True
        except Exception: pass
        
        return False

    def _execute_select(self, action: BrowserAction) -> bool:
        if not action.value: return False
        name = action.selector
        value = action.value
        roots = self._get_active_content_roots()

        for root in roots:
            attempts = [
                ("label select", lambda r=root: r.get_by_label(name, exact=False).first),
                ("role combobox", lambda r=root: r.get_by_role("combobox", name=name, exact=False).first),
            ]
            for label, get_loc in attempts:
                try:
                    loc = get_loc()
                    if loc.is_visible(timeout=1000):
                        loc.highlight()
                        try:
                            loc.select_option(value, timeout=2000)
                            return True
                        except Exception:
                            loc.click()
                            self.page.keyboard.type(value)
                            self.page.keyboard.press("Enter")
                            return True
                except Exception: continue
        return False

    def _execute_upload(self, action: BrowserAction) -> bool:
        if not action.value: return False
        name = action.selector
        roots = self._get_active_content_roots()

        for root in roots:
            attempts = [
                ("label upload", lambda r=root: r.get_by_label(name, exact=False).first),
                ("css file", lambda r=root: r.locator("input[type='file']").first),
            ]
            for label, get_loc in attempts:
                try:
                    loc = get_loc()
                    if loc.count() > 0:
                        loc.set_input_files(action.value, timeout=action.timeout)
                        return True
                except Exception: continue
        return False

    def _execute_scroll(self, action: BrowserAction) -> bool:
        scroll_amount = int(action.value) if action.value else 500
        self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        return True

    def _execute_wait(self, action: BrowserAction) -> bool:
        wait_time = int(action.value) if action.value else action.timeout
        self.page.wait_for_timeout(wait_time)
        return True
