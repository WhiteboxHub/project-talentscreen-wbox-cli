"""Ashby ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class AshbyHandler(GenericATSHandler):
    """Handler for Ashby ATS (jobs.ashbyhq.com).

    Ashby uses clean standard HTML form attributes.
    Fields use simple name attrs: firstName, lastName, email, phone, etc.
    """

    _NAME_FIELD_MAP = [
        ("firstName",    "personal.first_name",  95),
        ("first_name",   "personal.first_name",  95),
        ("lastName",     "personal.last_name",   95),
        ("last_name",    "personal.last_name",   95),
        ("email",        "personal.email",       95),
        ("phone",        "personal.phone",       90),
        ("phoneNumber",  "personal.phone",       90),
        ("linkedin",     "personal.linkedin",    90),
        ("linkedinUrl",  "personal.linkedin",    95),
        ("github",       "personal.github",      90),
        ("githubUrl",    "personal.github",      95),
        ("website",      "personal.website",     85),
        ("portfolioUrl", "personal.portfolio",   90),
        ("city",         "personal.city",        85),
        ("address",      "personal.address",     85),
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
            for field_name, path, confidence in self._NAME_FIELD_MAP:
                if name_attr == field_name or name_attr.lower() == field_name.lower():
                    value = FieldConfidenceScorer.resolve_from_resume(path, resume)
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Ashby platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Ashby apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "a:has-text('Apply')",
            "button:has-text('Apply Now')",
            "[class*='ashby-job-posting-apply']",
            "a[href*='/application']",
            "button[type='submit']",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked Ashby apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Ashby apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Ashby form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        ashby_fields = [
            ("first_name",  "input[name='firstName']",    personal.first_name),
            ("last_name",   "input[name='lastName']",     personal.last_name),
            ("email",       "input[name='email']",        personal.email),
            ("phone",       "input[name='phone']",        personal.phone),
            ("phone",       "input[name='phoneNumber']",  personal.phone),
            ("linkedin",    "input[name='linkedinUrl']",  personal.linkedin),
            ("github",      "input[name='githubUrl']",    personal.github),
        ]
        for key, selector, value in ashby_fields:
            if not value or key in results:
                continue
            try:
                el = self.page.query_selector(selector)
                if el:
                    self.page.fill(selector, value, timeout=3000)
                    results[key] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Ashby fill failed '{key}': {e}", phase=ExecutionPhase.RULES)
                results.setdefault(key, False)

        if resume_path:
            try:
                self.page.set_input_files("input[name='resume'], input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Ashby resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Ashby form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in ["button[type='submit']", "button:has-text('Submit Application')", "button:has-text('Submit')"]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Ashby submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        return super().handle_multi_step(state)
