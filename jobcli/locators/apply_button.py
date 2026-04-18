"""Rule-based locators for apply buttons."""

import time
from typing import Optional

import playwright.sync_api as pw_sync

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ExecutionPhase, LocatorResult, SelectorType

# Host/path hints that the application form likely lives here (not the marketing JD tab)
_ATS_URL_HINTS: tuple[str, ...] = (
    "myworkdayjobs",
    "workday",
    "greenhouse.io",
    "lever.co",
    "icims.com",
    "taleo",
    "successfactors",
    "phenom",
    "avature",
    "smartrecruiters",
    "ashbyhq",
    "ashby.com",
    "bamboohr",
    "jobvite",
    "ultipro",
    "adp.com",
    "paylocity",
    "tbe.",
    "hr.cloud.sap",
    "dynamics.com",
    "eightfold",
    "icims",
    "jobs.",
    "career",
    "apply",
    "requisition",
    "jobdetails",
    "job/",
    "signup",
)


def _score_page_for_application_host(page: Page) -> float:
    """Prefer tabs that look like ATS / apply flows over the original job posting tab."""
    try:
        u = (page.url or "").lower()
    except Exception:
        return 0.0
    if not u or u == "about:blank" or u.startswith("chrome-error://"):
        return -1.0
    score = min(len(u), 400) * 0.001
    for kw in _ATS_URL_HINTS:
        if kw in u:
            score += 3.0
    return score


def adopt_application_page_after_action(
    page: Page,
    *,
    page_count_before: int,
    url_before: str,
    logger: Optional[JobLogger] = None,
    poll_seconds: float = 22.0,
    page_ids_before: Optional[set[int]] = None,
) -> Page:
    """After an action that may open Workday/SSO/ATS, pick the right ``Page`` to automate.

    Uses (when provided) the set of page object ids **before** the action so we do not
    rely on ``context.pages[-1]`` order, which is not guaranteed across browsers.

    Otherwise falls back to tab-count growth and same-tab URL change detection.
    """
    context = page.context
    deadline = time.monotonic() + poll_seconds

    while time.monotonic() < deadline:
        pages = list(context.pages)
        new_pages: list[Page] = []
        if page_ids_before is not None:
            new_pages = [p for p in pages if id(p) not in page_ids_before]
        elif len(pages) > page_count_before:
            new_pages = [p for p in pages if p is not page]  # weak fallback

        if new_pages:
            best = max(new_pages, key=_score_page_for_application_host)
            if _score_page_for_application_host(best) < 0:
                time.sleep(0.2)
                continue
            inner_deadline = time.monotonic() + 14.0
            while time.monotonic() < inner_deadline:
                try:
                    u = (best.url or "").strip()
                except Exception:
                    u = ""
                if u and u != "about:blank" and not u.startswith("chrome-error://"):
                    break
                time.sleep(0.15)
            try:
                best.wait_for_load_state("domcontentloaded", timeout=35000)
            except Exception:
                pass
            try:
                final_u = best.url or ""
            except Exception:
                final_u = ""
            if final_u and final_u != "about:blank":
                if logger:
                    logger.info(
                        "Continuing on new browser tab (external ATS / SSO / apply flow).",
                        phase=ExecutionPhase.RULES,
                        url_preview=final_u[:200],
                    )
                try:
                    best.bring_to_front()
                except Exception:
                    pass
                return best

        try:
            cur = (page.url or "").strip()
        except Exception:
            cur = url_before
        if cur != url_before and cur and cur != "about:blank":
            if logger:
                logger.info(
                    "Apply navigated in the same tab.",
                    phase=ExecutionPhase.RULES,
                    url_preview=cur[:200],
                )
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            return page

        time.sleep(0.2)

    if logger:
        logger.debug(
            "No new tab or URL change detected after Apply; keeping current page.",
            phase=ExecutionPhase.RULES,
        )
    return page


class ApplyButtonLocator:
    """Comprehensive apply button locator with 30+ strategies."""

    def __init__(self, page: Page, logger: Optional[JobLogger] = None) -> None:
        """Initialize locator."""
        self.page = page
        self.logger = logger

    def _try_selector(
        self, selector: str, selector_type: SelectorType, name: str
    ) -> Optional[LocatorResult]:
        """Try a single selector strategy."""
        try:
            # Check if element exists
            if selector_type == SelectorType.CSS:
                element = self.page.query_selector(selector)
            elif selector_type == SelectorType.XPATH:
                element = self.page.query_selector(f"xpath={selector}")
            elif selector_type == SelectorType.TEXT:
                element = self.page.get_by_text(selector, exact=False).first
            elif selector_type == SelectorType.ROLE:
                element = self.page.get_by_role("button", name=selector).first
            else:
                return None

            if element and element.is_visible():
                if self.logger:
                    self.logger.info(
                        f"Found apply button using {name}",
                        phase=ExecutionPhase.RULES,
                        selector=selector,
                        selector_type=selector_type.value,
                    )

                return LocatorResult(
                    success=True,
                    selector=selector,
                    selector_type=selector_type,
                    locator_name=name,
                    phase=ExecutionPhase.RULES,
                )

        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"Locator {name} failed",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )

        return None

    def find(self, retry_count: int = 0) -> Optional[LocatorResult]:
        """Find apply button using robust filtering and retries."""
        import re
        import time
        if self.logger:
            self.logger.info(f"Starting apply button search (Retry {retry_count})", phase=ExecutionPhase.RULES)

        if retry_count == 1:
            if self.logger: self.logger.warning("Retry 1 triggered: Immediate re-poll", phase=ExecutionPhase.RULES)
        elif retry_count == 2:
            if self.logger: self.logger.warning("Retry 2 triggered: Scrolling to view", phase=ExecutionPhase.RULES)
            try: self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except: pass
            time.sleep(1.0)
        elif retry_count == 3:
            if self.logger: self.logger.warning("Retry 3 triggered: Post-wait polling", phase=ExecutionPhase.RULES)
            time.sleep(2.5)
        elif retry_count > 3:
            if self.logger: self.logger.error("3 retries exhausted handling Apply Button. Passing control to LLM.", phase=ExecutionPhase.RULES)
            return LocatorResult(success=False, error="Exhausted retries", phase=ExecutionPhase.RULES)

        try:
            # Dismiss cookie banners if present
            cookie_btn = self.page.locator("#onetrust-accept-btn-handler")
            if cookie_btn.is_visible():
                cookie_btn.click(force=True, timeout=1000)
        except Exception:
            pass

        # Use Playwright python to find valid elements
        text_pattern = re.compile(r"(?i)^(Apply|Apply[ -]Now|Submit Application)$")
        exclude_pattern = re.compile(r"(?i)(similar|other|save|share|refer)")
        
        try:
            elements = self.page.locator("button, a, [role='button'], [role='link']").all()
            for i, element in enumerate(elements):
                try:
                    if not element.is_visible() or not element.is_enabled():
                        continue
                    
                    text = (element.inner_text() or element.text_content() or "").strip()
                    if text_pattern.match(text) and not exclude_pattern.search(text):
                        if self.logger:
                            self.logger.info(
                                "Found apply button via regex",
                                strategy="regex",
                                phase=ExecutionPhase.RULES,
                            )
                        # We use text pattern as locator for click
                        return LocatorResult(
                            success=True,
                            selector=text,
                            selector_type=SelectorType.TEXT,
                            locator_name="regex_exact",
                            phase=ExecutionPhase.RULES,
                        )
                except Exception:
                    continue
        except Exception as e:
            if self.logger: self.logger.debug(f"Locator scan failed: {e}")

        # If not found, recurse with incremented retry
        return self.find(retry_count + 1)

    def click_apply_button(self) -> tuple[bool, Page]:
        """Find and click Apply, then return the page to automate (new tab/popup or same page).

        Many job boards open the real application (Workday, Phenom, etc.) in a **new tab**
        or via ``window.open``; Playwright surfaces those as extra pages in the same context.
        """
        result = self.find()

        if not result or not result.success:
            return False, self.page

        page = self.page
        context = page.context
        page_ids_before = {id(p) for p in context.pages}
        page_count_before = len(context.pages)
        url_before = page.url

        try:
            selector = result.selector

            if result.selector_type == SelectorType.TEXT:
                loc = page.get_by_text(selector, exact=True).first
            elif result.selector_type == SelectorType.CSS:
                loc = page.locator(selector).first
            elif result.selector_type == SelectorType.XPATH:
                loc = page.locator(f"xpath={selector}").first
            else:
                return False, page

            new_page = None
            try:
                with context.expect_page(timeout=22000) as pm:
                    try:
                        loc.click(timeout=8000)
                    except Exception:
                        loc.click(force=True, timeout=5000)
                new_page = pm.value
            except pw_sync.TimeoutError:
                new_page = None

            if new_page is not None:
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=45000)
                except Exception:
                    pass
                try:
                    nu = (new_page.url or "").strip()
                except Exception:
                    nu = ""
                if nu and nu != "about:blank" and not nu.startswith("chrome-error://"):
                    try:
                        new_page.bring_to_front()
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(
                            "Apply opened a new tab (expect_page).",
                            phase=ExecutionPhase.RULES,
                            selector=result.selector,
                            active_url=nu[:200],
                        )
                    return True, new_page

            active = adopt_application_page_after_action(
                page,
                page_count_before=page_count_before,
                url_before=url_before,
                logger=self.logger,
                page_ids_before=page_ids_before,
            )

            if self.logger:
                self.logger.info(
                    "Apply button handled",
                    phase=ExecutionPhase.RULES,
                    selector=result.selector,
                    active_url=(active.url or "")[:200],
                )
            return True, active

        except Exception as e:
            if self.logger:
                self.logger.error(
                    "Failed to click apply button",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )
            return False, page
