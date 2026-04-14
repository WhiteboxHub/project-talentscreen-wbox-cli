"""Discovery logic for Whitebox Learning dashboard."""

import os
import time
from typing import List, Optional

from playwright.sync_api import sync_playwright
from sqlalchemy.orm import Session

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from jobcli.core.logger import JobLogger, global_logger
from jobcli.core.schemas import ApplicationStatus, Job
from jobcli.storage.repositories import JobRepository


class WboxDiscoverer:
    """Discover jobs from Whitebox Learning dashboard."""

    def __init__(self, session: Session, logger: Optional[JobLogger] = None) -> None:
        """Initialize discoverer."""
        self.session = session
        self.logger = logger or global_logger  # Fallback to global logger
        self.job_repo = JobRepository(session)
        
        # Load URLs from environment
        self.login_url = os.getenv("WBOX_LOGIN_URL", "https://whitebox-learning.com/login")
        self.dashboard_url = os.getenv("WBOX_DASHBOARD_URL", "https://whitebox-learning.com/user_dashboard")
        
        # Credentials
        self.username = os.getenv("JOBCLI_USERNAME")
        self.password = os.getenv("JOBCLI_PASSWORD")

    def discover(self, headless: bool = True) -> List[Job]:
        """Discover jobs from dashboard."""
        discovered_jobs: List[Job] = []
        
        if not self.username or not self.password:
            if self.logger:
                self.logger.error("Missing credentials for Wbox login")
            return []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                # 1. Login
                if self.logger:
                    self.logger.info(f"Logging into {self.login_url}")
                
                page.goto(self.login_url)
                page.fill('input[name="email"]', self.username)
                page.fill('input[name="password"]', self.password)
                page.click('button:has-text("Login")')
                
                # Wait for dashboard or redirect
                page.wait_for_url("**/user_dashboard**", timeout=30000)
                
                if self.logger:
                    self.logger.info("Successfully logged in, navigating to dashboard")
                
                page.goto(self.dashboard_url)
                
                # Wait for grid to be fully loaded
                page.wait_for_load_state("networkidle")
                page.wait_for_selector(".ag-center-cols-container", timeout=30000)
                
                # Extraction phase
                if self.logger:
                    self.logger.info("Extracting job links from grid")
                
                # Give it a moment to ensure all cells are rendered
                time.sleep(5)
                
                # Identify links
                links = page.query_selector_all('a.font-semibold.text-blue-600')
                
                for link in links:
                    url = link.get_attribute("href")
                    title = link.inner_text().strip()
                    
                    if url and title:
                        # Check if job already exists
                        existing = self.job_repo.get_by_url(url)
                        if not existing:
                            job = Job(
                                url=url,
                                title=title,
                                status=ApplicationStatus.PENDING
                            )
                            # Try to find company name in parent row if possible
                            try:
                                # Row -> Cell -> Link
                                row = link.evaluate_handle('el => el.closest(".ag-row")')
                                if row:
                                    company_cell = row.as_element().query_selector('[col-id="company"]')
                                    if company_cell:
                                        job.company = company_cell.inner_text().strip()
                            except Exception:
                                pass
                                
                            self.job_repo.create(job)
                            discovered_jobs.append(job)

                if self.logger:
                    self.logger.info(f"Discovered {len(discovered_jobs)} new jobs")

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Discovery failed: {str(e)}")
                raise e
            finally:
                browser.close()
                
        return discovered_jobs

    def open_interactive(self) -> None:
        """Open dashboard in an interactive browser window."""
        if not self.username or not self.password:
            raise ValueError("Missing credentials for Wbox login")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # 1. Login
            page.goto(self.login_url)
            page.fill('input[name="email"]', self.username)
            page.fill('input[name="password"]', self.password)
            page.click('button:has-text("Login")')
            
            # Wait for dashboard
            page.wait_for_url("**/user_dashboard**", timeout=30000)
            
            print("\n[bold green]✓ Dashboard opened and logged in![/bold green]")
            print("The browser will remain open until you close the terminal or interrupt this command.")
            
            # Keep open
            page.wait_for_event("close", timeout=0)
