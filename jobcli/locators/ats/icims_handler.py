"""iCIMS ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class IcimsHandler(GenericATSHandler):
    """Handler for iCIMS ATS.

    iCIMS uses a heavily branded portal.  Key signals:
      - IDs prefixed with 'iCIMS_' on container divs
      - Input name attributes follow 'applicant.firstName' style on older portals
      - Newer portals use standard HTML name attrs + aria-label
    """

    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match iCIMS fields by name attribute and id patterns."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            name_attr = (el.get_attribute("name") or "").lower()
            id_attr   = (el.get_attribute("id")   or "").lower()
            personal  = resume.personal

            patterns = {
                "first":    (personal.first_name, 90),
                "fname":    (personal.first_name, 90),
                "last":     (personal.last_name,  90),
                "lname":    (personal.last_name,  90),
                "email":    (personal.email,       95),
                "phone":    (personal.phone,       90),
                "linkedin": (personal.linkedin,    85),
                "github":   (personal.github,      85),
                "zip":      (personal.zip_code,    85),
                "postal":   (personal.zip_code,    85),
                "city":     (personal.city,        85),
                "state":    (personal.state,       80),
                "address":  (personal.address,     85),
            }
            for keyword, (value, confidence) in patterns.items():
                if keyword in name_attr or keyword in id_attr:
                    if value:
                        return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"iCIMS platform match error: {e}", phase=ExecutionPhase.RULES
                )
        return None

    def find_apply_button(self) -> bool:
        """Find iCIMS apply button."""
        if self.logger:
            self.logger.info("Looking for iCIMS apply button", phase=ExecutionPhase.RULES)

        selectors = [
            ".iCIMS_Header_ApplyButton",
            "a[href*='applyURL']",
            "[data-icims='apply']",
            "a.iCIMS_Anchor:has-text('Apply')",
            "button:has-text('Apply Now')",
            ".iCIMS_ActionBar a",
        ]
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    if self.logger:
                        self.logger.info("Clicked iCIMS apply button", phase=ExecutionPhase.RULES, selector=selector)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"iCIMS apply selector failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().find_apply_button()

    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill iCIMS form using platform match + generic fallback."""
        if self.logger:
            self.logger.info("Filling iCIMS form", phase=ExecutionPhase.RULES)

        from jobcli.locators.form_fields import FormFiller
        filler = FormFiller(self.page, self.resume, self.logger)
        results: dict[str, Any] = filler.fill_personal_info()

        if resume_path:
            results["resume"] = filler.upload_resume(resume_path)

        results["work_authorization"] = filler.fill_work_authorization()
        results = self.generic_fill_failed_fields(results)

        if self.logger:
            self.logger.info("iCIMS form fill complete", phase=ExecutionPhase.RULES, results=results)
        return results

    def submit_application(self) -> bool:
        for selector in [
            "button.iCIMS_Button:has-text('Submit')",
            "input[type='submit'][value*='Submit']",
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
                    self.logger.warning(f"iCIMS submit failed '{selector}': {e}", phase=ExecutionPhase.RULES)
        return super().submit_application()

    def handle_multi_step(self, state: ApplicationState) -> bool:
        for selector in ["button.iCIMS_Button:has-text('Next')", "button:has-text('Continue')", "button:has-text('Next')"]:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible() and not el.is_disabled():
                    el.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception:
                continue
        return super().handle_multi_step(state)
