"""Workday ATS handler."""

import os
import re
from typing import Any, Optional, Union

from jobcli.profile.derived_profile import (
    composite_location_string,
    experience_narrative_for_forms,
)
from jobcli.profile.resume_normalize import normalize_linkedin_url
from jobcli.profile.schemas import ApplicationState, ExecutionPhase, ResumeData
from playwright.sync_api import Frame, Page

from jobcli.ats.handlers.generic_handler import GenericATSHandler
from jobcli.ats.locators.form_fields import FormFieldLocator, FormFiller


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

    def _workday_autofill_settle(self) -> None:
        """Give Workday time to parse a resume and populate the form after Autofill.

        Workday's PDF parser is slow — wait long enough for it to run and
        populate fields before the rules-based fill pass runs on top.
        """
        try:
            # Primary wait: up to 8 s for Workday's parser to populate fields.
            self.page.wait_for_timeout(8000)
        except Exception:
            pass
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=25000)
        except Exception:
            pass

    def _try_click_autofill_with_resume_in_modal(self, resume_path: Optional[str] = None) -> bool:
        """Click **Autofill with resume** and attach the PDF if Workday opens a file-chooser.

        Workday's "Autofill with Resume" button opens a file-chooser dialog so
        the PDF can be sent to Workday's own parser.  Previously the code just
        clicked the button and returned, so no file was ever selected — the
        parser never ran, and the form was left blank.

        Fix: wrap the click in Playwright's ``expect_file_chooser`` context
        so the PDF is automatically submitted.  If no file-chooser appears
        (some Workday tenants skip it when the candidate already has a resume
        on file), we fall through as before.
        """
        resume_file = resume_path or getattr(self, "resume_path_for_workday_modal", None)

        name_patterns = (
            re.compile(r"autofill.*resume", re.I),
            re.compile(r"^apply with resume$", re.I),
            re.compile(r"use.*resume.*autofill", re.I),
            re.compile(r"^import from resume$", re.I),
            re.compile(r"^fill with resume$", re.I),
        )

        def _click_and_attach(click_fn) -> bool:
            """Click via click_fn; intercept file-chooser if one appears."""
            if resume_file and os.path.isfile(resume_file):
                try:
                    with self.page.expect_file_chooser(timeout=5000) as fc_info:
                        click_fn()
                    fc_info.value.set_files(resume_file)
                    if self.logger:
                        self.logger.info(
                            "Workday: attached resume PDF to autofill file-chooser",
                            phase=ExecutionPhase.RULES,
                            path=resume_file,
                        )
                    return True
                except Exception:
                    # No file-chooser opened — fall through to plain click path.
                    pass
            # No resume file or no file-chooser: plain click already done via expect_file_chooser
            # entering, or we need to do it without the context.
            try:
                click_fn()
            except Exception:
                pass
            return True

        for name_re in name_patterns:
            try:
                loc = self.page.get_by_role("button", name=name_re).first
                if loc.is_visible(timeout=900):
                    loc.scroll_into_view_if_needed()
                    ok = _click_and_attach(lambda: loc.click(timeout=15000))
                    if self.logger:
                        self.logger.info(
                            f"Workday: clicked start-modal control matching {name_re.pattern!r} "
                            "(resume autofill)",
                            phase=ExecutionPhase.RULES,
                        )
                    return ok
            except Exception:
                continue

        for aid in (
            "autofillWithResume",
            "autofill-with-resume",
            "candidateAutofill",
            "applyWithResume",
            "autofill",
            "resumeAutofill",
        ):
            try:
                loc = self.page.locator(f"[data-automation-id='{aid}']").first
                if loc.is_visible(timeout=800):
                    ok = _click_and_attach(lambda: loc.click(timeout=15000))
                    if self.logger:
                        self.logger.info(
                            f"Workday: clicked data-automation-id='{aid}' (resume autofill entry)",
                            phase=ExecutionPhase.RULES,
                        )
                    return ok
            except Exception:
                continue

        try:
            scoped = self.page.locator("[role='dialog']").filter(
                has_text=re.compile(r"start your application|apply", re.I)
            )
            for name_re in name_patterns:
                try:
                    b = scoped.get_by_role("button", name=name_re).first
                    if b.is_visible(timeout=600):
                        ok = _click_and_attach(lambda: b.click(timeout=15000))
                        if self.logger:
                            self.logger.info(
                                "Workday: autofill in scoped dialog (resume path)",
                                phase=ExecutionPhase.RULES,
                            )
                        return ok
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _try_click_apply_manually_in_modal(self) -> bool:
        """Click **Apply Manually** and wait for the form to load (blank start)."""
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
        return False

    def _proceed_past_start_application_modal(
        self, resume_path: Optional[str] = None
    ) -> bool:
        """Clear Workday's post-Apply **Start your application** layer.

        When ``resume_path`` points to a real file, we **prefer** *Autofill with
        resume* so Workday's parser can populate fields; :meth:`fill_form` then
        merges and corrects from the structured profile JSON. If that button
        is missing, we use **Apply Manually** and rely on the upload + fill path.

        If no resume file is available, we keep the previous order: **Apply
        Manually** first, with autofill as a last-resort click.
        """
        from jobcli.ats.locators.overlay_dismiss import (
            blocking_modal_dialog_visible,
            dismiss_blocking_overlays,
        )

        try:
            self.page.wait_for_timeout(800)
        except Exception:
            pass

        if not self._start_application_modal_visible():
            return False

        prefer_autofill = bool(resume_path and str(resume_path).strip() and os.path.isfile(resume_path))
        aria_modal = blocking_modal_dialog_visible(self.page, timeout_ms=400)
        if self.logger:
            self.logger.info(
                "Blocking in-page modal detected (Workday application entry). "
                f"Resolving dialog — prefer_resume_autofill={prefer_autofill}.",
                phase=ExecutionPhase.RULES,
                aria_modal_dialog=aria_modal,
            )

        dismiss_blocking_overlays(self.page, self.logger, phase=ExecutionPhase.RULES)

        if prefer_autofill and self._try_click_autofill_with_resume_in_modal(resume_path=resume_path):
            self._workday_autofill_settle()
            if not self._start_application_modal_visible():
                return True
            if self.logger:
                self.logger.info(
                    "Autofill was clicked; modal may still be visible (upload may be required) — "
                    "continuing to Apply Manually or upload in fill_form.",
                    phase=ExecutionPhase.RULES,
                )

        if self._try_click_apply_manually_in_modal():
            return True

        if not prefer_autofill and self._try_click_autofill_with_resume_in_modal(resume_path=resume_path):
            self._workday_autofill_settle()
            if self.logger:
                self.logger.info(
                    "Workday: used Autofill with resume as secondary option (no local resume path)",
                    phase=ExecutionPhase.RULES,
                )
            return True

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
                            "Clicked 'Autofill with Resume' in Workday start modal (last resort)",
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
                    rpf = getattr(self, "resume_path_for_workday_modal", None)
                    self._proceed_past_start_application_modal(rpf)
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
            rpf = getattr(self, "resume_path_for_workday_modal", None)
            self._proceed_past_start_application_modal(rpf)
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
        """Fill Workday application form.

        If the **Start your application** dialog was already cleared via
        *Autofill with resume* at Apply time, the page may have partial
        data from Workday's PDF parser. This pass **merges** your
        structured :class:`ResumeData` (JSON) on top — filling empties
        and aligning name, contact, experience, and education to your
        source of truth. Upload + rules run even when autofill was used
        (some fields still need correction).
        """
        if self.logger:
            self.logger.info("Filling Workday form (merge profile JSON on top of any autofill)", phase=ExecutionPhase.RULES)

        rpf = resume_path or getattr(self, "resume_path_for_workday_modal", None)
        # Apply may have been triggered by LLM / generic path; clear entry modal if it reappears.
        self._proceed_past_start_application_modal(rpf)

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

        # Single-field "Location" (city, state, country) — many Workday
        # flows use a typeahead instead of separate address line fields.
        loc_composite = composite_location_string(self.resume)
        if loc_composite:
            for loc_key, loc_aid in (
                ("location_composite", "location"),
                ("location_composite", "workLocation"),
                ("location_composite", "searchLocation"),
                ("location_composite", "geolocation"),
                ("location_composite", "locationSearch"),
                ("location_composite", "locationGroup"),
            ):
                if self._fill_workday_input(loc_key, loc_aid, loc_composite):
                    results["location"] = True
                    break
                if self._fill_workday_dropdown(loc_key, loc_aid, loc_composite):
                    results["location"] = True
                    break
            if not results.get("location"):
                for root in self._workday_fill_roots():
                    try:
                        le = root.get_by_label(
                            re.compile(
                                r"^location$|^search\s*location$|where\s*are\s*you",
                                re.I,
                            )
                        ).last
                        if le.is_visible(timeout=600):
                            self.humanized_fill(le, loc_composite)
                            results["location"] = True
                            break
                    except Exception:
                        continue

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

        # Work history / education / certs — Workday "My Experience" step
        # shows only subsection titles (Work Experience, Education,
        # Certifications) and a separate [Add] per block. We must click
        # that Add before *each* row; see _workday_click_add_for_subsection.
        self._fill_workday_all_experience_rows(results)
        self._fill_workday_all_education_rows(results)
        self._fill_workday_all_certification_rows(results)

        # Generic fallback for anything that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Workday form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _workday_try_click_add_in_experience_section(self) -> bool:
        """Best-effort: [Add] in the data-automation-id work experience block (legacy UIs)."""
        for root in self._workday_fill_roots():
            try:
                section = root.locator(
                    "[data-automation-id*='workExperience'], "
                    "[data-automation-id*='WorkExperience'], "
                    "[data-automation-id*='Experience-']"
                ).first
                if not section.is_visible(timeout=800):
                    continue
                add = section.get_by_role("button", name=re.compile(r"^\+?\s*add\s*$", re.I)).first
                if add.is_visible(timeout=600):
                    add.click(timeout=5000)
                    self.page.wait_for_timeout(700)
                    if self.logger:
                        self.logger.info(
                            "Clicked Add in Workday work experience (automation-id) section",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
            except Exception:
                continue
        return False

    def _workday_click_add_for_subsection(
        self,
        heading_re: re.Pattern,
        log_label: str = "",
    ) -> bool:
        """Click the [Add] that belongs to a *named* block (e.g. Work Experience).

        The wizard step is often "My Experience", but the subsection title
        is the distinct string "Work Experience" with its own Add. We
        must not match the step name or we scope the wrong [Add] / none.

        Strategy: find visible text for ``heading_re``, then either the
        first ``following::button`` in document order, or a button
        under a shallow ancestor, preferring a label of ``^Add$``/``+Add``.
        """
        label = log_label or (heading_re.pattern or "")

        def _is_add(t: str) -> bool:
            t = (t or "").strip()
            if not t:
                return False
            return bool(re.match(r"^\+?\s*add(\s+|$)", t, re.I)) and "address" not in t.lower()

        for root in self._workday_fill_roots():
            try:
                h = root.get_by_text(heading_re, exact=False).first
                if not h.is_visible(timeout=1200):
                    continue
            except Exception:
                continue

            # 1) Next button in tree order (common when Add sits right under the title).
            for xp in (
                "xpath=following::button[1]",
                "xpath=following::a[@role='button' or contains(@class,'button')][1]",
            ):
                try:
                    btn = h.locator(xp).first
                    if not btn.is_visible(timeout=500):
                        continue
                    t = (btn.text_content() or btn.inner_text() or "").strip()
                    if not _is_add(t):
                        continue
                    btn.scroll_into_view_if_needed()
                    btn.click(timeout=5000)
                    self.page.wait_for_timeout(800)
                    if self.logger:
                        self.logger.info(
                            f"Workday: clicked Add under {label!r} (via following axis)",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
                except Exception:
                    continue

            # 2) Walk a few div ancestors: smallest container with one Add.
            for up in (1, 2, 3, 4, 5, 6, 7, 8):
                try:
                    box = h.locator(f"xpath=ancestor::div[{up}]").first
                    if not box.is_visible(timeout=200):
                        continue
                    add = box.get_by_role(
                        "button", name=re.compile(r"^\+?\s*add\s*$", re.I)
                    ).first
                    if not add.is_visible(timeout=400):
                        add = box.locator("a[role='button']", has_text=re.compile(r"^\+?\s*add\s*$", re.I)).first
                    if add.is_visible(timeout=500):
                        add.scroll_into_view_if_needed()
                        add.click(timeout=5000)
                        self.page.wait_for_timeout(800)
                        if self.logger:
                            self.logger.info(
                                f"Workday: clicked Add under {label!r} (via ancestor {up})",
                                phase=ExecutionPhase.RULES,
                            )
                        return True
                except Exception:
                    continue

        # 3) Legacy automation-id cluster (some tenants)
        if "work" in (heading_re.pattern or "").lower() or "experience" in (
            heading_re.pattern or ""
        ).lower():
            if self._workday_try_click_add_in_experience_section():
                return True

        if self.logger:
            self.logger.warning(
                f"Workday: could not find [Add] for subsection {label!r}",
                phase=ExecutionPhase.RULES,
            )
        return False

    def _workday_experience_pairs(
        self, ex: Any, short_key_prefix: str
    ) -> list[tuple[str, str, str]]:
        """Build (results_key, automation_id, value) for one job — no description.

        Long description is filled once via :meth:`_workday_fill_experience_narrative`
        so we do not write the same paragraph into six different boxes.
        """
        pairs: list[tuple[str, str, str]] = []
        if ex.title:
            pairs.extend(
                [
                    (f"{short_key_prefix}_jobTitle", "jobTitle", ex.title),
                    (f"{short_key_prefix}_positionTitle", "positionTitle", ex.title),
                ]
            )
        if ex.company:
            pairs.extend(
                [
                    (f"{short_key_prefix}_companyName", "companyName", ex.company),
                    (f"{short_key_prefix}_company", "company", ex.company),
                ]
            )
        if ex.start_date:
            pairs.append((f"{short_key_prefix}_start", "startDate", ex.start_date))
        if getattr(ex, "current", False):
            pairs.append((f"{short_key_prefix}_end", "endDate", "Present"))
        elif ex.end_date:
            pairs.append((f"{short_key_prefix}_end", "endDate", ex.end_date))
        return pairs

    def _workday_fill_experience_narrative(
        self, pfx: str, ex: Any, results: dict[str, Any]
    ) -> None:
        """One narrative block for job description / responsibilities (resume-aware)."""
        text = experience_narrative_for_forms(self.resume, ex)
        if not (text and str(text).strip()):
            return
        for aid in (
            "jobDescription",
            "description",
            "rolesAndResponsibilities",
            "summaryText",
            "responsibility",
            "responsibilityQualifications",
            "comments",
            "highlights",
        ):
            sk = f"{pfx}_narrative_{aid}"
            if self._workday_rich_text(sk, aid, text):
                results[f"{pfx}_narrative"] = True
                return
        for pat in (
            r"Description|Responsibilit|Duties|Summary|role\s*description|Key\s*accomplishment",
        ):
            for root in self._workday_fill_roots():
                try:
                    loc = root.get_by_label(re.compile(pat, re.I)).last
                    if loc.is_visible(timeout=600):
                        self.humanized_fill(loc, text)
                        if self.logger:
                            self.logger.info(
                                f"Workday: filled {pfx!r} narrative via label {pat!r}",
                                phase=ExecutionPhase.RULES,
                            )
                        results[f"{pfx}_narrative"] = True
                        return
                except Exception:
                    continue

    def _workday_rich_text(self, short_key: str, automation_id: str, value: str) -> bool:
        """Fill input, textarea, or contenteditable under a Workday field id."""
        if self._fill_workday_input(short_key, automation_id, value):
            return True
        for root in self._workday_fill_roots():
            for tag in ("textarea", "div[contenteditable='true']"):
                for sel in (
                    f"[data-automation-id='{automation_id}'] {tag}",
                    f"[data-automation-id*='{automation_id}'] {tag}",
                ):
                    try:
                        loc = root.locator(sel).first
                        if loc.count() == 0:
                            continue
                        if not loc.is_visible(timeout=500):
                            continue
                        self.humanized_fill(loc, value)
                        if self.logger:
                            self.logger.info(
                                f"Workday: filled rich text {short_key!r} ({sel[:80]})",
                                phase=ExecutionPhase.RULES,
                            )
                        return True
                    except Exception:
                        continue
        return False

    def _fill_workday_all_experience_rows(self, results: dict[str, Any]) -> None:
        """For each job: click [Add] under **Work Experience**, then fill by automation-ids."""
        for idx, ex in enumerate(self.resume.experience or []):
            heading = re.compile(
                r"^Work Experience$|Work\s+Experience|Employment\s+History|Professional\s+Experience",
                re.I,
            )
            if not self._workday_click_add_for_subsection(heading, "Work Experience"):
                if self.logger and idx == 0:
                    self.logger.warning(
                        "Workday: [Add] for work experience not clicked; "
                        "automation-id fallbacks on next fill may all fail",
                        phase=ExecutionPhase.RULES,
                    )

            pfx = "experience" if idx == 0 else f"experience_{idx + 1}"
            for short_key, aid, val in self._workday_experience_pairs(ex, pfx):
                if not val:
                    continue
                if self._fill_workday_input(short_key, aid, val):
                    results[short_key] = True
            self._workday_fill_experience_narrative(pfx, ex, results)

    def _workday_fill_education_field(
        self,
        short_key: str,
        aid: str,
        sval: str,
        label_regexes: list[str],
    ) -> bool:
        """Degree / major are often *comboboxes* in Workday, not ``<input>``."""
        if self._fill_workday_input(short_key, aid, sval):
            return True
        if self._fill_workday_dropdown(short_key, aid, sval):
            if self.logger:
                self.logger.info(
                    f"Workday: education field {short_key!r} set via dropdown (id={aid})",
                    phase=ExecutionPhase.RULES,
                )
            return True
        for rx in label_regexes:
            for root in self._workday_fill_roots():
                try:
                    loc = root.get_by_label(re.compile(rx, re.I)).last
                    if loc.is_visible(timeout=500):
                        self.humanized_fill(loc, sval)
                        if self.logger:
                            self.logger.info(
                                f"Workday: filled {short_key!r} via label {rx!r}",
                                phase=ExecutionPhase.RULES,
                            )
                        return True
                except Exception:
                    continue
        return False

    def _fill_workday_all_education_rows(self, results: dict[str, Any]) -> None:
        """For each school: [Add] under **Education** then field labels + common automation-ids."""
        for idx, ed in enumerate(self.resume.education or []):
            hpat = re.compile(
                r"^Education$|Education\s+History|Academic\s+Background|Schooling",
                re.I,
            )
            self._workday_click_add_for_subsection(hpat, "Education")
            pfx = "education" if idx == 0 else f"education_{idx + 1}"
            school_ok = degree_ok = field_ok = gpa_ok = year_ok = False
            for short_key, aid, val, label_regexes in self._workday_education_tuples(ed, pfx):
                if val is None or (isinstance(val, str) and not str(val).strip()):
                    continue
                sval = str(val) if not isinstance(val, str) else val
                if "_school_" in short_key and school_ok:
                    continue
                if "_degree_" in short_key and degree_ok:
                    continue
                if "_field_" in short_key and field_ok:
                    continue
                if "_gpa_" in short_key and gpa_ok:
                    continue
                if "_year_" in short_key and year_ok:
                    continue
                if self._workday_fill_education_field(
                    short_key, aid, sval, list(label_regexes)
                ):
                    results[short_key] = True
                    if "_school_" in short_key:
                        school_ok = True
                    if "_degree_" in short_key:
                        degree_ok = True
                    if "_field_" in short_key:
                        field_ok = True
                    if "_gpa_" in short_key:
                        gpa_ok = True
                    if "_year_" in short_key:
                        year_ok = True

    @staticmethod
    def _workday_education_tuples(
        ed: Any, pfx: str
    ) -> list[tuple[str, str, str, list[str]]]:
        """(short_key, auto_id, value, fallback label regexes)."""
        from jobcli.ats.locators.repeating_sections import EDUCATION_FIELD_LABELS

        out: list[tuple[str, str, str, list[str]]] = []
        if ed.school:
            pats = EDUCATION_FIELD_LABELS["school"]
            for aid in ("schoolName", "school", "university", "institution"):
                out.append((f"{pfx}_school_{aid}", aid, ed.school, pats))
        if ed.degree:
            pats = EDUCATION_FIELD_LABELS["degree"]
            for aid in (
                "degree",
                "degreeName",
                "educationalDegree",
                "educational-degree",
                "academicDegree",
                "academicLevel",
                "qualification",
                "programOfStudy",
                "degreeNameVisible",
            ):
                out.append((f"{pfx}_degree_{aid}", aid, ed.degree, pats))
        if ed.field_of_study:
            pats = EDUCATION_FIELD_LABELS["field_of_study"]
            for aid in ("fieldOfStudy", "major", "majorName", "concentration"):
                out.append((f"{pfx}_field_{aid}", aid, ed.field_of_study, pats))
        if ed.gpa is not None:
            pats = EDUCATION_FIELD_LABELS.get("gpa", [r"^gpa$", r"grade"])
            for aid in ("gpa", "gradePointAverage", "cumulativeGPA"):
                out.append((f"{pfx}_gpa_{aid}", aid, str(ed.gpa), pats))
        if ed.graduation_year is not None:
            pats = EDUCATION_FIELD_LABELS["graduation_year"]
            y = str(ed.graduation_year)
            for aid in ("graduationYear", "endDate", "year", "endYear", "yearOfGraduation"):
                out.append((f"{pfx}_year_{aid}", aid, y, pats))
        return out

    def _fill_workday_all_certification_rows(self, results: dict[str, Any]) -> None:
        """For each resume certification string: [Add] under **Certification(s)** and type it.

        If ``resume.certifications`` is empty, we do **nothing** — no Add
        clicks, no text — so the generic/LLM layers are less likely to
        invent a certification that is not in the profile JSON.
        """
        raw = self.resume.certifications or []
        certs = [c.strip() for c in raw if c and str(c).strip()]
        if not certs:
            return

        for idx, c in enumerate(certs):
            hpat = re.compile(
                r"^Certification(s)?$|Certifications|Professional\s+Certification",
                re.I,
            )
            if not self._workday_click_add_for_subsection(hpat, "Certifications"):
                if self.logger:
                    self.logger.warning(
                        f"Workday: could not click Add for certification row {idx + 1}",
                        phase=ExecutionPhase.RULES,
                    )
            self.page.wait_for_timeout(800)
            filled = False
            for short_key, aid, val in [
                (f"cert_name_{idx}", "certificationName", c),
                (f"cert_name_{idx}", "certification", c),
                (f"cert_name_{idx}", "certificationDescription", c),
            ]:
                if self._fill_workday_input(short_key, aid, val):
                    results[short_key] = True
                    filled = True
                    break
            if filled:
                results[f"cert_{idx}"] = True
                continue
            for root in self._workday_fill_roots():
                for rx in (
                    r"certification\s*name",
                    r"name\s*of\s*certification",
                    r"^license(\s*name)?$",
                    r"certificate(\s*name)?",
                ):
                    try:
                        loc = root.get_by_label(re.compile(rx, re.I)).last
                        if loc.is_visible(timeout=500):
                            self.humanized_fill(loc, c)
                            results[f"cert_{idx}"] = True
                            filled = True
                            if self.logger:
                                self.logger.info(
                                    f"Workday: certification {idx + 1} via label {rx!r}",
                                    phase=ExecutionPhase.RULES,
                                )
                            break
                    except Exception:
                        continue
                if filled:
                    break

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
                    self.humanized_fill(loc, value)
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

        rpf = getattr(self, "resume_path_for_workday_modal", None)
        if self._proceed_past_start_application_modal(rpf):
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
