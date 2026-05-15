"""Greenhouse ATS handler."""

import time
from typing import Any, Optional

from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from jobcli.ats.handlers.generic_handler import GenericATSHandler


class GreenhouseHandler(GenericATSHandler):
    """Handler for Greenhouse ATS.

    Uses hardcoded Greenhouse-specific selectors first (high precision),
    then falls back to the generic heuristic engine for any field that fails.
    """

    # ------------------------------------------------------------------
    # Platform-specific field match (by element id — Greenhouse pattern)
    # Ported from findPlatformSpecificMatch() in greenhouseStrategy.js
    # ------------------------------------------------------------------
    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match Greenhouse fields by id attribute."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            id_ = (el.get_attribute("id") or "").lower()
            label_text = ""
            try:
                label_text = el.evaluate(
                    """el => {
                        const lbl = el.closest('div.field, div.input-wrapper, div.select__container');
                        return lbl ? (lbl.querySelector('label')?.innerText || '') : '';
                    }"""
                ).lower()
            except Exception:
                pass

            personal = resume.personal
            if "first_name" in id_:
                return {"value": personal.first_name, "confidence": 95}
            if "last_name" in id_:
                return {"value": personal.last_name, "confidence": 95}
            if "email" in id_:
                return {"value": personal.email, "confidence": 95}
            if "phone" in id_:
                return {"value": personal.phone, "confidence": 95}
            if "linkedin" in id_ or "linkedin" in label_text:
                return {"value": personal.linkedin, "confidence": 90}
            if "github" in id_ or "github" in label_text:
                return {"value": personal.github, "confidence": 90}
            if (
                "portfolio" in id_
                or "website" in label_text
                or "portfolio" in label_text
            ):
                return {
                    "value": personal.portfolio or personal.website,
                    "confidence": 85,
                }
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
        """Find and click Greenhouse apply button."""
        if self.logger:
            self.logger.info(
                "Looking for Greenhouse apply button", phase=ExecutionPhase.RULES
            )

        selectors = [
            "#submit_app_button",
            ".application-button",
            "button:has-text('Submit Application')",
            "a#apply_button",
            "[data-greenhouse='apply']",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Greenhouse apply button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse apply selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        # Fallback to generic apply button detection
        if self.logger:
            self.logger.info(
                "Trying generic apply button fallback", phase=ExecutionPhase.RULES
            )
        return super().find_apply_button()

    # ------------------------------------------------------------------
    # Selector catalog — legacy + modern `job-boards.greenhouse.io`
    # ------------------------------------------------------------------
    # Greenhouse hosts two distinct application products:
    #
    #   LEGACY  (``boards.greenhouse.io/<co>/jobs/<id>``)
    #       Rails-rendered form; inputs use
    #       ``name="job_application[first_name]"`` etc.
    #
    #   MODERN  (``job-boards.greenhouse.io/<co>/jobs/<id>``)
    #       React-rendered form; inputs use plain ``id="first_name"`` and
    #       ``autocomplete="given-name"`` attributes, no
    #       ``job_application[...]`` wrapping.  Resume upload is a hidden
    #       file input under a custom "Attach resume" button.
    #
    # We try each candidate in order and accept the first one that matches.
    _FIELD_SELECTORS: dict[str, list[str]] = {
        "first_name": [
            "input[name='job_application[first_name]']",
            "input#first_name",
            "input[autocomplete='given-name']",
            "input[name='first_name']",
        ],
        "last_name": [
            "input[name='job_application[last_name]']",
            "input#last_name",
            "input[autocomplete='family-name']",
            "input[name='last_name']",
        ],
        "email": [
            "input[name='job_application[email]']",
            "input#email",
            "input[autocomplete='email']",
            "input[type='email']",
            "input[name='email']",
        ],
        "phone": [
            "input[name='job_application[phone]']",
            "input#phone",
            "input[autocomplete='tel']",
            "input[type='tel']",
            "input[name='phone']",
        ],
        "linkedin": [
            "input[name='job_application[linkedin_profile_url]']",
            "input#linkedin",
            "input[name='linkedin']",
            "input[name*='linkedin' i]",
        ],
        "resume": [
            "input[name='job_application[resume]']",
            "input[type='file'][name*='resume' i]",
            "input[type='file'][data-ui*='resume' i]",
            "input[type='file'][accept*='pdf']",
            "input[type='file']",
        ],
        "cover_letter": [
            "input[name='job_application[cover_letter]']",
            "input[type='file'][name*='cover' i]",
        ],
    }

    def _first_visible(self, selectors: list[str], timeout_ms: int = 500):
        """Return the first selector whose element is present & visible.

        Uses ``query_selector`` (no implicit wait) + a cheap visibility
        probe so a missing selector fails in a few ms rather than the 3s
        default ``page.fill`` timeout.  Returns ``None`` if nothing
        matches — caller is expected to log ONCE after trying all
        candidates.
        """
        for selector in selectors:
            try:
                el = self.page.query_selector(selector)
                if not el:
                    continue
                try:
                    if el.is_visible():
                        return selector
                except Exception:
                    # Hidden file inputs are intentionally not "visible"
                    # but are still fillable via set_input_files.
                    if "type='file'" in selector or "type=\"file\"" in selector:
                        return selector
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Field detection
    # ------------------------------------------------------------------
    def detect_form_fields(self) -> list[str]:
        """Detect Greenhouse form fields (legacy + modern)."""
        detected: list[str] = []
        for field_name, selectors in self._FIELD_SELECTORS.items():
            if self._first_visible(selectors):
                detected.append(field_name)
        return detected

    # ------------------------------------------------------------------
    # Form fill — platform-specific selectors + generic fallback
    # ------------------------------------------------------------------
    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Greenhouse application form."""
        if self.logger:
            self.logger.info("Filling Greenhouse form", phase=ExecutionPhase.RULES)

        results: dict[str, bool] = {}
        personal = self.resume.personal

        platform_fields: list[tuple[str, Optional[str]]] = [
            ("first_name", personal.first_name),
            ("last_name",  personal.last_name),
            ("email",      personal.email),
            ("phone",      personal.phone),
            ("linkedin",   personal.linkedin),
        ]

        for field_name, value in platform_fields:
            if not value:
                continue
            selector = self._first_visible(self._FIELD_SELECTORS[field_name])
            if not selector:
                # No selector shape matched — this is normal on forms
                # that don't have the field at all.  Skip silently; the
                # LLM / generic fallback will handle anything we missed.
                results[field_name] = False
                continue
            try:
                self.humanized_fill(self.page.locator(selector).first, value)
                results[field_name] = True
                if self.logger:
                    self.logger.info(
                        f"Filled Greenhouse '{field_name}'",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse fill failed for '{field_name}': {e}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
                results[field_name] = False

        # Resume upload — try each candidate file-input shape.
        if resume_path:
            uploaded = False
            for selector in self._FIELD_SELECTORS["resume"]:
                try:
                    if not self.page.query_selector(selector):
                        continue
                    self.page.set_input_files(selector, resume_path)
                    uploaded = True
                    try:
                        self.page.wait_for_load_state(
                            "domcontentloaded", timeout=5000
                        )
                    except Exception:
                        pass
                    break
                except Exception:
                    continue
            results["resume"] = uploaded
            if not uploaded and self.logger:
                self.logger.warning(
                    "Greenhouse resume upload: no matching file input found.",
                    phase=ExecutionPhase.RULES,
                )

        # Custom fields (work auth, sponsorship)
        self._fill_custom_fields(results)

        # Generic fallback for any field that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Greenhouse form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _fill_custom_fields(self, results: dict[str, bool]) -> None:
        """Fill Greenhouse custom fields (work authorization, sponsorship)."""
        auth = self.resume.work_authorization

        try:
            authorized = "Yes" if auth.authorized_to_work else "No"
            self.page.select_option(
                "select[name*='authorized_to_work']", authorized, timeout=3000
            )
            results["authorized_to_work"] = True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Greenhouse work-auth field not found or failed: {e}",
                    phase=ExecutionPhase.RULES,
                )
            results["authorized_to_work"] = False

        try:
            sponsorship = "Yes" if auth.require_sponsorship else "No"
            self.page.select_option(
                "select[name*='require_sponsorship']", sponsorship, timeout=3000
            )
            results["require_sponsorship"] = True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Greenhouse sponsorship field not found or failed: {e}",
                    phase=ExecutionPhase.RULES,
                )
            results["require_sponsorship"] = False

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_application(self) -> bool:
        """Submit Greenhouse application."""
        if self.logger:
            self.logger.info(
                "Submitting Greenhouse application", phase=ExecutionPhase.RULES
            )

        submit_selectors = [
            "input[type='submit'][value='Submit Application']",
            "button[type='submit']",
            "#submit_app_button",
        ]

        for selector in submit_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Greenhouse submit button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse submit selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        return super().submit_application()

    # ------------------------------------------------------------------
    # Multi-step
    # ------------------------------------------------------------------
    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Greenhouse multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Greenhouse step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        next_selectors = [
            "button:has-text('Next')",
            "input[type='submit'][value='Next']",
            ".btn-next",
        ]

        for selector in next_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    self.wait_for_page_load()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Greenhouse next selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        if "confirmation" in self.page.url or "thank" in self.page.url:
            if self.logger:
                self.logger.info(
                    "Reached Greenhouse confirmation page",
                    phase=ExecutionPhase.RULES,
                )
            return False

        return False
