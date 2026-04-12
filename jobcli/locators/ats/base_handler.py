"""Base ATS handler interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ApplicationState, ResumeData


class BaseATSHandler(ABC):
    """Base class for ATS-specific handlers."""

    def __init__(
        self,
        page: Page,
        resume: ResumeData,
        logger: Optional[JobLogger] = None,
    ) -> None:
        """Initialize handler."""
        self.page = page
        self.resume = resume
        self.logger = logger

    @abstractmethod
    def find_apply_button(self) -> bool:
        """Find and click the apply button."""
        pass

    @abstractmethod
    def detect_form_fields(self) -> list[str]:
        """Detect available form fields."""
        pass

    @abstractmethod
    def fill_form(self, resume_path: Optional[str] = None) -> dict[str, Any]:
        """Fill the application form."""
        pass

    @abstractmethod
    def submit_application(self) -> bool:
        """Submit the application."""
        pass

    @abstractmethod
    def handle_multi_step(self, state: ApplicationState) -> bool:
        """Handle multi-step application flow."""
        pass

    def wait_for_page_load(self, timeout: int = 5000) -> None:
        """Wait for page to load."""
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Page load timeout: {e}")

    def check_for_errors(self) -> Optional[str]:
        """Check for error messages on the page."""
        error_selectors = [
            ".error",
            ".error-message",
            ".alert-error",
            "[role='alert']",
            ".validation-error",
        ]

        for selector in error_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    return element.text_content() or "Unknown error"
            except Exception:
                continue

        return None
