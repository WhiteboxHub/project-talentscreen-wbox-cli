"""Core execution engine with three-phase strategy."""

import random
import time
import re
from typing import Optional

from playwright.sync_api import Page, sync_playwright

from jobcli.core.logger import JobLogger, global_logger
from jobcli.core.schemas import (
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
from jobcli.locators.apply_button import ApplyButtonLocator
from jobcli.locators.ats.handler_factory import ATSHandlerFactory
from jobcli.locators.ats_detector import ATSDetector
from jobcli.locators.form_fields import FormFiller
from jobcli.storage.models import Database
from jobcli.storage.repositories import (
    ApplicationLogRepository,
    JobRepository,
    LearnedLocatorRepository,
)


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
                user_agent=self.config.user_agent or None,
            )

            page = context.new_page()

            try:
                # Navigate to job
                logger.info("Navigating to job page", phase=ExecutionPhase.RULES)
                page.goto(job.url, timeout=30000)
                self._random_delay()

                # Capture initial screenshot
                logger.capture_screenshot(page, "initial", ExecutionPhase.RULES)

                # Detect ATS
                detector = ATSDetector(page, logger)
                ats_type = detector.detect(job.url)
                state.detected_ats = ats_type
                self.job_repo.update_ats_type(job.id or 0, ats_type)

                logger.info(f"Detected ATS: {ats_type.value}", phase=ExecutionPhase.RULES)

                # Phase 1: Try rule-based approach
                apply_clicked = self._click_apply_button(page, state, logger, ats_type)
                success = False

                if apply_clicked:
                    # Wait for form to load after clicking apply
                    page.wait_for_timeout(2000)
                    # Phase 1b: Try to fill form with rules
                    success = self._fill_form_rules(page, state, logger, ats_type)

                if not success:
                    # Phase 2: Try LLM reasoning (on current page state, form visible)
                    success = self._phase_llm(page, state, logger, apply_was_clicked=apply_clicked)

                if not success:
                    # Phase 3: Human in the loop
                    success = self._phase_human(page, state, logger, ats_type, apply_was_clicked=apply_clicked)

                if success:
                    logger.info("Application completed successfully")
                    self.job_repo.update_status(job.id or 0, ApplicationStatus.SUBMITTED)
                    return ApplicationStatus.SUBMITTED
                else:
                    logger.error("Application failed")
                    self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                    return ApplicationStatus.FAILED

            except Exception as e:
                logger.error(f"Application error: {e}")
                if self.config.screenshot_on_error:
                    logger.capture_screenshot(page, "error", state.current_phase)

                self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                return ApplicationStatus.FAILED

            finally:
                browser.close()
                logger.info("Browser closed")
                global_logger.info(f"Completed job {job.id}", status=state.status.value)

    def _click_apply_button(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
    ) -> bool:
        """Phase 1a: Click the apply button only."""
        try:
            handler = ATSHandlerFactory.create_handler(ats_type, page, self.resume, logger)
            if handler:
                logger.info(f"Using {ats_type.value} handler", phase=ExecutionPhase.RULES)
                return handler.find_apply_button()

            apply_locator = ApplyButtonLocator(page, logger)
            if apply_locator.click_apply_button():
                self._random_delay()
                logger.capture_screenshot(page, "after_apply_click", ExecutionPhase.RULES)
                return True
        except Exception as e:
            logger.error(f"Apply click failed: {e}", phase=ExecutionPhase.RULES)
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
                success = handler.submit_application()
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

            from jobcli.core.schemas import ActionType
            from jobcli.core.memory import AgentMemory
            from jobcli.core.synonym_resolver import SynonymResolver

            memory = AgentMemory(self.session)
            synonym_resolver = SynonymResolver()

            # Tell LLM whether apply was already clicked
            task = "fill_form_fields_only" if apply_was_clicked else "find_apply_button_and_fill_form"

            MAX_ASK_LOOPS = 3
            loop_count = 0
            executor = ToolExecutor(page, logger, memory=memory, synonym_resolver=synonym_resolver, ats_type=state.detected_ats)
            results = {}

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
                    
                # Execute actions
                llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.ASK]
                results = executor.execute_actions(llm_response)

                # Save successful actions automatically
                for action in llm_response.actions:
                    success = results.get(f"action_{llm_response.actions.index(action)}_{action.action.value}", False)
                    if success and action.value and action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT):
                        label = action.field_label or action.selector
                        memory.save_field_answer(label, action.value, state.detected_ats, success=True, source="llm")
                        if executor.last_successful_strategy:
                            memory.save_interaction(state.detected_ats, action.action.value, label, action.selector, executor.last_successful_strategy, True, page.url)

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
                            
                            if act.action == ActionType.SELECT:
                                options = executor.last_dropdown_options.get(act.selector, [])
                                if options:
                                    print(f"\nAvailable options for '{label}':")
                                    for i, opt in enumerate(options, 1):
                                        print(f"  {i}. {opt}")
                                        
                            answer = input(f"\n? {label} (attempted: {current_val}): ").strip()
                            if answer:
                                memory.save_field_answer(label, answer, state.detected_ats, success=True)
                                # Next loop will retry with the new memory context
                
                # Check for completion (Did we click apply, and did it navigate away or show success)
                # Here we are simplifying the check. If "Apply" or "Submit" was executed and no more actions remain.
                if not failed_actions and not ask_actions:
                    break
                        print("\n✅ Answers saved for future applications.")
                        print("=" * 60 + "\n")

                break

            # Check overall success (ignore failed non-critical actions like demographics)
            # Consider success if we have more successes than failures
            total = len(results)
            successes = sum(1 for v in results.values() if v)
            # At minimum, basic fields should be filled (>50% success rate)
            success = total > 0 and (successes / total) >= 0.5

            logger.info(
                f"LLM phase result: {successes}/{total} actions succeeded",
                phase=ExecutionPhase.LLM,
            )
            logger.log_phase_end(ExecutionPhase.LLM, success)

            if success:
                # Give the next step (like Demographics or Captcha) time to load
                page.wait_for_timeout(3000)
                logger.capture_screenshot(page, "llm_success", ExecutionPhase.LLM)

                # Check for Captcha
                from jobcli.core.anti_bot import AntiBotManager
                anti_bot = AntiBotManager(logger)
                if anti_bot.detect_captcha(page):
                    logger.warning(
                        "CAPTCHA detected after LLM execution. Pausing for human intervention.",
                        phase=ExecutionPhase.LLM,
                    )
                    if not self.config.headless:
                        print("\n" + "=" * 60)
                        print("🤖 CAPTCHA OR MULTI-STEP FORM DETECTED 🤖")
                        print("Please complete any remaining steps or Captchas in the browser.")
                        print("Once you reach the final Success screen, press ENTER here.")
                        print("=" * 60 + "\n")
                        input("Press ENTER to complete application: ")
                    else:
                        logger.error(
                            "CAPTCHA detected but running in headless mode. Cannot solve.",
                            phase=ExecutionPhase.LLM,
                        )
                        return False

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

    def _random_delay(self) -> None:
        """Add random delay to avoid bot detection."""
        delay = random.uniform(
            self.config.random_delay_min,
            self.config.random_delay_max,
        )
        time.sleep(delay)
