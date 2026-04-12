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

    def find(self) -> Optional[LocatorResult]:
        """Find apply button using all strategies."""
        if self.logger:
            self.logger.info("Starting apply button search", phase=ExecutionPhase.RULES)

        # Strategy 1-10: Text-based button selectors (case insensitive)
        text_patterns = [
            "Apply",
            "Apply Now",
            "Apply for this job",
            "Apply for this position",
            "Submit Application",
            "Easy Apply",
            "Quick Apply",
            "Apply Online",
            "Submit Resume",
            "Join Our Team",
        ]

        for i, text in enumerate(text_patterns, 1):
            result = self._try_selector(
                f"button:has-text('{text}')", SelectorType.CSS, f"text_button_{i}"
            )
            if result:
                return result

            # Also try with i flag for case-insensitive
            result = self._try_selector(
                f"button:text-is('{text}')", SelectorType.CSS, f"text_button_exact_{i}"
            )
            if result:
                return result

        # Strategy 11-15: Link-based selectors with "apply" in text
        link_patterns = [
            "a:has-text('Apply')",
            "a:has-text('Apply Now')",
            "a:has-text('Submit Application')",
            "a[href*='apply']",
            "a[href*='application']",
        ]

        for i, selector in enumerate(link_patterns, 11):
            result = self._try_selector(selector, SelectorType.CSS, f"link_{i}")
            if result:
                return result

        # Strategy 16-20: Input submit buttons
        submit_selectors = [
            "input[type='submit'][value*='Apply' i]",
            "input[type='submit'][value*='Submit' i]",
            "input[type='button'][value*='Apply' i]",
            "button[type='submit']:has-text('Apply')",
            "button[type='submit']:has-text('Submit')",
        ]

        for i, selector in enumerate(submit_selectors, 16):
            result = self._try_selector(selector, SelectorType.CSS, f"submit_{i}")
            if result:
                return result

        # Strategy 21-25: ARIA and role-based selectors
        aria_selectors = [
            "button[aria-label*='Apply' i]",
            "button[aria-label*='Submit' i]",
            "a[aria-label*='Apply' i]",
            "[role='button'][aria-label*='Apply' i]",
            "[role='link'][aria-label*='Apply' i]",
        ]

        for i, selector in enumerate(aria_selectors, 21):
            result = self._try_selector(selector, SelectorType.CSS, f"aria_{i}")
            if result:
                return result

        # Strategy 26-30: XPath strategies (more flexible)
        xpath_selectors = [
            "//button[contains(translate(text(), 'APPLY', 'apply'), 'apply')]",
            "//a[contains(translate(text(), 'APPLY', 'apply'), 'apply')]",
            "//button[contains(@class, 'apply')]",
            "//button[contains(@class, 'submit')]",
            "//a[contains(@href, 'apply')]",
        ]

        for i, selector in enumerate(xpath_selectors, 26):
            result = self._try_selector(selector, SelectorType.XPATH, f"xpath_{i}")
            if result:
                return result

        # Strategy 31-35: Common CSS class patterns
        class_selectors = [
            "button.apply-button",
            "button.btn-apply",
            "button.submit-application",
            ".apply-btn",
            ".application-button",
        ]

        for i, selector in enumerate(class_selectors, 31):
            result = self._try_selector(selector, SelectorType.CSS, f"class_{i}")
            if result:
                return result

        # Strategy 36-40: ID-based selectors
        id_selectors = [
            "#apply-button",
            "#applyButton",
            "#apply_button",
            "#submit-application",
            "#submitApplication",
        ]

        for i, selector in enumerate(id_selectors, 36):
            result = self._try_selector(selector, SelectorType.CSS, f"id_{i}")
            if result:
                return result

        if self.logger:
            self.logger.warning(
                "No apply button found using rule-based locators",
                phase=ExecutionPhase.RULES,
            )

        return LocatorResult(
            success=False,
            error="No apply button found",
            phase=ExecutionPhase.RULES,
        )

    def click_apply_button(self) -> bool:
        """Find and click the apply button."""
        result = self.find()

        if not result or not result.success:
            return False

        try:
            if result.selector_type == SelectorType.CSS:
                self.page.click(result.selector, timeout=5000)
            elif result.selector_type == SelectorType.XPATH:
                self.page.click(f"xpath={result.selector}", timeout=5000)
            else:
                return False

            if self.logger:
                self.logger.info(
                    "Successfully clicked apply button",
                    phase=ExecutionPhase.RULES,
                    selector=result.selector,
                )

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    "Failed to click apply button",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )
            return False
