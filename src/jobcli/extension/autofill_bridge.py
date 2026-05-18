"""Bridge JobCLI (Playwright) to TalentScreen v2 ``window.AutofillExtension``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from jobcli.profile.resume_export import resume_to_json_resume
from jobcli.profile.schemas import CommonQuestions, ResumeData
from jobcli.utils.logger import JobLogger


@dataclass
class ExtensionAutofillOptions:
    """Options passed to ``AutofillExtension.configure`` / ``fill``."""

    confidence_threshold: float = 0.7
    fill_eeo: bool = False
    fill_legal: bool = False
    fill_sensitive: bool = False
    preserve_user_values: bool = True
    api_timeout_ms: int = 30_000
    form_wait_timeout_ms: int = 15_000


@dataclass
class ExtensionAutofillResult:
    """Outcome of a single extension autofill attempt."""

    api_available: bool = False
    inject_success: bool = False
    fill_success: bool = False
    inject_error: Optional[str] = None
    validation_errors: list[str] = field(default_factory=list)
    fill_result: Optional[dict[str, Any]] = None
    report: Optional[dict[str, Any]] = None

    @property
    def fields_filled_count(self) -> int:
        if not self.fill_result:
            return 0
        filled = self.fill_result.get("fields", {}).get("filled") or []
        return len(filled)

    @property
    def completion_percentage(self) -> float:
        if not self.fill_result:
            return 0.0
        comp = self.fill_result.get("completion") or {}
        return float(comp.get("percentage") or 0.0)


def extension_api_available(page: Page) -> bool:
    """Return True if ``window.AutofillExtension`` is defined on *page*."""
    try:
        return bool(
            page.evaluate("() => typeof window.AutofillExtension !== 'undefined'")
        )
    except Exception:
        return False


def wait_for_autofill_api(page: Page, timeout_ms: int = 30_000) -> bool:
    """Block until ``window.AutofillExtension`` exists or timeout."""
    try:
        page.wait_for_function(
            "() => typeof window.AutofillExtension !== 'undefined'",
            timeout=timeout_ms,
        )
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False


def run_extension_autofill(
    page: Page,
    resume: ResumeData,
    logger: Optional[JobLogger] = None,
    questions: Optional[CommonQuestions] = None,
    options: Optional[ExtensionAutofillOptions] = None,
) -> ExtensionAutofillResult:
    """Inject profile and fill the current page via TalentScreen v2 API."""
    opts = options or ExtensionAutofillOptions()
    out = ExtensionAutofillResult()

    if not wait_for_autofill_api(page, timeout_ms=opts.api_timeout_ms):
        out.inject_error = "window.AutofillExtension not available on this page"
        if logger:
            logger.warning(
                "TalentScreen API unavailable (unsupported URL or content script not injected). "
                "Continuing with rules/LLM only.",
            )
        return out

    out.api_available = True

    try:
        page.wait_for_selector("input, textarea, select", timeout=opts.form_wait_timeout_ms)
    except PlaywrightTimeoutError:
        if logger:
            logger.debug("No form controls found before extension autofill; proceeding anyway.")

    profile = resume_to_json_resume(resume, questions=questions)

    inject = page.evaluate(
        "(p) => window.AutofillExtension.injectProfile(p)",
        profile,
    )
    if not isinstance(inject, dict):
        out.inject_error = "injectProfile returned unexpected value"
        return out

    if not inject.get("success"):
        out.inject_error = str(inject.get("error") or "injectProfile failed")
        errs = inject.get("validationErrors")
        if isinstance(errs, list):
            out.validation_errors = [str(e) for e in errs]
        if logger:
            logger.warning(f"Extension injectProfile failed: {out.inject_error}")
        return out

    out.inject_success = True
    if logger:
        logger.info(
            f"Extension profile injected (schema {inject.get('schemaVersion', '?')}).",
        )

    page.evaluate(
        """(o) => window.AutofillExtension.configure({
            confidenceThreshold: o.confidenceThreshold,
            fillEEO: o.fillEEO,
            fillLegal: o.fillLegal,
            fillSensitive: o.fillSensitive,
            preserveUserValues: o.preserveUserValues,
            pauseOnLowConfidence: true,
            pauseOnMissingData: true,
            pauseOnCAPTCHA: true,
        })""",
        {
            "confidenceThreshold": opts.confidence_threshold,
            "fillEEO": opts.fill_eeo,
            "fillLegal": opts.fill_legal,
            "fillSensitive": opts.fill_sensitive,
            "preserveUserValues": opts.preserve_user_values,
        },
    )

    fill_result = page.evaluate(
        "(p) => window.AutofillExtension.fill(p)",
        profile,
    )
    if isinstance(fill_result, dict):
        out.fill_result = fill_result
        out.fill_success = True
        comp = fill_result.get("completion") or {}
        pct = comp.get("percentage", 0)
        filled_n = len((fill_result.get("fields") or {}).get("filled") or [])
        failed_n = len((fill_result.get("fields") or {}).get("failed") or [])
        if logger:
            logger.info(
                f"Extension autofill complete: {filled_n} filled, {failed_n} failed, "
                f"{pct}% completion.",
            )
        for err in fill_result.get("errors") or []:
            if logger and err:
                logger.debug(f"Extension fill error: {err}")

    try:
        out.report = page.evaluate("() => window.AutofillExtension.exportReport()")
    except Exception:
        out.report = None

    return out


def export_extension_report(page: Page) -> Optional[dict[str, Any]]:
    """Return ``exportReport()`` from the extension, or ``None``."""
    if not extension_api_available(page):
        return None
    try:
        result = page.evaluate("() => window.AutofillExtension.exportReport()")
        return result if isinstance(result, dict) else None
    except Exception:
        return None
