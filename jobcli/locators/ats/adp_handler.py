"""ADP Recruiting (TotalSource) ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class ADPHandler(GenericATSHandler):
    """Handler for ADP Recruiting / WorkforceNow ATS.

    ADP Recruiting (formerly APUS / TotalSource) uses various portal flavors.
    The most common public portal (WorkforceNow) has React-rendered forms.
    The generic heuristic engine handles the heavy lifting; this handler
    adds ADP-specific apply-button detection and resume upload.
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
                ("firstname",  personal.first_name,  90),
                ("first",      personal.first_name,  85),
                ("lastname",   personal.last_name,   90),
                ("last",       personal.last_name,   85),
                ("email",      personal.email,       95),
                ("phone",      personal.phone,       90),
                ("zip",        personal.zip_code,    85),
                ("city",       personal.city,        80),
                ("state",      personal.state,       80),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"ADP platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for ADP apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "[id*='applyBtn']",
            "[id*='Apply']",
            ".adp-applyBtn",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply for this position')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked ADP apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"ADP apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling ADP form", phase=ExecutionPhase.RULES)

        from jobcli.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            try:
                upload_selectors = [
                    "input[type='file']",
                    "[id*='fileInput']",
                    "[id*='resumeUpload']",
                ]
                for sel in upload_selectors:
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
                    self.logger.warning(f"ADP resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("ADP form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "[id*='submitBtn']",
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
                    self.logger.warning(f"ADP submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "[id*='nextBtn']",
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
