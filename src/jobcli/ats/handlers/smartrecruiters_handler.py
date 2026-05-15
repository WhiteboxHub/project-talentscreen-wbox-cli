"""SmartRecruiters ATS handler."""

from typing import Any, Optional

from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.ats.handlers.generic_handler import GenericATSHandler


class SmartRecruitersHandler(GenericATSHandler):
    """Handler for SmartRecruiters ATS.

    SmartRecruiters uses data-test='input-<fieldName>' attributes extensively.
    Ref: jobs.smartrecruiters.com portal.
    """

    # data-test attribute → resume field value
    _DATA_TEST_MAP = [
        ("input-firstName",   "personal.first_name",  95),
        ("input-lastName",    "personal.last_name",   95),
        ("input-email",       "personal.email",       95),
        ("input-phoneNumber", "personal.phone",       95),
        ("input-phone",       "personal.phone",       95),
        ("input-linkedin",    "personal.linkedin",    90),
        ("input-website",     "personal.website",     85),
        ("input-city",        "personal.city",        85),
        ("input-state",       "personal.state",       85),
        ("input-zip",         "personal.zip_code",    85),
        ("input-country",     "personal.country",     85),
    ]

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match SmartRecruiters fields by data-test attribute."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None

            # Check element itself or its closest ancestor with data-test
            data_test = el.evaluate(
                "el => el.getAttribute('data-test') || "
                "el.closest('[data-test]')?.getAttribute('data-test') || ''"
            ).lower()

            scorer = __import__("jobcli.locators.form_fields", fromlist=["FieldConfidenceScorer"]).FieldConfidenceScorer
            for key, path, confidence in self._DATA_TEST_MAP:
                if key in data_test:
                    value = scorer.resolve_from_resume(path, resume)
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"SmartRecruiters platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for SmartRecruiters apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "[data-test='apply-button']",
            "[data-test='application-action-continue']",
            ".srm-btn-primary:has-text('Apply')",
            ".srm-button-continue",
            "button:has-text('Apply Now')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked SR apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"SR apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling SmartRecruiters form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        # Try data-test targeted fills first
        sr_fields = [
            ("first_name",  "input[data-test='input-firstName']",   personal.first_name),
            ("last_name",   "input[data-test='input-lastName']",    personal.last_name),
            ("email",       "input[data-test='input-email']",       personal.email),
            ("phone",       "input[data-test='input-phoneNumber']", personal.phone),
            ("linkedin",    "input[data-test='input-linkedin']",    personal.linkedin),
            ("city",        "input[data-test='input-city']",        personal.city),
        ]
        for key, selector, value in sr_fields:
            if not value:
                continue
            try:
                self.humanized_fill(self.page.locator(selector).first, value)
                results[key] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"SR fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results[key] = False

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"SR resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("SmartRecruiters form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "[data-test='submit-application']",
            "[data-test='application-action-submit']",
            "button[type='submit']",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"SR submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "[data-test='application-action-continue']",
            "[data-test='next-step']",
            "button:has-text('Next')",
            "button:has-text('Continue')",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible() and not el.is_disabled():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception:
                continue
        return super().handle_multi_step(state)
