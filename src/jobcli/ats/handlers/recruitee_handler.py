"""Recruitee ATS handler."""

from typing import Any, Optional

from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.ats.handlers.generic_handler import GenericATSHandler


class RecruiteeHandler(GenericATSHandler):
    """Handler for Recruitee ATS (recruitee.com / *.recruitee.com).

    Recruitee's candidate portal uses 'r6e-' class prefixes and standard
    HTML name attributes: first_name, last_name, email, phone, etc.
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
            combined  = name_attr + " " + id_attr
            personal  = resume.personal

            patterns = [
                ("first_name",  personal.first_name,  95),
                ("firstname",   personal.first_name,  95),
                ("last_name",   personal.last_name,   95),
                ("lastname",    personal.last_name,   95),
                ("email",       personal.email,       95),
                ("phone",       personal.phone,       90),
                ("city",        personal.city,        80),
                ("address",     personal.address,     80),
                ("linkedin",    personal.linkedin,    85),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Recruitee platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Recruitee apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".btn-candidate-apply",
            "a.recruit-button",
            "a[href*='/apply']",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Recruitee apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Recruitee apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Recruitee form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        rt_fields = [
            ("first_name", "input[name='first_name']",  personal.first_name),
            ("last_name",  "input[name='last_name']",   personal.last_name),
            ("email",      "input[name='email']",       personal.email),
            ("phone",      "input[name='phone']",       personal.phone),
            ("linkedin",   "input[name*='linkedin']",   personal.linkedin),
        ]
        for key, selector, value in rt_fields:
            if not value:
                continue
            try:
                el = self.page.query_selector(selector)
                if el:
                    self.humanized_fill(self.page.locator(selector).first, value)
                    results[key] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Recruitee fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results[key] = False

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Recruitee resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Recruitee form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit Application')",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Recruitee submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        return super().handle_multi_step(state)
