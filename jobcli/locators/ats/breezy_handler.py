"""Breezy HR ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class BreezyHandler(GenericATSHandler):
    """Handler for Breezy HR ATS (breezy.hr / app.breezy.hr).

    Breezy uses standard HTML5 form fields on its candidate portal.
    The generic heuristic engine covers most cases; platform match adds
    confidence for the standard name/email/phone pattern.
    """

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            name_attr = (el.get_attribute("name") or "").lower()
            id_attr   = (el.get_attribute("id")   or "").lower()
            personal  = resume.personal

            quick_map = {
                "name":           (f"{personal.first_name} {personal.last_name}", 90),
                "first_name":     (personal.first_name, 95),
                "last_name":      (personal.last_name,  95),
                "email":          (personal.email,       95),
                "phone":          (personal.phone,       90),
                "linkedin":       (personal.linkedin,    85),
                "city":           (personal.city,        80),
            }
            for keyword, (value, confidence) in quick_map.items():
                if keyword in name_attr or keyword in id_attr:
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Breezy platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Breezy apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".apply-btn",
            "a.btn:has-text('Apply')",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "[class*='breezy']:has-text('Apply')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Breezy apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Breezy apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Breezy form", phase=ExecutionPhase.RULES)

        from jobcli.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            results["resume"] = filler.upload_resume(resume_path)

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Breezy form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Breezy submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        return super().handle_multi_step(state)
