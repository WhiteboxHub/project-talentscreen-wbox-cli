"""Phenom People ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class PhenomHandler(GenericATSHandler):
    """Handler for Phenom People TXM ATS (various company career portals).

    Phenom People uses a React-based talent experience platform.
    Form fields typically use standard HTML5 name attributes with
    camelCase naming: firstName, lastName, email, phone, etc.
    """

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            name_attr = (el.get_attribute("name") or "")
            id_attr   = (el.get_attribute("id")   or "").lower()
            combined  = name_attr.lower() + " " + id_attr
            personal  = resume.personal

            patterns = [
                ("firstname",   personal.first_name,  92),
                ("first_name",  personal.first_name,  92),
                ("lastname",    personal.last_name,   92),
                ("last_name",   personal.last_name,   92),
                ("email",       personal.email,       95),
                ("phone",       personal.phone,       90),
                ("phonenumber", personal.phone,       90),
                ("linkedin",    personal.linkedin,    87),
                ("city",        personal.city,        82),
                ("zip",         personal.zip_code,    85),
                ("address",     personal.address,     82),
            ]
            for keyword, value, confidence in patterns:
                if keyword in combined and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Phenom platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Phenom apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".pptd-apply-button",
            "[class*='apply'][class*='button']",
            "[class*='applyButton']",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply for this job')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Phenom apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Phenom apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Phenom form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        phenom_fields = [
            ("first_name", "input[name='firstName']",   personal.first_name),
            ("last_name",  "input[name='lastName']",    personal.last_name),
            ("email",      "input[name='email']",       personal.email),
            ("phone",      "input[name='phone']",       personal.phone),
            ("phone",      "input[name='phoneNumber']", personal.phone),
            ("linkedin",   "input[name*='linkedin']",   personal.linkedin),
        ]
        for key, selector, value in phenom_fields:
            if not value or key in results:
                continue
            try:
                el = self.page.query_selector(selector)
                if el:
                    self.page.fill(selector, value, timeout=3000)
                    results[key] = True
                    if self.logger:
                        self.logger.info(f"Filled Phenom '{key}'", phase=ExecutionPhase.RULES)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Phenom fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results.setdefault(key, False)

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Phenom resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Phenom form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "button:has-text('Send application')",
            "button:has-text('Finish')",
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
                    self.logger.warning(f"Phenom submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
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
