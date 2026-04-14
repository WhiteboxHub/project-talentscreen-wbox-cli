"""SAP SuccessFactors ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class SuccessFactorsHandler(GenericATSHandler):
    """Handler for SAP SuccessFactors ATS (*.successfactors.com / *.sapsf.com).

    SuccessFactors is a complex SPA.  Element IDs often contain the field name
    in a suffix pattern like 'sfPrefix--firstName-inner'.
    The generic heuristic engine handles most cases well; the platform match
    adds confidence when SuccessFactors-style IDs are detected.
    """

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            id_attr = (el.get_attribute("id") or "").lower()
            name_attr = (el.get_attribute("name") or "").lower()
            combined = id_attr + " " + name_attr
            personal = resume.personal

            patterns = [
                ("firstname",   personal.first_name,  90),
                ("first_name",  personal.first_name,  90),
                ("lastname",    personal.last_name,   90),
                ("last_name",   personal.last_name,   90),
                ("email",       personal.email,       90),
                ("phone",       personal.phone,       85),
                ("mobile",      personal.phone,       85),
                ("linkedin",    personal.linkedin,    85),
                ("city",        personal.city,        80),
                ("zipcode",     personal.zip_code,    85),
                ("zip",         personal.zip_code,    80),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"SuccessFactors platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for SuccessFactors apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "[id*='applyBtn']",
            "[class*='applyBtn']",
            "button[class*='sap-']:has-text('Apply')",
            ".sapUiBtnText:has-text('Apply')",
            "bdi:has-text('Apply')",    # SAP UI5 icon button
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked SF apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=12000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"SF apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling SuccessFactors form", phase=ExecutionPhase.RULES)

        from jobcli.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            try:
                file_inputs = ["input[type='file']", "[id*='fileUpload']"]
                for sel in file_inputs:
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
                    self.logger.warning(f"SF resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("SuccessFactors form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "[id*='submitBtn']",
            "[class*='submitBtn']",
            "button[class*='sap-']:has-text('Submit')",
            "button[type='submit']",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load(timeout=12000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"SF submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "[id*='nextBtn']",
            "[id*='continueBtn']",
            "button[class*='sap-']:has-text('Next')",
            "button:has-text('Next')",
            "button:has-text('Continue')",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible() and not el.is_disabled():
                    el.click(timeout=3000)
                    self.wait_for_page_load(timeout=12000)
                    return True
            except Exception:
                continue
        return super().handle_multi_step(state)
