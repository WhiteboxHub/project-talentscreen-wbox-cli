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

    def click_option(self, question: str, value: str) -> Optional[bool]:
        """Ashby radio / checkbox / button-segment click.

        Ashby uses two distinct DOM patterns for single-choice questions:

        1. **Standard radios**: ``<fieldset><legend>Q?</legend>
           <label><input type="radio" value="Yes"/>Yes</label>...</fieldset>``
           Common for compliance, EEO, demographics.

        2. **Button-segmented control**: two (or more) ``<button>`` elements
           side-by-side inside a question container, e.g. for the
           "Are you eligible for a U.S Security Clearance?" Yes/No pair.
           These have no ``<input>`` backing — just styled buttons with
           visible text "Yes" / "No" and ``aria-pressed`` / ``aria-checked``
           to reflect state.

        We try #1 first (most common), then #2. Returns True on success,
        False if Ashby-specific DOM is detected but no option matched,
        None if nothing Ashby-like was found (so the caller falls through
        to the generic pipeline).
        """
        question = (question or "").strip()
        value = (value or "").strip()
        if not question or not value:
            return None
        try:
            js = r"""(args) => {
                const q = (args.q || '').toLowerCase().replace(/\s+/g, ' ').trim();
                const v = (args.v || '').toLowerCase().replace(/\s+/g, ' ').trim();
                if (!q || !v) return {ok: false, reason: 'empty'};
                const qTokens = q.split(/\s+/).filter(t => t.length >= 3);
                const matchesQuestion = (text) => {
                    const n = (text || '').toLowerCase().replace(/\s+/g, ' ').trim();
                    if (!n) return 0;
                    if (n === q) return 3;
                    if (n.includes(q)) return 2;
                    return qTokens.length && qTokens.every(t => n.includes(t)) ? 1 : 0;
                };
                const matchesValue = (el) => {
                    const attrVal = (el.getAttribute('value') || '').toLowerCase().trim();
                    if (attrVal === v) return 3;
                    const labels = [];
                    if (el.id) {
                        document.querySelectorAll('label[for="' + CSS.escape(el.id) + '"]')
                            .forEach(l => labels.push(l.textContent));
                    }
                    const wrap = el.closest('label');
                    if (wrap) labels.push(wrap.textContent);
                    const aria = el.getAttribute('aria-label');
                    if (aria) labels.push(aria);
                    for (const t of labels) {
                        const n = (t || '').toLowerCase().trim();
                        if (n === v) return 2;
                        if (n.includes(v) && v.length >= 2) return 1;
                    }
                    return attrVal && attrVal.includes(v) ? 1 : 0;
                };
                // ── Pass 1: native radio / checkbox inside a fieldset ──
                const fieldsets = [...document.querySelectorAll(
                    'fieldset, [role="radiogroup"], [role="group"]'
                )];
                let best = null;
                let bestScore = 0;
                for (const fs of fieldsets) {
                    let qScore = 0;
                    const legend = fs.querySelector(
                        ':scope > legend, :scope > label, :scope > .ashby-application-form-question-title'
                    );
                    if (legend) qScore = Math.max(qScore, matchesQuestion(legend.textContent));
                    const aria = fs.getAttribute('aria-label');
                    if (aria) qScore = Math.max(qScore, matchesQuestion(aria));
                    const lby = fs.getAttribute('aria-labelledby');
                    if (lby) {
                        const t = lby.split(/\s+/).map(id =>
                            document.getElementById(id)?.textContent || ''
                        ).join(' ');
                        qScore = Math.max(qScore, matchesQuestion(t));
                    }
                    if (qScore === 0) continue;
                    const inputs = fs.querySelectorAll('input[type="radio"], input[type="checkbox"]');
                    for (const inp of inputs) {
                        const vScore = matchesValue(inp);
                        if (vScore === 0) continue;
                        const total = qScore * 10 + vScore;
                        if (total > bestScore) { best = inp; bestScore = total; }
                    }
                }
                if (best) {
                    try { best.scrollIntoView({block: 'center'}); } catch (e) {}
                    const isOn = () => best.checked === true ||
                        best.getAttribute('aria-checked') === 'true';
                    if (!isOn()) { try { best.click(); } catch (e) {} }
                    if (!isOn()) {
                        const lab = best.closest('label') ||
                            (best.id && document.querySelector('label[for="' + CSS.escape(best.id) + '"]'));
                        if (lab) { try { lab.click(); } catch (e) {} }
                    }
                    if (!isOn()) {
                        const setter = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype, 'checked'
                        )?.set;
                        if (setter) setter.call(best, true); else best.checked = true;
                        best.dispatchEvent(new Event('input', {bubbles: true}));
                        best.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                    return {ok: isOn(), score: bestScore, mode: 'radio'};
                }

                // ── Pass 2: button-segmented control (e.g. Yes / No buttons) ──
                // Ashby renders some Yes/No questions as two styled <button>s
                // rather than radios. Locate the question container by its
                // visible title/label, then find the child button whose
                // accessible text matches the value.
                const matchesButtonText = (txt) => {
                    const n = (txt || '').toLowerCase().replace(/\s+/g, ' ').trim();
                    if (!n) return 0;
                    if (n === v) return 3;
                    if (n === v.replace(/[^a-z0-9]/g, '')) return 3;
                    if (n.includes(v)) return 2;
                    return 0;
                };
                // Ashby's question rows all have this wrapper class;
                // also accept generic form-row-ish wrappers.
                const rowSelectors = [
                    '.ashby-application-form-field-entry',
                    '.ashby-application-form-question',
                    '[class*="ashby-application-form"]',
                    '[class*="form-field"]',
                    '[class*="field-entry"]',
                    'label',
                    'div'
                ];
                // Find candidate title nodes whose text matches the question.
                const titleCandidates = [...document.querySelectorAll(
                    'label, legend, [class*="question-title"], [class*="field-label"], ' +
                    '[class*="FieldLabel"], [class*="field_label"], strong, h3, h4'
                )];
                let buttonBest = null;
                let buttonBestScore = 0;
                for (const titleEl of titleCandidates) {
                    const qScore = matchesQuestion(titleEl.textContent);
                    if (qScore === 0) continue;
                    // Walk up to find the nearest container that also
                    // contains clickable buttons.
                    let container = titleEl;
                    for (let i = 0; i < 6 && container; i++) {
                        const btns = container.querySelectorAll(
                            'button, [role="button"], [role="radio"], [role="switch"]'
                        );
                        if (btns.length > 0) {
                            for (const b of btns) {
                                if (b === titleEl) continue;
                                const txt = (b.innerText || b.textContent || '').trim();
                                const aria = b.getAttribute('aria-label') || '';
                                const vScore = Math.max(
                                    matchesButtonText(txt),
                                    matchesButtonText(aria),
                                );
                                if (vScore === 0) continue;
                                const total = qScore * 10 + vScore;
                                if (total > buttonBestScore) {
                                    buttonBest = b;
                                    buttonBestScore = total;
                                }
                            }
                            if (buttonBest) break;
                        }
                        container = container.parentElement;
                    }
                    if (buttonBest) break;
                }
                if (buttonBest) {
                    try { buttonBest.scrollIntoView({block: 'center'}); } catch (e) {}
                    const wasPressed = () => (
                        buttonBest.getAttribute('aria-pressed') === 'true' ||
                        buttonBest.getAttribute('aria-checked') === 'true' ||
                        buttonBest.getAttribute('data-state') === 'on' ||
                        buttonBest.classList.contains('selected') ||
                        buttonBest.classList.contains('active') ||
                        buttonBest.classList.contains('is-selected')
                    );
                    try { buttonBest.click(); } catch (e) {}
                    // Some Ashby buttons swallow plain .click() and only
                    // react to PointerEvent sequences — try that as a
                    // second attempt before giving up.
                    if (!wasPressed()) {
                        try {
                            const fire = (type) => buttonBest.dispatchEvent(
                                new PointerEvent(type, {bubbles: true, cancelable: true})
                            );
                            fire('pointerdown');
                            fire('pointerup');
                            fire('click');
                        } catch (e) {}
                    }
                    return {
                        ok: true, // we issued a click on the right button
                        score: buttonBestScore,
                        mode: 'button',
                        confirmed: wasPressed(),
                    };
                }
                return {ok: false, reason: 'no-match'};
            }"""
            for target in [self.page] + list(self.page.frames):
                try:
                    res = target.evaluate(js, {"q": question, "v": value})
                    if res and res.get("ok"):
                        if self.logger:
                            self.logger.info(
                                f"Ashby option click OK: '{question}' = '{value}' "
                                f"(mode={res.get('mode')}, "
                                f"score={res.get('score')}, "
                                f"confirmed={res.get('confirmed', True)})",
                                phase=ExecutionPhase.RULES,
                            )
                        return True
                except Exception:
                    continue
            return False
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Ashby click_option error: {e}", phase=ExecutionPhase.RULES
                )
            return False
