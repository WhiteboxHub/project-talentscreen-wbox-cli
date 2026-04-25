"""BambooHR ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class BambooHRHandler(GenericATSHandler):
    """Handler for BambooHR ATS.

    BambooHR's apply portal uses standard HTML name attributes on its form.
    Companies host job boards at <company>.bamboohr.com.
    """

    _FIELD_MAP = [
        ("firstName",   "personal.first_name",  95),
        ("first_name",  "personal.first_name",  95),
        ("lastName",    "personal.last_name",   95),
        ("last_name",   "personal.last_name",   95),
        ("email",       "personal.email",       95),
        ("phone",       "personal.phone",       90),
        ("address",     "personal.address",     85),
        ("city",        "personal.city",        85),
        ("state",       "personal.state",       80),
        ("zipCode",     "personal.zip_code",    85),
        ("country",     "personal.country",     80),
        ("linkedin",    "personal.linkedin",    85),
        ("website",     "personal.website",     80),
    ]

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            name_attr = el.get_attribute("name") or ""
            from jobcli.locators.form_fields import FieldConfidenceScorer
            for field_name, path, confidence in self._FIELD_MAP:
                if name_attr == field_name or name_attr.lower() == field_name.lower():
                    value = FieldConfidenceScorer.resolve_from_resume(path, resume)
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"BambooHR platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for BambooHR apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "#apply-button",
            ".btn-primary:has-text('Apply')",
            "a[href*='/application']",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked BambooHR apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"BambooHR apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling BambooHR form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        bhr_fields = [
            ("first_name",  "input[name='firstName']",  personal.first_name),
            ("last_name",   "input[name='lastName']",   personal.last_name),
            ("email",       "input[name='email']",      personal.email),
            ("phone",       "input[name='phone']",      personal.phone),
            ("address",     "input[name='address']",    personal.address),
            ("city",        "input[name='city']",       personal.city),
            ("zip_code",    "input[name='zipCode']",    personal.zip_code),
            ("linkedin",    "input[name*='linkedin']",  personal.linkedin),
        ]
        for key, selector, value in bhr_fields:
            if not value:
                continue
            try:
                el = self.page.query_selector(selector)
                if el:
                    self.humanized_fill(self.page.locator(selector).first, value)
                    results[key] = True
                    if self.logger:
                        self.logger.info(f"Filled BambooHR '{key}'", phase=ExecutionPhase.RULES)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"BambooHR fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results.setdefault(key, False)

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"BambooHR resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        # Cover letter textarea
        if hasattr(self.resume, "cover_letter") and self.resume.cover_letter:
            try:
                self.humanized_fill(self.page.locator("textarea[name='coverletter']").first, self.resume.cover_letter)
                results["cover_letter"] = True
            except Exception:
                results["cover_letter"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("BambooHR form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button[type='submit']:has-text('Submit')",
            "button.btn-primary",
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
                    self.logger.warning(f"BambooHR submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        return super().handle_multi_step(state)
