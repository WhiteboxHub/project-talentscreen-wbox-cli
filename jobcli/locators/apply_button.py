"""Rule-based locators for apply buttons."""

from typing import Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ExecutionPhase, LocatorResult, SelectorType


class ApplyButtonLocator:
    """Comprehensive apply button locator with 30+ strategies."""

    def __init__(self, page: Page, logger: Optional[JobLogger] = None) -> None:
        """Initialize locator."""
        self.page = page
        self.logger = logger

    def _try_selector(
        self, selector: str, selector_type: SelectorType, name: str
    ) -> Optional[LocatorResult]:
        """Try a single selector strategy."""
        try:
            # Check if element exists
            if selector_type == SelectorType.CSS:
                element = self.page.query_selector(selector)
            elif selector_type == SelectorType.XPATH:
                element = self.page.query_selector(f"xpath={selector}")
            elif selector_type == SelectorType.TEXT:
                element = self.page.get_by_text(selector, exact=False).first
            elif selector_type == SelectorType.ROLE:
                element = self.page.get_by_role("button", name=selector).first
            else:
                return None

            if element and element.is_visible():
                if self.logger:
                    self.logger.info(
                        f"Found apply button using {name}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                        selector_type=selector_type.value,
                    )

                return LocatorResult(
                    success=True,
                    selector=selector,
                    selector_type=selector_type,
                    locator_name=name,
                    phase=ExecutionPhase.RULES,
                )

        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"Locator {name} failed",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )

        return None

    def find(self, retry_count: int = 0) -> Optional[LocatorResult]:
        """Find apply button using robust filtering and retries."""
        import re
        import time
        if self.logger:
            self.logger.info(f"Starting apply button search (Retry {retry_count})", phase=ExecutionPhase.RULES)

        if retry_count == 1:
            if self.logger: self.logger.warning("Retry 1 triggered: Immediate re-poll", phase=ExecutionPhase.RULES)
        elif retry_count == 2:
            if self.logger: self.logger.warning("Retry 2 triggered: Scrolling to view", phase=ExecutionPhase.RULES)
            try: self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except: pass
            time.sleep(1.0)
        elif retry_count == 3:
            if self.logger: self.logger.warning("Retry 3 triggered: Post-wait polling", phase=ExecutionPhase.RULES)
            time.sleep(2.5)
        elif retry_count > 3:
            if self.logger: self.logger.error("3 retries exhausted handling Apply Button. Passing control to LLM.", phase=ExecutionPhase.RULES)
            return LocatorResult(success=False, error="Exhausted retries", phase=ExecutionPhase.RULES)

        try:
            # Dismiss cookie banners if present
            cookie_btn = self.page.locator("#onetrust-accept-btn-handler")
            if cookie_btn.is_visible():
                cookie_btn.click(force=True, timeout=1000)
        except Exception:
            pass

        # Use Playwright python to find valid elements
        text_pattern = re.compile(r"(?i)^(Apply|Apply[ -]Now|Submit Application)$")
        exclude_pattern = re.compile(r"(?i)(similar|other|save|share|refer)")
        
        try:
            elements = self.page.locator("button, a, [role='button'], [role='link']").all()
            for i, element in enumerate(elements):
                try:
                    if not element.is_visible() or not element.is_enabled():
                        continue
                    
                    text = (element.inner_text() or element.text_content() or "").strip()
                    if text_pattern.match(text) and not exclude_pattern.search(text):
                        if self.logger:
                            self.logger.info(
                                "Found apply button via regex",
                                strategy="regex",
                                phase=ExecutionPhase.RULES,
                            )
                        # We use text pattern as locator for click
                        return LocatorResult(
                            success=True,
                            selector=text,
                            selector_type=SelectorType.TEXT,
                            locator_name="regex_exact",
                            phase=ExecutionPhase.RULES,
                        )
                except Exception:
                    continue
        except Exception as e:
            if self.logger: self.logger.debug(f"Locator scan failed: {e}")

        # If not found, recurse with incremented retry
        return self.find(retry_count + 1)

    def click_apply_button(self) -> bool:
        """Find and click the apply button safely."""
        result = self.find()

        if not result or not result.success:
            return False

        try:
            selector = result.selector
            context = self.page.context
            
            if result.selector_type == SelectorType.TEXT:
                loc = self.page.get_by_text(selector, exact=True).first
            elif result.selector_type == SelectorType.CSS:
                loc = self.page.locator(selector).first
            elif result.selector_type == SelectorType.XPATH:
                loc = self.page.locator(f"xpath={selector}").first
            else:
                return False

            try:
                with context.expect_page(timeout=5000) as new_page_info:
                    loc.click(timeout=3000)
                new_page = new_page_info.value
                new_page.wait_for_load_state("domcontentloaded")
            except TimeoutError:
                # Page didn't open a new tab or click failed
                try:
                    loc.click(force=True, timeout=3000)
                except Exception as click_err:
                    if self.logger: self.logger.error("Click intercepted, resolving via force=True fallback", phase=ExecutionPhase.RULES)
                    loc.click(force=True)

            if self.logger:
                self.logger.info("Successfully clicked apply button", phase=ExecutionPhase.RULES, selector=result.selector)
            return True

        except Exception as e:
            if self.logger:
                self.logger.error("Failed to click apply button", phase=ExecutionPhase.RULES, error=str(e))
            return False
