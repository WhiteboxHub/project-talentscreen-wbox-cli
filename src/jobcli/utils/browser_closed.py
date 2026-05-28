"""Detect when the user closes the Playwright browser during apply."""


class BrowserClosed(Exception):
    """Raised when the visible Chrome window is closed during automation."""

    def __init__(self, message: str = "User closed the browser window") -> None:
        super().__init__(message)


BROWSER_CLOSED_SENTINEL = "__BROWSER_CLOSED__"


def is_playwright_page_closed(page: object | None) -> bool:
    """Return True if the Playwright page (or its context) is no longer available."""
    if page is None:
        return True
    try:
        if getattr(page, "is_closed", None) and page.is_closed():
            return True
    except Exception:
        return True
    try:
        ctx = getattr(page, "context", None)
        if ctx is not None and getattr(ctx, "browser", None) is not None:
            browser = ctx.browser
            if browser is not None and getattr(browser, "is_connected", None) and not browser.is_connected():
                return True
    except Exception:
        return True
    return False
