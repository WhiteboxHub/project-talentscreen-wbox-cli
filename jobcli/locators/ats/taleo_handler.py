"""Oracle Taleo ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class TaleoHandler(GenericATSHandler):
    """Handler for Oracle Taleo ATS (*.taleo.net).

    Taleo is a legacy ASP-era ATS with predictable id-based fields:
      id='firstName', id='lastName', id='email', id='phone', id='zipCode' etc.
    Multi-step flow advancing via 'Continue' buttons.
    """

    _ID_MAP = [
        ("firstname",   "personal.first_name",  95),
        ("lastname",    "personal.last_name",   95),
        ("email",       "personal.email",       95),
        ("phone",       "personal.phone",       90),
        ("zip",         "personal.zip_code",    90),
        ("zipcode",     "personal.zip_code",    90),
        ("city",        "personal.city",        85),
        ("state",       "personal.state",       85),
        ("country",     "personal.country",     85),
        ("address",     "personal.address",     85),
        ("linkedin",    "personal.linkedin",    85),
    ]

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            id_attr = (el.get_attribute("id") or "").lower().lstrip("id_")
            from jobcli.locators.form_fields import FieldConfidenceScorer
            for keyword, path, confidence in self._ID_MAP:
                if keyword in id_attr:
                    value = FieldConfidenceScorer.resolve_from_resume(path, resume)
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Taleo platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Taleo apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "a.btn-apply",
            "button.btn-apply",
            "a[href*='applyOnlineURL']",
            "input[value='Apply Now']",
            "button:has-text('Apply Now')",
            "#external\\:E button",  # Taleo iframe selector
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Taleo apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Taleo apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Taleo form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        taleo_fields = [
            ("first_name", "input[id='firstName']",         personal.first_name),
            ("last_name",  "input[id='lastName']",          personal.last_name),
            ("email",      "input[id='email']",             personal.email),
            ("phone",      "input[id='phone']",             personal.phone),
            ("zip_code",   "input[id='zipCode']",           personal.zip_code),
            ("city",       "input[id='city']",              personal.city),
        ]
        for key, selector, value in taleo_fields:
            if not value:
                continue
            try:
                el = self.page.query_selector(selector)
                if el:
                    self.page.fill(selector, value, timeout=3000)
                    results[key] = True
                    if self.logger:
                        self.logger.info(f"Filled Taleo '{key}'", phase=ExecutionPhase.RULES, selector=selector)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Taleo fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results[key] = False

        if resume_path:
            try:
                file_input = self.page.query_selector("input[type='file']")
                if file_input:
                    self.page.set_input_files("input[type='file']", resume_path)
                    results["resume"] = True
                    self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Taleo resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Taleo form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "input[type='submit'][value*='Submit']",
            "input[type='submit'][value*='Apply']",
            "button.btn-primary:has-text('Submit')",
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
                    self.logger.warning(f"Taleo submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "input[type='submit'][value='Continue']",
            "input[type='submit'][value='Next']",
            "button:has-text('Continue')",
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
        # Check for confirmation
        url = self.page.url
        if any(kw in url for kw in ("confirm", "thank", "success")):
            return False
        return super().handle_multi_step(state)
