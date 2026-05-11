"""Base ATS handler interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ApplicationState, ExecutionPhase, ResumeData


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

    def is_expired(self) -> bool:
        """Check for common 'Job Expired' indicators in the DOM."""
        expired_indicators = [
            "text=This job has expired",
            "text=Sorry, this job has expired",
            "text=This job is no longer available",
            "text=This position has been filled",
            "text=Job is no longer available",
            "text=The job you are looking for is no longer open",
            "text=This job posting has expired",
            "text=Position no longer available",
            "text=This role is closed",
            "text=No longer accepting applications",
            "text=This listing has been removed",
            "text=Job no longer active",
            "text=This job is closed",
            "text=The position you are looking for is filled",
        ]
        for indicator in expired_indicators:
            try:
                # Increased timeout to 2.5s to allow for slow-rendering banners.
                if self.page.locator(indicator).is_visible(timeout=2500):
                    if self.logger:
                        self.logger.info(
                            f"Detected expired job indicator: '{indicator}'",
                            phase=ExecutionPhase.RULES,
                        )
                    return True
            except Exception:
                continue

        # ── Fallback 2: Keyword scan in common message containers ────
        try:
            # Look for "expired" or "no longer available" in headers and banners
            js = r"""() => {
                const keywords = ['expired', 'no longer available', 'position filled', 'listing removed', 'listing has been removed'];
                const containers = document.querySelectorAll('h1, h2, h3, .banner, .message, .alert, .status');
                for (const el of containers) {
                    const text = (el.innerText || '').toLowerCase();
                    if (keywords.some(k => text.includes(k))) {
                        return text;
                    }
                }
                return null;
            }"""
            match_text = self.page.evaluate(js)
            if match_text:
                if self.logger:
                    self.logger.info(
                        f"Detected expiry keywords in container: '{match_text[:50]}...'",
                        phase=ExecutionPhase.RULES,
                    )
                return True
        except Exception:
            pass

        return False

    def click_option(self, question: str, value: str) -> Optional[bool]:
        """Click the option that answers *question* with *value*.

        Covers radio buttons, checkboxes, and selectable chips — the
        things a user would "click" rather than "type into". Handlers
        can override this to use ATS-specific DOM patterns (e.g. Ashby
        has a very consistent ``<fieldset><legend>…</legend>`` layout).

        Return values:
          * ``True``  — we clicked and verified the option is now selected.
          * ``False`` — we tried the ATS-specific path and it failed; the
                       caller should try a generic fallback.
          * ``None``  — no ATS-specific strategy applies to this question;
                       the caller should use its generic strategy.
        """
        return None

    def select_dropdown_option(self, question: str, value: str) -> Optional[bool]:
        """Open a dropdown for *question* and pick *value*.

        Same contract as :meth:`click_option`.
        """
        return None

    def humanized_fill(self, locator, value: str) -> None:
        """Type into a field with human-like cadence to evade bot detection."""
        import random as _r
        import sys as _sys

        if not value:
            return

        try:
            locator.scroll_into_view_if_needed(timeout=1500)
            locator.hover(timeout=1500)
            self.page.wait_for_timeout(_r.randint(80, 180))
        except Exception:
            pass

        # Use force=True to handle cases where elements like floating labels/headers
        # intercept the pointer events. Playwright's default actionability check
        # can be too strict in these scenarios.
        try:
            locator.click(timeout=1500, force=True)
        except Exception:
            # Final fallback if even forced click fails
            try:
                locator.focus(timeout=1000)
            except Exception:
                pass
        
        self.page.wait_for_timeout(_r.randint(120, 280))

        mod = "Meta" if _sys.platform == "darwin" else "Control"
        try:
            self.page.keyboard.press(f"{mod}+A")
            self.page.wait_for_timeout(_r.randint(30, 90))
            self.page.keyboard.press("Backspace")
            self.page.wait_for_timeout(_r.randint(40, 110))
        except Exception:
            try:
                locator.fill("")
            except Exception:
                pass

        words = value.split(" ")
        for idx, w in enumerate(words):
            if idx > 0:
                self.page.keyboard.type(" ", delay=_r.randint(40, 120))
            per_char_delay = _r.randint(55, 150)
            self.page.keyboard.type(w, delay=per_char_delay)
            if idx < len(words) - 1 and _r.random() < 0.18:
                self.page.wait_for_timeout(_r.randint(150, 350))

        self.page.wait_for_timeout(_r.randint(90, 220))
        try:
            self.page.keyboard.press("Tab")
        except Exception:
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
