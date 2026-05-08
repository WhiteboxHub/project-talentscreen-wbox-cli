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
    # Field detection & Interaction overrides
    # ------------------------------------------------------------------

    def select_dropdown_option(self, field_name: str, value: str) -> Optional[bool]:
        """ATS-specific location dropdown handler for Lever (overrides generic SELECT)."""
        import re
        field_lower = field_name.lower().replace("*", "").strip()
        if "location" in field_lower or "applying" in field_lower:
            try:
                location_selects = self.page.locator("select").all()
                for sel_el in location_selects:
                    try:
                        parent_text = ""
                        try:
                            parent = sel_el.locator("xpath=ancestor::div[1]")
                            parent_text = (parent.text_content(timeout=500) or "").lower()
                        except Exception:
                            pass
                        try:
                            a_name = sel_el.evaluate("el => el.labels?.[0]?.textContent || ''")
                            parent_text += " " + (a_name or "").lower()
                        except Exception:
                            pass

                        if "location" not in parent_text and "applying" not in parent_text:
                            continue

                        options = sel_el.evaluate(
                            "el => [...el.options].map(o => ({value: o.value, text: o.textContent.trim()}))"
                        )
                        real_opts = [o for o in options if o["text"].lower() not in ("select...", "select", "", "--")]
                        if not real_opts:
                            continue

                        val_lower = value.lower()
                        best = None
                        for opt in real_opts:
                            if val_lower in opt["text"].lower() or opt["text"].lower() in val_lower:
                                best = opt
                                break
                        if not best:
                            best = real_opts[0]

                        # Check if already selected correctly
                        current_text = sel_el.evaluate("el => el.options[el.selectedIndex]?.textContent || ''").strip()
                        if current_text and value and (value.lower() in current_text.lower() or current_text.lower() in value.lower()):
                             if self.logger:
                                 self.logger.info(f"Skipping Lever select—already matches '{current_text}'", phase=ExecutionPhase.LLM)
                             return True

                        sel_el.select_option(value=best["value"], timeout=3000)
                        if self.logger:
                            self.logger.info(
                                f"Selected Lever location (via ATS override): '{best['text']}'",
                                phase=ExecutionPhase.LLM,
                            )
                        return True
                    except Exception:
                        continue
            except Exception:
                pass
        return None  # Pass through to generic tool_executor

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
        import re
        from jobcli.core.derived_profile import composite_location_string

        if self.logger:
            self.logger.info("Filling Lever form", phase=ExecutionPhase.RULES)

        results: dict[str, bool] = {}

        # ── Resume upload (Priority: First) ───────────────────────────
        if resume_path:
            try:
                self.page.set_input_files("input[name='resume']", resume_path)
                results["resume"] = True
                self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                if self.logger:
                    self.logger.info("Uploaded resume (Lever)", phase=ExecutionPhase.RULES)
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever resume upload failed: {e}", phase=ExecutionPhase.RULES
                    )
                results["resume"] = False

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
                loc = self.page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    self.humanized_fill(loc, value)
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
                    loc = self.page.locator("input[name='org']").first
                    if loc.is_visible(timeout=1000):
                        self.humanized_fill(loc, current_exp.company)
                    results["org"] = True
                except Exception as e:
                    if self.logger:
                        self.logger.warning(
                            f"Lever fill failed for 'org': {e}",
                            phase=ExecutionPhase.RULES,
                        )
                    results["org"] = False

        # ── Current location (Lever standard field via label) ──────────
        loc_composite = composite_location_string(self.resume)
        if loc_composite:
            for label_re in (
                re.compile(r"current\s+location", re.I),
                re.compile(r"^location$", re.I),
            ):
                try:
                    loc = self.page.get_by_label(label_re, exact=False).first
                    if loc.is_visible(timeout=1200):
                        self.humanized_fill(loc, loc_composite)
                        results["current_location"] = True
                        if self.logger:
                            self.logger.info(
                                "Filled Lever 'current_location' via label",
                                phase=ExecutionPhase.RULES,
                            )
                        break
                except Exception:
                    continue

        # ── Current company (also available via label on many Lever forms) ──
        if self.resume.experience:
            latest = self.resume.experience[0] if self.resume.experience else None
            company = latest.company if latest else None
            if company and not results.get("org"):
                try:
                    loc = self.page.get_by_label(
                        re.compile(r"current\s+company", re.I), exact=False
                    ).first
                    if loc.is_visible(timeout=1000):
                        self.humanized_fill(loc, company)
                        results["current_company"] = True
                except Exception:
                    pass

        # ── "Which location are you applying for?" dropdown ────────────
        # Many Lever postings have a native <select> for location choice.
        # Pick the first non-placeholder option that best matches the
        # user's city/state, or default to the first real option.
        try:
            location_selects = self.page.locator(
                "select"
            ).all()
            for sel_el in location_selects:
                try:
                    # Check if this select is the location picker by
                    # looking at the label or parent text.
                    parent_text = ""
                    try:
                        parent = sel_el.locator("xpath=ancestor::div[1]")
                        parent_text = (parent.text_content(timeout=500) or "").lower()
                    except Exception:
                        pass
                    # Also check the label via accessible name
                    try:
                        a_name = sel_el.evaluate("el => el.labels?.[0]?.textContent || ''")
                        parent_text += " " + (a_name or "").lower()
                    except Exception:
                        pass

                    if "location" not in parent_text and "applying" not in parent_text:
                        continue

                    options = sel_el.evaluate(
                        "el => [...el.options].map(o => ({value: o.value, text: o.textContent.trim()}))"
                    )
                    # Filter out placeholder options
                    real_opts = [
                        o for o in options
                        if o["text"].lower() not in ("select...", "select", "", "--")
                    ]
                    if not real_opts:
                        continue

                    # Try to match user city/state
                    user_loc = (personal.city or "").lower()
                    best = real_opts[0]  # default to first
                    for opt in real_opts:
                        if user_loc and user_loc in opt["text"].lower():
                            best = opt
                            break

                    sel_el.select_option(value=best["value"], timeout=3000)
                    results["location_dropdown"] = True
                    if self.logger:
                        self.logger.info(
                            f"Selected Lever location: '{best['text']}'",
                            phase=ExecutionPhase.RULES,
                        )
                    break
                except Exception:
                    continue
        except Exception:
            pass

        # ── Work authorization / Survey radios ──────────────────────────────────
        radio_mappings = []
        wa = getattr(self.resume, "work_authorization", None)
        if wa:
            if wa.authorized_to_work:
                radio_mappings.append(
                    (r"authorized\s+to\s+work|legally\s+authorized", "Yes")
                )
            if not wa.require_sponsorship:
                radio_mappings.append(
                    (r"need\s+visa\s+sponsorship\s+now|require\s+sponsorship\s+now", "No")
                )
                radio_mappings.append(
                    (r"need\s+visa\s+sponsorship\s+in\s+(?:the\s+)?future|future.*sponsorship", "No")
                )

        # Standard Lever compliance questions
        radio_mappings.append((r"non-compete|non\scompete|noncompete", "No"))

        if radio_mappings:
            for pattern, answer in radio_mappings:
                try:
                    question = self.page.get_by_text(
                        re.compile(pattern, re.I), exact=False
                    ).first
                    if not question.is_visible(timeout=800):
                        continue
                    # Find the radio button with the given answer
                    # under the question's parent container
                    for ancestor_level in range(1, 6):
                        try:
                            container = question.locator(
                                f"xpath=ancestor::div[{ancestor_level}]"
                            ).first
                            radio = container.get_by_label(answer, exact=True).first
                            if radio.is_visible(timeout=400):
                                radio.check(timeout=2000)
                                key = re.sub(r'\W+', '_', pattern[:30]).lower()
                                results[f"wa_{key}"] = True
                                if self.logger:
                                    self.logger.info(
                                        f"Filled Lever work auth radio: {pattern[:40]} → {answer}",
                                        phase=ExecutionPhase.RULES,
                                    )
                                break
                        except Exception:
                            continue
                except Exception:
                    continue

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
                loc = self.page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    self.humanized_fill(loc, value)
                results[field_name] = True
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever fill failed for '{field_name}': {e}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                    )
                results[field_name] = False

        # Consent checkboxes
        self._fill_consent_checkboxes(results)

        # EEO dropdowns (Gender, Race, Veteran status)
        self._fill_eeo_dropdowns(results)

        # Generic fallback for any that failed
        results = self.generic_fill_failed_fields(results, resume_path=None)

        if self.logger:
            self.logger.info(
                "Lever form fill complete",
                phase=ExecutionPhase.RULES,
                results=results,
            )
        return results

    def _fill_eeo_dropdowns(self, results: dict[str, bool]) -> None:
        """Fill EEO demographic dropdowns (Gender, Race, Veteran status)."""
        import re
        demographics = getattr(self.resume, "demographics", None)
        if not demographics:
            return

        eeo_fields = [
            ("gender", demographics.gender, r"gender|sex"),
            ("race", demographics.race, r"race|ethnicity"),
            ("veteran_status", demographics.veteran_status, r"veteran"),
        ]
        for field_key, value, regex_pattern in eeo_fields:
            if not value:
                continue
            try:
                # Remove anchor ^ and $ to match "Gender (Please supply)", "Race / Ethnicity" etc.
                label_re = re.compile(regex_pattern, re.I)
                loc = self.page.get_by_label(label_re, exact=False).first
                if not loc.is_visible(timeout=800):
                    continue
                # Native <select>: try select_option with fuzzy text match
                tag = loc.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    options = loc.evaluate(
                        "el => [...el.options].map(o => ({value: o.value, text: o.textContent.trim()}))"
                    )
                    best = None
                    val_lower = value.lower()
                    for opt in options:
                        if val_lower in opt["text"].lower() or opt["text"].lower() in val_lower:
                            best = opt
                            break
                    if best:
                        loc.select_option(value=best["value"], timeout=2000)
                        results[field_key] = True
                        if self.logger:
                            self.logger.info(
                                f"Filled Lever EEO '{field_key}' → '{best['text']}'",
                                phase=ExecutionPhase.RULES,
                            )
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Lever EEO fill failed for '{field_key}': {e}",
                        phase=ExecutionPhase.RULES,
                    )

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
