"""UKG Pro (UltiPro) ATS handler."""

from typing import Any, Optional

from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.ats.handlers.generic_handler import GenericATSHandler


class UKGHandler(GenericATSHandler):
    """Handler for UKG Pro / UltiPro ATS (recruiting.ultipro.com / *.ukg.com).

    UKG Pro uses id-based fields with predictable patterns such as
    'ctl00_ContentPlaceHolder1_firstName' or shorter 'firstName'/'lastName'.
    Multi-step flow with Save & Continue buttons.
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
                ("firstname",   personal.first_name,  90),
                ("first_name",  personal.first_name,  90),
                ("lastname",    personal.last_name,   90),
                ("last_name",   personal.last_name,   90),
                ("email",       personal.email,       95),
                ("phone",       personal.phone,       90),
                ("zip",         personal.zip_code,    85),
                ("city",        personal.city,        80),
                ("address",     personal.address,     80),
                ("linkedin",    personal.linkedin,    85),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"UKG platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for UKG apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "[id*='btnApply']",
            "[id*='Apply']",
            "[class*='btn-apply']",
            "a:has-text('Apply Now')",
            "button:has-text('Apply Now')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked UKG apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"UKG apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling UKG form", phase=ExecutionPhase.RULES)

        from jobcli.ats.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            try:
                for sel in ["input[type='file']", "[id*='ResumeUpload']", "[id*='fileInput']"]:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.set_input_files(sel, resume_path)
                        results["resume"] = True
                        self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                        break
                else:
                    results["resume"] = False
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"UKG resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("UKG form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "[id*='btnSubmit']",
            "[id*='Submit']",
            "button:has-text('Submit')",
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
                    self.logger.warning(f"UKG submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "[id*='btnNext']",
            "[id*='btnContinue']",
            "button:has-text('Save & Continue')",
            "button:has-text('Next')",
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
