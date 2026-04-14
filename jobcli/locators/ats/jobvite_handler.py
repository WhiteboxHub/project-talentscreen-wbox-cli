"""Jobvite ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class JobviteHandler(GenericATSHandler):
    """Handler for Jobvite ATS (jobs.jobvite.com).

    Jobvite uses 'Applicant.fieldName' name attribute pattern on older portals
    and standard HTML5 form attrs on the newer Apply portal.
    """

    _NAME_PATTERNS = [
        ("applicant.firstname",  "personal.first_name",  95),
        ("applicant.lastname",   "personal.last_name",   95),
        ("applicant.email",      "personal.email",       95),
        ("applicant.phone",      "personal.phone",       90),
        ("applicant.address",    "personal.address",     85),
        ("applicant.city",       "personal.city",        85),
        ("applicant.state",      "personal.state",       80),
        ("applicant.zip",        "personal.zip_code",    85),
        ("applicant.linkedin",   "personal.linkedin",    90),
        ("applicant.github",     "personal.github",      90),
        ("applicant.website",    "personal.website",     85),
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
            for keyword, path, confidence in self._NAME_PATTERNS:
                if keyword in name_attr:
                    value = FieldConfidenceScorer.resolve_from_resume(path, resume)
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Jobvite platform match error: {e}", phase=ExecutionPhase.RULES)
        return None

    def find_apply_button(self) -> bool:
        if self.logger:
            self.logger.info("Looking for Jobvite apply button", phase=ExecutionPhase.RULES)

        selectors = [
            "a.jv-btn-apply",
            ".jv-header-apply a",
            "[data-jobvite='apply']",
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
                        self.logger.info("Clicked Jobvite apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Jobvite apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        if self.logger:
            self.logger.info("Filling Jobvite form", phase=ExecutionPhase.RULES)

        results: dict[str, Any] = {}
        personal = self.resume.personal

        # Try both old-style 'Applicant.*' and new-style standard attrs
        jv_fields = [
            ("first_name", [
                "input[name='Applicant.firstName']",
                "input[name='firstName']",
                "input[id='firstName']",
            ], personal.first_name),
            ("last_name", [
                "input[name='Applicant.lastName']",
                "input[name='lastName']",
                "input[id='lastName']",
            ], personal.last_name),
            ("email", [
                "input[name='Applicant.email']",
                "input[name='email']",
                "input[type='email']",
            ], personal.email),
            ("phone", [
                "input[name='Applicant.phone']",
                "input[name='phone']",
            ], personal.phone),
            ("linkedin", [
                "input[name='Applicant.linkedin']",
                "input[name*='linkedin']",
            ], personal.linkedin),
        ]
        for key, selectors, value in jv_fields:
            if not value:
                continue
            filled = False
            for selector in selectors:
                try:
                    el = self.page.query_selector(selector)
                    if el:
                        self.page.fill(selector, value, timeout=3000)
                        filled = True
                        break
                except Exception:
                    continue
            if not filled:
                if self.logger:
                    self.logger.warning(f"Jobvite fill failed for '{key}'", phase=ExecutionPhase.RULES)
            results[key] = filled

        if resume_path:
            try:
                self.page.set_input_files("input[type='file']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Jobvite resume upload failed: {e}", phase=ExecutionPhase.RULES)
                results["resume"] = False

        results = self.generic_fill_failed_fields(results)
        if self.logger:
            self.logger.info("Jobvite form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "input[type='submit'][value*='Apply']",
            "button.jv-btn-primary",
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
                    self.logger.warning(f"Jobvite submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in [
            "button.jv-btn-next",
            "button:has-text('Next')",
            "input[type='submit'][value='Next']",
        ]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible() and not el.is_disabled():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception:
                continue
        return super().handle_multi_step(state)
