"""Dismiss cookie banners, privacy/terms modals, and other overlays that block clicks."""

from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ExecutionPhase

# Accept / dismiss buttons (cookies, notices, generic modals)
_ACCEPT_BUTTON_SELECTORS: tuple[str, ...] = (
    "button:has-text('Accept')",
    "button:has-text('Accept All')",
    "button:has-text('Accept Cookies')",
    "button:has-text('I Accept')",
    "button:has-text('Agree')",
    "button:has-text('Close')",
    "button:has-text('Got it')",
    ".cookie-consent__action button",
    "[data-testid='cookie-accept']",
    ".onetrust-accept-btn-handler",
    "#onetrust-accept-btn-handler",
    ".cc-btn.cc-dismiss",
)

# Privacy / legal dialogs (e.g. BMS Phenom: full-screen backdrop before form is usable)
_PRIVACY_DIALOG_SELECTORS: tuple[str, ...] = (
    "[class*='privacyAgreement'] button:has-text('OK')",
    "[class*='privacyAgreement'] button:has-text('Ok')",
    "[role='dialog'][aria-modal='true'] button:has-text('OK')",
    "[role='dialog'][aria-modal='true'] button:has-text('Ok')",
    "[role='alertdialog'] button:has-text('OK')",
    "[role='dialog'][aria-modal='true'] button:has-text('I Agree')",
    "[role='dialog'][aria-modal='true'] button:has-text('Agree')",
)


def blocking_modal_dialog_visible(page: Page, *, timeout_ms: int = 500) -> bool:
    """True when an in-page \"popup\" is likely blocking the rest of the page.

    Many career sites use ``role=\"dialog\"`` + ``aria-modal=\"true\"`` (not ``window.open``).
    While that layer is visible, typical form clicks fail with *intercepts pointer events*.
    """
    try:
        return page.locator("[role='dialog'][aria-modal='true']").first.is_visible(
            timeout=timeout_ms
        )
    except Exception:
        return False


def dismiss_blocking_overlays(
    page: Page,
    logger: Optional[JobLogger] = None,
    *,
    phase: ExecutionPhase = ExecutionPhase.RULES,
) -> None:
    """Dismiss stacked overlays (privacy dialog then cookie banner, etc.)."""
    for _ in range(4):
        if not _dismiss_one_layer(page, logger, phase=phase):
            break


def _dismiss_one_layer(
    page: Page,
    logger: Optional[JobLogger],
    *,
    phase: ExecutionPhase,
) -> bool:
    """Try one round of dismissals. Returns True if something was clicked or Escape sent."""
    # Modal with aria-modal (e.g. BMS Phenom privacy) — scope OK to the dialog tree only.
    try:
        dialog = page.locator("[role='dialog'][aria-modal='true']").first
        if dialog.is_visible(timeout=700):
            for pattern in (r"^OK$", r"^Ok$", r"^I Agree$", r"^Agree$", r"^Accept$"):
                try:
                    btn = dialog.get_by_role(
                        "button", name=re.compile(pattern, re.I)
                    ).first
                    if btn.is_visible(timeout=500):
                        btn.click(timeout=2500, force=True)
                        page.wait_for_timeout(400)
                        if logger:
                            logger.info(
                                "Dismissed modal dialog via primary button",
                                phase=phase,
                                pattern=pattern,
                            )
                        return True
                except Exception:
                    continue
            try:
                fallback = dialog.locator(
                    "button:has-text('OK'), button:has-text('Ok')"
                ).first
                if fallback.is_visible(timeout=500):
                    fallback.click(timeout=2500, force=True)
                    page.wait_for_timeout(400)
                    if logger:
                        logger.info(
                            "Dismissed modal via dialog-scoped OK button",
                            phase=phase,
                        )
                    return True
            except Exception:
                pass
    except Exception:
        pass

    for sel in _PRIVACY_DIALOG_SELECTORS + _ACCEPT_BUTTON_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=800):
                loc.click(timeout=2500, force=True)
                page.wait_for_timeout(400)
                if logger:
                    logger.info(
                        "Dismissed blocking overlay",
                        phase=phase,
                        selector=sel[:120],
                    )
                return True
        except Exception:
            continue

    try:
        modal = page.locator(
            ".cookie-consent-modal, [class*='cookie-consent'], "
            "[role='dialog'][aria-modal='true']"
        ).first
        if modal.is_visible(timeout=500):
            page.keyboard.press("Escape")
            page.wait_for_timeout(350)
            if logger:
                logger.info(
                    "Sent Escape to dismiss visible overlay",
                    phase=phase,
                )
            return True
    except Exception:
        pass

    return False
