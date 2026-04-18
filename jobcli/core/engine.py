"""Core execution engine with three-phase strategy."""

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
    Job,
    ResumeData,
)
from jobcli.core.tool_executor import ToolExecutor
from jobcli.human.interface import HumanInterface
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
        """Apply to a single job using three-phase strategy."""
        global_logger.info(f"Starting application for job {job.id}", job_url=job.url)

        # Create job logger
        logger = JobLogger(
            job_id=job.id or 0,
            log_directory=self.config.log_directory,
            enable_screenshots=self.config.screenshot_on_error,
        )

        # Initialize state
        state = ApplicationState(
            job_id=job.id or 0,
            current_url=job.url,
        )

        # Launch browser
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.config.headless,
            )

            context = browser.new_context(
                user_agent=self.config.user_agent or self.anti_bot.get_random_user_agent(),
            )

            page = context.new_page()
            self.anti_bot.logger = logger

            try:
                # Navigate to job
                logger.info("Navigating to job page", phase=ExecutionPhase.RULES)
                import playwright.sync_api
                try:
                    page.goto(job.url, timeout=45000, wait_until="domcontentloaded")
                except playwright.sync_api.TimeoutError:
                    logger.warning("Page load timed out after 45s. Continuing anyway.", phase=ExecutionPhase.RULES)
                self._random_delay()

                # Dismiss any cookie consent modals that may block clicks
                self._dismiss_cookie_consent(page, logger)

                # Capture initial screenshot
                logger.capture_screenshot(page, "initial", ExecutionPhase.RULES)

                # Detect ATS
                detector = ATSDetector(page, logger)
                ats_type = detector.detect(job.url)
                state.detected_ats = ats_type
                self.job_repo.update_ats_type(job.id or 0, ats_type)

                logger.info(f"Detected ATS: {ats_type.value}", phase=ExecutionPhase.RULES)

                # Phase 1: Try rule-based approach (may switch to new tab / external ATS)
                apply_clicked, page = self._click_apply_button(page, state, logger, ats_type)
                success = False

                if apply_clicked:
                    # Wait for form to load after clicking apply
                    page.wait_for_timeout(2000)
                # --- Phase 1: AI Reasoning (LLM) ---
                print("\n" + "="*60)
                print("🧠 PHASE 1: AI REASONING (Autonomous Form Filling)")
                print("="*60)
                success = self._phase_llm(page, state, logger, apply_was_clicked=apply_clicked)

                if not success:
                    # SAFETY: If the LLM already successfully filled fields, but just failed to verify submission,
                    # don't run the Rules phase. The Rules phase is dumber and will likely corrupt the form.
                    # We check if 'answers were saved' or if any actions succeeded.
                    # For now, if LLM is active and it 'failed', we prefer HUMAN over RULES fallback if it had a try.
                    
                    print("\n" + "="*60)
                    print("⚠️  AI PHASE UNCERTAIN - Falling back to alternate strategy...")
                    print("="*60)
                    
                    # Phase 2: Rules-based fallback (Only if no significant progress was made by AI)
                    if state.step_count == 0: 
                        print("\n🤖 PHASE 2: RULE-BASED FALLBACK")
                        success = self._fill_form_rules(page, state, logger, ats_type)

                if not success:
                    # Phase 3: Human in the loop
                    print("\n" + "="*60)
                    print("🖐️  PHASE 3: HUMAN IN THE LOOP (Manual Inspection)")
                    print("="*60)
                    success = self._phase_human(page, state, logger, ats_type, apply_was_clicked=apply_clicked)

                if success:
                    logger.info("Application completed successfully")
                    self.job_repo.update_status(job.id or 0, ApplicationStatus.SUBMITTED)
                    status = ApplicationStatus.SUBMITTED
                else:
                    logger.error("Application failed")
                    self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                    status = ApplicationStatus.FAILED

                # Final inspection pause for headful mode
                if not self.config.headless:
                    print("\n" + "=" * 60)
                    print("🏁 APPLICATION FLOW FINISHED")
                    print("The browser will remain open so you can inspect the state.")
                    print("Press ENTER to close the browser and finish.")
                    print("=" * 60)
                    try:
                        input()
                    except (EOFError, KeyboardInterrupt):
                        pass

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
                # Graceful browser closure
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

    def _phase_llm(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        apply_was_clicked: bool = False,
    ) -> bool:
        """Phase 2: LLM reasoning."""
        logger.log_phase_start(ExecutionPhase.LLM)
        state.current_phase = ExecutionPhase.LLM

        # Check if LLM is configured
        provider = self.config.default_llm_provider
        api_key = None

        if provider == "openai":
            api_key = self.config.openai_api_key
        elif provider == "anthropic":
            api_key = self.config.anthropic_api_key
        elif provider == "gemini":
            api_key = self.config.gemini_api_key

        if not api_key:
            logger.warning(f"No API key configured for {provider}")
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return False

        try:
            # Wait a moment for any dynamic content to fully render
            page.wait_for_timeout(1500)

            # Dismiss any overlays / cookie banners BEFORE scanning — a blocking popup
            # makes aria_snapshot() return a mostly-empty tree and blocks all clicks.
            self._dismiss_cookie_consent(page, logger)

            # Scroll to form area if apply was already clicked
            if apply_was_clicked:
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
                    page.wait_for_timeout(500)
                except Exception:
                    pass

            # Extract Accessibility Tree (semantic, token-efficient)
            extractor = AccessibilityTreeExtractor(page)
            ax_tree = extractor.extract()

            # Save AX Tree snapshot
            logger.save_structured_dom(
                ax_tree.model_dump(),
                "ax_tree_snapshot",
                ExecutionPhase.LLM,
            )

            # Initialize LLM client
            llm_client = LLMClient(provider, api_key, logger)

            from jobcli.core.memory import AgentMemory
            from jobcli.core.synonym_resolver import SynonymResolver

            memory = AgentMemory(
                self.session,
                infer_location_country=self.config.infer_location_country,
            )
            synonym_resolver = SynonymResolver(
                infer_location_country=self.config.infer_location_country,
            )

            # Tell LLM whether apply was already clicked
            task = "fill_form_fields_only" if apply_was_clicked else "find_apply_button_and_fill_form"

            MAX_ASK_LOOPS = 3
            loop_count = 0
            executor = ToolExecutor(page, logger, memory=memory, synonym_resolver=synonym_resolver, ats_type=state.detected_ats)
            results = {}
            performed_uploads = set()  # Track what we've uploaded to avoid infinite loops

            while loop_count < MAX_ASK_LOOPS:
                loop_count += 1

                # Build Context from Memory
                memory_context = memory.build_llm_context(state.detected_ats)

                # Get actions from LLM using optimized AXTree
                llm_response = llm_client.analyze_page_from_axtree(
                    ax_tree,
                    self.resume,
                    task=task,
                    memory_context=memory_context,
                    dropdown_options=ax_tree.dropdown_fields,
                    resume_pdf_path=self.config.resume_pdf_path
                )

                if not llm_response:
                    logger.error("LLM returned no response")
                    logger.log_phase_end(ExecutionPhase.LLM, False)
                    return False

                if llm_response.requires_human:
                    logger.warning("LLM flagged requires_human but proceeding with actions anyway")

                ask_actions = [a for a in llm_response.actions if a.action == ActionType.ASK]
                if ask_actions:
                    if self.config.headless:
                        logger.error("LLM requested missing mandatory information, but running headless.", phase=ExecutionPhase.LLM)
                        return False
                        
                    print("\n" + "="*60)
                    print("⚠️  MISSING MANDATORY FIELDS DETECTED ⚠️")
                    for act in ask_actions:
                        question = act.value or f"Please provide a value for {act.selector}"
                        label = act.field_label or act.selector
                        
                        # Show dropdown options if we have them
                        options = []
                        for dp in ax_tree.dropdown_fields:
                            if dp["label"].lower() == label.lower():
                                options = dp["options"]
                                break
                                
                        if options:
                            print(f"\nAvailable options for '{label}':")
                            for i, opt in enumerate(options, 1):
                                print(f"  {i}. {opt}")
                                
                        answer = input(f"? {question} [{act.selector}]: ").strip()
                        if answer:
                            memory.save_field_answer(label, answer, state.detected_ats, success=True)
                            act.action = ActionType.FILL
                            act.value = answer
                    print("="*60 + "\n")
                    
                    # LLM responses are updated with human answers, continue execution
                    
                # Sort actions: Prioritize UPLOAD actions (resume/cover letter) 
                # This triggers ATS autofill early and expands hidden field sections.
                has_upload = any(a.action == ActionType.UPLOAD for a in llm_response.actions)
                if has_upload:
                    # Filter out uploads we've already done to avoid infinite loops
                    new_uploads = []
                    for act in llm_response.actions:
                        if act.action == ActionType.UPLOAD:
                            # Use only the filename as key to prevent redundant uploads via different selectors
                            upload_key = str(act.value).split('/')[-1].split('\\')[-1]
                            if upload_key not in performed_uploads:
                                new_uploads.append(act)
                                performed_uploads.add(upload_key)
                    
                    if new_uploads:
                        llm_response.actions = new_uploads
                        logger.info("Upload detected. Prioritizing upload and forcing re-scan to check for site autofill.", phase=ExecutionPhase.LLM)
                    else:
                        # We already did these uploads, ignore them this time
                        has_upload = False
                        llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.UPLOAD]
                
                # Execute actions
                _strip_apply_clicks_when_filling_only(llm_response, task)
                llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.ASK]
                ctx = page.context
                pids0 = {id(p) for p in ctx.pages}
                url0 = page.url
                n0 = len(ctx.pages)
                results = executor.execute_actions(llm_response)
                adopted = adopt_application_page_after_action(
                    page,
                    page_count_before=n0,
                    url_before=url0,
                    page_ids_before=pids0,
                    logger=logger,
                )
                if id(adopted) != id(page):
                    page = adopted
                    executor = ToolExecutor(
                        page,
                        logger,
                        memory=memory,
                        synonym_resolver=synonym_resolver,
                        ats_type=state.detected_ats,
                    )
                    extractor = AccessibilityTreeExtractor(page)
                    logger.info(
                        "LLM actions opened a new tab; continuing automation there.",
                        phase=ExecutionPhase.LLM,
                        url_preview=(page.url or "")[:200],
                    )
                    # Dismiss overlays on the newly opened tab before any interaction
                    self._dismiss_cookie_consent(page, logger)
                else:
                    page = adopted

                # If we uploaded something, wait and then force the loop to continue (re-scan)
                if has_upload:
                    wait_time = 5000 if "ashby" in page.url.lower() else 3500
                    logger.info(f"Upload executed. Waiting {wait_time/1000}s for site-native autofill...", phase=ExecutionPhase.LLM)
                    page.wait_for_timeout(wait_time)
                    ax_tree = extractor.extract()
                    # We skip the rest of the loop and go to re-scan
                    continue

                # Refresh AX tree so the NEXT loop iteration sees the current filled state.
                # Without this, the LLM re-reads a stale snapshot and tries to re-fill
                # already-filled fields (or worse, targets the wrong elements).
                ax_tree = extractor.extract()

                # Save successful actions automatically
                for action in llm_response.actions:
                    if action.field_label and action.value:
                        memory.save_field_answer(action.field_label, action.value, state.detected_ats)
                    success = results.get(f"action_{llm_response.actions.index(action)}_{action.action.value}", False)
                    if success and action.value and action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT):
                        label = action.field_label or action.selector
                        memory.save_field_answer(label, action.value, state.detected_ats, success=True, source="llm")
                        if executor.last_successful_strategy:
                            memory.save_interaction(state.detected_ats, action.action.value, label, action.selector, executor.last_successful_strategy, True, page.url)
                        # Mark that the LLM made real progress so the rules fallback won't
                        # overwrite correctly-filled fields.
                        state.step_count += 1

                # --- Terminal fallback for failed actions ---
                failed_actions = executor.get_failed_actions()
                if failed_actions and not self.config.headless:
                    # Filter to actionable failures (select/fill that could use user input)
                    actionable_failures = [
                        a for a in failed_actions
                        if a.action in (ActionType.SELECT, ActionType.FILL, ActionType.TYPE)
                    ]
                    if actionable_failures:
                        print("\n" + "=" * 60)
                        print("⚠️  SOME FORM FIELDS COULD NOT BE FILLED AUTOMATICALLY ⚠️")
                        print("Please provide values for the following fields.")
                        print("Press Enter to skip a field.")
                        print("These answers will be saved for future applications.")
                        print("=" * 60)

                        for act in actionable_failures:
                            label = act.field_label or act.selector
                            current_val = act.value or ""
                            
                            # SAFETY: If we already have a value in resume/memory, DO NOT prompt.
                            # The AI failed to mechanically click/type, so let the outer loop or rules phase try.
                            if current_val and current_val.strip():
                                continue

                            if act.action == ActionType.SELECT:
                                options = executor.last_dropdown_options.get(act.selector, [])
                                if options:
                                    print(f"\nAvailable options for '{label}':")
                                    for i, opt in enumerate(options, 1):
                                        print(f"  {i}. {opt}")
                                        
                            answer = input(f"\n? {label}: ").strip()
                            if answer:
                                memory.save_field_answer(label, answer, state.detected_ats, success=True)
                                # Next loop will retry with the new memory context
                
                # Check for completion (Did we click apply, and did it navigate away or show success)
                # Here we are simplifying the check. If "Apply" or "Submit" was executed and no more actions remain.
                if not failed_actions and not ask_actions:
                    print("\n✅ Answers saved for future applications.")
                    print("=" * 60 + "\n")
                    break

            # --- Multi-page form loop ---
            # After the initial LLM pass, check if we navigated to a new page
            # (e.g., user clicked Next). If so, repeat the LLM cycle.
            MAX_PAGES = 5
            page_count = 1
            
            while page_count < MAX_PAGES:
                # Check overall success of this page
                total = len(results)
                successes = sum(1 for v in results.values() if v)
                
                if total == 0 or (successes / total) < 0.5:
                    logger.info(f"LLM page {page_count} result: {successes}/{total} actions succeeded", phase=ExecutionPhase.LLM)
                    break
                
                logger.info(f"LLM page {page_count} result: {successes}/{total} actions succeeded", phase=ExecutionPhase.LLM)
                
                # Check for mandatory fields that are still empty
                required_but_empty = []
                for field in ax_tree.form_fields:
                    is_required = field.get("required") or "*" in field.get("label", "")
                    curr_val = field.get("value")
                    if is_required and not curr_val:
                        label = field.get("label") or field.get("name")
                        required_but_empty.append(label)
                
                if required_but_empty:
                    print("\n" + "!" * 40)
                    for lbl in required_but_empty:
                        logger.warning(f"Mandatory field '{lbl}' is empty. No answer found in memory.", phase=ExecutionPhase.LLM)
                    print("!" * 40 + "\n")

                # Give user a chance to manually interact with the browser
                if not self.config.headless:
                    print(f"⏳ Page {page_count} partially filled. You have 8 seconds to manually fix any empty fields.")
                    watched_names = [f.get("label") or f.get("name") for f in ax_tree.form_fields if (f.get("label") or f.get("name"))]
                    if watched_names:
                        unique_names = list(dict.fromkeys(watched_names))
                        print(f"   (Watching: {', '.join(unique_names[:8])}{'...' if len(unique_names) > 8 else ''})")
                    print("   Press ENTER to continue immediately, or wait for auto-continue.")
                    
                    try:
                        # Non-blocking wait: auto-continue after 8 seconds
                        import msvcrt
                        import time as _time
                        start = _time.time()
                        while (_time.time() - start) < 8:
                            if msvcrt.kbhit():
                                msvcrt.getch()
                                break
                            _time.sleep(0.2)
                    except (ImportError, Exception):
                        # Fallback for non-Windows or if msvcrt fails
                        page.wait_for_timeout(8000)
                    print("   ▶ Continuing automation...")
                
                # Wait for potential page transition after Next/Continue click
                page.wait_for_timeout(3000)
                
                # Dismiss cookie consent on new page
                self._dismiss_cookie_consent(page, logger)
                
                # Check for Captcha
                from jobcli.core.anti_bot import AntiBotManager
                anti_bot = AntiBotManager(logger)
                if anti_bot.detect_captcha(page):
                    logger.warning("CAPTCHA detected. Pausing for human intervention.", phase=ExecutionPhase.LLM)
                    if not self.config.headless:
                        print("\n" + "=" * 60)
                        print("🤖 CAPTCHA OR VERIFICATION DETECTED 🤖")
                        print("Please complete any CAPTCHAs in the browser.")
                        print("Once done, press ENTER here to continue.")
                        print("=" * 60 + "\n")
                        input("Press ENTER to continue: ")
                    else:
                        logger.error("CAPTCHA detected in headless mode. Cannot solve.", phase=ExecutionPhase.LLM)
                        return False
                
                # Wait for any SPA transitions or dynamic content loads
                page.wait_for_timeout(2000)
                
                # Check if there's a new form to fill (re-extract AX tree)
                new_ax_tree = extractor.extract()
                
                # Build list of already-filled fields to tell LLM to skip them
                filled_fields = []
                placeholders = ["select", "choose", "please choose", "select...", "select an option"]
                
                for field in new_ax_tree.form_fields:
                    val = str(field.get("value", "")).strip()
                    label = field.get("name", "unknown")
                    
                    # Treat placeholders as empty
                    is_placeholder = val.lower() in placeholders or val == ""
                    
                    if not is_placeholder:
                        filled_fields.append(f"- {label}: already has value '{val}'")
                        
                        # PERSISTENCE: Save manually filled fields to memory for future use
                        if memory.save_field_answer(label, val, state.detected_ats, source="human"):
                            logger.info(f"Learned answer for '{label}' from browser manual input.", phase=ExecutionPhase.LLM)
                
                # Compare: if URL unchanged AND form fields unchanged, we're done
                url_changed = new_ax_tree.url != ax_tree.url
                
                # Deep compare of fields (including values and checked state)
                fields_changed = False
                if len(new_ax_tree.form_fields) != len(ax_tree.form_fields):
                    fields_changed = True
                else:
                    for i, field in enumerate(new_ax_tree.form_fields):
                        old_field = ax_tree.form_fields[i]
                        # Compare normalized values to avoid trivial differences
                        if str(field.get("value", "")).strip() != str(old_field.get("value", "")).strip() or \
                           bool(field.get("checked")) != bool(old_field.get("checked")):
                            fields_changed = True
                            break
                
                # If a button was clicked (e.g. 'Next', 'Continue'), the page might have changed 
                button_clicked = any(a.action == ActionType.CLICK for a in (llm_response.actions if 'llm_response' in locals() else []))
                
                if not url_changed and not fields_changed and not button_clicked:
                    logger.info("No more actions needed or manual changes detected. Finish page fill loop.", phase=ExecutionPhase.LLM)
                    break
                
                filled_context = ""
                if filled_fields:
                    filled_context = "\n## ALREADY FILLED FIELDS (DO NOT re-fill these):\n" + "\n".join(filled_fields)
                
                # New page detected — run another LLM cycle
                page_count += 1
                
                if url_changed:
                    logger.info(f"Agent successfully traversed to a new Node. URL changed from {ax_tree.url} to {new_ax_tree.url}.", phase=ExecutionPhase.LLM)
                    # Dismiss overlays that may have appeared on the newly loaded page
                    self._dismiss_cookie_consent(page, logger)
                else:
                    logger.info("Agent detected dynamic DOM updates or new fields on the same page.", phase=ExecutionPhase.LLM)

                ax_tree = new_ax_tree
                
                # Verify if we are missing common bottom-of-page fields
                # Rippling/Workday/etc. often hide these until scrolled or later pages
                mandatory_keywords = ["gender", "veteran", "disability", "authorization", "visa", "legal"]
                found_in_tree = any(any(k in f.get("name", "").lower() for k in mandatory_keywords) for f in ax_tree.form_fields)
                
                if not found_in_tree and page_count < 4:
                    logger.info("Bottom-of-page fields (Gender/Auth) missing. Scrolling down...", phase=ExecutionPhase.LLM)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    ax_tree = extractor.extract()
                
                logger.info(f"New form page/node detected (page {page_count}). Running LLM again with updated context.", phase=ExecutionPhase.LLM)
                
                logger.save_structured_dom(ax_tree.model_dump(), f"ax_tree_page_{page_count}", ExecutionPhase.LLM)
                
                memory_context = (memory.build_llm_context(state.detected_ats) or "") + filled_context
                llm_response = llm_client.analyze_page_from_axtree(
                    ax_tree, self.resume,
                    task="fill_empty_fields_only",
                    memory_context=memory_context,
                    dropdown_options=ax_tree.dropdown_fields,
                    resume_pdf_path=self.config.resume_pdf_path,
                )
                
                if not llm_response:
                    logger.warning("LLM returned no response for new page.", phase=ExecutionPhase.LLM)
                    break

                _strip_apply_clicks_when_filling_only(llm_response, "fill_empty_fields_only")
                llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.ASK]
                ctx2 = page.context
                pids1 = {id(p) for p in ctx2.pages}
                url1 = page.url
                n1 = len(ctx2.pages)
                results = executor.execute_actions(llm_response)
                adopted2 = adopt_application_page_after_action(
                    page,
                    page_count_before=n1,
                    url_before=url1,
                    page_ids_before=pids1,
                    logger=logger,
                )
                if id(adopted2) != id(page):
                    page = adopted2
                    executor = ToolExecutor(
                        page,
                        logger,
                        memory=memory,
                        synonym_resolver=synonym_resolver,
                        ats_type=state.detected_ats,
                    )
                    extractor = AccessibilityTreeExtractor(page)
                    logger.info(
                        "LLM actions opened a new tab (multi-page loop); continuing there.",
                        phase=ExecutionPhase.LLM,
                        url_preview=(page.url or "")[:200],
                    )
                    # Dismiss overlays on the newly opened tab
                    self._dismiss_cookie_consent(page, logger)
                else:
                    page = adopted2

            # Final verification of mandatory fields before finishing Phase 2
            required_missing = []
            for field in ax_tree.form_fields:
               if field.get("required") or "*" in field.get("name", ""):
                   if not field.get("value") or not str(field.get("value")).strip():
                       required_missing.append(field.get("name", "unknown"))
            
            if required_missing and page_count < 5:
                logger.warning(f"Mandatory fields still empty: {required_missing}. Attempting one more fill cycle.", phase=ExecutionPhase.LLM)
                # This will naturally trigger a re-scan in the outer loop if we can structure it to continue
            
            # Final success evaluation: Check if we actually ended on a success page or have red marks
            red_marks = page.locator(".error, .invalid, [aria-invalid='true'], .red-text").count()
            if red_marks > 0:
                logger.warning(f"{red_marks} validation errors (red marks) detected on page. Application might not be submitted correctly.", phase=ExecutionPhase.LLM)
                if not self.config.headless:
                     page.wait_for_timeout(2000)

            total = len(results)
            successes = sum(1 for v in results.values() if v)
            
            # If we didn't fill many things, it might be a failure unless we are on a confirmation page
            _confirmation_texts = [
                "Thank you",
                "application submitted",
                "application is received",
                "successfully submitted",
                "application received",
            ]
            _text_confirmed = any(
                page.locator(f"text={t}").count() > 0
                for t in _confirmation_texts
            )
            is_confirmation = any(term in page.url.lower() for term in ["success", "confirmation", "thank-you"]) or _text_confirmed
            
            success = is_confirmation or (total > 0 and (successes / total) >= 0.5)
            
            if success:
                logger.info("Application appears successfully submitted!", phase=ExecutionPhase.LLM, success=True)
            else:
                logger.error("Application submission could not be verified.", phase=ExecutionPhase.LLM, success=False)

            logger.log_phase_end(ExecutionPhase.LLM, success)

            if success:
                page.wait_for_timeout(1000)
                logger.capture_screenshot(page, "llm_success", ExecutionPhase.LLM)

            return success

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Phase 2 failed: {e}", phase=ExecutionPhase.LLM)
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return False

    def _phase_human(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
        apply_was_clicked: bool = False,
    ) -> bool:
        """Phase 3: Human in the loop."""
        logger.log_phase_start(ExecutionPhase.HUMAN)
        state.current_phase = ExecutionPhase.HUMAN

        try:
            # Initialize human interface
            human = HumanInterface(page, self.locator_repo, logger)

            if not apply_was_clicked:
                # Only ask to find apply button if it hasn't been clicked yet
                success, selector, selector_type = human.request_help(
                    "find_apply_button",
                    ats_type,
                )

                if not success or not selector:
                    logger.warning("Human declined to help")
                    logger.log_phase_end(ExecutionPhase.HUMAN, False)
                    return False

                # Click apply button
                try:
                    if selector_type and selector_type.value == "css":
                        page.click(selector)
                    elif selector_type and selector_type.value == "xpath":
                        page.click(f"xpath={selector}")

                    logger.info("Clicked apply button with human help")
                    self._random_delay()
                    logger.capture_screenshot(page, "human_apply_click", ExecutionPhase.HUMAN)

                except Exception as e:
                    human.show_error(f"Failed to click: {e}")
                    return False

                human.show_success("Apply button clicked successfully")
            else:
                human.show_success("Apply was already clicked. Form should be visible.")

            # Show user the current state
            print("\n" + "=" * 60)
            print("🖐️  HUMAN-IN-THE-LOOP: Please review the browser window.")
            print("The form should be visible. You can manually fill any")
            print("remaining fields in the browser window now.")
            print("=" * 60)

            if not human.ask_continue():
                return False

            # Try to find and click submit
            print("\nLooking for submit button...")

            # Try multiple submit button patterns
            content_root = page
            # Check for iframe
            for pattern in ["greenhouse.io", "lever.co", "workday.com"]:
                try:
                    if page.locator(f"iframe[src*='{pattern}']").count() > 0:
                        content_root = page.frame_locator(f"iframe[src*='{pattern}']").first
                        break
                except Exception:
                    pass

            submit_patterns = [
                lambda: content_root.get_by_role("button", name="Submit", exact=False).first,
                lambda: content_root.get_by_role("button", name="Submit application", exact=False).first,
                lambda: content_root.get_by_text("Submit", exact=False).first,
                lambda: content_root.locator("button[type='submit']").first,
                lambda: content_root.locator("input[type='submit']").first,
            ]

            for get_submit in submit_patterns:
                try:
                    btn = get_submit()
                    if btn.is_visible(timeout=2000):
                        btn.scroll_into_view_if_needed(timeout=1000)
                        btn.click(timeout=3000)
                        logger.info("Clicked submit button")
                        human.show_success("Application submitted!")
                        logger.log_phase_end(ExecutionPhase.HUMAN, True)
                        return True
                except Exception:
                    continue

            # If no submit button found automatically, ask human
            print("\n⚠️  Could not find submit button automatically.")
            success, selector, selector_type = human.request_help(
                "find_submit_button",
                ats_type,
            )

            if success and selector:
                if selector_type and selector_type.value == "css":
                    page.click(selector)
                elif selector_type and selector_type.value == "xpath":
                    page.click(f"xpath={selector}")

                human.show_success("Application submitted!")
                logger.log_phase_end(ExecutionPhase.HUMAN, True)
                return True

            logger.log_phase_end(ExecutionPhase.HUMAN, False)
            return False

        except Exception as e:
            logger.error(f"Phase 3 failed: {e}", phase=ExecutionPhase.HUMAN)
            logger.log_phase_end(ExecutionPhase.HUMAN, False)
            return False

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
