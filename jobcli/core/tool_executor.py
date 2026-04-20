"""Safe tool execution layer for browser actions."""

import json
import re
from typing import Optional, List, Union

from playwright.sync_api import FrameLocator, Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import (
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
    ) -> None:
        """Initialize executor."""
        self.page = page
        self.logger = logger
        self.memory = memory
        self.synonym_resolver = synonym_resolver
        self.ats_type = ats_type
        self.last_successful_strategy = None
        self.last_dropdown_options = {}
        self._failed_actions = []

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

    def execute_action(self, action: BrowserAction) -> bool:
        """Execute a single browser action."""
        if self.logger:
            self.logger.info(
                f"Executing {action.action.value} action",
                phase=ExecutionPhase.LLM,
                selector=action.selector,
                field_label=action.field_label,
            )

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

        for i, action in enumerate(llm_response.actions):
            if action.confidence < 0.7:
                results[f"action_{i}"] = False
                continue

            success = self.execute_action(action)
            results[f"action_{i}_{action.action.value}"] = success

            if not success:
                self._failed_actions.append(action)
                continue

        return results

    def _execute_click(self, action: BrowserAction) -> bool:
        name = action.selector
        selector_type = action.selector_type

        # SAFETY: Block clicks on upload areas
        upload_keywords = ["upload", "resume", "cv", "attach", "drop or select"]
        if any(kw in name.lower() for kw in upload_keywords):
            if self.logger:
                self.logger.warning(f"Blocking click on '{name}' upload area. Use UPLOAD action instead.", phase=ExecutionPhase.LLM)
            return True

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
            attempts = [
                ("role button", lambda r=root: r.get_by_role("button", name=name, exact=False).first),
                ("role link", lambda r=root: r.get_by_role("link", name=name, exact=False).first),
                ("label", lambda r=root: r.get_by_label(name, exact=False).first),
                ("text", lambda r=root: r.get_by_text(name, exact=False).first),
                ("aria-labelledby", lambda r=root: r.locator(f"[aria-labelledby*='{name}']").first),
            ]
            for label, get_loc in attempts:
                try:
                    loc = get_loc()
                    if loc.is_visible(timeout=1000):
                        loc.highlight()
                        loc.click(timeout=action.timeout)
                        if self.logger: self.logger.info(f"Click executed via {label} in frame", phase=ExecutionPhase.LLM)
                        return True
                except Exception: continue
        
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
        name = action.selector
        roots = self._get_active_content_roots()

        for root in roots:
            attempts = [
                ("label", lambda r=root: r.get_by_label(name, exact=False).first),
                ("placeholder", lambda r=root: r.get_by_placeholder(name, exact=False).first),
                ("css input", lambda r=root: r.locator(f"input[name*='{name}' i]").first),
                ("css textarea", lambda r=root: r.locator(f"textarea[name*='{name}' i]").first),
                ("aria-labelledby", lambda r=root: r.locator(f"[aria-labelledby*='{name}']").first),
            ]
            for label, get_loc in attempts:
                try:
                    loc = get_loc()
                    if loc.is_visible(timeout=1000):
                        # Last-mile dropdown guard: if the matched element is
                        # actually a dropdown/combobox/select, do NOT type into
                        # it — redirect to the SELECT path which opens the
                        # widget and picks the matching option.  This catches
                        # the case where the LLM emitted `fill` on a dropdown
                        # AND the engine-side coerce missed (e.g. unlabeled
                        # custom widget).
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
                            loc.click(timeout=1000)
                            loc.fill("")
                            loc.press_sequentially(action.value, delay=35, timeout=action.timeout)
                            # Crucial: blur or tab to trigger autocomplete/validation
                            self.page.keyboard.press("Tab")
                        except Exception:
                            # JS Force Fill Fallback
                            js_code = """(el, val) => {
                                el.value = val;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                el.dispatchEvent(new Event('blur', { bubbles: true }));
                                return true;
                            }"""
                            loc.evaluate(js_code, action.value)
                            
                        if self.logger: self.logger.info(f"Fill executed via {label} in frame", phase=ExecutionPhase.LLM)
                        return True
                except Exception: continue
                
        # Last resort: JS global search and fill
        # Use json.dumps so names/values with apostrophes or quotes don't break the JS string
        _name_js = json.dumps(name.lower())
        _value_js = json.dumps(str(action.value))
        js_search = f"""(() => {{
            const needle = {_name_js};
            const val = {_value_js};
            const el = [...document.querySelectorAll('input,textarea')].find(e =>
                e.labels?.[0]?.textContent.toLowerCase().includes(needle) ||
                e.placeholder?.toLowerCase().includes(needle) ||
                e.name?.toLowerCase().includes(needle)
            );
            if (el) {{
                el.value = val;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }})()"""
        try:
            if self.page.evaluate(js_search):
                if self.logger: self.logger.info("Fill executed via global JS search", phase=ExecutionPhase.LLM)
                return True
        except Exception: pass
        
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

    def _execute_select(self, action: BrowserAction) -> bool:
        if not action.value: return False
        # Strip required-field marker (*) — it breaks label matching
        name = action.selector.rstrip("*").strip()
        value = self._normalize_fill_value(action.value)
        roots = self._get_active_content_roots()

        # --- Pass 1: HTML <select> via get_by_label (with force for hidden selects) ---
        for root in roots:
            for exact in (False, True):
                try:
                    loc = root.get_by_label(name, exact=exact).first
                    if loc.count() == 0:
                        continue
                    try:
                        loc.select_option(value, timeout=2000)
                        if self.logger: self.logger.info(f"Select via label (exact={exact})", phase=ExecutionPhase.LLM)
                        return True
                    except Exception:
                        # Try force=True for hidden backing <select> elements
                        try:
                            loc.select_option(value, timeout=2000, force=True)
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

        # --- Pass 3: radio button group (Workday yes/no compliance questions) ---
        for root in roots:
            try:
                radio = root.get_by_role("radio", name=value, exact=False).first
                if radio.count() > 0:
                    try:
                        radio.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                    if radio.is_visible(timeout=1500):
                        radio.click(timeout=3000)
                        if self.logger: self.logger.info(f"Select via radio button '{value}'", phase=ExecutionPhase.LLM)
                        return True
            except Exception:
                continue

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

    def _execute_upload(self, action: BrowserAction) -> bool:
        if not action.value: return False
        file_path = action.value
        name = action.selector

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

        # --- Strategy 1: File Chooser API (most reliable for React/Workday) ---
        # Playwright intercepts the OS file dialog that opens on click.
        trigger_selectors = [
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
            "[role='button']:has-text('attach')",
            "[role='button']:has-text('upload')",
        ]
        for root in search_roots:
            for sel in trigger_selectors:
                try:
                    trigger = root.locator(sel).first
                    if trigger.count() == 0:
                        continue
                    try:
                        trigger.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    if not trigger.is_visible(timeout=1200):
                        continue
                    with self.page.expect_file_chooser(timeout=6000) as fc_info:
                        trigger.click(timeout=3000)
                    fc_info.value.set_files(file_path)
                    self.page.wait_for_timeout(2500)
                    if self.logger:
                        self.logger.info(f"Upload via file chooser '{sel}'", phase=ExecutionPhase.LLM)
                    return True
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"Upload chooser '{sel}' failed: {e}", phase=ExecutionPhase.LLM)
                    continue

        # --- Strategy 2: Direct set_input_files on <input type="file"> ---
        # Playwright bypasses visibility; works even for display:none file inputs.
        file_selectors = [
            "[data-automation-id='file-upload-input']",
            "[data-automation-id*='file-upload'] input[type='file']",
            "[data-automation-id*='fileUpload'] input[type='file']",
            "input[type='file'][accept*='pdf']",
            "input[type='file'][accept*='doc']",
            "input[type='file']",
        ]
        for root in search_roots:
            for sel in file_selectors:
                try:
                    loc = root.locator(sel)
                    if loc.count() == 0:
                        continue
                    loc.first.set_input_files(file_path, timeout=8000)
                    self.page.wait_for_timeout(2500)
                    if self.logger:
                        self.logger.info(f"Upload via set_input_files '{sel}'", phase=ExecutionPhase.LLM)
                    return True
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"Upload set_input_files '{sel}' failed: {e}", phase=ExecutionPhase.LLM)
                    continue

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
