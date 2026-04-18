"""Workday ATS handler."""

import re
from typing import Any, Optional, Union

from jobcli.core.resume_normalize import normalize_linkedin_url
from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData
from playwright.sync_api import Frame, Page

from jobcli.locators.ats.generic_handler import GenericATSHandler
from jobcli.locators.form_fields import FormFieldLocator, FormFiller


class WorkdayHandler(GenericATSHandler):
    """Handler for Workday ATS.

    Uses hardcoded data-automation-id selectors first (Workday's stable API),
    then falls back to the generic heuristic engine for any field that fails.
    """

    # ------------------------------------------------------------------
    # Platform-specific field match (by data-automation-id — Workday pattern)
    # Ported from findPlatformSpecificMatch() in workdayStrategy.js
    # ------------------------------------------------------------------
    def find_platform_specific_match(
        self, input_selector: str, resume: ResumeData
    ) -> Optional[dict]:
        """Match Workday fields by data-automation-id attribute."""
        try:
            el = self.page.query_selector(input_selector)
            if not el:
                return None
            automation_id = (
                el.get_attribute("data-automation-id") or ""
            ).lower()
            personal = resume.personal

            mapping = {
                "legalname-first":      (personal.first_name,    95),
                "legalname-last":       (personal.last_name,     95),
                "email":                (personal.email,          95),
                "phone-number":         (personal.phone,          95),
                "address-line1":        (personal.address,        95),
                "address-city":         (personal.city,           95),
                "address-state":        (personal.state,          90),
                "address-postal-code":  (personal.zip_code,       95),
                "country":              (personal.country,        90),
            }
            for key, (value, confidence) in mapping.items():
                if key in automation_id and value:
                    return {"value": value, "confidence": confidence}
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"find_platform_specific_match error: {e}",
                    phase=ExecutionPhase.RULES,
                )
        return None

    # ------------------------------------------------------------------
    # Post-Apply modal (many tenants: "Start Your Application" → Manual / Autofill / Last)
    # ------------------------------------------------------------------
    def _start_application_modal_visible(self) -> bool:
        """Detect Workday's entry layer: visible text and/or ARIA modal dialog.

        This is not a separate browser window — it is an in-page overlay. Until it is
        cleared, automation that targets the job form will not work reliably.
        """
        try:
            if self.page.get_by_text(
                re.compile(r"start your application", re.I)
            ).first.is_visible(timeout=700):
                return True
        except Exception:
            pass
        try:
            dlg = self.page.locator("[role='dialog'][aria-modal='true']").first
            if dlg.is_visible(timeout=500):
                if dlg.get_by_text(re.compile(r"apply manually|autofill", re.I)).count():
                    return True
        except Exception:
            pass
        return False

    def _proceed_past_start_application_modal(self) -> bool:
        """If Workday shows the entry modal after Apply, pick a path (prefer Apply Manually)."""
        from jobcli.locators.overlay_dismiss import (
            blocking_modal_dialog_visible,
            dismiss_blocking_overlays,
        )

        try:
            self.page.wait_for_timeout(800)
        except Exception:
            pass

        if not self._start_application_modal_visible():
            return False

        aria_modal = blocking_modal_dialog_visible(self.page, timeout_ms=400)
        if self.logger:
            self.logger.info(
                "Blocking in-page modal detected (Workday application entry). "
                "Form automation cannot proceed until this dialog is cleared — "
                "attempting 'Apply Manually' (or Autofill fallback).",
                phase=ExecutionPhase.RULES,
                aria_modal_dialog=aria_modal,
            )

        dismiss_blocking_overlays(self.page, self.logger, phase=ExecutionPhase.RULES)

        try:
            scoped = self.page.locator("[role='dialog']").filter(
                has_text=re.compile(r"start your application", re.I)
            )
            if scoped.count() and scoped.first.is_visible(timeout=800):
                for name_re in (
                    re.compile(r"^\s*apply manually\s*$", re.I),
                    re.compile(r"apply manually", re.I),
                ):
                    try:
                        loc = scoped.get_by_role("button", name=name_re).first
                        if loc.is_visible(timeout=1200):
                            loc.click(timeout=10000)
                            self.wait_for_page_load(timeout=20000)
                            if self.logger:
                                self.logger.info(
                                    "Clicked 'Apply Manually' in Workday start modal (dialog-scoped)",
                                    phase=ExecutionPhase.RULES,
                                )
                            return True
                    except Exception:
                        continue
        except Exception:
            pass

        for name_re in (
            re.compile(r"^\s*apply manually\s*$", re.I),
            re.compile(r"apply manually", re.I),
        ):
            try:
                loc = self.page.get_by_role("button", name=name_re).first
                if loc.is_visible(timeout=1200):
                    loc.click(timeout=10000)
                    self.wait_for_page_load(timeout=20000)
                    if self.logger:
                        self.logger.info(
                            "Clicked 'Apply Manually' in Workday start modal",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
            except Exception:
                continue

        for aid in (
            "applyManually",
            "candidateApplyManually",
            "apply-manually",
        ):
            try:
                loc = self.page.locator(f"[data-automation-id='{aid}']").first
                if loc.is_visible(timeout=1000):
                    loc.click(timeout=10000)
                    self.wait_for_page_load(timeout=20000)
                    if self.logger:
                        self.logger.info(
                            f"Clicked Workday start modal control [{aid}]",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
            except Exception:
                continue

        try:
            loc = self.page.locator(
                "[role='dialog'] button:has-text('Apply Manually'), "
                "[role='dialog'] a:has-text('Apply Manually')"
            ).first
            if loc.is_visible(timeout=1500):
                loc.click(timeout=10000)
                self.wait_for_page_load(timeout=20000)
                if self.logger:
                    self.logger.info(
                        "Clicked 'Apply Manually' (dialog-scoped)",
                        phase=ExecutionPhase.RULES,
                    )
                return True
        except Exception:
            pass

        for name_re in (
            re.compile(r"autofill with resume", re.I),
            re.compile(r"apply with resume", re.I),
        ):
            try:
                loc = self.page.get_by_role("button", name=name_re).first
                if loc.is_visible(timeout=1000):
                    loc.click(timeout=15000)
                    self.wait_for_page_load(timeout=20000)
                    if self.logger:
                        self.logger.info(
                            "Clicked 'Autofill with Resume' in Workday start modal",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
            except Exception:
                continue

        if self.logger:
            still_blocked = (
                self._start_application_modal_visible()
                or blocking_modal_dialog_visible(self.page, timeout_ms=400)
            )
            self.logger.warning(
                "Workday start-application modal still present or could not be cleared; "
                "the page may still block normal clicks (pointer interception on overlays).",
                phase=ExecutionPhase.RULES,
                modal_still_visible=still_blocked,
            )
        return False

    # ------------------------------------------------------------------
    # Workday apply UI lives in iframes — scanning only `page` misses all fields
    # ------------------------------------------------------------------
    def _workday_child_frames(self) -> list[Frame]:
        frames: list[Frame] = []
        for frame in self.page.frames:
            try:
                if frame == self.page.main_frame:
                    continue
                u = (frame.url or "").lower()
                if any(
                    p in u
                    for p in (
                        "myworkdayjobs.com",
                        "workday.com",
                        "wd1.",
                        "wd2.",
                        "wd3.",
                        "wd5.",
                        "wd12.",
                        "dwp",
                        "ulrsrc",
                    )
                ):
                    frames.append(frame)
            except Exception:
                continue
        return frames

    def _workday_fill_roots(self) -> list[Union[Page, Frame]]:
        return [self.page, *self._workday_child_frames()]

    def _workday_primary_root(self) -> Union[Page, Frame]:
        best: Optional[Frame] = None
        best_n = 0
        for fr in self._workday_child_frames():
            try:
                n = fr.locator("[data-automation-id]").count()
                if n > best_n:
                    best_n = n
                    best = fr
            except Exception:
                continue
        if best is not None and best_n >= 2:
            if self.logger:
                self.logger.debug(
                    "Using Workday iframe for field operations",
                    phase=ExecutionPhase.RULES,
                    frame_url=(best.url or "")[:160],
                    automation_id_nodes=best_n,
                )
            return best
        return self.page

    def _get_filler(self) -> FormFiller:
        return FormFiller(self._workday_primary_root(), self.resume, self.logger)

    # ------------------------------------------------------------------
    # Apply button
    # ------------------------------------------------------------------
    def find_apply_button(self) -> bool:
        """Find and click Workday apply button."""
        if self.logger:
            self.logger.info(
                "Looking for Workday apply button", phase=ExecutionPhase.RULES
            )

        selectors = [
            "[data-automation-id='applyNowButton']",
            "[data-automation-id='applyManually']",
            "[data-automation-id='applyButton']",
            "button:has-text('Apply')",
            "a:has-text('Apply Manually')",
            ".css-apply-button",
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click(timeout=3000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Workday apply button",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    self.wait_for_page_load(timeout=10000)
                    self._proceed_past_start_application_modal()
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday apply selector failed '{selector}': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                continue

        parent_ok = super().find_apply_button()
        if parent_ok:
            self._proceed_past_start_application_modal()
        return parent_ok

    # ------------------------------------------------------------------
    # Field detection
    # ------------------------------------------------------------------
    def detect_form_fields(self) -> list[str]:
        """Detect Workday form fields via data-automation-id."""
        automation_ids = [
            "firstName", "lastName", "email", "phone",
            "addressLine1", "city", "state", "zipCode", "country",
        ]
        detected = []
        for field_id in automation_ids:
            try:
                if self.page.query_selector(f"[data-automation-id='{field_id}']"):
                    detected.append(field_id)
            except Exception:
                continue
        return detected

    # ------------------------------------------------------------------
    # Form fill — platform-specific selectors + generic fallback
    # ------------------------------------------------------------------
    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill Workday application form."""
        if self.logger:
            self.logger.info("Filling Workday form", phase=ExecutionPhase.RULES)

        # Apply may have been triggered by LLM / generic path; clear entry modal first.
        self._proceed_past_start_application_modal()

        results: dict[str, bool] = {}
        personal = self.resume.personal

        # Text/input fields — Workday wraps inputs in a container with automation-id
        field_mapping: list[tuple[str, str, Optional[str]]] = [
            ("first_name", "firstName",    personal.first_name),
            ("last_name",  "lastName",     personal.last_name),
            ("email",      "email",        personal.email),
            ("phone",      "phone",        personal.phone),
            ("address",    "addressLine1", personal.address),
            ("city",       "city",         personal.city),
            ("zip_code",   "zipCode",      personal.zip_code),
        ]

        for short_key, automation_id, value in field_mapping:
            if not value:
                continue
            results[short_key] = self._fill_workday_input(
                short_key, automation_id, value
            )

        # State — often a dropdown in Workday
        if personal.state:
            results["state"] = self._fill_workday_dropdown(
                "state", "state", personal.state
            )

        # Country — dropdown
        if personal.country:
            results["country"] = self._fill_workday_dropdown(
                "country", "country", personal.country
            )

        # LinkedIn URL (Workday validates URL shape; skip invalid / partial values)
        li_url = normalize_linkedin_url(personal.linkedin)
        if li_url:
            try:
                self.page.fill(
                    "input[data-automation-id='linkedInURL']",
                    li_url,
                    timeout=3000,
                )
                results["linkedin"] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday fill failed for 'linkedin': {e}",
                        phase=ExecutionPhase.RULES,
                    )
                results["linkedin"] = False

        # Resume upload
        if resume_path:
            results["resume"] = self._upload_resume_workday(resume_path)

        # Work history (rules): first résumé job — Workday uses repeatable sections + Add
        self._fill_workday_experience_first_entry(results)

        # Generic fallback for anything that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Workday form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _workday_try_click_add_in_experience_section(self) -> None:
        """Reveal first work-history row when the section is empty (Workday 'Add' pattern)."""
        for root in self._workday_fill_roots():
            try:
                section = root.locator(
                    "[data-automation-id*='workExperience'], "
                    "[data-automation-id*='WorkExperience'], "
                    "[data-automation-id*='Experience-']"
                ).first
                if not section.is_visible(timeout=800):
                    continue
                add = section.get_by_role("button", name=re.compile(r"^add$", re.I)).first
                if add.is_visible(timeout=600):
                    add.click(timeout=5000)
                    self.page.wait_for_timeout(700)
                    if self.logger:
                        self.logger.info(
                            "Clicked Add in Workday work experience section",
                            phase=ExecutionPhase.RULES,
                        )
                    return
            except Exception:
                continue

    def _fill_workday_experience_first_entry(self, results: dict[str, Any]) -> None:
        """Fill the first job from ``resume.experience`` using common Workday automation-ids."""
        if not self.resume.experience:
            return
        ex = self.resume.experience[0]

        # Headings vary by tenant ("Work Experience", "My Experience", …)
        for root in self._workday_fill_roots():
            try:
                if root.get_by_text(
                    re.compile(r"work experience|my experience|employment history", re.I)
                ).first.is_visible(timeout=800):
                    self._workday_try_click_add_in_experience_section()
                    break
            except Exception:
                continue

        # Common Workday candidate-field ids (first row / single row)
        pairs: list[tuple[str, str, str]] = []
        if ex.title:
            pairs.extend(
                [
                    ("experience_jobTitle", "jobTitle", ex.title),
                    ("experience_positionTitle", "positionTitle", ex.title),
                ]
            )
        if ex.company:
            pairs.extend(
                [
                    ("experience_companyName", "companyName", ex.company),
                    ("experience_company", "company", ex.company),
                ]
            )
        if ex.start_date:
            pairs.append(("experience_start", "startDate", ex.start_date))
        if ex.end_date:
            pairs.append(("experience_end", "endDate", ex.end_date))
        if ex.description:
            desc = (ex.description or "").strip()[:8000]
            if desc:
                pairs.extend(
                    [
                        ("experience_jobDescription", "jobDescription", desc),
                        ("experience_description", "description", desc),
                        ("experience_roles", "rolesAndResponsibilities", desc),
                    ]
                )

        for short_key, aid, val in pairs:
            if not val:
                continue
            if self._fill_workday_input(short_key, aid, val):
                results[short_key] = True

    def _fill_workday_input(
        self, short_key: str, automation_id: str, value: str
    ) -> bool:
        """Fill a Workday control by data-automation-id (exact or suffix; page + iframes)."""
        selectors = [
            f"[data-automation-id='{automation_id}'] input",
            f"input[data-automation-id='{automation_id}']",
            f"[data-automation-id='{automation_id}'] textarea",
            f"textarea[data-automation-id='{automation_id}']",
            f"[data-automation-id*='{automation_id}'] input",
            f"input[data-automation-id*='{automation_id}']",
            f"[data-automation-id*='-{automation_id}'] input",
            f"[data-automation-id*='-{automation_id}'] textarea",
        ]
        for root in self._workday_fill_roots():
            for selector in selectors:
                try:
                    loc = root.locator(selector).first
                    if loc.count() == 0:
                        continue
                    if not loc.is_visible(timeout=900):
                        continue
                    loc.fill(value, timeout=5000)
                    if self.logger:
                        self.logger.info(
                            f"Filled Workday '{short_key}'",
                            phase=ExecutionPhase.RULES,
                            selector=selector[:120],
                        )
                    return True
                except Exception:
                    continue

        if self.logger:
            self.logger.warning(
                f"Workday input not found for '{short_key}' "
                f"(automation-id='{automation_id}')",
                phase=ExecutionPhase.RULES,
            )
        return False

    def _fill_workday_dropdown(
        self, short_key: str, automation_id: str, value: str
    ) -> bool:
        """Fill a Workday dropdown (combobox / listbox) using fuzzy matching."""
        root = self._workday_primary_root()
        field_locator = FormFieldLocator(root, self.logger)

        for sel_template in (
            f"select[data-automation-id='{automation_id}']",
            f"select[data-automation-id*='{automation_id}']",
        ):
            try:
                if root.query_selector(sel_template):
                    if field_locator.fill_select_fuzzy(sel_template, value):
                        return True
            except Exception:
                continue

        for trig in (
            f"[data-automation-id='{automation_id}']",
            f"[data-automation-id*='{automation_id}']",
        ):
            try:
                trigger = root.query_selector(trig)
                if trigger and trigger.is_visible():
                    trigger.click(timeout=3000)
                    self.page.keyboard.type(value)
                    root.wait_for_selector(
                        f"{trig} [role='option']",
                        timeout=3000,
                    )
                    option = root.query_selector(f"{trig} [role='option']")
                    if option:
                        option.click()
                        if self.logger:
                            self.logger.info(
                                f"Filled Workday dropdown '{short_key}': '{value}'",
                                phase=ExecutionPhase.RULES,
                            )
                        return True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Workday dropdown fill failed for '{short_key}': {e}",
                        phase=ExecutionPhase.RULES,
                    )

        return False

    def _upload_resume_workday(self, resume_path: str) -> bool:
        """Upload resume in Workday."""
        upload_selectors = [
            "[data-automation-id='file-upload-input']",
            "input[type='file']",
            "[data-automation-id*='file-upload']",
            "[data-automation-id='Upload Resume']",
        ]

        for root in self._workday_fill_roots():
            for selector in upload_selectors:
                try:
                    loc = root.locator(selector).first
                    if loc.count() == 0:
                        continue
                    loc.set_input_files(resume_path, timeout=8000)
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(
                            "Uploaded resume to Workday",
                            phase=ExecutionPhase.RULES,
                            selector=selector,
                        )
                    return True
                except Exception as e:
                    if self.logger:
                        self.logger.debug(
                            f"Workday resume upload try failed: {selector}: {e}",
                            phase=ExecutionPhase.RULES,
                        )
                    continue

        if self.logger:
            self.logger.warning(
                "Workday resume upload failed in all roots",
                phase=ExecutionPhase.RULES,
            )
        return False

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_application(self) -> bool:
        """Submit Workday application."""
        if self.logger:
            self.logger.info(
                "Submitting Workday application", phase=ExecutionPhase.RULES
            )

        submit_selectors = [
            "[data-automation-id='bottom-navigation-next-button']",
            "[data-automation-id*='bottom-navigation-next']",
            "[data-automation-id='submitButton']",
            "[data-automation-id*='submitButton']",
            "button:has-text('Submit')",
        ]

        for root in self._workday_fill_roots():
            for selector in submit_selectors:
                try:
                    loc = root.locator(selector).first
                    if loc.count() and loc.is_visible(timeout=1200) and not loc.is_disabled():
                        loc.click(timeout=5000)
                        if self.logger:
                            self.logger.info(
                                "Clicked Workday submit/next",
                                phase=ExecutionPhase.RULES,
                                selector=selector[:100],
                            )
                        self.wait_for_page_load(timeout=10000)
                        return True
                except Exception as e:
                    if self.logger:
                        self.logger.debug(
                            f"Workday submit try failed: {selector}: {e}",
                            phase=ExecutionPhase.RULES,
                        )
                    continue
            try:
                btn = root.get_by_role(
                    "button", name=re.compile(r"save and continue", re.I)
                ).first
                if btn.is_visible(timeout=1000) and not btn.is_disabled():
                    btn.click(timeout=5000)
                    if self.logger:
                        self.logger.info(
                            "Clicked Workday 'Save and Continue'",
                            phase=ExecutionPhase.RULES,
                        )
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception:
                pass

        return super().submit_application()

    # ------------------------------------------------------------------
    # Multi-step
    # ------------------------------------------------------------------
    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle Workday multi-step flow."""
        if self.logger:
            self.logger.info(
                f"Handling Workday step {state.step_count}",
                phase=ExecutionPhase.RULES,
            )

        if self._proceed_past_start_application_modal():
            return True

        for root in self._workday_fill_roots():
            for next_sel in (
                "[data-automation-id='bottom-navigation-next-button']",
                "[data-automation-id*='bottom-navigation-next']",
            ):
                try:
                    loc = root.locator(next_sel).first
                    if (
                        loc.count()
                        and loc.is_visible(timeout=1000)
                        and not loc.is_disabled()
                    ):
                        loc.click(timeout=5000)
                        self.wait_for_page_load(timeout=10000)
                        return True
                except Exception as e:
                    if self.logger:
                        self.logger.debug(
                            f"Workday Next try: {next_sel}: {e}",
                            phase=ExecutionPhase.RULES,
                        )
                    continue
            try:
                save = root.get_by_role(
                    "button", name=re.compile(r"save and continue", re.I)
                ).first
                if save.is_visible(timeout=800) and not save.is_disabled():
                    save.click(timeout=5000)
                    self.wait_for_page_load(timeout=10000)
                    return True
            except Exception:
                pass

        # Review page indicators
        review_indicators = [
            "[data-automation-id='review-section']",
            "text=Review and Submit",
            "text=Review Your Application",
        ]
        for indicator in review_indicators:
            for root in self._workday_fill_roots():
                try:
                    if root.query_selector(indicator):
                        if self.logger:
                            self.logger.info(
                                "Reached Workday review page",
                                phase=ExecutionPhase.RULES,
                            )
                        return False
                except Exception as e:
                    if self.logger:
                        self.logger.warning(
                            f"Workday review indicator check failed '{indicator}': {e}",
                            phase=ExecutionPhase.RULES,
                        )

        url_lower = self.page.url.lower()
        if "confirmation" in url_lower or "thank" in url_lower:
            if self.logger:
                self.logger.info(
                    "Reached Workday confirmation page", phase=ExecutionPhase.RULES
                )
            return False

        return True
