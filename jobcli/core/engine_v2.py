"""Enhanced execution engine with LangGraph state machine and Rich progress tracking."""

from playwright.sync_api import sync_playwright
from rich.console import Console

from jobcli.core.logger import JobLogger, global_logger
from jobcli.core.memory import AgentMemory
from jobcli.core.progress import ApplicationProgressTracker, create_status_table
from jobcli.core.schemas import (
    ApplicationState,
    ApplicationStatus,
    Config,
    Job,
    ResumeData,
)
from jobcli.core.state_machine import ApplicationStateMachine
from jobcli.core.url_normalize import normalize_job_url
from jobcli.llm.client import LLMClient
from jobcli.locators.ats_detector import ATSDetector
from jobcli.storage.models import Database
from jobcli.storage.repositories import (
    JobRepository,
    LearnedLocatorRepository,
)


class EnhancedApplicationEngine:
    """Enhanced engine with LangGraph and Rich progress tracking."""

    def __init__(
        self,
        config: Config,
        resume: ResumeData,
        database: Database,
        console: Console | None = None,
    ) -> None:
        """Initialize enhanced engine."""
        self.config = config
        self.resume = resume
        self.database = database
        self.console = console or Console()
        self.session = database.get_session()

        # Initialize repositories
        self.job_repo = JobRepository(self.session)
        self.locator_repo = LearnedLocatorRepository(self.session)

        # Initialize state machine
        self.state_machine = ApplicationStateMachine()

        # Initialize LLM client if configured
        self.llm_client = self._initialize_llm_client()

        # Statistics
        self.stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
        }

    def _initialize_llm_client(self) -> LLMClient | None:
        """Initialize LLM client based on configuration."""
        provider = self.config.default_llm_provider
        api_key = None

        if provider == "openai":
            api_key = self.config.openai_api_key
        elif provider == "anthropic":
            api_key = self.config.anthropic_api_key
        elif provider == "gemini":
            api_key = self.config.gemini_api_key

        if api_key:
            return LLMClient(provider, api_key)

        return None

    def apply_to_job(
        self,
        job: Job,
        progress_tracker: ApplicationProgressTracker | None = None,
    ) -> ApplicationStatus:
        """Apply to a single job using LangGraph state machine."""
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
                logger.info("Navigating to job page")
                if progress_tracker:
                    progress_tracker.update_action("Navigating", job.url[:50])

                page.goto(job.url, timeout=30000)

                if job.id and page.url and normalize_job_url(page.url) != normalize_job_url(job.url):
                    self.job_repo.update_resolved_url(job.id, page.url)

                # Capture initial screenshot
                logger.capture_screenshot(page, "initial")

                # Detect ATS
                detector = ATSDetector(page, logger)
                ats_type = detector.detect(job.url)
                state.detected_ats = ats_type
                self.job_repo.update_ats_type(job.id or 0, ats_type)

                logger.info(f"Detected ATS: {ats_type.value}")
                if progress_tracker:
                    progress_tracker.update_action(
                        "ATS Detected", ats_type.value.title()
                    )

                agent_memory = AgentMemory(
                    self.session,
                    infer_location_country=self.config.infer_location_country,
                    job_id=job.id,
                )
                final_status = self.state_machine.run(
                    page=page,
                    state=state,
                    resume=self.resume,
                    logger=logger,
                    ats_type=ats_type,
                    resume_pdf_path=self.config.resume_pdf_path or "",
                    locator_repo=self.locator_repo,
                    llm_client=self.llm_client,
                    agent_memory=agent_memory,
                    job_id=job.id,
                    job_repo=self.job_repo,
                    job_board_url=job.url,
                    infer_location_country=self.config.infer_location_country,
                )

                # Update job status
                self.job_repo.update_status(job.id or 0, final_status)

                # Update statistics
                self.stats["processed"] += 1
                if final_status == ApplicationStatus.SUBMITTED:
                    self.stats["successful"] += 1
                elif final_status == ApplicationStatus.SKIPPED:
                    self.stats["skipped"] += 1
                else:
                    self.stats["failed"] += 1

                logger.info(f"Application completed with status: {final_status.value}")
                return final_status

            except Exception as e:
                logger.error(f"Application error: {e}")
                if self.config.screenshot_on_error:
                    logger.capture_screenshot(page, "error")

                self.job_repo.update_status(job.id or 0, ApplicationStatus.FAILED)
                self.stats["processed"] += 1
                self.stats["failed"] += 1

                return ApplicationStatus.FAILED

            finally:
                browser.close()
                logger.info("Browser closed")

    def apply_to_jobs_batch(self, jobs: list[Job]) -> dict[str, int]:
        """Apply to multiple jobs with progress tracking."""
        progress_tracker = ApplicationProgressTracker(self.console)
        progress_tracker.start_batch(len(jobs))

        with progress_tracker.display():
            for i, job in enumerate(jobs, 1):
                try:
                    progress_tracker.start_job(job.url, i, len(jobs))

                    status = self.apply_to_job(job, progress_tracker)

                    progress_tracker.end_job(
                        success=(status == ApplicationStatus.SUBMITTED)
                    )

                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Interrupted by user[/yellow]")
                    break

                except Exception as e:
                    self.console.print(f"\n[red]Error: {e}[/red]")
                    progress_tracker.end_job(success=False)
                    continue

        # Display summary
        summary_table = create_status_table(
            jobs_processed=self.stats["processed"],
            jobs_successful=self.stats["successful"],
            jobs_failed=self.stats["failed"],
            jobs_skipped=self.stats["skipped"],
        )

        self.console.print("\n")
        self.console.print(summary_table)

        return self.stats

    def get_statistics(self) -> dict[str, int]:
        """Get application statistics."""
        return self.stats.copy()
