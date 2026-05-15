"""Cornerstone OnDemand ATS handler."""

from typing import Any, Optional

from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.ats.handlers.generic_handler import GenericATSHandler


class CornerstoneHandler(GenericATSHandler):
    """Handler for Cornerstone OnDemand ATS (csod.com).

    Cornerstone (CSOD) uses a multi-step wizard with React-rendered forms.
    Element ids often contain 'CSOD' or 'csod' prefixes.
    """

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            id_attr   = (el.get_attribute("id")   or "").lower()
            name_attr = (el.get_attribute("name") or "").lower()
            aria_attr = (el.get_attribute("aria-label") or "").lower()
            combined  = " ".join([id_attr, name_attr, aria_attr])
            personal  = resume.personal

            patterns = [
                ("firstname",  personal.first_name,  90),
                ("first name", personal.first_name,  88),
                ("lastname",   personal.last_name,   90),
                ("last name",  personal.last_name,   88),
                ("email",      personal.email,       95),
                ("phone",      personal.phone,       90),
                ("zip",        personal.zip_code,    85),
                ("city",       personal.city,        80),
                ("linkedin",   personal.linkedin,    85),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Cornerstone platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Cornerstone apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".csod-apply-btn",
            "[class*='applyButton']",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply for this Job')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Cornerstone apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Cornerstone apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Cornerstone form", phase=ExecutionPhase.RULES)

        from jobcli.ats.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            results["resume"] = filler.upload_resume(resume_path)

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Cornerstone form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "[class*='submitButton']",
            "button:has-text('Submit')",
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
                    self.logger.warning(f"Cornerstone submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "[class*='nextButton']",
            "button:has-text('Next')",
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
