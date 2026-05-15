"""Human-like interaction helpers for evading bot detection."""

from playwright.sync_api import Page, Locator, Frame
from typing import Union

def humanized_fill(page: Union[Page, Frame], locator: Locator, value: str) -> None:
    """Type into a field with human-like cadence to evade bot detection."""
    import random as _r
    import sys as _sys

    if hasattr(page, "page"):
        page = page.page

    if not value:
        return

    try:
        locator.hover(timeout=1500)
        page.wait_for_timeout(_r.randint(80, 180))
    except Exception:
        pass

    locator.click(timeout=1500)
    page.wait_for_timeout(_r.randint(120, 280))

    mod = "Meta" if _sys.platform == "darwin" else "Control"
    try:
        page.keyboard.press(f"{mod}+A")
        page.wait_for_timeout(_r.randint(30, 90))
        page.keyboard.press("Backspace")
        page.wait_for_timeout(_r.randint(40, 110))
    except Exception:
        try:
            locator.fill("")
        except Exception:
            pass

    words = value.split(" ")
    for idx, w in enumerate(words):
        if idx > 0:
            page.keyboard.type(" ", delay=_r.randint(40, 120))
        per_char_delay = _r.randint(55, 150)
        page.keyboard.type(w, delay=per_char_delay)
        if idx < len(words) - 1 and _r.random() < 0.18:
            page.wait_for_timeout(_r.randint(150, 350))

    page.wait_for_timeout(_r.randint(90, 220))
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
