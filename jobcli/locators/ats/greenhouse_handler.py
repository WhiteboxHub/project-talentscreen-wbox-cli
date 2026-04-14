"""Greenhouse ATS handler."""

import time
from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class GreenhouseHandler(GenericATSHandler):
    """Handler for Greenhouse ATS.

    Uses hardcoded Greenhouse-specific selectors first (high precision),
    then falls back to the generic heuristic engine for any field that fails.
    """

    # ------------------------------------------------------------------
    # Platform-specific field match (by element id — Greenhouse pattern)
    # Ported from findPlatformSpecificMatch() in greenhouseStrategy.js
    # ------------------------------------------------------------------
    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match Greenhouse fields by id attribute."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            id_ = (el.get_attribute("id") or "").lower()
            label_text = ""
            try:
                label_text = el.evaluate(
                    """el => {
                        const lbl = el.closest('div.field, div.input-wrapper, div.select__container');
                        return lbl ? (lbl.querySelector('label')?.innerText || '') : '';
                    }"""
                ).lower()
            except Exception:
                pass

            personal = resume.personal
            if "first_name" in id_:
                return {"value": personal.first_name, "confidence": 95}
            if "last_name" in id_:
                return {"value": personal.last_name, "confidence": 95}
            if "email" in id_:
                return {"value": personal.email, "confidence": 95}
            if "phone" in id_:
                return {"value": personal.phone, "confidence": 95}
            if "linkedin" in id_ or "linkedin" in label_text:
                return {"value": personal.linkedin, "confidence": 90}
            if "github" in id_ or "github" in label_text:
                return {"value": personal.github, "confidence": 90}
            if (
                "portfolio" in id_
                or "website" in label_text
                or "portfolio" in label_text
            ):
                return {
                    "value": personal.portfolio or personal.website,
                    "confidence": 85,
                }
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
        """Find and click Greenhouse apply button."""
        if self.logger:
            self.logger.info(
                "Looking for Greenhouse apply button", phase=ExecutionPhase.RULES
            )

        selectors = [
            "#submit_app_button",
            ".application-button",
            "button:has-text('Submit Application')",
            "a#apply_button",
            "[data-greenhouse='apply']",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Greenhouse apply button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse apply selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        # Fallback to generic apply button detection
        if self.logger:
            self.logger.info(
                "Trying generic apply button fallback", phase=ExecutionPhase.RULES
            )
        return super().find_apply_button()

    # ------------------------------------------------------------------
    # Field detection
    # ------------------------------------------------------------------
    def detect_form_fields(self) -> list[str]:
        """Detect Greenhouse form fields."""
        field_selectors = {
            "first_name":  "input[name='job_application[first_name]']",
            "last_name":   "input[name='job_application[last_name]']",
            "email":       "input[name='job_application[email]']",
            "phone":       "input[name='job_application[phone]']",
            "resume":      "input[name='job_application[resume]']",
            "cover_letter":"input[name='job_application[cover_letter]']",
            "linkedin":    "input[name='job_application[linkedin_profile_url]']",
        }
        detected = []
        for field_name, selector in field_selectors.items():
            try:
                if self.page.query_selector(selector):
                    detected.append(field_name)
            except Exception:
                continue
        return detected

    # ------------------------------------------------------------------
    # Form fill — platform-specific selectors + generic fallback
    # ------------------------------------------------------------------
    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Greenhouse application form."""
        if self.logger:
            self.logger.info("Filling Greenhouse form", phase=ExecutionPhase.RULES)

        results: dict[str, bool] = {}
        personal = self.resume.personal

        platform_fields: list[tuple[str, str, Optional[str]]] = [
            ("first_name",  "input[name='job_application[first_name]']", personal.first_name),
            ("last_name",   "input[name='job_application[last_name]']",  personal.last_name),
            ("email",       "input[name='job_application[email]']",       personal.email),
            ("phone",       "input[name='job_application[phone]']",       personal.phone),
            ("linkedin",    "input[name='job_application[linkedin_profile_url]']", personal.linkedin),
        ]

        for field_name, selector, value in platform_fields:
            if not value:
                continue
            try:
                self.page.fill(selector, value, timeout=3000)
                results[field_name] = True
                if self.logger:
                    self.logger.info(
                        f"Filled Greenhouse '{field_name}'",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse fill failed for '{field_name}': {e}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
                results[field_name] = False

        # Resume upload
        if resume_path:
            try:
                self.page.set_input_files(
                    "input[name='job_application[resume]']", resume_path
                )
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse resume upload failed: {e}",
                        phase=ExecutionPhase.RULES,
                    )
                results["resume"] = False

        # Custom fields (work auth, sponsorship)
        self._fill_custom_fields(results)

        # Generic fallback for any field that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Greenhouse form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _fill_custom_fields(self, results: dict[str, bool]) -> None:
        """Fill Greenhouse custom fields (work authorization, sponsorship)."""
        auth = self.resume.work_authorization

        try:
            authorized = "Yes" if auth.authorized_to_work else "No"
            self.page.select_option(
                "select[name*='authorized_to_work']", authorized, timeout=3000
            )
            results["authorized_to_work"] = True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Greenhouse work-auth field not found or failed: {e}",
                    phase=ExecutionPhase.RULES,
                )
            results["authorized_to_work"] = False

        try:
            sponsorship = "Yes" if auth.require_sponsorship else "No"
            self.page.select_option(
                "select[name*='require_sponsorship']", sponsorship, timeout=3000
            )
            results["require_sponsorship"] = True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Greenhouse sponsorship field not found or failed: {e}",
                    phase=ExecutionPhase.RULES,
                )
            results["require_sponsorship"] = False

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_application(self) -> bool:
        """Submit Greenhouse application."""
        if self.logger:
            self.logger.info(
                "Submitting Greenhouse application", phase=ExecutionPhase.RULES
            )

        submit_selectors = [
            "input[type='submit'][value='Submit Application']",
            "button[type='submit']",
            "#submit_app_button",
        ]

        for selector in submit_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Greenhouse submit button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse submit selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return super().submit_application()

    # ------------------------------------------------------------------
    # Multi-step
    # ------------------------------------------------------------------
    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Greenhouse multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Greenhouse step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        next_selectors = [
            "button:has-text('Next')",
            "input[type='submit'][value='Next']",
            ".btn-next",
        ]

        for selector in next_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse next selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        if "confirmation" in self.page.url or "thank" in self.page.url:
            if self.logger:
                self.logger.info(
                    "Reached Greenhouse confirmation page",
                    phase=ExecutionPhase.RULES,
                )
            return False

        return False
