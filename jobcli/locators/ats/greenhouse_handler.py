"""Greenhouse ATS handler."""

import time
from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase
from jobcli.locators.ats.base_handler import BaseATSHandler


class GreenhouseHandler(BaseATSHandler):
    """Handler for Greenhouse ATS."""

    def find_apply_button(self) -> bool:
        """Find and click Greenhouse apply button."""
        if self.logger:
            self.logger.info("Looking for Greenhouse apply button", phase=ExecutionPhase.RULES)

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
            except Exception:
                continue

        return False

    def detect_form_fields(self) -> list[str]:
        """Detect Greenhouse form fields."""
        fields = []

        field_selectors = {
            "first_name": "input[name='job_application[first_name]']",
            "last_name": "input[name='job_application[last_name]']",
            "email": "input[name='job_application[email]']",
            "phone": "input[name='job_application[phone]']",
            "resume": "input[name='job_application[resume]']",
            "cover_letter": "input[name='job_application[cover_letter]']",
            "linkedin": "input[name='job_application[linkedin_profile_url]']",
        }

        for field_name, selector in field_selectors.items():
            if self.page.query_selector(selector):
                fields.append(field_name)

        return fields

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Greenhouse application form."""
        if self.logger:
            self.logger.info("Filling Greenhouse form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        # First name
        try:
            self.page.fill("input[name='job_application[first_name]']", personal.first_name)
            results["first_name"] = True
        except Exception:
            results["first_name"] = False

        # Last name
        try:
            self.page.fill("input[name='job_application[last_name]']", personal.last_name)
            results["last_name"] = True
        except Exception:
            results["last_name"] = False

        # Email
        try:
            self.page.fill("input[name='job_application[email]']", personal.email)
            results["email"] = True
        except Exception:
            results["email"] = False

        # Phone
        try:
            self.page.fill("input[name='job_application[phone]']", personal.phone)
            results["phone"] = True
        except Exception:
            results["phone"] = False

        # LinkedIn
        if personal.linkedin:
            try:
                self.page.fill(
                    "input[name='job_application[linkedin_profile_url]']",
                    personal.linkedin,
                )
                results["linkedin"] = True
            except Exception:
                results["linkedin"] = False

        # Resume upload
        if resume_path:
            try:
                self.page.set_input_files(
                    "input[name='job_application[resume]']",
                    resume_path,
                )
                results["resume"] = True
                time.sleep(1)  # Wait for upload
            except Exception:
                results["resume"] = False

        # Handle custom fields
        self._fill_custom_fields()

        if self.logger:
            self.logger.info(
                "Greenhouse form filled",
                phase=ExecutionPhase.RULES,
                results=results,
            )

        return results

    def _fill_custom_fields(self) -> None:
        """Fill Greenhouse custom fields."""
        # Work authorization
        try:
            authorized = "Yes" if self.resume.work_authorization.authorized_to_work else "No"
            self.page.select_option(
                "select[name*='authorized_to_work']",
                authorized,
            )
        except Exception:
            pass

        # Sponsorship
        try:
            sponsorship = "Yes" if self.resume.work_authorization.require_sponsorship else "No"
            self.page.select_option(
                "select[name*='require_sponsorship']",
                sponsorship,
            )
        except Exception:
            pass

    def submit_application(self) -> bool:
        """Submit Greenhouse application."""
        if self.logger:
            self.logger.info("Submitting Greenhouse application", phase=ExecutionPhase.RULES)

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
                            "Clicked submit button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception:
                continue

        return False

    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Greenhouse multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Greenhouse step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        # Check for "Next" button
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
            except Exception:
                continue

        # Check for confirmation page
        if "confirmation" in self.page.url or "thank" in self.page.url:
            if self.logger:
                self.logger.info(
                    "Reached confirmation page",
                    phase=ExecutionPhase.RULES,
                )
            return False

        return False
