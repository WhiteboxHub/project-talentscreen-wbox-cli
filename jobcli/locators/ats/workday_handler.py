"""Workday ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler
from jobcli.locators.form_fields import FormFieldLocator


class WorkdayHandler(GenericATSHandler):
    """Handler for Workday ATS.

    Uses hardcoded data-automation-id selectors first (Workday's stable API),
    then falls back to the generic heuristic engine for any field that fails.
    """

    # ------------------------------------------------------------------
    # Platform-specific field match (by data-automation-id — Workday pattern)
    # Ported from findPlatformSpecificMatch() in workdayStrategy.js
    # ------------------------------------------------------------------
    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match Workday fields by data-automation-id attribute."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            automation_id = (
                el.get_attribute("data-automation-id") or ""
            ).lower()
            personal = resume.personal

            mapping = {
                "legalname-first":      (personal.first_name,    95),
                "legalname-last":       (personal.last_name,     95),
                "email":                (personal.email,          95),
                "phone-number":         (personal.phone,          95),
                "address-line1":        (personal.address,        95),
                "address-city":         (personal.city,           95),
                "address-state":        (personal.state,          90),
                "address-postal-code":  (personal.zip_code,       95),
                "country":              (personal.country,        90),
            }
            for key, (value, confidence) in mapping.items():
                if key in automation_id and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"find_platform_specific_match error: {e}",
                    phase=ExecutionPhase.RULES,
                )
        return None

    # ------------------------------------------------------------------
    # Apply button
    # ------------------------------------------------------------------
    def find_apply_button(self) -> bool:
        """Find and click Workday apply button."""
        if self.logger:
            self.logger.info(
                "Looking for Workday apply button", phase=ExecutionPhase.RULES
            )

        selectors = [
            "[data-automation-id='applyNowButton']",
            "[data-automation-id='applyManually']",
            "[data-automation-id='applyButton']",
            "button:has-text('Apply')",
            "a:has-text('Apply Manually')",
            ".css-apply-button",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Workday apply button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday apply selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return super().find_apply_button()

    # ------------------------------------------------------------------
    # Field detection
    # ------------------------------------------------------------------
    def detect_form_fields(self) -> list[str]:
        """Detect Workday form fields via data-automation-id."""
        automation_ids = [
            "firstName", "lastName", "email", "phone",
            "addressLine1", "city", "state", "zipCode", "country",
        ]
        detected = []
        for field_id in automation_ids:
            try:
                if self.page.query_selector(f"[data-automation-id='{field_id}']"):
                    detected.append(field_id)
            except Exception:
                continue
        return detected

    # ------------------------------------------------------------------
    # Form fill — platform-specific selectors + generic fallback
    # ------------------------------------------------------------------
    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Workday application form."""
        if self.logger:
            self.logger.info("Filling Workday form", phase=ExecutionPhase.RULES)

        results: dict[str, bool] = {}
        personal = self.resume.personal

        # Text/input fields — Workday wraps inputs in a container with automation-id
        field_mapping: list[tuple[str, str, Optional[str]]] = [
            ("first_name", "firstName",    personal.first_name),
            ("last_name",  "lastName",     personal.last_name),
            ("email",      "email",        personal.email),
            ("phone",      "phone",        personal.phone),
            ("address",    "addressLine1", personal.address),
            ("city",       "city",         personal.city),
            ("zip_code",   "zipCode",      personal.zip_code),
        ]

        for short_key, automation_id, value in field_mapping:
            if not value:
                continue
            results[short_key] = self._fill_workday_input(
                short_key, automation_id, value
            )

        # State — often a dropdown in Workday
        if personal.state:
            results["state"] = self._fill_workday_dropdown(
                "state", "state", personal.state
            )

        # Country — dropdown
        if personal.country:
            results["country"] = self._fill_workday_dropdown(
                "country", "country", personal.country
            )

        # LinkedIn URL
        if personal.linkedin:
            try:
                self.page.fill(
                    "input[data-automation-id='linkedInURL']",
                    personal.linkedin,
                    timeout=3000,
                )
                results["linkedin"] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday fill failed for 'linkedin': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                results["linkedin"] = False

        # Resume upload
        if resume_path:
            results["resume"] = self._upload_resume_workday(resume_path)

        # Generic fallback for anything that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Workday form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _fill_workday_input(
        self, short_key: str, automation_id: str, value: str
    ) -> bool:
        """Fill a Workday text input identified by data-automation-id."""
        selectors = [
            f"[data-automation-id='{automation_id}'] input",
            f"input[data-automation-id='{automation_id}']",
        ]
        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element:
                    self.page.fill(selector, value, timeout=3000)
                    if self.logger:
                        self.logger.info(
                            f"Filled Workday '{short_key}'",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    return True
            except Exception:
                continue

        if self.logger:
            self.logger.warning(
                f"Workday input not found for '{short_key}' "
                f"(automation-id='{automation_id}')",
                phase=ExecutionPhase.RULES,
            )
        return False

    def _fill_workday_dropdown(
        self, short_key: str, automation_id: str, value: str
    ) -> bool:
        """Fill a Workday dropdown (combobox / listbox) using fuzzy matching."""
        field_locator = FormFieldLocator(self.page, self.logger)

        # Try standard <select> with fuzzy match first
        selector = f"select[data-automation-id='{automation_id}']"
        try:
            if self.page.query_selector(selector):
                return field_locator.fill_select_fuzzy(selector, value)
        except Exception:
            pass

        # Workday often renders custom comboboxes — click to open, type, press Enter
        trigger_selector = f"[data-automation-id='{automation_id}']"
        try:
            trigger = self.page.query_selector(trigger_selector)
            if trigger and trigger.is_visible():
                trigger.click(timeout=3000)
                self.page.keyboard.type(value)
                self.page.wait_for_selector(
                    f"[data-automation-id='{automation_id}'] [role='option']",
                    timeout=3000,
                )
                # Click the first matching option
                option = self.page.query_selector(
                    f"[data-automation-id='{automation_id}'] [role='option']"
                )
                if option:
                    option.click()
                    if self.logger:
                        self.logger.info(
                            f"Filled Workday dropdown '{short_key}': '{value}'",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Workday dropdown fill failed for '{short_key}': {e}",
                    phase=ExecutionPhase.RULES,
                )

        return False

    def _upload_resume_workday(self, resume_path: str) -> bool:
        """Upload resume in Workday."""
        upload_selectors = [
            "[data-automation-id='file-upload-input']",
            "input[type='file']",
            "[data-automation-id='Upload Resume']",
        ]

        for selector in upload_selectors:
            try:
                element = self.page.query_selector(selector)
                if element:
                    self.page.set_input_files(selector, resume_path)
                    # Wait for the upload to register instead of sleeping
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(
                            "Uploaded resume to Workday",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday resume upload failed on '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return False

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_application(self) -> bool:
        """Submit Workday application."""
        if self.logger:
            self.logger.info(
                "Submitting Workday application", phase=ExecutionPhase.RULES
            )

        submit_selectors = [
            "[data-automation-id='bottom-navigation-next-button']",
            "[data-automation-id='submitButton']",
            "button:has-text('Submit')",
        ]

        for selector in submit_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Workday submit button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday submit selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return super().submit_application()

    # ------------------------------------------------------------------
    # Multi-step
    # ------------------------------------------------------------------
    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Workday multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Workday step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        next_button = "[data-automation-id='bottom-navigation-next-button']"
        try:
            element = self.page.query_selector(next_button)
            if element and element.is_visible() and not element.is_disabled():
                element.click(timeout=3000)
                self.wait_for_page_load(timeout=10000)
                return True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Workday Next button failed: {e}", phase=ExecutionPhase.RULES
                )

        # Review page indicators
        review_indicators = [
            "[data-automation-id='review-section']",
            "text=Review and Submit",
            "text=Review Your Application",
        ]
        for indicator in review_indicators:
            try:
                if self.page.query_selector(indicator):
                    if self.logger:
                        self.logger.info(
                            "Reached Workday review page",
                            phase=ExecutionPhase.RULES,
                        )
                    return False
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday review indicator check failed '{indicator}': {e}",
                        phase=ExecutionPhase.RULES,
                    )

        url_lower = self.page.url.lower()
        if "confirmation" in url_lower or "thank" in url_lower:
            if self.logger:
                self.logger.info(
                    "Reached Workday confirmation page", phase=ExecutionPhase.RULES
                )
            return False

        return True
