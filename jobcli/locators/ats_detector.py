"""ATS detection system."""

import re
from typing import Optional
from urllib.parse import urlparse

from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ATSType, ExecutionPhase


class ATSDetector:
    """Detect ATS system from URL and page content."""

    # URL patterns for ATS detection
    URL_PATTERNS = {
        ATSType.GREENHOUSE: [
            r"greenhouse\.io",
            r"boards\.greenhouse\.io",
            r"job-boards\.greenhouse\.io",
        ],
        ATSType.LEVER: [r"lever\.co", r"jobs\.lever\.co"],
        ATSType.WORKDAY: [r"myworkdayjobs\.com", r"workday\.com/.*jobs"],
        ATSType.ICIMS: [r"icims\.com", r".*\.icims\.com"],
        ATSType.TALEO: [r"taleo\.net", r".*\.taleo\.net"],
        ATSType.SAP_SUCCESSFACTORS: [r"successfactors\.com", r".*\.successfactors\.com"],
        ATSType.SMARTRECRUITERS: [r"smartrecruiters\.com", r"jobs\.smartrecruiters\.com"],
        ATSType.JOBVITE: [r"jobvite\.com", r"jobs\.jobvite\.com"],
        ATSType.ASHBY: [r"ashbyhq\.com", r"jobs\.ashbyhq\.com"],
        ATSType.BREEZY_HR: [r"breezy\.hr", r".*\.breezy\.hr"],
        ATSType.RECRUITEE: [r"recruitee\.com", r".*\.recruitee\.com"],
        ATSType.JAZZ_HR: [r"jazzhr\.com", r".*\.jazzhr\.com"],
        ATSType.BAMBOO_HR: [r"bamboohr\.com", r".*\.bamboohr\.com"],
        ATSType.WORKABLE: [r"workable\.com", r"apply\.workable\.com"],
        ATSType.ADP_RECRUITING: [r"adp\.com/.*recruiting", r"recruiting\.adp\.com"],
        ATSType.PAYLOCITY: [r"paylocity\.com", r"recruiting\.paylocity\.com"],
        ATSType.UKG_PRO: [r"ultipro\.com", r"recruiting\.ultipro\.com"],
        ATSType.CORNERSTONE: [r"csod\.com", r".*\.csod\.com"],
        ATSType.AVATURE: [r"avature\.net", r".*\.avature\.net"],
        ATSType.PHENOM_PEOPLE: [r"phenompeople\.com", r".*\.phenompeople\.com"],
        ATSType.RIPPLING: [r"rippling\.com", r".*\.rippling\.com"],
    }

    # DOM signatures for ATS detection
    DOM_SIGNATURES = {
        ATSType.GREENHOUSE: [
            "data-greenhouse",
            "greenhouse-application",
            "grnhse_app",
        ],
        ATSType.LEVER: ["lever-application", "lever-frame", "data-lever"],
        ATSType.WORKDAY: ["wd-", "workday-", "data-automation-id"],
        ATSType.ICIMS: ["icims", "iCIMS"],
        ATSType.TALEO: ["taleo", "requisitionDescriptionInterface"],
        ATSType.SAP_SUCCESSFACTORS: ["sf-", "successfactors"],
        ATSType.SMARTRECRUITERS: ["smartrecruiters", "data-sr-"],
        ATSType.JOBVITE: ["jobvite", "jv-"],
        ATSType.ASHBY: ["ashby", "ashbyhq"],
        ATSType.BREEZY_HR: ["breezy", "bzc-"],
        ATSType.RECRUITEE: ["recruitee", "r6e-"],
        ATSType.JAZZ_HR: ["jazzhr", "jazz-"],
        ATSType.BAMBOO_HR: ["bamboohr", "bamboo-"],
        ATSType.WORKABLE: ["workable", "whr-"],
        ATSType.ADP_RECRUITING: ["adp", "recruiting-adp"],
        ATSType.PAYLOCITY: ["paylocity", "pcty-"],
        ATSType.UKG_PRO: ["ultipro", "ukg-"],
        ATSType.CORNERSTONE: ["csod", "cornerstone"],
        ATSType.AVATURE: ["avature", "avature-"],
        ATSType.PHENOM_PEOPLE: ["phenom", "px-"],
        ATSType.RIPPLING: ["rippling", "ats-rippling"],
    }

    # Meta tag patterns
    META_PATTERNS = {
        ATSType.GREENHOUSE: ["greenhouse"],
        ATSType.LEVER: ["lever"],
        ATSType.WORKDAY: ["workday"],
        ATSType.SMARTRECRUITERS: ["smartrecruiters"],
    }

    def __init__(self, page: Page, logger: Optional[JobLogger] = None) -> None:
        """Initialize ATS detector."""
        self.page = page
        self.logger = logger

    def detect_from_url(self, url: str) -> Optional[ATSType]:
        """Detect ATS from URL patterns."""
        parsed = urlparse(url)
        full_url = parsed.netloc + parsed.path

        for ats_type, patterns in self.URL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, full_url, re.IGNORECASE):
                    if self.logger:
                        self.logger.info(
                            f"Detected {ats_type.value} from URL",
                            phase=ExecutionPhase.RULES,
                            url=url,
                            pattern=pattern,
                        )
                    return ats_type

        return None

    def detect_from_dom(self) -> Optional[ATSType]:
        """Detect ATS from DOM signatures.

        We no longer do a raw substring check against ``page.content()``:
        that caused false positives like LinkedIn → ``ukg_pro`` when the
        substring ``"ultipro"`` appeared in some unrelated JSON blob on
        the page.  Instead, we require each signature to appear as one
        of:

        * an element attribute value (``data-*``, ``class``, ``id``,
          ``aria-*``, ``name``) — strong signal
        * an iframe / script / link ``src``/``href`` — strong signal
        * a meta tag content — strong signal
        * page HTML, but only when surrounded by non-word boundaries
          AND either the host domain already hints at that ATS OR the
          signature itself is longer than 4 characters — weak fallback
        """
        try:
            # Fast-path: inspect known structural elements first.
            structural_checks = [
                ("iframe[src], script[src], link[href]", ("src", "href")),
                ("meta[name='generator']", ("content",)),
                ("[data-ats], [data-greenhouse], [data-lever], "
                 "[data-automation-id], [data-workday], [data-ashby], "
                 "[data-icims], [data-smartrecruiters], [data-jobvite], "
                 "[data-workable], [data-recruitee], [data-breezy], "
                 "[class*='ashby-'], [class*='greenhouse'], "
                 "[class*='lever-'], [class*='wd-'], [class*='icims']",
                 ("data-ats", "class", "id")),
            ]
            for css, attrs in structural_checks:
                try:
                    elements = self.page.query_selector_all(css)
                except Exception:
                    continue
                for el in elements[:50]:
                    for attr in attrs:
                        try:
                            v = el.get_attribute(attr) or ""
                        except Exception:
                            v = ""
                        if not v:
                            continue
                        v_lower = v.lower()
                        for ats_type, signatures in self.DOM_SIGNATURES.items():
                            for sig in signatures:
                                if sig.lower() in v_lower:
                                    if self.logger:
                                        self.logger.info(
                                            f"Detected {ats_type.value} from DOM",
                                            phase=ExecutionPhase.RULES,
                                            signature=sig,
                                            source=f"{css}[{attr}]",
                                        )
                                    return ats_type

            # Weak fallback: word-boundary match on page HTML — only for
            # signatures that are long enough to be unlikely as random
            # substring noise.
            html = self.page.content()
            try:
                current_host = (self.page.url or "").lower()
            except Exception:
                current_host = ""
            for ats_type, signatures in self.DOM_SIGNATURES.items():
                for signature in signatures:
                    if len(signature) < 5:
                        continue  # too short — high false-positive risk
                    pat = re.compile(
                        r"(?<![A-Za-z0-9])" + re.escape(signature) + r"(?![A-Za-z0-9])",
                        re.IGNORECASE,
                    )
                    if pat.search(html):
                        # Extra guard: if the current host is a known job
                        # board, demote weak HTML matches — they're
                        # almost always employer names in search results
                        # rather than ATS fingerprints.
                        if any(
                            board in current_host
                            for board in (
                                "linkedin.com", "indeed.com", "glassdoor.com",
                                "ziprecruiter.com", "monster.com",
                                "simplyhired.com", "dice.com", "wellfound.com",
                                "jobright.ai", "builtin.com",
                            )
                        ):
                            continue
                        if self.logger:
                            self.logger.info(
                                f"Detected {ats_type.value} from DOM",
                                phase=ExecutionPhase.RULES,
                                signature=signature,
                                source="html (weak)",
                            )
                        return ats_type

        except Exception as e:
            if self.logger:
                self.logger.error(
                    "Failed to detect ATS from DOM",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )

        return None

    def detect_from_meta_tags(self) -> Optional[ATSType]:
        """Detect ATS from meta tags."""
        try:
            # Check generator meta tag
            generator = self.page.query_selector("meta[name='generator']")
            if generator:
                content = generator.get_attribute("content") or ""
                for ats_type, patterns in self.META_PATTERNS.items():
                    for pattern in patterns:
                        if re.search(r'\b' + re.escape(pattern.lower()) + r'\b', content.lower()):
                            if self.logger:
                                self.logger.info(
                                    f"Detected {ats_type.value} from meta tag",
                                    phase=ExecutionPhase.RULES,
                                    content=content,
                                )
                            return ats_type

            # Check other meta tags
            meta_tags = self.page.query_selector_all("meta")
            for meta in meta_tags:
                content = meta.get_attribute("content") or ""
                for ats_type, patterns in self.META_PATTERNS.items():
                    for pattern in patterns:
                        if re.search(r'\b' + re.escape(pattern.lower()) + r'\b', content.lower()):
                            if self.logger:
                                self.logger.info(
                                    f"Detected {ats_type.value} from meta content",
                                    phase=ExecutionPhase.RULES,
                                    content=content,
                                )
                            return ats_type

        except Exception as e:
            if self.logger:
                self.logger.error(
                    "Failed to detect ATS from meta tags",
                    phase=ExecutionPhase.RULES,
                    error=str(e),
                )

        return None

    def detect(self, url: str) -> ATSType:
        """Detect ATS using all methods."""
        if self.logger:
            self.logger.info("Starting ATS detection", phase=ExecutionPhase.RULES, url=url)

        # Try URL first (fastest)
        ats_type = self.detect_from_url(url)
        if ats_type:
            return ats_type

        # Try meta tags
        ats_type = self.detect_from_meta_tags()
        if ats_type:
            return ats_type

        # Try DOM signatures (slowest)
        ats_type = self.detect_from_dom()
        if ats_type:
            return ats_type

        if self.logger:
            self.logger.warning(
                "Could not detect ATS type, using UNKNOWN",
                phase=ExecutionPhase.RULES,
            )

        return ATSType.UNKNOWN
