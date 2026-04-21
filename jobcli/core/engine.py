"""Core execution engine — unified agent loop with integrated human checkpoints.

Instead of a three-phase waterfall (LLM → Rules → Human), the engine runs a
single agent loop.  Human interaction is woven inline via ``AgentInterface``,
whose behaviour adapts to the configured ``InteractionMode`` (auto / supervised
/ manual) — similar to how Claude Code integrates approval into its tool loop.
"""

import random
import time
import re
from typing import Optional

from playwright.sync_api import Page, sync_playwright

from jobcli.core.logger import JobLogger, global_logger
from jobcli.core.schemas import (
    ActionType,
    ApplicationState,
    ApplicationStatus,
    ATSType,
    Config,
    ExecutionPhase,
    InteractionMode,
    Job,
    ResumeData,
)
from jobcli.core.tool_executor import ToolExecutor
from jobcli.human.agent_interface import AgentInterface
from jobcli.llm.client import LLMClient
from jobcli.llm.ax_tree_extractor import AccessibilityTreeExtractor
from jobcli.core.anti_bot import AntiBotManager
from jobcli.locators.apply_button import ApplyButtonLocator, adopt_application_page_after_action
from jobcli.locators.ats.handler_factory import ATSHandlerFactory
from jobcli.locators.ats_detector import ATSDetector
from jobcli.locators.form_fields import FormFiller
from jobcli.storage.models import Database
from jobcli.storage.repositories import (
    ApplicationLogRepository,
    JobRepository,
    LearnedLocatorRepository,
)


def _strip_apply_clicks_when_filling_only(llm_response, task: str) -> None:
    """Avoid LLM repeatedly clicking Apply on the JD tab after we already adopted to ATS."""
    if task not in ("fill_form_fields_only", "fill_empty_fields_only"):
        return
    if not llm_response or not llm_response.actions:
        return

    pat = re.compile(r"(?i)(apply\s*now|submit\s*application|\bapply\b)")

    def looks_like_apply(a) -> bool:
        blob = " ".join(
            str(x)
            for x in (a.field_label, a.selector, a.value)
            if x
        )
        return bool(pat.search(blob))

    llm_response.actions = [
        a for a in llm_response.actions
        if not (a.action == ActionType.CLICK and looks_like_apply(a))
    ]


# Reject third-party / federated apply variants no matter what task the
# LLM was asked to do.  Belt-and-braces with the prompt rule + the
# rule-based locator's third-party filter.
_THIRD_PARTY_APPLY_RE = re.compile(
    r"(?i)("
    r"easy\s*apply|"
    r"apply\s+(with|via|using|through|on)\s+|"
    r"\blinkedin\b|\bindeed\b|\bglassdoor\b|\bziprecruiter\b|"
    r"\bmonster\b|\bgoogle\b|\bfacebook\b|\bseek\b|\bnaukri\b|\bxing\b|"
    r"\bsign\s*in\s+with\b|\bcontinue\s+with\b|\boauth\b|\bsso\b"
    r")"
)


def _safe_domain(url: str) -> str:
    """Extract the host (domain) from a URL, lowercased; safe on bad input."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return host
    except Exception:
        return ""


def _normalize_label(s: str) -> str:
    """Normalize a field label for comparison (strip *, whitespace, punctuation, case)."""
    if not s:
        return ""
    s = s.replace("*", " ").replace(":", " ").replace("?", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _build_dropdown_label_set(ax_tree) -> dict[str, dict]:
    """Return ``{normalized_label: {options, type}}`` for every dropdown on the page.

    Generic across ALL ATS / sites — works off the accessibility tree:

    * Native ``<select>`` elements (``ax_tree.dropdown_fields[*].type == 'native_select'``).
    * Custom ARIA combobox / listbox / menu (any ``role`` of ``combobox``, ``listbox``).
    * Any form field whose role is ``combobox``, ``listbox``, or whose name matches a
      known dropdown in ``dropdown_fields`` (custom button-style dropdowns).

    The engine uses this to *coerce* LLM ``fill``/``type`` actions to ``select``
    when they target one of these labels (which is the #1 cause of "agent
    typing into a dropdown" failures across every ATS).
    """
    result: dict[str, dict] = {}

    for dp in (getattr(ax_tree, "dropdown_fields", None) or []):
        label = _normalize_label(dp.get("label", ""))
        if label:
            result[label] = {
                "options": dp.get("options", []) or [],
                "type": dp.get("type", "custom_dropdown"),
            }

    for f in (getattr(ax_tree, "form_fields", None) or []):
        role = (f.get("role") or "").lower()
        label = _normalize_label(f.get("name", "") or f.get("label", ""))
        if not label:
            continue
        if role in ("combobox", "listbox", "menu"):
            result.setdefault(label, {"options": [], "type": "aria_dropdown"})

    return result


def _coerce_dropdown_actions(llm_response, ax_tree, logger=None) -> int:
    """Coerce ``fill``/``type`` actions that target a dropdown label into ``select``.

    The LLM frequently emits ``action="fill"`` for fields that are actually
    dropdowns/comboboxes — typing into a closed dropdown does nothing on most
    sites and silently fails on Workday/Greenhouse/Ashby/etc.  This safety net
    rewrites the action *before* execution so the executor takes the proper
    open-dropdown-then-pick-option path.

    Generic implementation — works on every ATS that exposes dropdowns via
    ``<select>`` or ``role="combobox"``/``"listbox"``.

    Returns the number of actions coerced.
    """
    if not llm_response or not llm_response.actions:
        return 0

    dropdown_labels = _build_dropdown_label_set(ax_tree)
    if not dropdown_labels:
        return 0

    coerced = 0
    for a in llm_response.actions:
        if a.action not in (ActionType.FILL, ActionType.TYPE):
            continue
        candidates = [
            _normalize_label(a.field_label or ""),
            _normalize_label(a.selector or ""),
        ]
        match_label = None
        for cand in candidates:
            if not cand:
                continue
            if cand in dropdown_labels:
                match_label = cand
                break
            for dl in dropdown_labels:
                if cand and dl and (cand in dl or dl in cand):
                    match_label = dl
                    break
            if match_label:
                break
        if not match_label:
            continue

        a.action = ActionType.SELECT
        coerced += 1
        if logger:
            logger.warning(
                f"Coerced FILL→SELECT for dropdown field '{a.field_label or a.selector}' "
                f"(value='{a.value}', options_known={len(dropdown_labels[match_label]['options'])})",
                phase=ExecutionPhase.LLM,
            )

    return coerced


def _empty_required_fields(ax_tree) -> list[str]:
    """Return labels of required fields that are still empty on the current page.

    A field is considered required if ``required=True`` OR its name contains
    an asterisk (``*``).  A field is considered empty if its value/checked
    state is empty/false.

    Generic across all ATS — uses ARIA properties and the asterisk convention.
    """
    if not ax_tree:
        return []
    empty: list[str] = []
    for f in (getattr(ax_tree, "form_fields", None) or []):
        label = (f.get("name") or f.get("label") or "").strip()
        if not label:
            continue
        is_required = bool(f.get("required")) or "*" in label
        if not is_required:
            continue

        role = (f.get("role") or "").lower()
        val = str(f.get("value", "") or "").strip()
        checked = f.get("checked")

        if role in ("checkbox", "radio", "switch"):
            if not (checked is True or (isinstance(checked, str) and checked.lower() in ("true", "on", "yes", "1"))):
                empty.append(label)
        else:
            if not val or val.lower() in ("select", "select...", "select an option", "choose", "please choose", "--"):
                empty.append(label)

    seen: set[str] = set()
    out: list[str] = []
    for lbl in empty:
        norm = _normalize_label(lbl)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(lbl)
    return out


_NEXT_BUTTON_RE = re.compile(
    r"(?i)\b(next|continue|proceed|save\s*&?\s*continue|review|submit|submit\s+application|apply|finish|complete)\b"
)


def _split_off_advance_clicks(llm_response) -> tuple[list, list]:
    """Split LLM actions into ``(non_advance, advance_clicks)``.

    "Advance" clicks = Next / Continue / Submit / Apply / Review / Finish.
    These are the buttons that move the user to the *next* page or submit
    the application.  The engine holds them back when required fields are
    still empty so the human can fill them first.
    """
    if not llm_response or not llm_response.actions:
        return [], []

    advance, rest = [], []
    for a in llm_response.actions:
        if a.action != ActionType.CLICK:
            rest.append(a)
            continue
        blob = " ".join(str(x) for x in (a.field_label, a.selector, a.value) if x)
        if _NEXT_BUTTON_RE.search(blob):
            advance.append(a)
        else:
            rest.append(a)
    return rest, advance


def _strip_third_party_apply_clicks(llm_response, logger=None) -> None:
    """Drop any CLICK action that targets a third-party apply / sign-in button.

    The LLM is instructed not to emit these (see ``_build_axtree_prompt``)
    but we filter again as a safety net.
    """
    if not llm_response or not llm_response.actions:
        return
    kept = []
    for a in llm_response.actions:
        if a.action == ActionType.CLICK:
            blob = " ".join(str(x) for x in (a.field_label, a.selector, a.value) if x)
            if _THIRD_PARTY_APPLY_RE.search(blob):
                if logger:
                    logger.warning(
                        f"Dropping third-party apply click proposed by LLM: '{blob[:100]}'",
                        phase=ExecutionPhase.LLM,
                    )
                continue
        kept.append(a)
    llm_response.actions = kept


class ApplicationEngine:
    """Core engine for job application automation."""

    def __init__(
        self,
        config: Config,
        resume: ResumeData,
        database: Database,
    ) -> None:
        """Initialize engine."""
        self.config = config
        self.resume = resume
        self.database = database
        self.session = database.get_session()

        # Initialize repositories
        self.job_repo = JobRepository(self.session)
        self.log_repo = ApplicationLogRepository(self.session)
        self.locator_repo = LearnedLocatorRepository(self.session)
        
        self.anti_bot = AntiBotManager()

    def apply_to_job(self, job: Job) -> ApplicationStatus:
        """Apply to a single job using a unified agent loop with inline human checkpoints."""
        global_logger.info(f"Starting application for job {job.id}", job_url=job.url)

        logger = JobLogger(
            job_id=job.id or 0,
            log_directory=self.config.log_directory,
            enable_screenshots=self.config.screenshot_on_error,
        )

        state = ApplicationState(
            job_id=job.id or 0,
            current_url=job.url,
        )

        mode = self.config.interaction_mode

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.config.headless)
            context = browser.new_context(
                user_agent=self.config.user_agent or self.anti_bot.get_random_user_agent(),
            )
            page = context.new_page()
            self.anti_bot.logger = logger

            # AgentInterface is created once and used throughout the loop.
            # Memory + ATS type are populated as soon as we know them so every
            # human prompt can check the DB first.
            agent = AgentInterface(
                page,
                self.locator_repo,
                mode=mode,
                logger=logger,
                resume=self.resume,
            )

            try:
                # ── 1. Navigate ─────────────────────────────────────────
                agent.show_phase_banner("Navigating to job page")
                import playwright.sync_api
                try:
                    page.goto(job.url, timeout=45000, wait_until="domcontentloaded")
                except playwright.sync_api.TimeoutError:
                    logger.warning("Page load timed out after 45s. Continuing anyway.", phase=ExecutionPhase.RULES)
                self._random_delay()
                self._dismiss_cookie_consent(page, logger)
                logger.capture_screenshot(page, "initial", ExecutionPhase.RULES)

                # ── 2. Detect ATS ───────────────────────────────────────
                detector = ATSDetector(page, logger)
                ats_type = detector.detect(job.url)
                state.detected_ats = ats_type
                self.job_repo.update_ats_type(job.id or 0, ats_type)
                agent.set_context(ats_type=ats_type)
                agent.show_status(f"Detected ATS: {ats_type.value}", phase=ExecutionPhase.RULES)

                # ── 3. Click Apply (auto, with inline human fallback) ───
                agent.show_phase_banner("Finding and clicking Apply button")
                apply_clicked, page = self._click_apply_button(page, state, logger, ats_type)
                # Page may have changed (new tab) — update agent's reference
                agent.page = page

                if not apply_clicked:
                    agent.show_warning("Could not find Apply button automatically.")
                    # First try the lightweight "tell me the selector" path.
                    ok, selector, stype = agent.request_help_finding_element("find_apply_button", ats_type)
                    if ok and selector:
                        try:
                            if stype and stype.value == "xpath":
                                page.click(f"xpath={selector}")
                            else:
                                page.click(selector)
                            apply_clicked = True
                            agent.show_success("Apply button clicked with your help.")
                            self._random_delay()
                            logger.capture_screenshot(page, "human_apply_click", ExecutionPhase.HUMAN)
                        except Exception as e:
                            agent.show_error(f"Click failed: {e}")

                    # If still stuck, hand the browser to the human entirely
                    # and resume from whatever page they end up on.
                    if not apply_clicked:
                        handoff = agent.handoff_to_human(
                            reason="Could not find a native Apply button on this page.",
                            hint="Click the correct Apply button yourself (avoid 'Apply with LinkedIn/Indeed'), "
                                 "or navigate to the application form. Then press ENTER to hand control back.",
                        )
                        if handoff.cancelled:
                            self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                            return ApplicationStatus.FAILED

                        page = handoff.page
                        agent.page = page

                        # If the human navigated forward, treat the apply step
                        # as already completed — do NOT go back. Re-detect ATS
                        # in case they landed on an entirely different host
                        # (e.g. company site -> Workday/Greenhouse).
                        if handoff.advanced:
                            apply_clicked = True
                            try:
                                new_ats = ATSDetector(page, logger).detect(page.url)
                                if new_ats != ats_type:
                                    ats_type = new_ats
                                    state.detected_ats = ats_type
                                    self.job_repo.update_ats_type(job.id or 0, ats_type)
                                    agent.set_context(ats_type=ats_type)
                                    agent.show_status(
                                        f"Re-detected ATS after handoff: {ats_type.value}",
                                        phase=ExecutionPhase.RULES,
                                    )
                            except Exception:
                                pass
                            logger.capture_screenshot(page, "human_apply_resume", ExecutionPhase.HUMAN)
                else:
                    agent.show_success("Apply button clicked.")

                if apply_clicked:
                    page.wait_for_timeout(2000)

                # ── 4. Fill form — unified agent loop ───────────────────
                agent.show_phase_banner("Filling application form")
                success = self._agent_fill_loop(page, state, logger, agent, apply_was_clicked=apply_clicked)

                if not success and state.step_count == 0:
                    # Rules-based fallback only if AI made zero progress
                    agent.show_status("AI made no progress — trying rule-based fill...", phase=ExecutionPhase.RULES)
                    success = self._fill_form_rules(page, state, logger, ats_type)

                if not success:
                    agent.show_warning("Automation could not complete the form.")
                    handoff = agent.handoff_to_human(
                        reason="The agent could not finish the form on its own.",
                        hint="Fill any missing fields and submit (or click Next) yourself. "
                             "When you're done, press ENTER and the agent will resume from "
                             "the page you're currently on.",
                    )
                    if handoff.cancelled:
                        self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                        return ApplicationStatus.FAILED

                    page = handoff.page
                    agent.page = page

                    # If the human advanced (e.g. clicked Next/Submit), give
                    # the agent one more pass on the *new* page rather than
                    # declaring success/failure based on the old one.
                    if handoff.advanced:
                        agent.show_status(
                            "Continuing from where you left off...",
                            phase=ExecutionPhase.HUMAN,
                        )
                        success = self._agent_fill_loop(
                            page, state, logger, agent, apply_was_clicked=True
                        )

                    if not success:
                        success = self._submission_looks_plausible(page)

                # ── 5. Final status ─────────────────────────────────────
                if success:
                    agent.show_success("Application completed successfully!")
                    logger.info("Application completed successfully")
                    self.job_repo.update_status(job.id or 0, ApplicationStatus.SUBMITTED)
                    status = ApplicationStatus.SUBMITTED
                else:
                    agent.show_error("Application could not be verified as submitted.")
                    logger.error("Application failed")
                    self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                    status = ApplicationStatus.FAILED

                # Increment the local apps-since-sync counter regardless of
                # outcome — the sync extractor will filter by confidence anyway.
                try:
                    from jobcli.core.memory import AgentMemory as _AM
                    _mem = _AM(self.session, job_id=job.id)
                    _mem.increment_apps_since_sync()
                except Exception:
                    pass

                # ── 6. Final browser pause ──────────────────────────────
                if not self.config.headless:
                    agent.final_browser_pause()

                return status

            except Exception as e:
                logger.error(f"Application error: {e}")
                if self.config.screenshot_on_error:
                    try:
                        logger.capture_screenshot(page, "error", state.current_phase)
                    except Exception:
                        pass
                self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                return ApplicationStatus.FAILED
            finally:
                try:
                    if 'page' in locals() and page:
                        page.context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                    logger.info("Browser closed")
                except Exception:
                    pass
                global_logger.info(f"Completed job {job.id}", status=state.status.value)

    def _click_apply_button(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
    ) -> tuple[bool, Page]:
        """Phase 1a: Click Apply and follow new tab / popup / redirect when needed."""
        try:
            context = page.context
            page_ids_before = {id(p) for p in context.pages}
            page_count_before = len(context.pages)
            url_before = page.url

            handler = ATSHandlerFactory.create_handler(ats_type, page, self.resume, logger)
            if handler:
                logger.info(f"Using {ats_type.value} handler", phase=ExecutionPhase.RULES)
                ok = handler.find_apply_button()
                page = adopt_application_page_after_action(
                    page,
                    page_count_before=page_count_before,
                    url_before=url_before,
                    logger=logger,
                    page_ids_before=page_ids_before,
                )
                if ok:
                    self._random_delay()
                    logger.capture_screenshot(page, "after_apply_click", ExecutionPhase.RULES)
                return ok, page

            apply_locator = ApplyButtonLocator(page, logger)
            ok, page = apply_locator.click_apply_button()
            if ok:
                self._random_delay()
                logger.capture_screenshot(page, "after_apply_click", ExecutionPhase.RULES)
            return ok, page
        except Exception as e:
            logger.error(f"Apply click failed: {e}", phase=ExecutionPhase.RULES)
        return False, page

    def _submission_looks_plausible(self, page: Page) -> bool:
        """Heuristic: URL or page text suggests a completed application (not just a click)."""
        try:
            url = (page.url or "").lower()
        except Exception:
            return False
        if any(
            kw in url
            for kw in (
                "thank",
                "success",
                "confirm",
                "submitted",
                "complete",
                "received",
                "acknowledgement",
            )
        ):
            return True
        try:
            blob = (page.content() or "")[:120000].lower()
        except Exception:
            return False

        for pat in (
            r"thank you for applying",
            r"application received",
            r"successfully submitted",
            r"submission.{0,40}complete",
            r"we.{0,60}received your application",
            r"your application has been submitted",
        ):
            if re.search(pat, blob, re.I):
                return True
        return False

    def _fill_form_rules(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
    ) -> bool:
        """Phase 1b: Fill form with rule-based locators."""
        logger.log_phase_start(ExecutionPhase.RULES)
        state.current_phase = ExecutionPhase.RULES
        try:
            logger.info("Starting form fill", phase=ExecutionPhase.RULES)
            resume_path = self.config.resume_pdf_path

            handler = ATSHandlerFactory.create_handler(ats_type, page, self.resume, logger)
            if handler:
                handler.fill_form(resume_path)
                self._random_delay()
                # Same as legacy _phase_rules: wizard flows need Next/Continue before final submit.
                max_steps = 5
                for step in range(max_steps):
                    state.step_count = step + 1
                    if not handler.handle_multi_step(state):
                        break
                    self._random_delay()
                clicked = handler.submit_application()
                if not clicked:
                    logger.log_phase_end(ExecutionPhase.RULES, False)
                    return False
                page.wait_for_timeout(2500)
                success = self._submission_looks_plausible(page)
                if not success:
                    logger.warning(
                        "A submit-style control was clicked, but no thank-you / confirmation "
                        "signal was detected. The application may still be in progress.",
                        phase=ExecutionPhase.RULES,
                    )
                logger.log_phase_end(ExecutionPhase.RULES, success)
                return success

            form_filler = FormFiller(page, self.resume, logger)
            fill_results = form_filler.fill_all(resume_path)

            personal_results = fill_results.get("personal_info", {})
            fields_filled = sum(1 for v in personal_results.values() if v)
            resume_uploaded = fill_results.get("resume_uploaded", False)

            self._random_delay()
            logger.capture_screenshot(page, "form_filled", ExecutionPhase.RULES)

            if fields_filled > 0 or resume_uploaded:
                logger.info(
                    f"Form fill validated: {fields_filled} fields filled",
                    phase=ExecutionPhase.RULES,
                )
                logger.log_phase_end(ExecutionPhase.RULES, True)
                return True
            else:
                logger.warning("0 fields filled by rules. Falling through to LLM.", phase=ExecutionPhase.RULES)
                logger.log_phase_end(ExecutionPhase.RULES, False)
                return False
        except Exception as e:
            logger.error(f"Form fill failed: {e}", phase=ExecutionPhase.RULES)
            logger.log_phase_end(ExecutionPhase.RULES, False)
            return False

    def _phase_rules(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
    ) -> bool:
        """Phase 1 (combined): Legacy path for ATS handlers with multi-step support."""
        logger.log_phase_start(ExecutionPhase.RULES)
        state.current_phase = ExecutionPhase.RULES
        try:
            handler = ATSHandlerFactory.create_handler(ats_type, page, self.resume, logger)
            if handler:
                logger.info(f"Using {ats_type.value} handler", phase=ExecutionPhase.RULES)
                if not handler.find_apply_button():
                    logger.warning("ATS handler failed to find apply button")
                    return False
                self._random_delay()
                logger.capture_screenshot(page, "after_apply_click", ExecutionPhase.RULES)
                resume_path = self.config.resume_pdf_path
                handler.fill_form(resume_path)
                self._random_delay()
                logger.capture_screenshot(page, "form_filled", ExecutionPhase.RULES)
                max_steps = 5
                for step in range(max_steps):
                    state.step_count = step + 1
                    if not handler.handle_multi_step(state):
                        break
                    self._random_delay()
                success = handler.submit_application()
                logger.log_phase_end(ExecutionPhase.RULES, success)
                return success
        except Exception as e:
            logger.error(f"Phase 1 failed: {e}", phase=ExecutionPhase.RULES)
            logger.log_phase_end(ExecutionPhase.RULES, False)
        return False

    def _agent_fill_loop(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        agent: AgentInterface,
        apply_was_clicked: bool = False,
    ) -> bool:
        """Unified agent loop: LLM drives form-filling, human is integrated inline.

        This replaces the old separate _phase_llm + _phase_human waterfall.
        The ``agent`` (AgentInterface) handles every human-facing checkpoint;
        its behaviour adapts automatically based on InteractionMode.
        """
        logger.log_phase_start(ExecutionPhase.LLM)
        state.current_phase = ExecutionPhase.LLM

        provider = self.config.default_llm_provider
        api_key = None
        if provider == "openai":
            api_key = self.config.openai_api_key
        elif provider == "anthropic":
            api_key = self.config.anthropic_api_key
        elif provider == "gemini":
            api_key = self.config.gemini_api_key

        if not api_key:
            # Don't just bail — a missing/invalid LLM key is a routine
            # situation (free tier exhausted, key rotated, network down).
            # Hand the form to the human so they can finish it, then return
            # success based on whether the resulting page looks plausible.
            agent.show_warning(
                f"No API key for {provider} — switching to human-driven mode."
            )
            handoff = agent.handoff_to_human(
                reason=f"AI provider '{provider}' has no API key configured.",
                hint="Fill and submit the form yourself in the browser. "
                     "When you're done, press ENTER and JobCLI will record the result.",
            )
            logger.log_phase_end(ExecutionPhase.LLM, not handoff.cancelled)
            return (not handoff.cancelled) and self._submission_looks_plausible(handoff.page)

        try:
            page.wait_for_timeout(1500)
            self._dismiss_cookie_consent(page, logger)

            if apply_was_clicked:
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
                    page.wait_for_timeout(500)
                except Exception:
                    pass

            extractor = AccessibilityTreeExtractor(page)
            ax_tree = extractor.extract()
            logger.save_structured_dom(ax_tree.model_dump(), "ax_tree_snapshot", ExecutionPhase.LLM)

            llm_client = LLMClient(provider, api_key, logger)

            from jobcli.core.memory import AgentMemory
            from jobcli.core.synonym_resolver import SynonymResolver

            memory = AgentMemory(
                self.session,
                infer_location_country=self.config.infer_location_country,
                job_id=state.job_id,
            )
            synonym_resolver = SynonymResolver(infer_location_country=self.config.infer_location_country)

            # Give the AgentInterface DB access so every human prompt checks
            # memory first and every human answer is auto-persisted.
            agent.set_context(memory=memory)

            task = "fill_form_fields_only" if apply_was_clicked else "find_apply_button_and_fill_form"

            MAX_ASK_LOOPS = 3
            loop_count = 0
            executor = ToolExecutor(page, logger, memory=memory, synonym_resolver=synonym_resolver, ats_type=state.detected_ats)
            results: dict = {}
            performed_uploads: set = set()

            # ── Inner fill loop (handles ASK retries) ──────────────────
            while loop_count < MAX_ASK_LOOPS:
                loop_count += 1
                agent.show_status(f"AI iteration {loop_count}/{MAX_ASK_LOOPS}", phase=ExecutionPhase.LLM)

                memory_context = memory.build_llm_context(state.detected_ats)
                llm_response = llm_client.analyze_page_from_axtree(
                    ax_tree, self.resume, task=task,
                    memory_context=memory_context,
                    dropdown_options=ax_tree.dropdown_fields,
                    resume_pdf_path=self.config.resume_pdf_path,
                )

                if not llm_response:
                    # Most common cause: 429 insufficient_quota, transient
                    # network failure, or provider outage.  Don't drop the
                    # user — hand them the browser with a clear visual cue
                    # so they can finish the form themselves.
                    agent.show_error(
                        "AI is unavailable (no response) — handing the form to you."
                    )
                    handoff = agent.handoff_to_human(
                        reason="The AI provider returned no response (likely API quota exhausted or network error).",
                        hint="Finish the form yourself in the browser. When done, "
                             "press ENTER and JobCLI will resume from your current page.",
                    )
                    logger.log_phase_end(ExecutionPhase.LLM, not handoff.cancelled)
                    if handoff.cancelled:
                        return False
                    page = handoff.page
                    agent.page = page
                    # Trust the human: if they advanced the page, treat as success.
                    return handoff.advanced or self._submission_looks_plausible(page)

                if llm_response.requires_human:
                    logger.warning("LLM flagged requires_human — proceeding with actions anyway")

                # ── Handle ASK actions: STOP-AND-WAIT semantics ──────────
                # When the AI requests info, we do NOT execute any other
                # actions in this iteration.  We pause, gather every missing
                # answer (DB-first via the agent), persist new answers to
                # memory, then re-run the LLM so it sees the enriched memory
                # context and proposes proper FILL actions next time.
                ask_actions = [a for a in llm_response.actions if a.action == ActionType.ASK]
                if ask_actions:
                    agent.show_status(
                        f"AI requested {len(ask_actions)} answer(s) — pausing all other actions.",
                        phase=ExecutionPhase.HUMAN,
                    )
                    answered_any = False
                    for act in ask_actions:
                        label = act.field_label or act.selector
                        options = None
                        for dp in ax_tree.dropdown_fields:
                            if dp["label"].lower() == label.lower():
                                options = dp["options"]
                                break
                        # request_field_input does DB-lookup-first and persists
                        # any new human answer automatically.
                        answer = agent.request_field_input(
                            label, options=options, question_text=act.value,
                        )
                        if answer:
                            answered_any = True
                            # Mutate the action in-place so this iteration's
                            # planned operations don't run; we'll re-loop with
                            # the updated memory instead.
                            act.action = ActionType.FILL
                            act.value = answer

                    if answered_any:
                        # Re-run the LLM cycle with the new memory context.
                        # This guarantees the model considers all already-known
                        # answers when planning the next batch of actions.
                        agent.show_status(
                            "Memory updated — re-running AI with new context.",
                            phase=ExecutionPhase.LLM,
                        )
                        ax_tree = extractor.extract()
                        continue
                    # No answers gathered — fall through and execute whatever
                    # non-ASK actions the model proposed.

                # ── Upload prioritisation ─────────────────────────────────
                has_upload = any(a.action == ActionType.UPLOAD for a in llm_response.actions)
                if has_upload:
                    new_uploads = []
                    for act in llm_response.actions:
                        if act.action == ActionType.UPLOAD:
                            upload_key = str(act.value).split('/')[-1].split('\\')[-1]
                            if upload_key not in performed_uploads:
                                new_uploads.append(act)
                                performed_uploads.add(upload_key)
                    if new_uploads:
                        llm_response.actions = new_uploads
                        agent.show_status("Upload detected — prioritising and re-scanning for autofill.", phase=ExecutionPhase.LLM)
                    else:
                        has_upload = False
                        llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.UPLOAD]

                # ── Show action plan / get approval ───────────────────────
                _strip_apply_clicks_when_filling_only(llm_response, task)
                _strip_third_party_apply_clicks(llm_response, logger)
                # Generic dropdown safety net: any FILL/TYPE that targets a
                # known dropdown label is rewritten to SELECT so the executor
                # opens the dropdown instead of typing into the closed widget.
                _coerce_dropdown_actions(llm_response, ax_tree, logger)
                llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.ASK]

                # ── Required-fields-first gate ────────────────────────────
                # If the LLM wants to click Next/Continue/Submit/Apply but
                # required (*) fields are still empty, hold those clicks back,
                # surface the missing labels, and ask the human to fill them
                # via the modal (which itself checks DB-memory first).
                non_advance, advance_clicks = _split_off_advance_clicks(llm_response)
                empty_required = _empty_required_fields(ax_tree)
                if advance_clicks and empty_required:
                    agent.show_warning(
                        f"Holding {len(advance_clicks)} Next/Submit click(s) — "
                        f"{len(empty_required)} required field(s) still empty: "
                        + ", ".join(empty_required[:6])
                        + ("…" if len(empty_required) > 6 else "")
                    )
                    for label in empty_required:
                        options = None
                        for dp in (ax_tree.dropdown_fields or []):
                            if _normalize_label(dp.get("label", "")) == _normalize_label(label):
                                options = dp.get("options") or None
                                break
                        agent.request_field_input(
                            label,
                            options=options,
                            question_text=f"Required field '{label}' is empty.",
                        )
                    # Drop the advance clicks for this iteration; only execute
                    # the non-advance actions (fills/selects/uploads).  The
                    # next loop iteration will re-extract the AX tree and the
                    # LLM will re-plan, this time with the human's new answers.
                    llm_response.actions = non_advance

                if not agent.approve_action_plan(llm_response.actions):
                    agent.show_warning("Action plan rejected — skipping this iteration.")
                    break

                # ── Execute actions ───────────────────────────────────────
                ctx = page.context
                pids0 = {id(p) for p in ctx.pages}
                url0, n0 = page.url, len(ctx.pages)
                results = executor.execute_actions(llm_response)

                adopted = adopt_application_page_after_action(
                    page, page_count_before=n0, url_before=url0,
                    page_ids_before=pids0, logger=logger,
                )
                if id(adopted) != id(page):
                    page = adopted
                    agent.page = page
                    executor = ToolExecutor(page, logger, memory=memory, synonym_resolver=synonym_resolver, ats_type=state.detected_ats)
                    extractor = AccessibilityTreeExtractor(page)
                    agent.show_status("Followed new tab.", phase=ExecutionPhase.LLM)
                    self._dismiss_cookie_consent(page, logger)
                else:
                    page = adopted

                if has_upload:
                    wait_time = 5000 if "ashby" in page.url.lower() else 3500
                    agent.show_status(f"Upload done — waiting {wait_time/1000}s for autofill...", phase=ExecutionPhase.LLM)
                    page.wait_for_timeout(wait_time)
                    ax_tree = extractor.extract()
                    continue

                ax_tree = extractor.extract()

                # Save successful actions to memory + persist locators per
                # ATS+domain so future runs (same site or sibling employer on
                # the same ATS) can short-circuit element discovery.
                page_domain = _safe_domain(page.url)
                for action in llm_response.actions:
                    if action.field_label and action.value:
                        memory.save_field_answer(action.field_label, action.value, state.detected_ats)
                    action_success = results.get(f"action_{llm_response.actions.index(action)}_{action.action.value}", False)
                    if action_success and action.value and action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT):
                        label = action.field_label or action.selector
                        memory.save_field_answer(label, action.value, state.detected_ats, success=True, source="llm")
                        if executor.last_successful_strategy:
                            memory.save_interaction(state.detected_ats, action.action.value, label, action.selector, executor.last_successful_strategy, True, page.url)
                        # Domain-aware learned locator (idempotent upsert).
                        try:
                            self.locator_repo.upsert_for_field(
                                ats_type=state.detected_ats,
                                domain=page_domain,
                                purpose=f"{action.action.value}:{_normalize_label(label)}",
                                selector=action.selector,
                                selector_type=action.selector_type,
                                success=True,
                                job_id=state.job_id,
                            )
                        except Exception as e:
                            logger.debug(f"locator persist skipped: {e}", phase=ExecutionPhase.LLM)
                        state.step_count += 1
                        # Record successful execution back into memory so
                        # confidence scores reflect real browser outcomes.
                        if action.field_label and action.value:
                            try:
                                memory.record_field_outcome(
                                    field_label=action.field_label,
                                    value=action.value,
                                    success=True,
                                    ats_type=state.detected_ats,
                                )
                            except Exception:
                                pass
                    elif action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT) and not action_success:
                        # Track failures too so confidence scoring stays honest.
                        try:
                            self.locator_repo.upsert_for_field(
                                ats_type=state.detected_ats,
                                domain=page_domain,
                                purpose=f"{action.action.value}:{_normalize_label(action.field_label or action.selector)}",
                                selector=action.selector,
                                selector_type=action.selector_type,
                                success=False,
                                job_id=state.job_id,
                            )
                        except Exception:
                            pass
                        # Record failed execution so confidence degrades correctly.
                        if action.field_label and action.value:
                            try:
                                memory.record_field_outcome(
                                    field_label=action.field_label,
                                    value=action.value,
                                    success=False,
                                    ats_type=state.detected_ats,
                                )
                            except Exception:
                                pass

                # ── Handle failed fields — inline human input ─────────────
                # AgentInterface internally checks the DB first and persists
                # any new answers, so we don't need to re-save here.
                failed_actions = executor.get_failed_actions()
                if failed_actions:
                    agent.show_failed_fields(
                        failed_actions,
                        dropdown_options_by_selector=getattr(executor, "last_dropdown_options", None),
                    )

                if not failed_actions and not ask_actions:
                    agent.show_success("All actions completed.")
                    break

            # ── Multi-page form loop ──────────────────────────────────────
            MAX_PAGES = 5
            page_count = 1

            while page_count < MAX_PAGES:
                total = len(results)
                successes = sum(1 for v in results.values() if v)

                if total == 0 or (successes / total) < 0.5:
                    logger.info(f"Page {page_count}: {successes}/{total} actions succeeded", phase=ExecutionPhase.LLM)
                    break

                agent.show_status(f"Page {page_count}: {successes}/{total} actions succeeded.", phase=ExecutionPhase.LLM)

                # Check for still-empty mandatory fields
                required_but_empty = []
                for field in ax_tree.form_fields:
                    is_required = field.get("required") or "*" in field.get("label", "")
                    if is_required and not field.get("value"):
                        required_but_empty.append(field.get("label") or field.get("name"))
                if required_but_empty:
                    for lbl in required_but_empty:
                        agent.show_warning(f"Mandatory field '{lbl}' still empty.")

                # Checkpoint: let human review / manually fix in the browser
                agent.pause_for_review(
                    f"Page {page_count} filled. Review the browser and fix any empty fields.",
                    timeout_seconds=8,
                )

                page.wait_for_timeout(3000)
                self._dismiss_cookie_consent(page, logger)

                # CAPTCHA check — handled through agent
                anti_bot = AntiBotManager(logger)
                if anti_bot.detect_captcha(page):
                    if not agent.handle_captcha():
                        logger.log_phase_end(ExecutionPhase.LLM, False)
                        return False

                page.wait_for_timeout(2000)
                new_ax_tree = extractor.extract()

                # Learn manually-filled fields from browser
                filled_fields = []
                placeholders = ["select", "choose", "please choose", "select...", "select an option"]
                for field in new_ax_tree.form_fields:
                    val = str(field.get("value", "")).strip()
                    label = field.get("name", "unknown")
                    if val.lower() not in placeholders and val:
                        filled_fields.append(f"- {label}: already has value '{val}'")
                        if memory.save_field_answer(label, val, state.detected_ats, source="human"):
                            logger.info(f"Learned answer for '{label}' from browser.", phase=ExecutionPhase.LLM)

                url_changed = new_ax_tree.url != ax_tree.url
                fields_changed = False
                if len(new_ax_tree.form_fields) != len(ax_tree.form_fields):
                    fields_changed = True
                else:
                    for i, field in enumerate(new_ax_tree.form_fields):
                        old_field = ax_tree.form_fields[i]
                        if str(field.get("value", "")).strip() != str(old_field.get("value", "")).strip() or \
                           bool(field.get("checked")) != bool(old_field.get("checked")):
                            fields_changed = True
                            break

                button_clicked = any(a.action == ActionType.CLICK for a in (llm_response.actions if 'llm_response' in locals() else []))
                if not url_changed and not fields_changed and not button_clicked:
                    break

                page_count += 1
                if url_changed:
                    agent.show_status("Navigated to new page.", phase=ExecutionPhase.LLM)
                    self._dismiss_cookie_consent(page, logger)
                else:
                    agent.show_status("New fields detected on same page.", phase=ExecutionPhase.LLM)

                ax_tree = new_ax_tree

                mandatory_keywords = ["gender", "veteran", "disability", "authorization", "visa", "legal"]
                found_in_tree = any(any(k in f.get("name", "").lower() for k in mandatory_keywords) for f in ax_tree.form_fields)
                if not found_in_tree and page_count < 4:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    ax_tree = extractor.extract()

                agent.show_status(f"Running AI on page {page_count}...", phase=ExecutionPhase.LLM)
                logger.save_structured_dom(ax_tree.model_dump(), f"ax_tree_page_{page_count}", ExecutionPhase.LLM)

                filled_context = ""
                if filled_fields:
                    filled_context = "\n## ALREADY FILLED FIELDS (DO NOT re-fill these):\n" + "\n".join(filled_fields)
                memory_context = (memory.build_llm_context(state.detected_ats) or "") + filled_context

                llm_response = llm_client.analyze_page_from_axtree(
                    ax_tree, self.resume, task="fill_empty_fields_only",
                    memory_context=memory_context,
                    dropdown_options=ax_tree.dropdown_fields,
                    resume_pdf_path=self.config.resume_pdf_path,
                )
                if not llm_response:
                    break

                _strip_apply_clicks_when_filling_only(llm_response, "fill_empty_fields_only")
                _strip_third_party_apply_clicks(llm_response, logger)
                _coerce_dropdown_actions(llm_response, ax_tree, logger)
                llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.ASK]

                # Required-fields-first gate (same as the inner loop).
                non_advance2, advance2 = _split_off_advance_clicks(llm_response)
                empty_req2 = _empty_required_fields(ax_tree)
                if advance2 and empty_req2:
                    agent.show_warning(
                        f"Holding {len(advance2)} Next/Submit click(s) on page {page_count} — "
                        f"{len(empty_req2)} required field(s) still empty."
                    )
                    for label in empty_req2:
                        options = None
                        for dp in (ax_tree.dropdown_fields or []):
                            if _normalize_label(dp.get("label", "")) == _normalize_label(label):
                                options = dp.get("options") or None
                                break
                        agent.request_field_input(
                            label,
                            options=options,
                            question_text=f"Required field '{label}' is empty.",
                        )
                    llm_response.actions = non_advance2

                if not agent.approve_action_plan(llm_response.actions):
                    break

                ctx2 = page.context
                pids1 = {id(p) for p in ctx2.pages}
                url1, n1 = page.url, len(ctx2.pages)
                results = executor.execute_actions(llm_response)

                adopted2 = adopt_application_page_after_action(
                    page, page_count_before=n1, url_before=url1,
                    page_ids_before=pids1, logger=logger,
                )
                if id(adopted2) != id(page):
                    page = adopted2
                    agent.page = page
                    executor = ToolExecutor(page, logger, memory=memory, synonym_resolver=synonym_resolver, ats_type=state.detected_ats)
                    extractor = AccessibilityTreeExtractor(page)
                    self._dismiss_cookie_consent(page, logger)
                else:
                    page = adopted2

            # ── Pre-submission checkpoint ─────────────────────────────────
            required_missing = []
            for field in ax_tree.form_fields:
                if field.get("required") or "*" in field.get("name", ""):
                    if not field.get("value") or not str(field.get("value")).strip():
                        required_missing.append(field.get("name", "unknown"))
            if required_missing:
                agent.show_warning(f"Mandatory fields still empty: {required_missing}")

            red_marks = page.locator(".error, .invalid, [aria-invalid='true'], .red-text").count()
            if red_marks > 0:
                agent.show_warning(f"{red_marks} validation errors on page.")
                if not self.config.headless:
                    page.wait_for_timeout(2000)

            # ── Confirm submission (integrated checkpoint) ────────────────
            if not agent.confirm_submission():
                agent.show_warning("Submission declined by user.")
                logger.log_phase_end(ExecutionPhase.LLM, False)
                return False

            # ── Final success evaluation ──────────────────────────────────
            total = len(results)
            successes = sum(1 for v in results.values() if v)
            _confirmation_texts = [
                "Thank you", "application submitted", "application is received",
                "successfully submitted", "application received",
            ]
            _text_confirmed = any(page.locator(f"text={t}").count() > 0 for t in _confirmation_texts)
            is_confirmation = any(term in page.url.lower() for term in ["success", "confirmation", "thank-you"]) or _text_confirmed
            success = is_confirmation or (total > 0 and (successes / total) >= 0.5)

            if success:
                agent.show_success("Application submitted!")
                page.wait_for_timeout(1000)
                logger.capture_screenshot(page, "llm_success", ExecutionPhase.LLM)
            else:
                agent.show_error("Submission could not be verified.")

            logger.log_phase_end(ExecutionPhase.LLM, success)
            return success

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Agent loop failed: {e}", phase=ExecutionPhase.LLM)
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return False

    # NOTE: _phase_human has been removed.  Human interaction is now integrated
    # inline via AgentInterface checkpoints throughout _agent_fill_loop and
    # apply_to_job.  See request_help_finding_element(), request_field_input(),
    # confirm_submission(), etc.

    def _dismiss_cookie_consent(self, page: Page, logger: JobLogger) -> None:
        """Dismiss cookie banners, privacy dialogs, and other overlays that block clicks."""
        from jobcli.locators.overlay_dismiss import dismiss_blocking_overlays

        dismiss_blocking_overlays(page, logger, phase=ExecutionPhase.RULES)

    def _random_delay(self) -> None:
        """Add random delay using the anti-bot manager."""
        if hasattr(self, "anti_bot") and self.anti_bot:
            self.anti_bot.random_delay()
        else:
            delay = random.uniform(
                self.config.random_delay_min,
                self.config.random_delay_max,
            )
            time.sleep(delay)
