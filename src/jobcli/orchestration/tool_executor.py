"""Safe tool execution layer for browser actions."""

import json
import re
from typing import Any, Optional, List, Union

from playwright.sync_api import FrameLocator, Page

from jobcli.utils.fill_guard import (
    PLACEHOLDER_VALUES,
    read_locator_value,
    should_skip_refill,
)

# Back-compat alias for tests and internal checks.
_PLACEHOLDER_VALUES = PLACEHOLDER_VALUES
from jobcli.utils.logger import JobLogger
from jobcli.profile.schemas import (
    ATSType,
    ActionType,
    BrowserAction,
    ExecutionPhase,
    LLMActionResponse,
    SelectorType,
)

# Known ATS iframe URL patterns to look for
_ATS_IFRAME_PATTERNS = [
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "icims.com",
    "taleo.net",
    "ashby.com",
    "bamboohr.com",
    "smartrecruiters.com",
    "paylocity.com",
    "myworkdayjobs.com",
]

class ToolExecutor:
    """Execute browser actions safely with validation."""

    def __init__(
        self,
        page: Page,
        logger: Optional[JobLogger] = None,
        memory=None,
        synonym_resolver=None,
        ats_type=None,
        ats_handler=None,
    ) -> None:
        """Initialize executor."""
        self.page = page
        self.logger = logger
        self.memory = memory
        self.synonym_resolver = synonym_resolver
        self.ats_type = ats_type
        # Optional ATS-specific handler. When supplied, the executor
        # will consult it FIRST for radios/checkboxes/dropdowns before
        # falling back to generic strategies. This is how we leverage
        # the site-specific DOM knowledge each handler already encodes
        # (Ashby fieldset layout, Workday combobox tricks, …).
        self.ats_handler = ats_handler
        self.last_successful_strategy = None
        self.last_dropdown_options = {}
        self._failed_actions = []
        # Track uploads that already succeeded this session so we don't
        # re-upload the same file every iteration (the LLM can't always
        # see the "file attached" indicator in the AXTree and keeps
        # proposing the UPLOAD action again).
        self._completed_uploads: set[str] = set()

    @staticmethod
    def _normalize_fill_value(value: Any) -> str:
        """Coerce ``value`` to a clean string suitable for ``.fill`` /
        ``.select_option`` / ``.type``.

        Previously referenced but never defined — every call to
        ``_execute_select`` therefore crashed with
        ``'ToolExecutor' object has no attribute '_normalize_fill_value'``.
        """
        if value is None:
            return ""
        s = str(value)
        # Strip surrounding whitespace and collapse internal runs of
        # whitespace so "  Yes   " and "Yes" match the same option.
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _question_for(action: BrowserAction) -> str:
        """Pick the best "question text" for a click/select action.

        The LLM frequently emits CLICK/SELECT actions where ``selector`` is the
        *answer* ("Yes", "No", "United States", …) and the real question lives
        in ``field_label``.  Using ``selector`` as the question then makes the
        ATS handler search for a fieldset containing "Yes", which never
        matches — producing the confusing ``AI Action: click on Yes`` errors.

        Heuristic:
        * If ``field_label`` exists AND the selector is short / identical to
          the value / a known yes-no-ish token → use ``field_label``.
        * Otherwise keep ``selector``.
        """
        sel = (action.selector or "").strip()
        lbl = (action.field_label or "").strip()
        val = (action.value or "").strip()
        if not lbl:
            return sel
        sel_low = sel.lower().rstrip("*").strip()
        val_low = val.lower()
        answer_like = {
            "yes", "no", "agree", "disagree", "true", "false",
            "accept", "decline", "i agree", "i accept",
        }
        if sel_low == val_low and val_low:
            return lbl
        if sel_low in answer_like:
            return lbl
        # Very short selector that isn't the question itself.
        if len(sel_low) <= 24 and sel_low != lbl.lower() and lbl:
            # Only override if the label is meaningfully longer (a real
            # question) — avoids clobbering short-but-valid field names
            # like "Email" that the LLM sometimes puts in both fields.
            if len(lbl) > len(sel_low) + 4:
                return lbl
        return sel

    def _get_active_content_roots(self) -> List[Union[Page, FrameLocator]]:
        """Return a list of potential content roots (main page + all matching iframes)."""
        roots: List[Union[Page, FrameLocator]] = [self.page]
        
        # Add all frames that might be the ATS form
        for frame in self.page.frames:
            try:
                url = frame.url or ""
                if any(p in url.lower() for p in _ATS_IFRAME_PATTERNS):
                    roots.append(frame.frame_locator(":root"))
            except Exception:
                continue
                
        # Also try explicitly by common iframe IDs/names
        for selector in ["iframe[id*='grnhse']", "iframe[id*='gh_']", "iframe[id*='apply']", "#grnhse_iframe"]:
            try:
                if self.page.locator(selector).count() > 0:
                    roots.append(self.page.frame_locator(selector))
            except Exception:
                continue
                
        return roots

    def _read_live_value(self, selector: str) -> Optional[str]:
        """Best-effort read of the current value of an input/textarea/select."""
        if not selector:
            return None
        try:
            return read_locator_value(self.page.locator(selector).first)
        except Exception:
            return None

    def execute_action(self, action: BrowserAction) -> bool:
        """Execute a single browser action."""
        if self.logger:
            self.logger.info(
                f"Executing {action.action.value} action",
                phase=ExecutionPhase.LLM,
                selector=action.selector,
                field_label=action.field_label,
            )

        # Guard: FILL/TYPE/SELECT without a value is never really "successful".
        # Playwright's `.fill("")` technically succeeds (it clears the field),
        # which previously hid the LLM emitting value-less actions.  Mark
        # them as failures up front so the engine routes them through
        # ``show_failed_fields`` → human-driven retry instead of silently
        # leaving the form blank.
        if action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT):
            if not (action.value and str(action.value).strip()):
                if self.logger:
                    self.logger.warning(
                        f"{action.action.value} on '{action.field_label or action.selector}' "
                        "has empty value — treating as failed so the human can provide it.",
                        phase=ExecutionPhase.LLM,
                    )
                return False

        # Last-line-of-defense skip guard. The engine already filters
        # already-filled fields out of the LLM response before they reach
        # the executor (see ``ApplicationEngine._snapshot_filled``), but
        # other phases (rules, ATS handlers, ASK-resolved retries) can
        # also call ``execute_action`` directly. Treat a field that
        # currently has a real value as already-done so no phase
        # overwrites it.
        if action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT):
            try:
                if action.selector:
                    loc = self.page.locator(action.selector).first
                    if should_skip_refill(loc, str(action.value) if action.value else None):
                        live = read_locator_value(loc) or ""
                        if self.logger:
                            self.logger.info(
                                f"[skip-refill] '{action.field_label or action.selector}' "
                                f"already has '{live}' — not overwriting.",
                                phase=ExecutionPhase.LLM,
                            )
                        return True
            except Exception:
                pass

        try:
            # Route to appropriate action handler
            if action.action == ActionType.CLICK:
                return self._execute_click(action)
            elif action.action in (ActionType.TYPE, ActionType.FILL):
                return self._execute_type(action)
            elif action.action == ActionType.SELECT:
                return self._execute_select(action)
            elif action.action == ActionType.UPLOAD:
                return self._execute_upload(action)
            elif action.action == ActionType.SCROLL:
                return self._execute_scroll(action)
            elif action.action == ActionType.WAIT:
                return self._execute_wait(action)
            else:
                if self.logger:
                    self.logger.error(f"Unknown action type: {action.action}", phase=ExecutionPhase.LLM)
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Action execution failed: {e}", phase=ExecutionPhase.LLM, action=action.action.value, selector=action.selector)
            return False

    def get_failed_actions(self) -> list[BrowserAction]:
        """Return the list of actions that failed during the last execute_actions call."""
        return getattr(self, '_failed_actions', [])

    def execute_actions(self, llm_response: LLMActionResponse) -> dict[str, bool]:
        """Execute a sequence of actions from LLM."""
        if llm_response.requires_human:
            if self.logger:
                self.logger.warning("LLM requested human intervention", phase=ExecutionPhase.LLM, reasoning=llm_response.reasoning)
            return {"requires_human": True}

        results: dict[str, bool] = {}
        self._failed_actions: list[BrowserAction] = []

        # One-time page warm-up before the first form interaction.
        # Real users spend a couple seconds scanning the page, moving
        # the mouse, scrolling, before they start typing.  Skipping
        # this is one of the strongest behavioural signals that
        # Ashby / Cloudflare Turnstile / PerimeterX latch onto.
        self._warmup_page_if_needed()

        for i, action in enumerate(llm_response.actions):
            # Navigation and uploads must never be dropped on confidence alone —
            # the LLM often under-scores a lone "Continue" / "Next" CLICK; skipping
            # it leaves the user on step 1 while the engine thinks the page is
            # complete and proceeds to submit (Workday multi-step bug).
            if action.confidence < 0.7 and action.action not in (
                ActionType.CLICK,
                ActionType.UPLOAD,
            ):
                results[f"action_{i}"] = False
                continue

            # Randomised inter-action delay so a 9-field form doesn't
            # complete in 3 seconds flat.  Upload actions already have
            # their own long wait so we don't stack another on top.
            if i > 0 and action.action != ActionType.UPLOAD:
                try:
                    import random as _r
                    self.page.wait_for_timeout(_r.randint(350, 1100))
                except Exception:
                    pass

            success = self.execute_action(action)
            results[f"action_{i}_{action.action.value}"] = success

            if not success:
                self._failed_actions.append(action)
                continue

        return results

    def _warmup_page_if_needed(self) -> None:
        """Simulate a human scanning a page before interacting with it.

        Runs at most once per ``ToolExecutor`` instance (gated by
        ``self._warmup_done``).  Mouse jitter, soft scroll, and a short
        reading pause are the three behavioural signals that bot-risk
        models weight most heavily, so we produce plausible values for
        each before the first FILL/CLICK action.  All branches swallow
        exceptions because the warm-up is best-effort — if any of it
        fails we'd rather proceed than abort the application.
        """
        if getattr(self, "_warmup_done", False):
            return
        self._warmup_done = True
        try:
            import random as _r
            vp = self.page.viewport_size or {"width": 1366, "height": 864}
            w, h = int(vp.get("width", 1366)), int(vp.get("height", 864))
            # 2-4 mouse moves at human-like step sizes.
            for _ in range(_r.randint(2, 4)):
                try:
                    x = _r.randint(int(w * 0.15), int(w * 0.85))
                    y = _r.randint(int(h * 0.15), int(h * 0.6))
                    self.page.mouse.move(x, y, steps=_r.randint(8, 18))
                    self.page.wait_for_timeout(_r.randint(90, 230))
                except Exception:
                    break
            # 1-2 soft scrolls.
            for _ in range(_r.randint(1, 2)):
                try:
                    self.page.mouse.wheel(0, _r.randint(120, 360))
                    self.page.wait_for_timeout(_r.randint(220, 520))
                except Exception:
                    break
            # Reading pause before the first interaction (800-1800ms).
            self.page.wait_for_timeout(_r.randint(800, 1800))
        except Exception:
            # Warm-up is best-effort; never block the actual fill.
            pass

    def _humanized_fill(self, locator, value: str) -> bool:
        """Fill ``locator`` with human-like keystroke cadence. Returns False if skipped."""
        from jobcli.utils.fill_guard import is_reserved_form_value

        if is_reserved_form_value(value):
            if self.logger:
                self.logger.info(
                    f"[skip-value] refusing to type reserved keyword '{value}' into field",
                    phase=ExecutionPhase.LLM,
                )
            return False
        if should_skip_refill(locator, value):
            if self.logger:
                self.logger.info(
                    "[skip-refill] field already populated — not retyping",
                    phase=ExecutionPhase.LLM,
                )
            return False
        import random as _r
        # Hover before clicking — real clicks always land after a
        # mouse-move.  Anti-bot models track mouse-path entropy, and
        # ``locator.click()`` alone synthesises a click without moving
        # the cursor, which is itself a fingerprint.  ``hover()`` runs
        # Playwright's natural ``move(steps=)`` helper internally.
        try:
            locator.hover(timeout=1500)
            self.page.wait_for_timeout(_r.randint(80, 180))
        except Exception:
            # Some elements can't be hovered (offscreen, hidden, etc.);
            # fall through to the click regardless.
            pass
        locator.click(timeout=1500)
        self.page.wait_for_timeout(_r.randint(120, 280))

        # Clear existing content with actual keyboard events.  Using a
        # keyboard shortcut leaves the same signal trail a human user
        # would (keydown/keyup pairs).  `meta` on macOS, `control` on
        # every other platform.
        import sys as _sys
        mod = "Meta" if _sys.platform == "darwin" else "Control"
        try:
            self.page.keyboard.press(f"{mod}+A")
            self.page.wait_for_timeout(_r.randint(30, 90))
            self.page.keyboard.press("Backspace")
            self.page.wait_for_timeout(_r.randint(40, 110))
        except Exception:
            # Worst case fall back to the old silent clear.
            try:
                locator.fill("")
            except Exception:
                pass

        # Type in short bursts with natural variance.  Break the value
        # into word groups and pause between them ~20% of the time to
        # mimic a human pausing to think / look at the next field.
        words = value.split(" ")
        for idx, w in enumerate(words):
            if idx > 0:
                self.page.keyboard.type(" ", delay=_r.randint(40, 120))
            # Per-character delay: 55-150ms, with a bias toward the
            # lower end for common letters so longer strings don't feel
            # artificially slow.
            per_char_delay = _r.randint(55, 150)
            self.page.keyboard.type(w, delay=per_char_delay)
            # Occasional 150-350ms "thinking" pause between words.
            if idx < len(words) - 1 and _r.random() < 0.18:
                self.page.wait_for_timeout(_r.randint(150, 350))

        # Small pause before Tab so focus/blur don't fire in the same
        # frame as the last keystroke.
        self.page.wait_for_timeout(_r.randint(90, 220))
        try:
            self.page.keyboard.press("Tab")
        except Exception:
            pass
        return True

    def _is_workday_ats(self) -> bool:
        t = self.ats_type
        if t is None:
            return False
        if t == ATSType.WORKDAY:
            return True
        if isinstance(t, str) and t.strip().lower() == "workday":
            return True
        return False

    def _click_label_variants(self, name: str) -> List[str]:
        """LLMs often say 'Continue Button' but a11y name is 'Continue' — try both."""
        raw = (name or "").strip()
        if not raw:
            return []
        stripped = re.sub(r"\s+button\s*$", "", raw, flags=re.I).strip() or raw
        out: List[str] = []
        for c in (stripped, raw):
            if c and c not in out:
                out.append(c)
        return out

    def _try_wizard_advance_click(self, action: BrowserAction, name: str) -> bool:
        """Workday/ATS wizard: bottom nav and regex button names the generic path misses."""
        n = (name or "").lower()
        nav_like = bool(
            re.search(
                r"\b(continue|next|proceed|save\s+and\s+continue|save\s*&\s*continue)\b",
                n,
            )
        )
        if not nav_like and not self._is_workday_ats():
            return False
        roots = self._get_active_content_roots()
        sels = (
            "[data-automation-id='bottom-navigation-next-button']",
            "[data-automation-id*='bottom-navigation-next']",
            "button:has-text('Save and continue')",
            "button:has-text('Save and Continue')",
        )
        for root in roots:
            for sel in sels:
                try:
                    loc = root.locator(sel).first
                    if not loc.count():
                        continue
                    if not loc.is_visible(timeout=1500):
                        continue
                    try:
                        if loc.is_disabled():
                            continue
                    except Exception:
                        pass
                    loc.highlight()
                    loc.click(timeout=action.timeout)
                    if self.logger:
                        self.logger.info(
                            f"Click wizard advance via selector: {sel!r}",
                            phase=ExecutionPhase.LLM,
                        )
                    return True
                except Exception:
                    continue
        # Loose accessible-name match (handles 'Continue' when LLM said 'Continue Button')
        try:
            nav_re = re.compile(
                r"^(continue|next|proceed|save and continue|save & continue)\s*$",
                re.I,
            )
        except Exception:
            nav_re = re.compile(r"continue|next", re.I)
        for root in roots:
            try:
                b = root.get_by_role("button", name=nav_re).first
                if b.is_visible(timeout=1200):
                    try:
                        if b.is_disabled():
                            continue
                    except Exception:
                        pass
                    b.highlight()
                    b.click(timeout=action.timeout)
                    if self.logger:
                        self.logger.info(
                            "Click wizard advance via button role (regex name)",
                            phase=ExecutionPhase.LLM,
                        )
                    return True
            except Exception:
                continue
        return False

    def _execute_click(self, action: BrowserAction) -> bool:
        # Use field_label when the raw selector is just the answer ("Yes"/"No")
        # — otherwise the ATS handler searches for a fieldset containing "Yes"
        # and never finds the right question.
        name = self._question_for(action)
        name_candidates = self._click_label_variants(name) or [name]
        
        # Add a fuzzy cleaned attempt if it contains hallucinated suffixes
        clean_name = name.lower()
        for suffix in [" button", " checkbox", " radio", " link", " dropdown"]:
            if suffix in clean_name:
                clean_name = clean_name.replace(suffix, "").strip()
        if clean_name and clean_name != name.lower() and clean_name not in [c.lower() for c in name_candidates]:
            name_candidates.append(clean_name)

        selector_type = action.selector_type

        # SAFETY: Block clicks on upload areas
        upload_keywords = ["upload", "resume", "cv", "attach", "drop or select"]
        if any(kw in name.lower() for kw in upload_keywords):
            if self.logger:
                self.logger.warning(f"Blocking click on '{name}' upload area. Use UPLOAD action instead.", phase=ExecutionPhase.LLM)
            return True

        # ──────────────────────────────────────────────────────────────
        # Radio / checkbox coercion.
        # When the LLM emits CLICK with both a question-text ``selector``
        # AND a value like "Yes"/"No"/"Agree", it's really asking us to
        # pick a specific radio option. Route through the ATS handler
        # first (Ashby / Workday / etc. know their DOM patterns), then
        # the generic SELECT path.
        # ──────────────────────────────────────────────────────────────
        if (action.value or "").strip() and selector_type not in (SelectorType.CSS, SelectorType.XPATH):
            # 1) ATS-specific option click — fastest and most reliable
            #    when we know the site.
            if self.ats_handler is not None:
                try:
                    handler_result = self.ats_handler.click_option(name, action.value)
                    if handler_result is True:
                        if self.logger:
                            self.logger.info(
                                f"Click via {type(self.ats_handler).__name__}.click_option",
                                phase=ExecutionPhase.LLM,
                            )
                        return True
                    # False = tried and failed → keep going to generic.
                    # None  = handler has no ATS-specific path → generic.
                except Exception as e:
                    if self.logger:
                        self.logger.debug(
                            f"ATS click_option raised: {e}", phase=ExecutionPhase.LLM
                        )

            # 2) Generic SELECT path (scoped-radio helper + combobox + radio-role).
            select_action = BrowserAction(
                action=ActionType.SELECT,
                selector=name,  # already resolved from field_label when needed
                selector_type=action.selector_type,
                value=action.value,
                field_label=action.field_label or name,
                confidence=action.confidence,
                timeout=action.timeout,
            )
            if self._execute_select(select_action):
                return True
            # fall through to plain click if the SELECT path failed

        roots = self._get_active_content_roots()

        # Try CSS/XPath first across all roots
        if selector_type in (SelectorType.CSS, SelectorType.XPATH):
            raw = name if selector_type == SelectorType.CSS else f"xpath={name}"
            for root in roots:
                try:
                    loc = root.locator(raw)
                    if loc.count() > 0:
                        loc.first.highlight()
                        loc.first.click(timeout=action.timeout)
                        return True
                except Exception: continue
            return False

        # Try semantic selectors across all roots
        for root in roots:
            for sem_name in name_candidates:
                attempts = [
                    (
                        "role button",
                        lambda r=root, n=sem_name: r.get_by_role(
                            "button", name=n, exact=False
                        ).first,
                    ),
                    (
                        "role link",
                        lambda r=root, n=sem_name: r.get_by_role(
                            "link", name=n, exact=False
                        ).first,
                    ),
                    (
                        "label",
                        lambda r=root, n=sem_name: r.get_by_label(
                            n, exact=False
                        ).first,
                    ),
                    (
                        "text",
                        lambda r=root, n=sem_name: r.get_by_text(
                            n, exact=False
                        ).first,
                    ),
                    (
                        "aria-labelledby",
                        lambda r=root, n=sem_name: r.locator(
                            f"[aria-labelledby*='{n}']"
                        ).first,
                    ),
                ]
                for label, get_loc in attempts:
                    try:
                        loc = get_loc()
                        if loc.is_visible(timeout=1000):
                            loc.highlight()
                            loc.click(timeout=action.timeout)
                            if self.logger:
                                self.logger.info(
                                    f"Click executed via {label} in frame (name={sem_name!r})",
                                    phase=ExecutionPhase.LLM,
                                )
                            return True
                    except Exception:
                        continue

        if self._try_wizard_advance_click(action, name):
            return True
        return False

    def _looks_like_dropdown(self, loc) -> bool:
        """Return True if the matched element is a dropdown / combobox / select.

        Generic detector — works on every ATS:
        * native ``<select>`` element
        * ARIA ``role="combobox"`` / ``"listbox"`` / ``"menu"``
        * any element with ``aria-haspopup="listbox"|"menu"|"true"``
        * any element with ``aria-autocomplete="list"|"both"`` (typeahead)
        * read-only / button-like inputs that act as dropdown triggers
          (e.g. Workday, Greenhouse Demographics)
        """
        try:
            return bool(loc.evaluate(
                """(el) => {
                    if (!el) return false;
                    const tag = (el.tagName || '').toLowerCase();
                    if (tag === 'select') return true;
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    if (['combobox','listbox','menu'].includes(role)) return true;
                    const hp = (el.getAttribute('aria-haspopup') || '').toLowerCase();
                    if (['listbox','menu','tree','dialog','true'].includes(hp)) return true;
                    const ac = (el.getAttribute('aria-autocomplete') || '').toLowerCase();
                    if (['list','both'].includes(ac)) return true;
                    // Common pattern: <button> wrapped in a [role=combobox] container
                    const parentRole = (el.closest('[role="combobox"],[role="listbox"]')?.getAttribute('role') || '').toLowerCase();
                    if (['combobox','listbox'].includes(parentRole)) return true;
                    // A "select"-shaped readonly input that opens a popup
                    if (tag === 'input') {
                        const t = (el.getAttribute('type') || 'text').toLowerCase();
                        if (t !== 'text' && t !== 'search') return false;
                        if (el.readOnly && (el.getAttribute('aria-haspopup') || el.getAttribute('aria-controls'))) return true;
                    }
                    return false;
                }"""
            ))
        except Exception:
            return False

    def _execute_type(self, action: BrowserAction) -> bool:
        if not action.value: return False
        # Strip required-field marker (*) and trailing punctuation — they
        # break label matching on sites that render "Name" in the DOM but
        # the LLM emits "Name*" (from visible text).  Mirrors the same
        # normalisation _execute_select does.
        raw_name = action.selector
        name = raw_name.rstrip("*").strip()
        # Also try a version with trailing "?" / ":" / "." removed.
        name_stripped = re.sub(r"[\s\*\?\:\.]+$", "", name).strip()
        candidate_names = [name]
        if name_stripped and name_stripped != name:
            candidate_names.append(name_stripped)
        # If no fuzz happened at all, keep the raw as-is.
        if raw_name != name:
            candidate_names.append(raw_name)
        roots = self._get_active_content_roots()

        # Build a cross-product of (root × candidate-name × strategy).
        # Using each candidate_name maximises the chance of matching when
        # the LLM emits "Name*" but the DOM label is "Name" / "name" /
        # "full_name".
        attempt_specs: list[tuple[str, callable]] = []
        for cn in candidate_names:
            # Escape single-quotes for the CSS attribute selectors.
            cn_css = cn.replace("'", "\\'")
            for root in roots:
                attempt_specs.extend([
                    (f"label[{cn!r}]",        lambda r=root, n=cn: r.get_by_label(n, exact=False).first),
                    (f"placeholder[{cn!r}]",  lambda r=root, n=cn: r.get_by_placeholder(n, exact=False).first),
                    (f"css input[{cn!r}]",    lambda r=root, n=cn_css: r.locator(f"input[name*='{n}' i]").first),
                    (f"css textarea[{cn!r}]", lambda r=root, n=cn_css: r.locator(f"textarea[name*='{n}' i]").first),
                    (f"aria-labelledby[{cn!r}]", lambda r=root, n=cn_css: r.locator(f"[aria-labelledby*='{n}']").first),
                    (f"css id[{cn!r}]",       lambda r=root, n=cn_css: r.locator(f"input[id*='{n}' i], textarea[id*='{n}' i]").first),
                    (f"css aria-label[{cn!r}]", lambda r=root, n=cn_css: r.locator(f"input[aria-label*='{n}' i], textarea[aria-label*='{n}' i]").first),
                ])

        # Single pass — first match wins.
        for label, get_loc in attempt_specs:
            try:
                loc = get_loc()
                if not loc.is_visible(timeout=1000):
                    continue
                # Last-mile dropdown guard: if the matched element is
                # actually a dropdown/combobox/select, redirect to SELECT.
                if self._looks_like_dropdown(loc):
                    if self.logger:
                        self.logger.warning(
                            f"Element for '{name}' is a dropdown — redirecting FILL to SELECT.",
                            phase=ExecutionPhase.LLM,
                        )
                    select_action = BrowserAction(
                        action=ActionType.SELECT,
                        selector=name,
                        selector_type=action.selector_type,
                        value=action.value,
                        field_label=action.field_label,
                        confidence=action.confidence,
                        timeout=action.timeout,
                    )
                    return self._execute_select(select_action)

                loc.highlight()
                try:
                    # Avoid typing if the existing value is already a
                    # reasonable match. Important for ATS forms where a
                    # resume upload triggers autofill _after_ the LLM plan.
                    try:
                        current_val = (loc.input_value() or "").strip()
                        target_val = str(action.value).strip()
                        # Allow exact matches, or substring matches only if the current value is a long string (like a URL or description)
                        # We don't want to skip "Bavish Kangari" just because the field currently has "Bavish"
                        is_match = False
                        if target_val and current_val:
                            tv_lower, cv_lower = target_val.lower(), current_val.lower()
                            if tv_lower == cv_lower:
                                is_match = True
                            elif len(cv_lower) > 15 and (tv_lower in cv_lower or cv_lower in tv_lower):
                                is_match = True
                                
                        if is_match:
                            if self.logger:
                                self.logger.info(
                                    f"Skipping fill for '{name}' — already matches '{current_val}'",
                                    phase=ExecutionPhase.LLM,
                                )
                            return True
                    except Exception:
                        pass

                    # Humanised entry path — every step mirrors what a real
                    # user does, with randomised timing so ATS spam
                    # classifiers (Ashby, Greenhouse, Cloudflare) don't
                    # flag the submission.  The common failure mode BEFORE
                    # this was: click → fill("") → press_sequentially at a
                    # fixed 35ms/char → instant Tab.  That happens in ~3s
                    # for an entire form and is indistinguishable from a
                    # bot to anyone monitoring keystroke cadence.
                    self._humanized_fill(loc, str(action.value))
                except Exception:
                    # Last resort: only synthesise events if real typing
                    # wasn't possible (e.g. the element intercepts
                    # keystrokes oddly).  Prefer this LESS because it's
                    # the easiest automation signal to detect.
                    js_code = """(el, val) => {
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                        return true;
                    }"""
                    loc.evaluate(js_code, action.value)

                if self.logger:
                    self.logger.info(f"Fill executed via {label}", phase=ExecutionPhase.LLM)
                return True
            except Exception:
                continue


        # ─────────────────────────────────────────────────────────────
        # Last resort: aggressive JS-side search across main page AND
        # every same-origin iframe.  Covers DOM patterns that Playwright's
        # ``get_by_label`` misses, which is extremely common on Ashby /
        # Greenhouse / other custom ATS forms where the label-input
        # relationship is via ``aria-labelledby``, ``data-*`` attrs, or
        # sibling DOM position instead of a ``<label for>`` pair.
        # ─────────────────────────────────────────────────────────────
        # Feed the JS every normalised variant so "Name*" / "Name" / "name"
        # all count as matches for a DOM label of "Name".
        _needles_js = json.dumps([cn.lower() for cn in candidate_names])
        _value_js = json.dumps(str(action.value))
        js_search = f"""(() => {{
            const needles = {_needles_js};
            const val = {_value_js};
            // Collect token lists per needle for fuzzy fallback matching.
            const needleTokens = needles.map(n =>
                n.split(/\\s+/).filter(t => t.length >= 2)
            );
            const scoreLabelMatch = (text) => {{
                if (!text) return 0;
                const t = text.toLowerCase();
                let best = 0;
                for (let i = 0; i < needles.length; i++) {{
                    const needle = needles[i];
                    if (!needle) continue;
                    if (t === needle) {{ best = Math.max(best, 100); continue; }}
                    if (t.includes(needle)) {{ best = Math.max(best, 60); continue; }}
                    const toks = needleTokens[i];
                    if (toks.length && toks.every(k => t.includes(k))) {{
                        best = Math.max(best, 40);
                    }}
                }}
                return best;
            }};
            const setValue = (el) => {{
                try {{
                    const proto = el.tagName.toLowerCase() === 'textarea'
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) setter.call(el, val); else el.value = val;
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    el.focus?.();
                    return true;
                }} catch (e) {{ return false; }}
            }};
            const isFillable = (el) => {{
                if (!el) return false;
                const tag = el.tagName.toLowerCase();
                if (tag !== 'input' && tag !== 'textarea') return false;
                if (tag === 'input') {{
                    const t = (el.getAttribute('type') || 'text').toLowerCase();
                    if (['checkbox','radio','file','submit','button','hidden','reset'].includes(t)) return false;
                    if (el.readOnly) return false;
                }}
                if (el.disabled) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                return true;
            }};
            const rootDocs = [document];
            document.querySelectorAll('iframe').forEach(f => {{
                try {{ if (f.contentDocument) rootDocs.push(f.contentDocument); }}
                catch (e) {{}}
            }});
            const candidates = [];
            for (const root of rootDocs) {{
                const fields = [...root.querySelectorAll('input,textarea')].filter(isFillable);
                for (const el of fields) {{
                    let bestScore = 0;
                    const bump = (s) => {{ if (s > bestScore) bestScore = s; }};
                    bump(scoreLabelMatch(el.getAttribute('aria-label')));
                    bump(scoreLabelMatch(el.getAttribute('placeholder')));
                    bump(scoreLabelMatch(el.getAttribute('name')));
                    bump(scoreLabelMatch(el.getAttribute('id')));
                    bump(scoreLabelMatch(el.getAttribute('data-qa')));
                    bump(scoreLabelMatch(el.getAttribute('data-testid')));
                    // aria-labelledby → gather referenced text
                    const lby = el.getAttribute('aria-labelledby');
                    if (lby) {{
                        const text = lby.split(/\\s+/)
                            .map(id => root.getElementById?.(id)?.textContent || '')
                            .join(' ');
                        bump(scoreLabelMatch(text));
                    }}
                    // <label for=id> pair
                    if (el.id) {{
                        const lbl = root.querySelector?.(`label[for="${{el.id}}"]`);
                        if (lbl) bump(scoreLabelMatch(lbl.textContent));
                    }}
                    // Wrapping <label>
                    const wrap = el.closest?.('label');
                    if (wrap) bump(scoreLabelMatch(wrap.textContent));
                    // Nearest ancestor label/legend (up 4 levels)
                    let cur = el.parentElement, depth = 0;
                    while (cur && depth < 4) {{
                        const nearLbl = cur.querySelector?.(':scope > label, :scope > legend, :scope > .label, :scope > [class*="label"]');
                        if (nearLbl && nearLbl !== wrap) {{
                            bump(scoreLabelMatch(nearLbl.textContent));
                            if (bestScore >= 60) break;
                        }}
                        cur = cur.parentElement; depth++;
                    }}
                    // Preceding sibling text nodes (Ashby pattern)
                    const prev = el.previousElementSibling;
                    if (prev) bump(scoreLabelMatch(prev.textContent?.slice(0, 120)));
                    if (bestScore > 0) candidates.push({{el, score: bestScore}});
                }}
            }}
            candidates.sort((a, b) => b.score - a.score);
            for (const c of candidates) {{
                if (setValue(c.el)) return c.score;
            }}
            return 0;
        }})()"""
        # Evaluate the deep JS search in EVERY frame, not just the main
        # page.  Cross-origin iframes (very common on Ashby / custom ATS
        # domains) have ``contentDocument === null`` from the parent, so
        # we must ask Playwright to hop into each frame's execution
        # context directly.
        eval_targets = [self.page] + list(self.page.frames)
        for target in eval_targets:
            try:
                score = target.evaluate(js_search)
                if score and int(score) > 0:
                    if self.logger:
                        frame_url = getattr(target, "url", "main")
                        self.logger.info(
                            f"Fill executed via deep JS search (score={score}) "
                            f"for '{name}' in frame [{frame_url}]",
                            phase=ExecutionPhase.LLM,
                        )
                    return True
            except Exception as e:
                if self.logger:
                    self.logger.debug(
                        f"Deep JS fill search in frame failed: {e}",
                        phase=ExecutionPhase.LLM,
                    )
                continue

        if self.logger:
            self.logger.warning(
                f"Could not fill '{name}' — no element matched any strategy "
                "(label/placeholder/name/aria/JS-scan).",
                phase=ExecutionPhase.LLM,
            )
        return False

    def _pick_dropdown_option(self, value: str) -> bool:
        """After a dropdown/combobox has been opened, pick the best matching option."""
        try:
            # Collect all visible options across page (handles Workday portal dropdown)
            opts = self.page.locator("[role='option'], [role='listbox'] [role='option'], li[role='option']")
            count = min(opts.count(), 50)
            if count == 0:
                return False
            # Try exact match first, then starts-with, then contains
            val_lower = value.lower()
            for strategy in ("exact", "starts", "contains"):
                for i in range(count):
                    try:
                        opt = opts.nth(i)
                        text = (opt.text_content() or "").strip().lower()
                        if strategy == "exact" and text == val_lower:
                            opt.click(timeout=2000)
                            return True
                        elif strategy == "starts" and text.startswith(val_lower):
                            opt.click(timeout=2000)
                            return True
                        elif strategy == "contains" and val_lower in text:
                            opt.click(timeout=2000)
                            return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False

    def _click_and_fill_combobox(self, loc, value: str) -> bool:
        """Click a combobox/select element, type the value, then pick the best option."""
        try:
            loc.scroll_into_view_if_needed(timeout=2000)
            loc.click(timeout=3000)
            self.page.wait_for_timeout(400)
            self.page.keyboard.type(value, delay=30)
            self.page.wait_for_timeout(600)
            if self._pick_dropdown_option(value):
                return True
            # No visible options found — try ArrowDown + Enter (works for some ATS)
            self.page.keyboard.press("ArrowDown")
            self.page.wait_for_timeout(200)
            self.page.keyboard.press("Enter")
            return True
        except Exception:
            return False

    def _select_scoped_button_pair(self, question: str, value: str) -> bool:
        """Click a ``<button>`` answering *question* with *value*.

        Handles the "segmented-control" pattern where an ATS renders a
        single-choice question as two side-by-side ``<button>`` elements
        (e.g. Ashby's Yes / No pair for "Are you eligible for a U.S
        Security Clearance?"). There is no ``<input>`` backing these, so
        the radio-based helpers miss them.

        Strategy: walk up from the nearest label/legend/heading whose
        text matches the question, find the nearest ancestor that also
        contains clickable ``<button>``s, then click the one whose
        visible text / aria-label matches the value. Scoping to the
        question's own container prevents picking the first Yes/No on
        the page.
        """
        if not question or not value:
            return False
        try:
            js = r"""(args) => {
                const q = (args.q || '').toLowerCase().replace(/\s+/g, ' ').trim();
                const v = (args.v || '').toLowerCase().replace(/\s+/g, ' ').trim();
                if (!q || !v) return false;
                const qTokens = q.split(/\s+/).filter(t => t.length >= 3);
                const matchQ = (text) => {
                    const n = (text || '').toLowerCase().replace(/\s+/g, ' ').trim();
                    if (!n) return 0;
                    if (n === q) return 3;
                    if (n.includes(q)) return 2;
                    return qTokens.length && qTokens.every(t => n.includes(t)) ? 1 : 0;
                };
                const matchV = (text) => {
                    const n = (text || '').toLowerCase().replace(/\s+/g, ' ').trim();
                    if (!n) return 0;
                    if (n === v) return 3;
                    if (n.split(/\s+/)[0] === v) return 2;
                    if (n.includes(v)) return 1;
                    return 0;
                };
                const titleNodes = [...document.querySelectorAll(
                    'label, legend, [class*="question-title"], [class*="field-label"], ' +
                    '[class*="FieldLabel"], [class*="field_label"], strong, h3, h4, p'
                )];
                let best = null;
                let bestScore = 0;
                for (const t of titleNodes) {
                    const qScore = matchQ(t.textContent);
                    if (qScore === 0) continue;
                    let container = t;
                    for (let i = 0; i < 6 && container; i++) {
                        const btns = container.querySelectorAll(
                            'button:not([type="submit"]), [role="button"], [role="radio"], [role="switch"]'
                        );
                        if (btns.length > 0) {
                            for (const b of btns) {
                                if (b === t || b.contains(t)) continue;
                                const txt = (b.innerText || b.textContent || '').trim();
                                const aria = b.getAttribute('aria-label') || '';
                                const vScore = Math.max(matchV(txt), matchV(aria));
                                if (vScore === 0) continue;
                                const total = qScore * 10 + vScore;
                                if (total > bestScore) {
                                    best = b; bestScore = total;
                                }
                            }
                            if (best) break;
                        }
                        container = container.parentElement;
                    }
                    if (best) break;
                }
                if (!best) return false;
                try { best.scrollIntoView({block: 'center'}); } catch (e) {}
                try { best.click(); } catch (e) {}
                try {
                    const fire = (type) => best.dispatchEvent(
                        new PointerEvent(type, {bubbles: true, cancelable: true})
                    );
                    fire('pointerdown');
                    fire('pointerup');
                } catch (e) {}
                return true;
            }"""
            for target in [self.page] + list(self.page.frames):
                try:
                    if target.evaluate(js, {"q": question, "v": value}):
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def _select_scoped_radio(self, question: str, value: str) -> bool:
        """Click the radio/checkbox that answers *question* with *value*.

        Scopes the search to the fieldset / ancestor that actually owns
        the question text, so we never cross-contaminate two Yes/No
        questions on the same page. Tolerates:

        * ``<fieldset><legend>Question?</legend>…<input value="Yes">``
        * ``<div>Question?</div>…<label><input value="Yes"> Yes</label>``
        * Ashby-style ``<div role="radiogroup" aria-label="Question?">``
        * Hidden ``<input>`` toggled via a sibling ``<label>``

        Verifies the chosen radio is actually ``:checked`` after click.
        Returns False if no matching pair can be confirmed.
        """
        try:
            question_lower = (question or "").lower().strip()
            value_lower = (value or "").lower().strip()
            if not question_lower or not value_lower:
                return False

            # Use Playwright to evaluate in every frame so iframes work.
            eval_targets = [self.page] + list(self.page.frames)
            # JS: return an ID we can target from Python — we mark the
            # chosen input with a data attribute, then Playwright clicks
            # it.  This avoids the fragile "click the first visible" trap.
            marker = "__jobcli_selected_radio__"
            js = r"""(args) => {
                const question = args.q;
                const value = args.v;
                const marker = args.m;
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const qNorm = norm(question);
                const vNorm = norm(value);
                const qTokens = qNorm.split(/\s+/).filter(t => t.length >= 3);
                const containsQuestion = (text) => {
                    const n = norm(text);
                    if (!n) return 0;
                    if (n === qNorm) return 3;
                    if (n.includes(qNorm)) return 2;
                    if (qTokens.length && qTokens.every(t => n.includes(t))) return 1;
                    return 0;
                };
                const valueMatches = (el) => {
                    // Prefer the *value* attribute, then the associated
                    // label text, then the accessible name.
                    const attrVal = norm(el.getAttribute('value'));
                    if (attrVal === vNorm) return 3;
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
                        const n = norm(t);
                        if (n === vNorm) return 2;
                        if (n.includes(vNorm) && vNorm.length >= 2) return 1;
                    }
                    return attrVal && (attrVal.includes(vNorm) || vNorm.includes(attrVal)) ? 1 : 0;
                };
                const radios = [...document.querySelectorAll(
                    'input[type="radio"], input[type="checkbox"], [role="radio"], [role="checkbox"]'
                )];
                let best = null;
                let bestScore = 0;
                for (const el of radios) {
                    // Walk up to find the question text anchor.
                    let q = 0;
                    let cur = el.parentElement;
                    let depth = 0;
                    while (cur && depth < 8) {
                        // Prefer structural containers
                        const legend = cur.querySelector(':scope > legend, :scope > label');
                        if (legend) q = Math.max(q, containsQuestion(legend.textContent));
                        const aria = cur.getAttribute?.('aria-label');
                        if (aria) q = Math.max(q, containsQuestion(aria));
                        const lby = cur.getAttribute?.('aria-labelledby');
                        if (lby) {
                            const txt = lby.split(/\s+/).map(id =>
                                document.getElementById(id)?.textContent || ''
                            ).join(' ');
                            q = Math.max(q, containsQuestion(txt));
                        }
                        // Plain text nodes at this level (Ashby pattern)
                        q = Math.max(q, containsQuestion(cur.textContent?.slice(0, 400)));
                        if (q >= 2) break;
                        cur = cur.parentElement;
                        depth++;
                    }
                    if (q === 0) continue;
                    const v = valueMatches(el);
                    if (v === 0) continue;
                    const total = q * 10 + v;
                    if (total > bestScore) {
                        best = el;
                        bestScore = total;
                    }
                }
                if (!best) return null;
                // Mark it for Python to grab.
                best.setAttribute(marker, '1');
                // Also try to click it right here — dispatching native
                // events covers React-controlled radios that ignore
                // synthetic clicks.
                try {
                    best.scrollIntoView({block: 'center', behavior: 'instant'});
                } catch (e) {}
                const isChecked = () => best.checked === true ||
                    best.getAttribute('aria-checked') === 'true';
                const tryClick = (el) => {
                    try { el.click(); return true; } catch (e) { return false; }
                };
                // Native click on the input
                tryClick(best);
                if (!isChecked()) {
                    // Click the wrapping label (some React forms only
                    // respond to label clicks).
                    const lab = best.closest('label') ||
                        (best.id && document.querySelector('label[for="' + CSS.escape(best.id) + '"]'));
                    if (lab) tryClick(lab);
                }
                if (!isChecked()) {
                    // Last resort: set the property + dispatch events.
                    try {
                        const proto = HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(proto, 'checked')?.set;
                        if (setter) setter.call(best, true); else best.checked = true;
                        best.dispatchEvent(new Event('input', {bubbles: true}));
                        best.dispatchEvent(new Event('change', {bubbles: true}));
                    } catch (e) {}
                }
                return {checked: isChecked(), score: bestScore};
            }"""
            for target in eval_targets:
                try:
                    result = target.evaluate(js, {"q": question, "v": value, "m": marker})
                    if result and result.get("checked"):
                        return True
                    # If the JS found an element but couldn't toggle it
                    # (cross-origin or React shadow DOM refusing), let
                    # Playwright try clicking the marked node by
                    # locator.
                    if result is not None:
                        try:
                            loc = target.locator(f"[{marker}]").first
                            if loc.count() > 0:
                                try:
                                    loc.scroll_into_view_if_needed(timeout=1500)
                                except Exception:
                                    pass
                                loc.click(timeout=3000)
                                # Re-verify
                                verified = target.evaluate(
                                    f"() => {{ const el = document.querySelector('[{marker}]'); return el && (el.checked === true || el.getAttribute('aria-checked') === 'true'); }}"
                                )
                                if verified:
                                    return True
                        except Exception:
                            pass
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def _execute_select(self, action: BrowserAction) -> bool:
        if not action.value: return False
        # Prefer the true question text over an answer-shaped selector.
        name = self._question_for(action).rstrip("*").strip()
        value = self._normalize_fill_value(action.value)

        # ATS-specific fast path. Handler can answer for either radios
        # (``click_option``) or true dropdowns (``select_dropdown_option``).
        if self.ats_handler is not None:
            for method_name in ("click_option", "select_dropdown_option"):
                try:
                    method = getattr(self.ats_handler, method_name, None)
                    if callable(method):
                        result = method(name, value)
                        if result is True:
                            if self.logger:
                                self.logger.info(
                                    f"Select via {type(self.ats_handler).__name__}.{method_name}",
                                    phase=ExecutionPhase.LLM,
                                )
                            return True
                except Exception as e:
                    if self.logger:
                        self.logger.debug(
                            f"ATS {method_name} raised: {e}", phase=ExecutionPhase.LLM
                        )

        roots = self._get_active_content_roots()

        # --- Pass 1: HTML <select> via get_by_label (with force for hidden selects) ---
        for root in roots:
            for exact in (False, True):
                try:
                    loc = root.get_by_label(name, exact=exact).first
                    if loc.count() == 0:
                        continue
                    try:
                        # Skip if already selected correctly to avoid overwriting user edits or autofill
                        try:
                            current_text = loc.evaluate("el => el.options[el.selectedIndex]?.textContent || ''").strip()
                            if current_text and value and (value.lower() in current_text.lower() or current_text.lower() in value.lower()):
                                if self.logger:
                                    self.logger.info(f"Skipping select for '{name}' — already matches '{current_text}'", phase=ExecutionPhase.LLM)
                                return True
                        except Exception:
                            pass

                        loc.select_option(value, timeout=2000)
                        if self.logger: self.logger.info(f"Select via label (exact={exact})", phase=ExecutionPhase.LLM)
                        return True
                    except Exception:
                        # Try normal select first for hidden backing <select> elements
                        try:
                            loc.select_option(value, timeout=2000)
                            if self.logger: self.logger.info(f"Select via label force (exact={exact})", phase=ExecutionPhase.LLM)
                            return True
                        except Exception:
                            pass
                except Exception:
                    continue

        # --- Pass 2: combobox by accessible name ---
        for root in roots:
            try:
                loc = root.get_by_role("combobox", name=name, exact=False).first
                if loc.count() > 0:
                    try:
                        # Skip if already selected
                        try:
                            current_text = (loc.text_content() or loc.input_value() or "").strip()
                            if current_text and value and (value.lower() in current_text.lower() or current_text.lower() in value.lower()):
                                if self.logger:
                                    self.logger.info(f"Skipping select for '{name}' (combobox) — already matches '{current_text}'", phase=ExecutionPhase.LLM)
                                return True
                        except Exception:
                            pass

                        loc.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                    if loc.is_visible(timeout=1500):
                        try:
                            loc.select_option(value, timeout=2000)
                            if self.logger: self.logger.info("Select via combobox role", phase=ExecutionPhase.LLM)
                            return True
                        except Exception:
                            if self._click_and_fill_combobox(loc, value):
                                if self.logger: self.logger.info("Select via combobox click+fill", phase=ExecutionPhase.LLM)
                                return True
            except Exception:
                continue

        # --- Pass 3: SCOPED radio/checkbox — find the fieldset whose
        #     label/legend matches the question text, then click the
        #     option whose value matches. This is critical for Ashby /
        #     any ATS with multiple Yes/No questions on one page: a
        #     plain ``get_by_role("radio", name="Yes")`` would just
        #     click the *first* "Yes" on the page, which is almost
        #     certainly the wrong question.
        if self._select_scoped_radio(name, value):
            if self.logger:
                self.logger.info(
                    f"Select via scoped radio '{name}' = '{value}'",
                    phase=ExecutionPhase.LLM,
                )
            return True

        # --- Pass 3b: SCOPED BUTTON-SEGMENTED group.
        #     Some ATSes render Yes/No (or other short option sets) as two
        #     styled ``<button>``s instead of radios — there is no
        #     ``<input>`` element to match, so Pass 3 misses them. Walk
        #     up from the nearest label/title matching the question and
        #     click the child button whose visible text matches the value.
        if self._select_scoped_button_pair(name, value):
            if self.logger:
                self.logger.info(
                    f"Select via scoped button '{name}' = '{value}'",
                    phase=ExecutionPhase.LLM,
                )
            return True

        # --- Pass 4: scan ALL comboboxes; match by aria-labelledby / ancestor label text ---
        # Handles Workday pattern where combobox accessible name ≠ question text label.
        for root in roots:
            try:
                all_combos = root.locator("[role='combobox'], [role='listbox']")
                count = min(all_combos.count(), 25)
                name_lower = name.lower()
                for i in range(count):
                    loc = all_combos.nth(i)
                    try:
                        # Resolve the associated label text via JS (not just accessible name)
                        resolved = loc.evaluate("""(el) => {
                            // aria-labelledby → join all referenced element texts
                            const lby = el.getAttribute('aria-labelledby');
                            if (lby) {
                                const t = lby.split(/\\s+/)
                                    .map(id => document.getElementById(id)?.textContent || '')
                                    .join(' ').trim();
                                if (t) return t;
                            }
                            // aria-label
                            const al = el.getAttribute('aria-label');
                            if (al) return al;
                            // Closest ancestor label / legend / heading
                            let cur = el.parentElement;
                            while (cur) {
                                const lbl = cur.querySelector(':scope > label, :scope > legend');
                                if (lbl) return lbl.textContent;
                                cur = cur.parentElement;
                                if (!cur || cur === document.body) break;
                            }
                            return '';
                        }""").lower()
                        if name_lower not in resolved:
                            continue
                        try:
                            loc.scroll_into_view_if_needed(timeout=1500)
                        except Exception:
                            pass
                        if self._click_and_fill_combobox(loc, value):
                            if self.logger: self.logger.info(f"Select via combobox scan for '{name}'", phase=ExecutionPhase.LLM)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

        return False

    def _verify_upload_present(self, file_path: str) -> bool:
        """Best-effort check that *some* attachment indicator is visible.

        We look for either:
          * the original file's basename displayed somewhere (most ATS
            show the attached filename once upload completes), OR
          * a Delete/Remove button near a resume/attachment region, OR
          * an ``input[type=file]`` whose ``files`` list is non-empty.

        Runs across main page + all frames.  Returns True if ANY signal
        is present, False otherwise.
        """
        import os
        basename = os.path.basename(file_path).lower() if file_path else ""
        targets = [self.page] + list(self.page.frames)
        for target in targets:
            try:
                js = r"""(name) => {
                    const needle = (name || '').toLowerCase();
                    if (needle) {
                        const all = document.body ? document.body.innerText.toLowerCase() : '';
                        if (all.includes(needle)) return 'filename-visible';
                    }
                    const inputs = [...document.querySelectorAll('input[type="file"]')];
                    for (const inp of inputs) {
                        if (inp.files && inp.files.length > 0) return 'input-has-files';
                    }
                    const delBtns = [...document.querySelectorAll('button, [role="button"]')]
                        .filter(b => /^(delete|remove|clear)$/i.test((b.textContent || '').trim()));
                    for (const b of delBtns) {
                        // Only count it if near a resume/attachment region.
                        let cur = b.parentElement; let depth = 0;
                        while (cur && depth < 6) {
                            const t = (cur.textContent || '').toLowerCase();
                            if (t.includes('resume') || t.includes('attachment') || t.includes('cv')) {
                                return 'delete-btn-near-attachment';
                            }
                            cur = cur.parentElement; depth++;
                        }
                    }
                    return '';
                }"""
                signal = target.evaluate(js, basename)
                if signal:
                    return True
            except Exception:
                continue
        return False

    # Shared category vocabulary for classifying the upload target label
    # (e.g. "Resume/CV" vs "Cover Letter") and the file being uploaded.
    _RESUME_KEYWORDS = ("resume", "cv", "curriculum", "vitae")
    _COVER_KEYWORDS = ("cover letter", "cover_letter", "cover-letter", "coverletter")
    _PORTFOLIO_KEYWORDS = ("portfolio", "transcript", "writing sample", "work sample")

    @staticmethod
    def _classify_upload_target(label: str) -> Optional[str]:
        """Return ``'resume' | 'cover_letter' | 'portfolio' | None``.

        Classifies the *target* field the LLM wants to upload into, based
        on its label/field name.  Used to scope which attach buttons the
        executor is allowed to click so we never drop a resume into a
        cover-letter slot.
        """
        s = (label or "").lower().strip()
        if not s:
            return None
        for kw in ToolExecutor._COVER_KEYWORDS:
            if kw in s:
                return "cover_letter"
        for kw in ToolExecutor._PORTFOLIO_KEYWORDS:
            if kw in s:
                return "portfolio"
        for kw in ToolExecutor._RESUME_KEYWORDS:
            if kw in s:
                return "resume"
        return None

    @staticmethod
    def _classify_file(file_path: str) -> Optional[str]:
        """Classify a local file by its basename (resume vs cover letter)."""
        import os as _os
        fname = _os.path.basename(file_path or "").lower()
        for kw in ToolExecutor._COVER_KEYWORDS + ("cover",):
            if kw in fname:
                return "cover_letter"
        for kw in ToolExecutor._RESUME_KEYWORDS:
            if kw in fname:
                return "resume"
        return None

    def _scoped_container_for_label(self, label: str):
        """Return a Playwright locator scoping search to *one* labelled section.

        We try several strategies to resolve "the container holding the
        field titled X":

          1. ``<label for=id>`` → climb to the nearest form-field wrapper
             (``<fieldset>``, ``<div role='group'>``, custom wrappers).
          2. ``aria-labelledby`` → element that references a label with
             the given text.
          3. Heading/text node with the exact label → closest upload-
             widget container (has a file input or attach button
             underneath).

        Returns ``None`` when we can't pin down a unique container, so
        the caller falls back to global search.
        """
        if not label:
            return None
        clean = label.rstrip("*").strip()
        if not clean:
            return None
        try:
            js = r"""(lbl) => {
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const wanted = norm(lbl);
                if (!wanted) return null;

                // Look for any element whose visible text (just this node,
                // not its subtree) matches the label.
                const candidates = [];
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_ELEMENT
                );
                let n;
                while ((n = walker.nextNode())) {
                    const tag = n.tagName;
                    if (!['LABEL', 'LEGEND', 'H1', 'H2', 'H3', 'H4',
                          'H5', 'H6', 'DIV', 'SPAN', 'P'].includes(tag)) continue;
                    // Own text only (not from children) — avoids matching
                    // giant containers that happen to contain the label
                    // somewhere deep inside.
                    let own = '';
                    for (const c of n.childNodes) {
                        if (c.nodeType === 3) own += c.nodeValue || '';
                    }
                    if (!own) continue;
                    if (norm(own) !== wanted &&
                        norm(own).replace(/\*$/, '').trim() !== wanted) continue;
                    candidates.push(n);
                    if (candidates.length >= 5) break;
                }
                if (!candidates.length) return null;

                // For each candidate, climb up to the nearest wrapper
                // that also contains an upload widget (file input or
                // an attach/upload/browse button).
                const uploadSel =
                    "input[type='file'], " +
                    "button, [role='button']";
                for (const c of candidates) {
                    let node = c;
                    for (let depth = 0; depth < 8 && node; depth++) {
                        const widgets = node.querySelectorAll(uploadSel);
                        let hasUpload = false;
                        widgets.forEach(w => {
                            if (hasUpload) return;
                            if (w.tagName === 'INPUT' &&
                                (w.type || '').toLowerCase() === 'file') {
                                hasUpload = true; return;
                            }
                            const t = (w.innerText || w.textContent || '')
                                .toLowerCase();
                            if (/attach|upload|browse|choose file|select file/
                                .test(t)) hasUpload = true;
                        });
                        if (hasUpload) {
                            // Tag the chosen container so Playwright can
                            // locate it.  Use a random attribute to avoid
                            // collisions with existing markup.
                            const tag = `jobcli-upload-scope-${Date.now()}-${
                                Math.floor(Math.random() * 1e6)}`;
                            node.setAttribute('data-jobcli-scope', tag);
                            return tag;
                        }
                        node = node.parentElement;
                    }
                }
                return null;
            }"""
            tag = self.page.evaluate(js, clean)
            if not tag:
                return None
            return self.page.locator(f"[data-jobcli-scope='{tag}']").first
        except Exception:
            return None

    def _execute_upload(self, action: BrowserAction) -> bool:
        if not action.value: return False
        file_path = action.value
        name = action.selector
        # Resolve the true target-field label — prefer ``field_label`` when
        # the LLM has given us both, otherwise fall back to selector.
        target_label = (action.field_label or name or "").strip()
        target_category = self._classify_upload_target(target_label)
        file_category = self._classify_file(file_path)

        # ──────────────────────────────────────────────────────────────
        # Cross-category guard.
        # ──────────────────────────────────────────────────────────────
        # Refuse to attach a resume file into a cover-letter slot (the
        # LLM often does this when no cover letter is available: it
        # falls back to whatever ``resume_pdf_path`` is in the config).
        # Silently writing the wrong file makes applications look sloppy
        # and is one of the hardest-to-debug cross-field bugs, so we
        # fail loudly instead.
        if (
            target_category == "cover_letter"
            and file_category == "resume"
        ):
            if self.logger:
                self.logger.warning(
                    f"Refusing to upload resume file into '{target_label}' — "
                    "file looks like a resume, not a cover letter. "
                    "Leaving the field empty for the human to decide.",
                    phase=ExecutionPhase.LLM,
                )
            return False

        # ──────────────────────────────────────────────────────────────
        # Anti-Bot Guard: Refuse to upload to "Autofill" or "Parse" 
        # ──────────────────────────────────────────────────────────────
        lower_label = target_label.lower()
        if any(word in lower_label for word in ("autofill", "parse", "extract", "populate", "import")):
            if self.logger:
                self.logger.warning(
                    f"Refusing to upload to parser field '{target_label}' to avoid spam flags.",
                    phase=ExecutionPhase.LLM,
                )
            return True

        # Check if the button is generically named "upload file" but belongs to an autofill section
        if "upload" in lower_label:
            try:
                scoped_root = self._scoped_container_for_label(target_label)
                if scoped_root:
                    root_text = (scoped_root.text_content(timeout=500) or "").lower()
                    if "autofill" in root_text or "parse" in root_text:
                        if self.logger:
                            self.logger.warning(
                                f"Refusing to upload to generic '{target_label}' because its container mentions autofill/parse.",
                                phase=ExecutionPhase.LLM,
                            )
                        return True
            except Exception:
                pass

        # ──────────────────────────────────────────────────────────────
        # Global Dedupe: Never upload the exact same file twice in one session.
        # This prevents the bot from uploading the resume to both the
        # "Autofill" button and the actual "Resume/CV" attachment zone.
        # ──────────────────────────────────────────────────────────────
        for completed_key in self._completed_uploads:
            if file_path in completed_key:
                try:
                    still_attached = self._verify_upload_present(file_path)
                except Exception:
                    still_attached = True
                
                if still_attached:
                    if self.logger:
                        self.logger.info(
                            f"File '{file_path}' was already uploaded this session. "
                            f"Skipping redundant upload to '{name}' to avoid bot flags.",
                            phase=ExecutionPhase.LLM,
                        )
                    return True

                if self.logger:
                    self.logger.info(
                        f"File '{file_path}' was previously uploaded but the "
                        "attachment is gone — allowing re-upload.",
                        phase=ExecutionPhase.LLM,
                    )
                break
        
        # Add to completed uploads
        dedupe_key = f"{(target_label or '').lower().strip()}::{file_path}"

        # All roots: main page + actual child Frame objects
        search_roots = [self.page]
        for frame in self.page.frames:
            if frame != self.page.main_frame:
                search_roots.append(frame)

        # Diagnostic scan — logged so we know what exists at upload time
        if self.logger:
            try:
                n_file = self.page.locator("input[type='file']").count()
                n_wd   = self.page.locator("[data-automation-id='file-upload-input'],[data-automation-id='file-upload']").count()
                n_btn  = self.page.get_by_role("button", name=re.compile(r"attach|upload|browse|choose file", re.I)).count()
                self.logger.info(
                    f"Upload scan: file_inputs={n_file} wd_selectors={n_wd} attach_buttons={n_btn} selector='{name}'",
                    phase=ExecutionPhase.LLM,
                )
            except Exception:
                pass

        # --- Pre-check: Workday "Delete + re-upload" flow ---
        # If a file is already attached, Workday hides the upload zone.
        # We must click Delete first to reveal the dropzone, then upload.
        try:
            delete_btns = self.page.get_by_role("button", name=re.compile(r"^(delete|remove)$", re.I))
            if delete_btns.count() > 0:
                # Only delete if we're near a resume/attachment section
                near_resume = self.page.locator(
                    "[data-automation-id*='resume'], [data-automation-id*='attachment'], "
                    "[data-automation-id*='Resume'], [data-automation-id*='Attachment']"
                ).count() > 0
                if near_resume:
                    delete_btns.first.click(timeout=3000)
                    self.page.wait_for_timeout(1200)
                    if self.logger:
                        self.logger.info("Cleared existing attachment; upload zone should reappear.", phase=ExecutionPhase.LLM)
        except Exception:
            pass

        # ──────────────────────────────────────────────────────────────
        # Scope the trigger search to the labelled container when we
        # know which field we're uploading into.
        # ──────────────────────────────────────────────────────────────
        # On multi-upload forms (Resume + Cover Letter + Portfolio) the
        # generic ``button:has-text('Attach')`` selector matches EVERY
        # attach button, and the first one in DOM order wins — which is
        # almost always the resume button.  This code finds the field's
        # container (label → closest field wrapper) and prefers triggers
        # inside that subtree before falling back to global search.
        scoped_root = self._scoped_container_for_label(target_label)

        # Generic global triggers — used only after the scoped pass.
        trigger_selectors_global = [
            "[data-automation-id='file-upload']",
            "[data-automation-id*='file-upload']:not(input)",
            "[data-automation-id*='fileUpload']:not(input)",
            "[data-automation-id='resumeUpload']",
            "[data-automation-id*='resume'] button",
            "[data-automation-id*='attachment'] button",
            "button:has-text('Attach')",
            "button:has-text('Upload')",
            "button:has-text('Browse')",
            "button:has-text('Choose File')",
            "button:has-text('Select File')",
            "button:has-text('Select from')",
            "button:has-text('Device')",
            "[role='button']:has-text('attach')",
            "[role='button']:has-text('upload')",
        ]
        # Category-specific triggers.  Only used when we know the target.
        trigger_selectors_category: list[str] = []
        if target_category == "cover_letter":
            trigger_selectors_category = [
                "[data-automation-id*='cover' i] button",
                "[data-automation-id*='coverLetter' i] button",
                "[name*='cover_letter' i] + * button",
            ]
        elif target_category == "resume":
            trigger_selectors_category = [
                "[data-automation-id='resumeUpload']",
                "[data-automation-id*='resume' i] button",
                "button:has-text('Resume')",
                "button:has-text('CV')",
                "button:has-text('Attach')",
                "[role='button']:has-text('Attach')",
                "[class*='resume' i] button",
            ]
        elif target_category == "portfolio":
            trigger_selectors_category = [
                "[data-automation-id*='portfolio' i] button",
                "[data-automation-id*='transcript' i] button",
                "[data-automation-id*='writing' i] button",
            ]

        def _try_trigger(root, sel: str) -> bool:
            try:
                trigger = root.locator(sel).first
                if trigger.count() == 0:
                    return False
                
                # Anti-bot check: if this button is inside an Autofill section, skip it!
                is_trap = trigger.evaluate("""el => {
                    let node = el;
                    // Only go up 3 levels to avoid hitting the global <form> which contains the whole page text
                    for (let depth = 0; depth < 3 && node; depth++) {
                        const text = (node.textContent || '').toLowerCase();
                        if (text.includes('autofill') || text.includes('parse') || text.includes('extract')) {
                            // ensure we are looking at the widget's own text, not the global page text
                            if (text.length < 500) {
                                return true;
                            }
                        }
                        // Also check attributes
                        const attrs = [...node.attributes].map(a => (a.value || '').toLowerCase());
                        if (attrs.some(v => v.includes('autofill') || v.includes('parse'))) {
                            return true;
                        }
                        node = node.parentElement;
                    }
                    return false;
                }""")
                if is_trap:
                    return False
                    
                try:
                    trigger.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                if not trigger.is_visible(timeout=1200):
                    return False
                with self.page.expect_file_chooser(timeout=6000) as fc_info:
                    trigger.click(timeout=3000)
                fc_info.value.set_files(file_path)
                self.page.wait_for_timeout(5500)
                if self.logger:
                    self.logger.info(
                        f"Upload via file chooser '{sel}' (target='{target_label}')",
                        phase=ExecutionPhase.LLM,
                    )
                self._completed_uploads.add(dedupe_key)
                return True
            except Exception as e:
                if self.logger:
                    self.logger.debug(
                        f"Upload chooser '{sel}' failed: {e}",
                        phase=ExecutionPhase.LLM,
                    )
                return False

        # --- Strategy 1a: Scoped trigger inside the labelled container ---
        if scoped_root is not None:
            for sel in (
                "button",
                "[role='button']",
                "input[type='file']",
            ):
                # ``input[type='file']`` is handled in strategy 2 below;
                # here we only click buttons to get at the file chooser.
                if sel.startswith("input"):
                    continue
                if _try_trigger(scoped_root, sel):
                    return True

        # --- Strategy 1b: Category-specific global triggers ---
        for sel in trigger_selectors_category:
            for root in search_roots:
                if _try_trigger(root, sel):
                    return True

        # --- Strategy 1c: Generic global triggers (last resort) ---
        # Only fall through to these when we couldn't locate a scoped
        # container — otherwise we'd risk hitting the wrong upload slot.
        if scoped_root is None or target_category is None:
            for sel in trigger_selectors_global:
                for root in search_roots:
                    if _try_trigger(root, sel):
                        return True

        # --- Strategy 2: Direct set_input_files on <input type="file"> ---
        # Scoped version first, then global.  The scoped version is the
        # #1 safeguard against resume-into-cover-letter cross-writes.
        def _try_file_input(root, sel: str) -> bool:
            try:
                loc = root.locator(sel)
                count = loc.count()
                if self.logger:
                    self.logger.info(f"[DEBUG] _try_file_input selector='{sel}' count={count}", phase=ExecutionPhase.LLM)
                if count == 0:
                    return False
                
                for i in range(count):
                    element = loc.nth(i)
                    # Anti-bot check: if this file input is inside an Autofill section, skip it!
                    is_trap = element.evaluate("""el => {
                        let node = el;
                        for (let depth = 0; depth < 4 && node; depth++) {
                            const text = (node.textContent || '').toLowerCase();
                            if (text.includes('autofill') || text.includes('parse') || text.includes('extract')) {
                                if (text.length < 500) return true;
                            }
                            const attrs = [...node.attributes].map(a => (a.value || '').toLowerCase());
                            if (attrs.some(v => v.includes('autofill') || v.includes('parse'))) {
                                return true;
                            }
                            node = node.parentElement;
                        }
                        return false;
                    }""")
                    
                    if self.logger:
                        self.logger.info(f"[DEBUG] _try_file_input i={i} is_trap={is_trap}", phase=ExecutionPhase.LLM)
                        
                    if is_trap:
                        if self.logger:
                            self.logger.warning(
                                f"Skipping file input {i} because it belongs to an autofill/parse widget.",
                                phase=ExecutionPhase.LLM,
                            )
                        continue

                    element.set_input_files(file_path, timeout=8000)
                    self.page.wait_for_timeout(5500)
                    if self.logger:
                        self.logger.info(
                            f"Upload via set_input_files '{sel}' (target='{target_label}')",
                            phase=ExecutionPhase.LLM,
                        )
                    self._completed_uploads.add(dedupe_key)
                    return True
                return False
            except Exception as e:
                if self.logger:
                    self.logger.debug(
                        f"Upload set_input_files '{sel}' failed: {e}",
                        phase=ExecutionPhase.LLM,
                    )
                return False

        file_selectors = [
            "[data-automation-id='file-upload-input']",
            "[data-automation-id*='file-upload'] input[type='file']",
            "[data-automation-id*='fileUpload'] input[type='file']",
            "input[type='file'][accept*='pdf']",
            "input[type='file'][accept*='doc']",
            "input[type='file']",
        ]

        if scoped_root is not None:
            for sel in file_selectors:
                if _try_file_input(scoped_root, sel):
                    return True

        # Global fallback — only when no scoped container exists, or
        # when we have no category information at all.
        if scoped_root is None or target_category is None:
            for root in search_roots:
                for sel in file_selectors:
                    if _try_file_input(root, sel):
                        return True

        # --- Strategy 3: Scroll the page to reveal the upload zone, then retry ---
        try:
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(500)
            for scroll_y in (300, 600, 900):
                self.page.evaluate(f"window.scrollTo(0, {scroll_y})")
                self.page.wait_for_timeout(400)
                for sel in [
                    "[data-automation-id='file-upload']",
                    "button:has-text('Attach')",
                    "button:has-text('Upload')",
                    "input[type='file']",
                ]:
                    try:
                        loc = self.page.locator(sel).first
                        if loc.count() == 0:
                            continue
                        if sel.startswith("input"):
                            loc.set_input_files(file_path, timeout=5000)
                        else:
                            if not loc.is_visible(timeout=800):
                                continue
                            with self.page.expect_file_chooser(timeout=5000) as fc_info:
                                loc.click(timeout=2000)
                            fc_info.value.set_files(file_path)
                        self.page.wait_for_timeout(2500)
                        if self.logger:
                            self.logger.info(f"Upload via scroll+retry '{sel}'", phase=ExecutionPhase.LLM)
                        self._completed_uploads.add(dedupe_key)
                        return True
                    except Exception:
                        continue
        except Exception:
            pass

        if self.logger:
            self.logger.warning(
                f"Upload failed for '{name}': all strategies exhausted "
                f"(file_chooser, set_input_files, scroll+retry)",
                phase=ExecutionPhase.LLM,
            )
        return False

    def _execute_scroll(self, action: BrowserAction) -> bool:
        scroll_amount = int(action.value) if action.value else 500
        self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        return True

    def _execute_wait(self, action: BrowserAction) -> bool:
        wait_time = int(action.value) if action.value else action.timeout
        self.page.wait_for_timeout(wait_time)
        return True
