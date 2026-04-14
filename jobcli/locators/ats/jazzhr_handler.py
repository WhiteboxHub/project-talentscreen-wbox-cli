"""JazzHR ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class JazzHRHandler(GenericATSHandler):
    """Handler for JazzHR ATS (app.jazz.co / <company>.applytojob.com).

    JazzHR uses standard HTML form fields with well-known id attributes.
    Apply portal is hosted under applytojob.com for many companies.
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
                ("firstname",  personal.first_name,  95),
                ("first_name", personal.first_name,  95),
                ("lastname",   personal.last_name,   95),
                ("last_name",  personal.last_name,   95),
                ("email",      personal.email,       95),
                ("phone",      personal.phone,       90),
                ("city",       personal.city,        80),
                ("state",      personal.state,       80),
                ("zip",        personal.zip_code,    85),
                ("linkedin",   personal.linkedin,    85),
                ("cover",      None,                 0),  # cover letter — skip
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"JazzHR platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for JazzHR apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "#apply-now",
            ".jazzhr-apply-button",
            "a.apply_button",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "input[type='submit'][value='Apply Now']",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked JazzHR apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"JazzHR apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling JazzHR form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        jazz_fields = [
            ("first_name", "input#firstname, input[name='firstname']", personal.first_name),
            ("last_name",  "input#lastname,  input[name='lastname']",  personal.last_name),
            ("email",      "input#email,     input[name='email']",     personal.email),
            ("phone",      "input#phone,     input[name='phone']",     personal.phone),
            ("city",       "input#city,      input[name='city']",      personal.city),
            ("linkedin",   "input[name*='linkedin']",                  personal.linkedin),
        ]
        for key, selector, value in jazz_fields:
            if not value:
                continue
            try:
                # Try each sub-selector in the comma-separated list
                filled = False
                for sel in [s.strip() for s in selector.split(",")]:
                    el = self.page.query_selector(sel)
                    if el:
                        self.page.fill(sel, value, timeout=3000)
                        results[key] = True
                        filled = True
                        break
                if not filled:
                    results[key] = False
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"JazzHR fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results[key] = False

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"JazzHR resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("JazzHR form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "input[type='submit'][value='Submit']",
            "input[type='submit'][value='Apply']",
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
                    self.logger.warning(f"JazzHR submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        return super().handle_multi_step(state)
