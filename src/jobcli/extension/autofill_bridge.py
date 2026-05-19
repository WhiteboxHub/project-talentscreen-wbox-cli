"""Bridge JobCLI (Playwright) to TalentScreen v2 ``window.AutofillExtension``."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.sync_api import Frame, Page, TimeoutError as PlaywrightTimeoutError

from jobcli.profile.resume_export import resume_to_json_resume
from jobcli.profile.schemas import CommonQuestions, ResumeData
from jobcli.utils.logger import JobLogger

# Host fragments aligned with extension manifest ATS coverage
_ATS_HOST_FRAGMENTS: tuple[str, ...] = (
    "myworkdayjobs.com",
    "greenhouse.io",
    "lever.co",
    "smartrecruiters.com",
    "applytojob.com",
    "bamboohr.com",
    "icims.com",
    "indeed.com",
    "linkedin.com",
    "workable.com",
    "taleo.net",
    "successfactors.com",
    "successfactors.eu",
    "personio.com",
    "personio.de",
    "recruitee.com",
    "teamtailor.com",
    "ultipro.com",
    "myultipro.com",
    "ukg.com",
    "paycomonline.net",
    "paychex.com",
    "oraclecloud.com",
    "brassring.com",
    "ashbyhq.com",
    "workforcenow.adp.com",
    "jobvite.com",
    "rippling-ats.com",
)


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
    target_frame_url: Optional[str] = None

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


_AUTOFILL_API_PROBE = """() => {
    return typeof window.AutofillExtension !== 'undefined'
        && window.AutofillExtension.__bridge === true;
}"""


def _is_likely_ats_frame_url(url: str) -> bool:
    """Return True if *url* looks like a job-application frame (not captcha CDN)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return any(fragment in host for fragment in _ATS_HOST_FRAGMENTS)


def _ordered_frames_for_probe(page: Page) -> list[Frame]:
    """ATS application frames first, then others (skips prioritizing hcaptcha iframes)."""
    try:
        all_frames = list(page.frames)
    except Exception:
        return []

    ats_frames: list[Frame] = []
    other_frames: list[Frame] = []
    for frame in all_frames:
        if _is_likely_ats_frame_url(frame.url or ""):
            ats_frames.append(frame)
        else:
            other_frames.append(frame)

    ordered: list[Frame] = []
    main = page.main_frame
    if main in ats_frames:
        ordered.append(main)
        ats_frames = [f for f in ats_frames if f is not main]
    ordered.extend(ats_frames)
    ordered.extend(other_frames)
    return ordered


def _frame_has_autofill_api(frame: Frame) -> bool:
    try:
        return bool(frame.evaluate(_AUTOFILL_API_PROBE))
    except Exception:
        return False


def find_autofill_frame(page: Page) -> Optional[Frame]:
    """Return the first frame where the page-world bridge API exists."""
    for frame in _ordered_frames_for_probe(page):
        if _frame_has_autofill_api(frame):
            return frame
    return None


def extension_api_available(page: Page) -> bool:
    """Return True if ``window.AutofillExtension`` bridge is callable in any frame."""
    return find_autofill_frame(page) is not None


def wait_for_autofill_api(page: Page, timeout_ms: int = 30_000) -> Optional[Frame]:
    """Poll until the bridge API appears, or timeout."""
    try:
        page.wait_for_function(
            """() => typeof window.AutofillExtension !== 'undefined'
                && window.AutofillExtension.__bridge === true""",
            timeout=min(timeout_ms, 10_000),
        )
    except Exception:
        pass

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        frame = find_autofill_frame(page)
        if frame is not None:
            return frame
        try:
            page.wait_for_timeout(300)
        except Exception:
            break
    return None


def _extension_version_hint(extension_dir: Optional[str]) -> str:
    if not extension_dir:
        return ""
    try:
        from jobcli.extension.helpers import read_extension_manifest_version

        ver = read_extension_manifest_version(extension_dir)
        return f" Extension loaded from: {extension_dir} (manifest v{ver or '?'})."
    except Exception:
        return f" Extension loaded from: {extension_dir}."


def _evaluate_api(frame: Frame, expression: str, arg: Any = None) -> Any:
    """Run JS on *frame*; await Promises returned by the page-world bridge."""
    if arg is None:
        return frame.evaluate(expression)
    return frame.evaluate(expression, arg)


def run_extension_autofill(
    page: Page,
    resume: ResumeData,
    logger: Optional[JobLogger] = None,
    questions: Optional[CommonQuestions] = None,
    options: Optional[ExtensionAutofillOptions] = None,
    extension_dir: Optional[str] = None,
) -> ExtensionAutofillResult:
    """Inject profile and fill the current page via TalentScreen v2 API."""
    opts = options or ExtensionAutofillOptions()
    out = ExtensionAutofillResult()

    frame = wait_for_autofill_api(page, timeout_ms=opts.api_timeout_ms)
    if frame is None:
        out.inject_error = "window.AutofillExtension bridge not available on this page"
        if logger:
            urls = []
            try:
                urls = [f.url for f in _ordered_frames_for_probe(page)[:8]]
            except Exception:
                pass
            ver_hint = _extension_version_hint(extension_dir)
            logger.warning(
                "TalentScreen API unavailable (missing page-world bridge, content script not "
                f"injected, or wrong frame). Frames checked: {urls or ['?']}.{ver_hint} "
                "Ensure extension includes pageWorldBridge.js (v2.0.0+). "
                "Continuing with rules/LLM only.",
            )
        return out

    out.api_available = True
    out.target_frame_url = frame.url
    if logger:
        logger.info(f"TalentScreen API found on frame: {frame.url}")

    try:
        frame.wait_for_selector("input, textarea, select", timeout=opts.form_wait_timeout_ms)
    except PlaywrightTimeoutError:
        if logger:
            logger.debug("No form controls found before extension autofill; proceeding anyway.")

    profile = resume_to_json_resume(resume, questions=questions)
    email = (profile.get("basics") or {}).get("email") or ""
    if not email.strip():
        out.inject_error = "Resume has no email — extension requires basics.email"
        if logger:
            logger.warning(
                f"{out.inject_error}. Re-run jobcli resume-upload with a JSON that includes email. "
                "Continuing with rules/LLM only.",
            )
        return out

    inject = _evaluate_api(
        frame,
        "async (p) => await window.AutofillExtension.injectProfile(p)",
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
            detail = "; ".join(out.validation_errors) if out.validation_errors else out.inject_error
            logger.warning(
                f"Extension injectProfile failed: {out.inject_error}. "
                f"Validation: {detail}. Continuing with rules/LLM only.",
            )
        return out

    out.inject_success = True
    if logger:
        logger.info(
            f"Extension profile injected (schema {inject.get('schemaVersion', '?')}).",
        )

    _evaluate_api(
        frame,
        """async (o) => await window.AutofillExtension.configure({
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

    fill_result = _evaluate_api(
        frame,
        "async (p) => await window.AutofillExtension.fill(p)",
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
        out.report = _evaluate_api(frame, "async () => await window.AutofillExtension.exportReport()")
    except Exception:
        out.report = None

    return out


def export_extension_report(page: Page) -> Optional[dict[str, Any]]:
    """Return ``exportReport()`` from the extension, or ``None``."""
    frame = find_autofill_frame(page)
    if frame is None:
        return None
    try:
        result = _evaluate_api(frame, "async () => await window.AutofillExtension.exportReport()")
        return result if isinstance(result, dict) else None
    except Exception:
        return None
