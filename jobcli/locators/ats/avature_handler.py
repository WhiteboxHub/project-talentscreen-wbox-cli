"""Avature ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class AvatureHandler(GenericATSHandler):
    """Handler for Avature ATS (avature.net / *.avature.net).

    Avature is a configurable SPA-based ATS used primarily by large enterprises.
    Field ids vary heavily by configuration; the generic heuristic engine
    provides the primary fill strategy.
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
            combined  = id_attr + " " + name_attr
            personal  = resume.personal

            patterns = [
                ("firstname",  personal.first_name,  88),
                ("first_name", personal.first_name,  88),
                ("lastname",   personal.last_name,   88),
                ("last_name",  personal.last_name,   88),
                ("email",      personal.email,       92),
                ("phone",      personal.phone,       88),
                ("city",       personal.city,        80),
                ("zip",        personal.zip_code,    82),
                ("linkedin",   personal.linkedin,    83),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Avature platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Avature apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".apply-btn",
            "[class*='applyButton']",
            "a:has-text('Apply Now')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Avature apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Avature apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Avature form", phase=ExecutionPhase.RULES)

        from jobcli.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            results["resume"] = filler.upload_resume(resume_path)

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Avature form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button:has-text('Submit')",
            "button[type='submit']",
            "input[type='submit']",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Avature submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('Save & Continue')",
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
