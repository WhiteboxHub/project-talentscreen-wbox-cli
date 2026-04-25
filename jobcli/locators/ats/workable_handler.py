"""Workable ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class WorkableHandler(GenericATSHandler):
    """Handler for Workable ATS (apply.workable.com).

    Workable uses simple lowercase name attributes on form inputs.
    Fields: firstname, lastname, email, phone, address, city, state, zipcode, etc.
    Resume is parsed auto-magically after upload.
    """

    _FIELD_MAP = [
        ("firstname",  "personal.first_name",  95),
        ("lastname",   "personal.last_name",   95),
        ("email",      "personal.email",       95),
        ("phone",      "personal.phone",       90),
        ("address",    "personal.address",     85),
        ("city",       "personal.city",        85),
        ("state",      "personal.state",       80),
        ("zipcode",    "personal.zip_code",    85),
        ("country",    "personal.country",     80),
        ("linkedin",   "personal.linkedin",    85),
        ("github",     "personal.github",      85),
        ("website",    "personal.website",     80),
    ]

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            name_attr = (el.get_attribute("name") or "").lower()
            from jobcli.locators.form_fields import FieldConfidenceScorer
            for field_name, path, confidence in self._FIELD_MAP:
                if name_attr == field_name:
                    value = FieldConfidenceScorer.resolve_from_resume(path, resume)
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Workable platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Workable apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "button[data-ui='apply-button']",
            ".btn-primary:has-text('Apply')",
            "button:has-text('Apply for this job')",
            "a:has-text('Apply Now')",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Workable apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Workable apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Workable form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        wk_fields = [
            ("first_name", "input[name='firstname']",  personal.first_name),
            ("last_name",  "input[name='lastname']",   personal.last_name),
            ("email",      "input[name='email']",      personal.email),
            ("phone",      "input[name='phone']",      personal.phone),
            ("address",    "input[name='address']",    personal.address),
            ("city",       "input[name='city']",       personal.city),
            ("zip_code",   "input[name='zipcode']",    personal.zip_code),
            ("linkedin",   "input[name='linkedin']",   personal.linkedin),
            ("github",     "input[name='github']",     personal.github),
        ]
        for key, selector, value in wk_fields:
            if not value:
                continue
            try:
                el = self.page.query_selector(selector)
                if el:
                    self.humanized_fill(self.page.locator(selector).first, value)
                    results[key] = True
                    if self.logger:
                        self.logger.info(f"Filled Workable '{key}'", phase=ExecutionPhase.RULES)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Workable fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results.setdefault(key, False)

        # Summary / cover letter
        if hasattr(self.resume, "summary") and self.resume.summary:
            try:
                self.humanized_fill(self.page.locator("textarea[name='summary']").first, self.resume.summary)
                results["summary"] = True
            except Exception:
                results["summary"] = False

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Workable resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Workable form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button[data-ui='submit-button']",
            "button.btn-primary:has-text('Submit')",
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
                    self.logger.warning(f"Workable submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        return super().handle_multi_step(state)
