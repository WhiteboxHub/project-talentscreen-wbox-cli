"""Workday ATS handler."""

import time
from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase
from jobcli.locators.ats.base_handler import BaseATSHandler


class WorkdayHandler(BaseATSHandler):
    """Handler for Workday ATS."""

    def find_apply_button(self) -> bool:
        """Find and click Workday apply button."""
        if self.logger:
            self.logger.info("Looking for Workday apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "[data-automation-id='applyButton']",
            "button:has-text('Apply')",
            "a:has-text('Apply Manually')",
            "[data-automation-id='Apply Manually']",
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
            except Exception:
                continue

        return False

    def detect_form_fields(self) -> list[str]:
        """Detect Workday form fields."""
        fields = []

        # Workday uses data-automation-id extensively
        common_automation_ids = [
            "firstName",
            "lastName",
            "email",
            "phone",
            "addressLine1",
            "city",
            "state",
            "zipCode",
            "country",
        ]

        for field_id in common_automation_ids:
            selector = f"[data-automation-id='{field_id}']"
            if self.page.query_selector(selector):
                fields.append(field_id)

        return fields

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Workday application form."""
        if self.logger:
            self.logger.info("Filling Workday form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        # Workday uses data-automation-id attributes
        field_mapping = {
            "firstName": personal.first_name,
            "lastName": personal.last_name,
            "email": personal.email,
            "phone": personal.phone,
            "addressLine1": personal.address,
            "city": personal.city,
            "state": personal.state,
            "zipCode": personal.zip_code,
        }

        for automation_id, value in field_mapping.items():
            if value:
                try:
                    selector = f"[data-automation-id='{automation_id}'] input"
                    element = self.page.query_selector(selector)
                    if not element:
                        selector = f"input[data-automation-id='{automation_id}']"
                        element = self.page.query_selector(selector)

                    if element:
                        self.page.fill(selector, value)
                        results[automation_id] = True
                except Exception:
                    results[automation_id] = False

        # Country selection (dropdown)
        if personal.country:
            try:
                self.page.click("[data-automation-id='country']")
                time.sleep(0.5)
                self.page.click(f"text={personal.country}")
                results["country"] = True
            except Exception:
                results["country"] = False

        # LinkedIn URL
        if personal.linkedin:
            try:
                self.page.fill(
                    "input[data-automation-id='linkedInURL']",
                    personal.linkedin,
                )
                results["linkedin"] = True
            except Exception:
                results["linkedin"] = False

        # Resume upload
        if resume_path:
            results["resume"] = self._upload_resume_workday(resume_path)

        # Handle additional sections
        self._fill_work_experience()

        if self.logger:
            self.logger.info(
                "Workday form filled",
                phase=ExecutionPhase.RULES,
                results=results,
            )

        return results

    def _upload_resume_workday(self, resume_path: str) -> bool:
        """Upload resume in Workday."""
        try:
            # Look for resume upload button/link
            upload_selectors = [
                "[data-automation-id='file-upload-input']",
                "input[type='file']",
                "[data-automation-id='Upload Resume']",
            ]

            for selector in upload_selectors:
                element = self.page.query_selector(selector)
                if element:
                    self.page.set_input_files(selector, resume_path)
                    time.sleep(2)  # Wait for upload
                    return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    "Failed to upload resume to Workday",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )

        return False

    def _fill_work_experience(self) -> None:
        """Fill work experience section."""
        if not self.resume.experience:
            return

        # Workday often auto-parses resume, so this may not be needed
        # But we can add manual entry if required
        pass

    def submit_application(self) -> bool:
        """Submit Workday application."""
        if self.logger:
            self.logger.info("Submitting Workday application", phase=ExecutionPhase.RULES)

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
            except Exception:
                continue

        return False

    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Workday multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Workday step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        # Workday has multiple steps - check for "Next" button
        next_button = "[data-automation-id='bottom-navigation-next-button']"

        try:
            element = self.page.query_selector(next_button)
            if element and element.is_visible() and not element.is_disabled():
                element.click(timeout=3000)
                self.wait_for_page_load(timeout=10000)
                return True
        except Exception:
            pass

        # Check for review page
        review_indicators = [
            "[data-automation-id='review-section']",
            "text=Review and Submit",
            "text=Review Your Application",
        ]

        for indicator in review_indicators:
            if self.page.query_selector(indicator):
                if self.logger:
                    self.logger.info(
                        "Reached Workday review page",
                        phase=ExecutionPhase.RULES,
                    )
                # On review page, try to submit
                return False

        # Check for confirmation
        if "confirmation" in self.page.url or "thank" in self.page.url.lower():
            if self.logger:
                self.logger.info(
                    "Reached Workday confirmation page",
                    phase=ExecutionPhase.RULES,
                )
            return False

        return True
