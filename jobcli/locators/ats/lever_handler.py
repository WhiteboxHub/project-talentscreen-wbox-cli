"""Lever ATS handler."""

import time
from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase
from jobcli.locators.ats.base_handler import BaseATSHandler


class LeverHandler(BaseATSHandler):
    """Handler for Lever ATS."""

    def find_apply_button(self) -> bool:
        """Find and click Lever apply button."""
        if self.logger:
            self.logger.info("Looking for Lever apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".postings-btn",
            ".template-btn-submit",
            "a.posting-apply",
            "button:has-text('Apply for this job')",
            "[data-lever='apply']",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Lever apply button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception:
                continue

        return False

    def detect_form_fields(self) -> list[str]:
        """Detect Lever form fields."""
        fields = []

        field_selectors = {
            "name": "input[name='name']",
            "email": "input[name='email']",
            "phone": "input[name='phone']",
            "org": "input[name='org']",
            "resume": "input[name='resume']",
            "cover_letter": "textarea[name='cover-letter']",
            "urls": "input[name='urls[LinkedIn]']",
        }

        for field_name, selector in field_selectors.items():
            if self.page.query_selector(selector):
                fields.append(field_name)

        return fields

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Lever application form."""
        if self.logger:
            self.logger.info("Filling Lever form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        # Full name (Lever uses single name field)
        try:
            full_name = f"{personal.first_name} {personal.last_name}"
            self.page.fill("input[name='name']", full_name)
            results["name"] = True
        except Exception:
            results["name"] = False

        # Email
        try:
            self.page.fill("input[name='email']", personal.email)
            results["email"] = True
        except Exception:
            results["email"] = False

        # Phone
        try:
            self.page.fill("input[name='phone']", personal.phone)
            results["phone"] = True
        except Exception:
            results["phone"] = False

        # Company/Organization (if currently employed)
        if self.resume.experience:
            current_experience = next(
                (exp for exp in self.resume.experience if exp.current), None
            )
            if current_experience:
                try:
                    self.page.fill("input[name='org']", current_experience.company)
                    results["org"] = True
                except Exception:
                    results["org"] = False

        # LinkedIn URL
        if personal.linkedin:
            try:
                self.page.fill("input[name='urls[LinkedIn]']", personal.linkedin)
                results["linkedin"] = True
            except Exception:
                results["linkedin"] = False

        # GitHub URL
        if personal.github:
            try:
                self.page.fill("input[name='urls[GitHub]']", personal.github)
                results["github"] = True
            except Exception:
                results["github"] = False

        # Portfolio/Website
        if personal.portfolio or personal.website:
            url = personal.portfolio or personal.website
            try:
                self.page.fill("input[name='urls[Portfolio]']", url or "")
                results["portfolio"] = True
            except Exception:
                results["portfolio"] = False

        # Resume upload
        if resume_path:
            try:
                self.page.set_input_files("input[name='resume']", resume_path)
                results["resume"] = True
                time.sleep(1)  # Wait for upload
            except Exception:
                results["resume"] = False

        # Handle additional questions
        self._fill_additional_questions()

        if self.logger:
            self.logger.info(
                "Lever form filled",
                phase=ExecutionPhase.RULES,
                results=results,
            )

        return results

    def _fill_additional_questions(self) -> None:
        """Fill Lever additional questions."""
        # Check for consent checkboxes
        try:
            consent_boxes = self.page.query_selector_all("input[type='checkbox']")
            for checkbox in consent_boxes:
                label = checkbox.evaluate("el => el.labels[0]?.textContent")
                # Check GDPR/consent boxes
                if label and any(
                    word in label.lower()
                    for word in ["consent", "agree", "terms", "privacy"]
                ):
                    if not checkbox.is_checked():
                        checkbox.check()
        except Exception:
            pass

    def submit_application(self) -> bool:
        """Submit Lever application."""
        if self.logger:
            self.logger.info("Submitting Lever application", phase=ExecutionPhase.RULES)

        submit_selectors = [
            "button.template-btn-submit",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit application')",
        ]

        for selector in submit_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible() and not element.is_disabled():
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
        """Handle Lever multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Lever step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        # Lever typically has a single-page application
        # Check for confirmation
        if "success" in self.page.url or "confirmation" in self.page.url:
            if self.logger:
                self.logger.info(
                    "Reached Lever confirmation page",
                    phase=ExecutionPhase.RULES,
                )
            return False

        # Check for success message on page
        success_indicators = [
            ".application-confirmation",
            ".success-message",
            "text=Thank you for applying",
            "text=Application submitted",
        ]

        for indicator in success_indicators:
            if self.page.query_selector(indicator):
                if self.logger:
                    self.logger.info(
                        "Found Lever success indicator",
                        phase=ExecutionPhase.RULES,
                        indicator=indicator,
                    )
                return False

        return True  # Continue if no success indicators found
