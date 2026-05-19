"""Browser lifecycle management — isolated from application logic.

Responsibilities:
- Playwright session lifecycle (start/stop)
- Context/page creation
- Extension loading
- Resource cleanup (temp directories)
- Stealth configuration
"""

import os
import tempfile
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from jobcli.core.anti_bot import AntiBotManager
from jobcli.core.logger import JobLogger, global_logger
from jobcli.core.schemas import Config


class BrowserManager:
    """Manages Playwright browser lifecycle and resource cleanup."""

    def __init__(self, config: Config, logger: Optional[JobLogger] = None) -> None:
        """Initialize browser manager.

        Args:
            config: Application configuration
            logger: Optional job logger
        """
        self.config = config
        self.logger = logger
        self.anti_bot = AntiBotManager(logger=logger)

        # Browser session state
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.user_data_dir: Optional[str] = None
        self.extension_dir: Optional[str] = None

    def start_session(self) -> BrowserContext:
        """Start a browser session and return the context.

        Returns:
            BrowserContext ready for use

        Raises:
            RuntimeError: If session already started
        """
        if self.context:
            return self.context

        from jobcli.core.stealth import (
            CONTEXT_OPTIONS,
            IGNORE_DEFAULT_ARGS,
            LAUNCH_ARGS,
        )

        self.playwright = sync_playwright().start()

        # Validate extension path
        extension_dir = self.config.extension_path
        if extension_dir and not os.path.exists(extension_dir):
            global_logger.warning(
                f"EXTENSION_PATH '{extension_dir}' does not exist — launching without extension."
            )
            extension_dir = None

        self.extension_dir = extension_dir
        launch_args = list(LAUNCH_ARGS)

        if self.extension_dir:
            # Create temporary user data directory for extension
            self.user_data_dir = tempfile.mkdtemp(prefix="jobcli_ext_profile_")
            launch_args.extend([
                f"--disable-extensions-except={self.extension_dir}",
                f"--load-extension={self.extension_dir}"
            ])
            global_logger.info(
                f"Launching persistent browser context with extension: {self.extension_dir}"
            )

            # Persistent context (required for extensions)
            self.context = self.playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=False,  # Extensions require non-headless
                args=launch_args,
                ignore_default_args=IGNORE_DEFAULT_ARGS,
                **CONTEXT_OPTIONS,
            )
        else:
            # Standard browser (no extension)
            global_logger.info("Launching standard browser (no extension)")
            self.browser = self.playwright.chromium.launch(
                headless=self.config.headless,
                args=launch_args,
                ignore_default_args=IGNORE_DEFAULT_ARGS,
            )
            self.context = self.browser.new_context(**CONTEXT_OPTIONS)

        # Apply stealth if headless
        if self.config.headless and self.context:
            from jobcli.core.stealth import apply_stealth
            apply_stealth(self.context, logger=self.logger)

        return self.context

    def create_page(self) -> Page:
        """Create a new page in the current context.

        Returns:
            New Page instance

        Raises:
            RuntimeError: If no active context
        """
        if not self.context:
            raise RuntimeError("No active browser context. Call start_session() first.")

        return self.context.new_page()

    def stop_session(self) -> None:
        """Stop the browser session and clean up all resources.

        Safe to call multiple times (idempotent).
        Closes context, browser, Playwright, and deletes temp directories.
        """
        # Close context
        if self.context:
            try:
                self.context.close()
            except Exception as e:
                global_logger.warning(f"Failed to close context: {e}")
            finally:
                self.context = None

        # Close browser
        if self.browser:
            try:
                self.browser.close()
            except Exception as e:
                global_logger.warning(f"Failed to close browser: {e}")
            finally:
                self.browser = None

        # Stop Playwright
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                global_logger.warning(f"Failed to stop Playwright: {e}")
            finally:
                self.playwright = None

        # Clean up temporary user data directory
        if self.user_data_dir and os.path.exists(self.user_data_dir):
            try:
                import shutil
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
                global_logger.info(f"Cleaned up temp browser profile: {self.user_data_dir}")
            except Exception as e:
                global_logger.warning(f"Failed to clean temp directory: {e}")
            finally:
                self.user_data_dir = None

    def inject_resume_into_extension(
        self,
        page: Page,
        resume_data: dict,
        logger: Optional[JobLogger] = None,
    ) -> bool:
        """Inject resume data into TalentScreen extension storage.

        Args:
            page: Browser page
            resume_data: Resume JSON to inject
            logger: Optional logger

        Returns:
            True if injection succeeded
        """
        if not self.extension_dir:
            return False

        try:
            import json

            # Inject via chrome.storage.local API
            page.evaluate(
                f"""
                (async () => {{
                    const resume = {json.dumps(resume_data)};
                    if (chrome && chrome.storage && chrome.storage.local) {{
                        await chrome.storage.local.set({{ talentscreen_resume: resume }});
                    }}
                }})();
                """
            )

            if logger:
                logger.info("Injected resume data into extension storage")
            return True

        except Exception as e:
            if logger:
                logger.warning(f"Failed to inject resume into extension: {e}")
            return False

    def __enter__(self):
        """Context manager support: start session on enter."""
        self.start_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support: stop session on exit."""
        self.stop_session()
