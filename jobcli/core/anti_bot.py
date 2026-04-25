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

    #: Visible challenge widgets — reCAPTCHA v2, hCaptcha, Turnstile, etc.
    #: IMPORTANT: we deliberately do NOT match bare ``iframe[src*='recaptcha']``
    #: here because that matches Google's INVISIBLE reCAPTCHA v3 anchor
    #: iframe (loaded silently on thousands of ATS pages, e.g. Greenhouse,
    #: and producing no user-visible challenge).  Use the more specific
    #: reCAPTCHA v2 bframe / challenge iframes instead, which are only
    #: injected when a real puzzle is being shown to the user.
    CAPTCHA_SELECTORS = [
        # reCAPTCHA v2 — the `bframe` is the puzzle popup, NOT the always-
        # present v3 score iframe.  It only exists on-screen when the user
        # is actively being challenged.
        "iframe[src*='recaptcha/api2/bframe']",
        "iframe[src*='recaptcha/enterprise/bframe']",
        "iframe[title*='recaptcha challenge' i]",
        # hCaptcha challenge (not the invisible hcaptcha).
        "iframe[src*='hcaptcha.com/captcha']",
        "iframe[src*='hcaptcha'][src*='challenge']",
        "iframe[title*='hCaptcha challenge' i]",
        # Cloudflare Turnstile / managed challenge.
        "iframe[src*='challenges.cloudflare.com/turnstile/v0/api']",
        "iframe[src*='challenges.cloudflare.com'][src*='interactive']",
        "iframe[title*='Cloudflare' i][title*='challenge' i]",
        "#cf-challenge-running",
        "#challenge-form",
        "#challenge-running",
        "#challenge-stage",
        # ArkoseLabs / FunCaptcha — only matches when an actual challenge
        # panel is rendered, not silent background checks.
        "iframe[src*='arkoselabs'][src*='challenge']",
        "iframe[src*='funcaptcha'][src*='challenge']",
        # Generic "please verify" iframe titles (broad but safe).
        "iframe[title='I am not a robot' i]",
        "iframe[title*='security check' i]",
        # Turnstile form input appears only when interactive challenge shows.
        "input[name='cf-turnstile-response']:not([value=''])",
        # GeeTest CAPTCHA — drag-the-icon / slide-puzzle used by Lever,
        # some Workday tenants, and Chinese-market ATS platforms.
        ".geetest_panel_box",
        ".geetest_widget",
        ".geetest_holder",
        ".geetest_popup_wrap",
        "div[class*='geetest'][class*='panel']",
        "div[class*='geetest'][class*='box']",
    ]

    #: Page text indicators for bot / human-verification interstitials.
    #: Matched against the *visible* body text on small (< 4000 char)
    #: pages only — challenges are almost always sparse interstitial
    #: pages with very little other content.  The patterns below are
    #: deliberately specific phrases found on real CAPTCHA screens.
    #: Generic words like "access denied" / "blocked" were removed
    #: because they also appear in help articles and privacy boilerplate
    #: on legitimate ATS pages.
    CHALLENGE_TEXT_PATTERNS = [
        "verify you are human",
        "verify that you are human",
        "verify you're human",
        "verifying you are human",
        "prove you're human",
        "i'm not a robot",
        "checking your browser before accessing",
        "checking if the site connection is secure",
        "please wait while we verify",
        "please enable javascript and cookies",
        "press & hold to confirm",
        "complete the security check to access",
        "ddos protection by cloudflare",
        "performance & security by cloudflare",
        "attention required! cloudflare",
    ]

    #: Extremely specific CAPTCHA phrases (like puzzle instructions)
    #: that have virtually zero chance of being false positives in normal
    #: ATS content. These are checked regardless of page body size, which
    #: is required for in-page overlays like GeeTest on long Lever forms.
    HIGH_SIGNAL_CHALLENGE_PATTERNS = [
        "please drag the icon",
        "drag the icon on the left",
        "slide to verify",
        "drag the slider",
        "choose everything that you can see in the sample",
        "select all images with",
        "please click each image containing",
    ]

    def detect_captcha(self, page: Page) -> bool:
        """Detect a visible CAPTCHA / human-verification challenge on the page.

        Covers three categories:
          1. Widget iframes / elements (reCAPTCHA, hCaptcha, Cloudflare
             Turnstile, ArkoseLabs/FunCaptcha).
          2. Cloudflare / Akamai / PerimeterX interstitial challenge pages.
          3. Body-text patterns such as "Verify you are human", "Just a
             moment...", "I'm not a robot".

        When *any* of them match we return True so the engine can freeze all
        automation — any programmatic clicking/scrolling/AX-tree extraction
        while a bot challenge is active tends to flag the session and break
        the verification.
        """
        try:
            for selector in self.CAPTCHA_SELECTORS:
                try:
                    loc = page.locator(selector).first
                    if not loc.is_visible(timeout=800):
                        continue
                    # Additional sanity check: widgets like Google's
                    # invisible reCAPTCHA badge (``.grecaptcha-badge``) and
                    # the reCAPTCHA v3 score iframe are technically
                    # "visible" in Playwright's sense (non-zero box, not
                    # ``display: none``) but they're 256×60 score widgets
                    # in a corner — NOT a user-facing challenge.  Only
                    # treat an iframe as a real challenge when it's large
                    # enough to be a puzzle (>= 200px on either axis) or
                    # it's a non-iframe selector (a full-page interstitial).
                    if selector.startswith("iframe"):
                        try:
                            box = loc.bounding_box()
                        except Exception:
                            box = None
                        if box is not None:
                            w = box.get("width") or 0
                            h = box.get("height") or 0
                            if w < 200 or h < 100:
                                continue
                    if self.logger:
                        # Rich treats [...] as markup tags, so escape
                        # brackets in the selector before logging or the
                        # message renders as just "iframe".
                        safe = (selector or "").replace("[", r"\[")
                        self.logger.warning(f"CAPTCHA detected: {safe}")
                    return True
                except Exception:
                    continue

            # Title fast-path — Cloudflare's "Just a moment..." page sets this.
            try:
                title = (page.title() or "").lower()
                for needle in ("just a moment", "attention required", "access denied"):
                    if needle in title:
                        if self.logger:
                            self.logger.warning(
                                f"CAPTCHA detected via page title: '{title[:80]}'"
                            )
                        return True
            except Exception:
                pass

            # Body-text check (scan all frames since CAPTCHAs use iframes)
            try:
                frame_texts = []
                for frame in page.frames:
                    try:
                        frame_texts.append((frame.text_content("body", timeout=500) or "").strip().lower())
                    except Exception:
                        pass
                
                body = " ".join(frame_texts)
                if not body.strip():
                    return False
                
                # Check high-signal (unmistakable) phrases regardless of page size
                # because in-page CAPTCHA modals load on top of the full form.
                for pattern in self.HIGH_SIGNAL_CHALLENGE_PATTERNS:
                    if pattern in body:
                        if self.logger:
                            self.logger.warning(
                                f"High-signal CAPTCHA text detected: '{pattern}'"
                            )
                        return True

                # For generic terms (verify human, etc.), only check if the
                # page is small (interstitial challenge page) to prevent
                # false positives against privacy policy legalese.
                if len(body) < 4000:
                    for pattern in self.CHALLENGE_TEXT_PATTERNS:
                        if pattern in body:
                            if self.logger:
                                self.logger.warning(
                                    f"CAPTCHA interstitial text detected: '{pattern}'"
                                )
                            return True
            except Exception:
                pass

            return False

        except Exception:
            return False

    def wait_until_cleared(
        self,
        page: Page,
        *,
        max_wait_seconds: int = 90,
        poll_interval_seconds: float = 1.5,
    ) -> bool:
        """Poll until ``detect_captcha`` reports False (or timeout).

        The engine calls this *after* the human has pressed ENTER so we
        avoid proceeding when the challenge is still visible (browsers
        sometimes need a second to finalise the cookie set).  Returns True
        when the challenge has cleared.
        """
        import time as _t
        deadline = _t.time() + max_wait_seconds
        while _t.time() < deadline:
            if not self.detect_captcha(page):
                return True
            _t.sleep(poll_interval_seconds)
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
