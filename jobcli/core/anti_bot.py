"""Anti-bot detection and countermeasures."""

import random
import time
from typing import Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger


class AntiBotManager:
    """Manage anti-bot detection strategies."""

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(self, logger: Optional[JobLogger] = None) -> None:
        """Initialize anti-bot manager."""
        self.logger = logger

    @staticmethod
    def get_random_user_agent() -> str:
        """Get random user agent string."""
        return random.choice(AntiBotManager.USER_AGENTS)

    def random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Add random delay to mimic human behavior."""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def human_like_typing(self, page: Page, selector: str, text: str) -> None:
        """Type text with human-like delays."""
        element = page.query_selector(selector)
        if not element:
            return

        # Clear existing text
        element.fill("")

        # Type character by character with random delays
        for char in text:
            element.type(char)
            # Random delay between keystrokes (50-150ms)
            time.sleep(random.uniform(0.05, 0.15))

    def human_like_click(self, page: Page, selector: str) -> bool:
        """Click with human-like behavior."""
        try:
            element = page.query_selector(selector)
            if not element:
                return False

            # Scroll element into view
            element.scroll_into_view_if_needed()

            # Random delay before click
            time.sleep(random.uniform(0.1, 0.3))

            # Hover before clicking
            element.hover()
            time.sleep(random.uniform(0.05, 0.15))

            # Click
            element.click()

            return True

        except Exception:
            return False

    def detect_captcha(self, page: Page) -> bool:
        """Detect if CAPTCHA is present on page."""
        captcha_indicators = [
            "recaptcha",
            "g-recaptcha",
            "captcha",
            "hcaptcha",
            "h-captcha",
            "cf-challenge",
            "cloudflare",
        ]

        try:
            html = page.content().lower()

            for indicator in captcha_indicators:
                if indicator in html:
                    if self.logger:
                        self.logger.warning(
                            f"CAPTCHA detected: {indicator}",
                        )
                    return True

            return False

        except Exception:
            return False

    def detect_bot_block(self, page: Page) -> bool:
        """Detect if page shows bot blocking message."""
        block_indicators = [
            "access denied",
            "blocked",
            "suspicious activity",
            "automated access",
            "bot detected",
            "please verify you are human",
        ]

        try:
            text = page.text_content("body") or ""
            text_lower = text.lower()

            for indicator in block_indicators:
                if indicator in text_lower:
                    if self.logger:
                        self.logger.warning(
                            f"Bot block detected: {indicator}",
                        )
                    return True

            return False

        except Exception:
            return False

    def handle_rate_limit(self, attempt: int) -> None:
        """Handle rate limiting with exponential backoff."""
        # Exponential backoff: 2^attempt seconds, max 60 seconds
        delay = min(2**attempt, 60)

        # Add jitter
        delay = delay + random.uniform(0, delay * 0.1)

        if self.logger:
            self.logger.warning(
                f"Rate limit detected, waiting {delay:.1f} seconds",
            )

        time.sleep(delay)


class RetryManager:
    """Manage retry logic with exponential backoff."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        logger: Optional[JobLogger] = None,
    ) -> None:
        """Initialize retry manager."""
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.logger = logger

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        # Exponential backoff with jitter
        delay = min(
            self.initial_delay * (self.exponential_base**attempt),
            self.max_delay,
        )

        # Add random jitter (±10%)
        jitter = random.uniform(-0.1 * delay, 0.1 * delay)
        return delay + jitter

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if should retry based on attempt and error."""
        if attempt >= self.max_retries:
            return False

        # List of retryable errors
        retryable_errors = [
            "timeout",
            "network",
            "connection",
            "temporary",
            "rate limit",
        ]

        error_str = str(error).lower()
        return any(err in error_str for err in retryable_errors)


class TimeoutManager:
    """Manage operation timeouts."""

    DEFAULT_TIMEOUTS = {
        "page_load": 30000,  # 30 seconds
        "click": 5000,  # 5 seconds
        "type": 3000,  # 3 seconds
        "wait": 10000,  # 10 seconds
        "upload": 15000,  # 15 seconds
    }

    def __init__(self, custom_timeouts: Optional[dict[str, int]] = None) -> None:
        """Initialize timeout manager."""
        self.timeouts = self.DEFAULT_TIMEOUTS.copy()
        if custom_timeouts:
            self.timeouts.update(custom_timeouts)

    def get_timeout(self, operation: str) -> int:
        """Get timeout for operation."""
        return self.timeouts.get(operation, 5000)


class ErrorHandler:
    """Handle and categorize errors."""

    ERROR_CATEGORIES = {
        "network": [
            "net::ERR_",
            "NetworkError",
            "Connection refused",
            "Connection reset",
        ],
        "timeout": ["Timeout", "timeout exceeded", "Waiting failed"],
        "element_not_found": [
            "Element not found",
            "No element found",
            "Selector not found",
        ],
        "captcha": ["CAPTCHA", "recaptcha", "hcaptcha"],
        "access_denied": ["Access Denied", "403", "401", "Unauthorized"],
        "rate_limit": ["Too many requests", "Rate limit", "429"],
    }

    def __init__(self, logger: Optional[JobLogger] = None) -> None:
        """Initialize error handler."""
        self.logger = logger

    def categorize_error(self, error: Exception) -> str:
        """Categorize error by type."""
        error_str = str(error)

        for category, patterns in self.ERROR_CATEGORIES.items():
            for pattern in patterns:
                if pattern.lower() in error_str.lower():
                    return category

        return "unknown"

    def is_retryable(self, error: Exception) -> bool:
        """Check if error is retryable."""
        category = self.categorize_error(error)

        retryable_categories = ["network", "timeout", "rate_limit"]

        return category in retryable_categories

    def handle_error(
        self,
        error: Exception,
        context: str,
        page: Optional[Page] = None,
    ) -> dict[str, str]:
        """Handle error and return info."""
        category = self.categorize_error(error)

        if self.logger:
            self.logger.error(
                f"Error in {context}",
                error=str(error),
                category=category,
            )

        # Capture screenshot on error if page available
        if page and self.logger:
            try:
                self.logger.capture_screenshot(page, f"error_{context}")
            except Exception:
                pass

        return {
            "category": category,
            "error": str(error),
            "context": context,
            "retryable": str(self.is_retryable(error)),
        }
