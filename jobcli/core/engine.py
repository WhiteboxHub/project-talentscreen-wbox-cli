"""Core execution engine with three-phase strategy."""

import random
import time
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
from jobcli.llm.dom_extractor import DOMExtractor
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
                success = self._phase_rules(page, state, logger, ats_type)

                if not success:
                    # Phase 2: Try LLM reasoning
                    success = self._phase_llm(page, state, logger)

                if not success:
                    # Phase 3: Human in the loop
                    success = self._phase_human(page, state, logger, ats_type)

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

    def _phase_rules(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
    ) -> bool:
        """Phase 1: Rule-based locators."""
        logger.log_phase_start(ExecutionPhase.RULES)
        state.current_phase = ExecutionPhase.RULES

        try:
            # Try ATS-specific handler first
            handler = ATSHandlerFactory.create_handler(ats_type, page, self.resume, logger)

            if handler:
                logger.info(f"Using {ats_type.value} handler", phase=ExecutionPhase.RULES)

                # Find and click apply button
                if not handler.find_apply_button():
                    logger.warning("ATS handler failed to find apply button")
                    return False

                self._random_delay()
                logger.capture_screenshot(page, "after_apply_click", ExecutionPhase.RULES)

                # Fill form
                resume_path = self.config.resume_pdf_path
                handler.fill_form(resume_path)

                self._random_delay()
                logger.capture_screenshot(page, "form_filled", ExecutionPhase.RULES)

                # Handle multi-step if needed
                max_steps = 5
                for step in range(max_steps):
                    state.step_count = step + 1
                    should_continue = handler.handle_multi_step(state)

                    if not should_continue:
                        break

                    self._random_delay()

                # Submit
                success = handler.submit_application()
                logger.log_phase_end(ExecutionPhase.RULES, success)

                if success:
                    logger.capture_screenshot(page, "submitted", ExecutionPhase.RULES)

                return success

            else:
                # Fallback to generic locators
                logger.info("Using generic locators", phase=ExecutionPhase.RULES)

                # Find apply button
                apply_locator = ApplyButtonLocator(page, logger)
                if not apply_locator.click_apply_button():
                    logger.warning("Generic apply button locator failed")
                    return False

                self._random_delay()
                logger.capture_screenshot(page, "after_apply_click", ExecutionPhase.RULES)

                # Fill form
                form_filler = FormFiller(page, self.resume, logger)
                form_filler.fill_all(self.config.resume_pdf_path)

                self._random_delay()
                logger.capture_screenshot(page, "form_filled", ExecutionPhase.RULES)

                logger.log_phase_end(ExecutionPhase.RULES, True)
                return True

        except Exception as e:
            logger.error(f"Phase 1 failed: {e}", phase=ExecutionPhase.RULES)
            logger.log_phase_end(ExecutionPhase.RULES, False)
            return False

    def _phase_llm(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
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
            # Extract DOM
            extractor = DOMExtractor(page)
            dom_snapshot = extractor.extract()

            # Save DOM snapshot
            logger.save_structured_dom(
                dom_snapshot.model_dump(),
                "for_llm",
                ExecutionPhase.LLM,
            )

            # Initialize LLM client
            llm_client = LLMClient(provider, api_key, logger)

            # Get actions from LLM
            llm_response = llm_client.analyze_page(
                dom_snapshot,
                self.resume,
                task="find_apply_button_and_fill_form",
            )

            if not llm_response:
                logger.error("LLM returned no response")
                logger.log_phase_end(ExecutionPhase.LLM, False)
                return False

            if llm_response.requires_human:
                logger.warning("LLM requested human intervention")
                logger.log_phase_end(ExecutionPhase.LLM, False)
                return False

            # Execute actions
            executor = ToolExecutor(page, logger)
            results = executor.execute_actions(llm_response)

            success = all(results.values())
            logger.log_phase_end(ExecutionPhase.LLM, success)

            if success:
                logger.capture_screenshot(page, "llm_success", ExecutionPhase.LLM)

            return success

        except Exception as e:
            logger.error(f"Phase 2 failed: {e}", phase=ExecutionPhase.LLM)
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return False

    def _phase_human(
        self,
        page: Page,
        state: ApplicationState,
        logger: JobLogger,
        ats_type: ATSType,
    ) -> bool:
        """Phase 3: Human in the loop."""
        logger.log_phase_start(ExecutionPhase.HUMAN)
        state.current_phase = ExecutionPhase.HUMAN

        try:
            # Initialize human interface
            human = HumanInterface(page, self.locator_repo, logger)

            # Request help for apply button
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

            # Fill form with human supervision
            human.show_success("Apply button clicked successfully")

            if not human.ask_continue():
                return False

            # Use form filler
            form_filler = FormFiller(page, self.resume, logger)
            form_filler.fill_all(self.config.resume_pdf_path)

            self._random_delay()
            logger.capture_screenshot(page, "human_form_filled", ExecutionPhase.HUMAN)

            # Confirm submission
            if human.confirm_submission():
                # Try to find and click submit
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    "button:has-text('Submit')",
                ]

                for selector in submit_selectors:
                    try:
                        page.click(selector)
                        logger.info("Clicked submit button")
                        human.show_success("Application submitted!")
                        logger.log_phase_end(ExecutionPhase.HUMAN, True)
                        return True
                    except Exception:
                        continue

                # If no submit button found, ask human
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
