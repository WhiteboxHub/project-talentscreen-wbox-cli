"""Paylocity ATS handler."""

from typing import Any, Optional

from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.ats.handlers.generic_handler import GenericATSHandler


class PaylocityHandler(GenericATSHandler):
    """Handler for Paylocity Recruiting ATS (recruiting.paylocity.com).

    Paylocity uses a React SPA with standard aria-label and placeholder text.
    The generic heuristic engine handles most fields well.
    """

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Paylocity apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "button:has-text('Apply for this position')",
            "button:has-text('Apply Now')",
            ".btn-apply",
            "a:has-text('Apply')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Paylocity apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Paylocity apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Paylocity form", phase=ExecutionPhase.RULES)

        from jobcli.ats.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            results["resume"] = filler.upload_resume(resume_path)

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Paylocity form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button:has-text('Submit Application')",
            "button[type='submit']",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Paylocity submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "button:has-text('Next')",
            "button:has-text('Save & Continue')",
            "button:has-text('Continue')",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible() and not el.is_disabled():
                    el.click(timeout=3000)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception:
                continue
        return super().handle_multi_step(state)
