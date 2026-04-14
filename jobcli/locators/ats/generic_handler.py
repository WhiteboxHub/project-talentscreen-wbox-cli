"""Generic ATS handler — universal fallback for any ATS platform.

All platform-specific handlers (Greenhouse, Lever, Workday, …) inherit from
this class.  Subclasses add hardcoded platform selectors by overriding
fill_form(); anything that fails falls back to the heuristic FormFiller
via the generic_fill_failed_fields() helper.

The find_platform_specific_match() hook is available for subclasses that
want per-element override logic in the future.
"""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.base_handler import BaseATSHandler
from jobcli.locators.form_fields import FormFiller


class GenericATSHandler(BaseATSHandler):
    """Universal fallback handler driven by heuristic confidence scoring.

    Subclasses override fill_form() to add platform-specific logic, then
    call self.generic_fill_failed_fields(results, resume_path) to let the
    generic engine fill anything that wasn't resolved by exact selectors.
    """

    # ------------------------------------------------------------------
    # Hook for subclasses (future per-element override)
    # ------------------------------------------------------------------
    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Return {'value': ..., 'confidence': ...} for platform-specific
        field detection, or None to fall through to generic scoring.

        Override in subclasses (e.g. Greenhouse matches by element id,
        Workday matches by data-automation-id).
        """
        return None

    # ------------------------------------------------------------------
    # Generic field-fill helpers
    # ------------------------------------------------------------------
    def _get_filler(self) -> FormFiller:
        """Create a FormFiller bound to the current page and resume."""
        return FormFiller(self.page, self.resume, self.logger)

    def generic_fill_failed_fields(
        self,
        results: dict[str, bool],
        resume_path: Optional[str] = None,
    ) -> dict[str, bool]:
        """Run the generic heuristic fill for any field that returned False.

        Call this at the end of a platform-specific fill_form() to ensure
        nothing is silently skipped.  Only failed fields are retried.

        Returns an updated copy of results.
        """
        failed = [k for k, v in results.items() if not v]
        if not failed:
            return results

        if self.logger:
            self.logger.info(
                f"Generic fallback triggered for {len(failed)} failed field(s): {failed}",
                phase=ExecutionPhase.RULES,
            )

        filler = self._get_filler()
        generic = filler.fill_personal_info()

        updated = dict(results)
        for short_key in failed:
            if generic.get(short_key):
                updated[short_key] = True
                if self.logger:
                    self.logger.info(
                        f"Generic fallback succeeded for '{short_key}'",
                        phase=ExecutionPhase.RULES,
                    )
        return updated

    # ------------------------------------------------------------------
    # BaseATSHandler implementation — used when no subclass overrides
    # ------------------------------------------------------------------
    def find_apply_button(self) -> bool:
        """Generic apply button detection — tries common cross-ATS patterns."""
        if self.logger:
            self.logger.info(
                "Looking for apply button (generic)", phase=ExecutionPhase.RULES
            )

        selectors = [
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply for this job')",
            "a:has-text('Apply for this job')",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "[data-automation-id='applyNowButton']",
            "[data-automation-id='applyButton']",
            ".apply-button",
            "#apply-button",
            "[class*='apply'][class*='btn']",
            "[class*='apply-btn']",
            "[class*='apply-button']",
            "button[type='submit']",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked apply button (generic)",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Apply button selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        if self.logger:
            self.logger.warning(
                "No apply button found (generic)", phase=ExecutionPhase.RULES
            )
        return False

    def detect_form_fields(self) -> list[str]:
        """Detect all visible, fillable form fields on the page."""
        fields: list[str] = []
        try:
            elements = self.page.query_selector_all(
                "input:not([type='hidden']):not([disabled]), "
                "textarea:not([disabled]), "
                "select:not([disabled])"
            )
            for el in elements:
                try:
                    if el.is_visible():
                        name = el.get_attribute("name") or el.get_attribute("id") or ""
                        if name:
                            fields.append(name)
                except Exception:
                    continue
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"detect_form_fields error: {e}", phase=ExecutionPhase.RULES
                )
        return fields

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill the form using the heuristic confidence engine (generic fallback)."""
        if self.logger:
            self.logger.info(
                "Filling form (generic handler)", phase=ExecutionPhase.RULES
            )

        filler = self._get_filler()
        results = filler.fill_all(resume_path)

        filled = sum(1 for v in results.get("personal_info", {}).values() if v)
        total = len(results.get("personal_info", {}))
        if self.logger:
            self.logger.info(
                f"Generic fill complete: {filled}/{total} personal fields",
                phase=ExecutionPhase.RULES,
            )
        return results

    def submit_application(self) -> bool:
        """Generic submit button detection."""
        if self.logger:
            self.logger.info(
                "Submitting application (generic)", phase=ExecutionPhase.RULES
            )

        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "button:has-text('Apply')",
        ]

        for selector in submit_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible() and not element.is_disabled():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked submit button (generic)",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Submit selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        if self.logger:
            self.logger.warning(
                "No submit button found (generic)", phase=ExecutionPhase.RULES
            )
        return False

    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Generic multi-step: detect confirmation, click Next/Continue."""
        if self.logger:
            self.logger.info(
                f"Handling step {state.step_count} (generic)",
                phase=ExecutionPhase.RULES,
            )

        # Confirmation / success URL signals → stop stepping
        url_lower = self.page.url.lower()
        if any(
            kw in url_lower
            for kw in ("confirmation", "thank", "success", "submitted")
        ):
            if self.logger:
                self.logger.info(
                    "Detected confirmation URL — stopping",
                    phase=ExecutionPhase.RULES,
                    url=self.page.url,
                )
            return False

        # On-page success text
        success_indicators = [
            "text=Thank you for applying",
            "text=Application submitted",
            "text=Application received",
            ".application-confirmation",
            ".success-message",
        ]
        for indicator in success_indicators:
            try:
                if self.page.query_selector(indicator):
                    if self.logger:
                        self.logger.info(
                            "Detected on-page success indicator — stopping",
                            phase=ExecutionPhase.RULES,
                            indicator=indicator,
                        )
                    return False
            except Exception:
                continue

        # Try to advance multi-step form
        next_selectors = [
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "input[type='submit'][value='Next']",
            ".btn-next",
            "[data-automation-id='bottom-navigation-next-button']",
        ]
        for selector in next_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible() and not element.is_disabled():
                    element.click(timeout=3000)
                    self.wait_for_page_load()
                    if self.logger:
                        self.logger.info(
                            "Clicked Next/Continue (generic)",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Next selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return False
