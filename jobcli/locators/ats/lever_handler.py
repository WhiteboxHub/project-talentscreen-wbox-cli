"""Lever ATS handler."""

from typing import Any, Optional

from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.locators.ats.generic_handler import GenericATSHandler


class LeverHandler(GenericATSHandler):
    """Handler for Lever ATS.

    Uses hardcoded Lever name-attribute selectors first (high precision),
    then falls back to the generic heuristic engine for any field that fails.
    """

    # ------------------------------------------------------------------
    # Platform-specific field match (by name attr — Lever pattern)
    # Ported from findPlatformSpecificMatch() in leverStrategy.js
    # ------------------------------------------------------------------
    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match Lever fields by name attribute."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            name_attr = (el.get_attribute("name") or "").lower()
            personal = resume.personal

            if name_attr == "name":
                full_name = f"{personal.first_name} {personal.last_name}"
                return {"value": full_name, "confidence": 95}
            if name_attr == "email":
                return {"value": personal.email, "confidence": 95}
            if name_attr == "phone":
                return {"value": personal.phone, "confidence": 95}
            if name_attr == "org":
                current = next(
                    (e for e in resume.experience if e.current), None
                )
                if current:
                    return {"value": current.company, "confidence": 90}
            if "linkedin" in name_attr:
                return {"value": personal.linkedin, "confidence": 95}
            if "github" in name_attr:
                return {"value": personal.github, "confidence": 95}
            if "portfolio" in name_attr:
                return {"value": personal.portfolio, "confidence": 95}
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"find_platform_specific_match error: {e}",
                    phase=ExecutionPhase.RULES,
                )
        return None

    # ------------------------------------------------------------------
    # Apply button
    # ------------------------------------------------------------------
    def find_apply_button(self) -> bool:
        """Find and click Lever apply button."""
        if self.logger:
            self.logger.info(
                "Looking for Lever apply button", phase=ExecutionPhase.RULES
            )

        selectors = [
            "a.template-btn-submit",
            "a.postings-btn",
            "a[href$='/apply']",
            ".postings-btn",
            "a.posting-apply",
            "button:has-text('Apply for this job')",
            "[data-lever='apply']",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Lever apply button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever apply selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return super().find_apply_button()

    # ------------------------------------------------------------------
    # Field detection
    # ------------------------------------------------------------------
    def detect_form_fields(self) -> list[str]:
        """Detect Lever form fields."""
        field_selectors = {
            "name":         "input[name='name']",
            "email":        "input[name='email']",
            "phone":        "input[name='phone']",
            "org":          "input[name='org']",
            "resume":       "input[name='resume']",
            "cover_letter": "textarea[name='cover-letter']",
            "urls":         "input[name='urls[LinkedIn]']",
        }
        detected = []
        for field_name, selector in field_selectors.items():
            try:
                if self.page.query_selector(selector):
                    detected.append(field_name)
            except Exception:
                continue
        return detected

    # ------------------------------------------------------------------
    # Form fill — platform-specific selectors + generic fallback
    # ------------------------------------------------------------------
    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Lever application form."""
        if self.logger:
            self.logger.info("Filling Lever form", phase=ExecutionPhase.RULES)

        results: dict[str, bool] = {}
        personal = self.resume.personal

        # Full name (Lever uses a single 'name' field)
        full_name = f"{personal.first_name} {personal.last_name}"
        for field_name, selector, value in [
            ("name",  "input[name='name']",  full_name),
            ("email", "input[name='email']", personal.email),
            ("phone", "input[name='phone']", personal.phone),
        ]:
            if not value:
                continue
            try:
                self.page.fill(selector, value, timeout=3000)
                results[field_name] = True
                if self.logger:
                    self.logger.info(
                        f"Filled Lever '{field_name}'",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever fill failed for '{field_name}': {e}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
                results[field_name] = False

        # Company/org (current employer)
        if self.resume.experience:
            current_exp = next(
                (exp for exp in self.resume.experience if exp.current), None
            )
            if current_exp:
                try:
                    self.page.fill("input[name='org']", current_exp.company, timeout=3000)
                    results["org"] = True
                except Exception as e:
                    if self.logger:
                        self.logger.warning(
                            f"Lever fill failed for 'org': {e}",
                            phase=ExecutionPhase.RULES,
                        )
                    results["org"] = False

        # Social / portfolio URLs
        url_fields: list[tuple[str, str, Optional[str]]] = [
            ("linkedin",  "input[name='urls[LinkedIn]']",  personal.linkedin),
            ("github",    "input[name='urls[GitHub]']",    personal.github),
            ("portfolio", "input[name='urls[Portfolio]']", personal.portfolio or personal.website),
        ]
        for field_name, selector, value in url_fields:
            if not value:
                continue
            try:
                self.page.fill(selector, value, timeout=3000)
                results[field_name] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever fill failed for '{field_name}': {e}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
                results[field_name] = False

        # Resume upload
        if resume_path:
            try:
                self.page.set_input_files("input[name='resume']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever resume upload failed: {e}", phase=ExecutionPhase.RULES
                    )
                results["resume"] = False

        # Consent checkboxes
        self._fill_consent_checkboxes(results)

        # Generic fallback for any that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Lever form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _fill_consent_checkboxes(self, results: dict[str, bool]) -> None:
        """Check GDPR / consent checkboxes."""
        try:
            consent_boxes = self.page.query_selector_all("input[type='checkbox']")
            for checkbox in consent_boxes:
                try:
                    label = checkbox.evaluate(
                        "el => el.labels && el.labels[0]?.textContent || ''"
                    )
                    if label and any(
                        word in label.lower()
                        for word in ["consent", "agree", "terms", "privacy"]
                    ):
                        if not checkbox.is_checked():
                            checkbox.check()
                except Exception as inner_e:
                    if self.logger:
                        self.logger.warning(
                            f"Lever consent checkbox failed: {inner_e}",
                            phase=ExecutionPhase.RULES,
                        )
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Lever _fill_consent_checkboxes error: {e}",
                    phase=ExecutionPhase.RULES,
                )

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_application(self) -> bool:
        """Submit Lever application."""
        if self.logger:
            self.logger.info(
                "Submitting Lever application", phase=ExecutionPhase.RULES
            )

        submit_selectors = [
            "button.template-btn-submit",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit application')",
        ]

        for selector in submit_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible() and not element.is_disabled():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Lever submit button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever submit selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return super().submit_application()

    # ------------------------------------------------------------------
    # Multi-step
    # ------------------------------------------------------------------
    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Lever multi-step flow (Lever is mostly single-page)."""
        if self.logger:
            self.logger.info(
                f"Handling Lever step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        url = self.page.url
        if "success" in url or "confirmation" in url:
            if self.logger:
                self.logger.info(
                    "Reached Lever confirmation page", phase=ExecutionPhase.RULES
                )
            return False

        success_indicators = [
            ".application-confirmation",
            ".success-message",
            "text=Thank you for applying",
            "text=Application submitted",
        ]
        for indicator in success_indicators:
            try:
                if self.page.query_selector(indicator):
                    if self.logger:
                        self.logger.info(
                            "Found Lever success indicator",
                            phase=ExecutionPhase.RULES,
                            indicator=indicator,
                        )
                    return False
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever indicator check failed '{indicator}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return True  # No success indicators found — continue
