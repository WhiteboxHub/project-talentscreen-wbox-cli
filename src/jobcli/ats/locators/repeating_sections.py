"""Repeating-section filler (Work Experience, Education, Certifications, etc.).

Workday, iCIMS, Greenhouse's extended career form, Cornerstone, Taleo,
and SAP SuccessFactors all render the Work Experience and Education
parts of an application as **repeating sub-forms**:

    ┌─ Work Experience ────────────────────────────────┐
    │  (empty)                      [ + Add ]          │
    └──────────────────────────────────────────────────┘

    After clicking Add:

    ┌─ Work Experience ────────────────────────────────┐
    │  Job Title   [                                ]  │
    │  Company     [                                ]  │
    │  Start Date  [        ]  End Date [         ]   │
    │  Description [                                ]  │
    │                                        [Save]   │
    └──────────────────────────────────────────────────┘

    Then another ``[ + Add Another ]`` button appears and the pattern
    repeats for every additional entry.

This module encapsulates that pattern so individual ATS handlers don't
have to re-implement it.  A handler just declares the section it cares
about and the label-regex → resume-value mapping; we handle all the
clicking, waiting, scoping, error recovery, and iteration.

Design goals:

* **ATS-agnostic** — pure DOM heuristics (role-based selectors + label
  regexes) so we can reuse the same code from Workday, Greenhouse,
  iCIMS, and the generic handler.
* **Resilient** — every click and fill is wrapped in try/except with
  logging.  A failure on entry ``n`` does not block entry ``n+1``.
* **Non-destructive** — we never delete existing rows; we only add.
* **Observable** — every action produces a log line at ``info`` or
  ``warning`` level.  Counts are returned so the caller can decide
  whether to hand off to the human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence, Union

from playwright.sync_api import Frame, Locator, Page


@dataclass
class SectionFillResult:
    """Outcome of one repeating-section fill pass.

    ``filled_entries`` is the number of entries the filler successfully
    typed *any* value into.  ``partial`` flags a pass where some
    entries were filled but at least one field per entry was missing —
    useful for the caller when deciding whether to trigger a human
    handoff on the rest.
    """

    section: str
    total_entries: int = 0
    filled_entries: int = 0
    skipped_entries: int = 0
    failed_fields: list[str] = field(default_factory=list)
    partial: bool = False

    @property
    def ok(self) -> bool:
        return self.filled_entries == self.total_entries and not self.partial


# ──────────────────────────────────────────────────────────────────────
# Core filler
# ──────────────────────────────────────────────────────────────────────

#: Root = page or iframe locator where the repeating section lives.
Root = Union[Page, Frame]

#: Button label patterns used by ATSes (case-insensitive regex fragments).
DEFAULT_ADD_BUTTONS = (
    r"^\s*\+?\s*add\s*$",
    r"add\s+another",
    r"add\s+experience",
    r"add\s+another\s+experience",
    r"add\s+work\s+experience",
    r"add\s+job",
    r"add\s+position",
    r"add\s+education",
    r"add\s+another\s+education",
    r"add\s+degree",
    r"add\s+school",
    r"add\s+certification",
)
DEFAULT_SAVE_BUTTONS = (
    r"^save\s*$",
    r"save\s+and\s+continue",
    r"^done\s*$",
    r"^ok\s*$",
)


class RepeatingSectionFiller:
    """Fill a Workday-style repeating form section for multiple entries.

    Constructed once per section (so the caller can pass its own roots
    and section heading regexes).  Call :meth:`fill_entries` for each
    resume list (experience, education, …) — it clicks ``Add`` the
    right number of times and types each field into the newly-revealed
    sub-form.

    Parameters
    ----------
    roots
        Playwright ``Page`` and/or iframe ``Frame`` objects to search.
        Workday's form often lives in a cross-origin iframe, so every
        ATS handler should pass its full iframe chain here.
    section_name
        Human-readable label used in log lines ("work experience",
        "education").  Must match the section the caller is targeting.
    section_heading_patterns
        List of regex fragments that identify the section heading on
        the page.  The filler scopes all subsequent work to the first
        matching section.
    logger
        Optional project logger.  If ``None`` we log nothing — useful
        for unit tests.
    """

    def __init__(
        self,
        roots: Sequence[Root],
        section_name: str,
        section_heading_patterns: Sequence[str],
        logger: Any = None,
        add_button_patterns: Sequence[str] = DEFAULT_ADD_BUTTONS,
        save_button_patterns: Sequence[str] = DEFAULT_SAVE_BUTTONS,
    ) -> None:
        if not roots:
            raise ValueError("RepeatingSectionFiller needs at least one root")
        self.roots = list(roots)
        self.section_name = section_name
        self.section_heading_re = [re.compile(p, re.I) for p in section_heading_patterns]
        self.add_btn_re = [re.compile(p, re.I) for p in add_button_patterns]
        self.save_btn_re = [re.compile(p, re.I) for p in save_button_patterns]
        self.logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fill_entries(
        self,
        entries: Iterable[dict[str, Any]],
        field_labels: dict[str, Sequence[str]],
    ) -> SectionFillResult:
        """Iterate ``entries`` and fill a sub-form for each one.

        Each entry is a ``{field_name: value}`` dict, where ``field_name``
        must be a key in ``field_labels``.  ``field_labels`` maps each
        field to a list of regex patterns that match the on-screen
        label of that input.  The first regex that finds a visible
        input wins.

        Example
        -------
        ::

            filler.fill_entries(
                entries=[
                    {"title": "Software Engineer", "company": "Acme",
                     "start": "2022-01", "end": "2024-05",
                     "description": "Built …"},
                    {"title": "Intern", "company": "Beta", …},
                ],
                field_labels={
                    "title":       [r"^job title$", r"position title"],
                    "company":     [r"company\s*name", r"^company$", r"employer"],
                    "start":       [r"start\s*date", r"from\s*date"],
                    "end":         [r"end\s*date", r"to\s*date"],
                    "description": [r"description", r"responsibilit"],
                },
            )
        """
        entries = list(entries)
        result = SectionFillResult(section=self.section_name, total_entries=len(entries))
        if not entries:
            return result

        section = self._find_section()
        if section is None:
            self._log(
                "info",
                f"No '{self.section_name}' section found — skipping repeating fill.",
            )
            result.skipped_entries = len(entries)
            return result

        for idx, entry in enumerate(entries):
            self._log(
                "info",
                f"Filling {self.section_name} entry {idx + 1}/{len(entries)}",
                idx=idx,
                entry_keys=list(entry.keys()),
            )
            clicked = self._click_add(section)
            if not clicked:
                # Some ATSes render the first row inline, so no Add is
                # required for entry 0.  We only log a warning if we
                # couldn't add AND there's no pre-existing empty row to
                # fill.
                if idx > 0:
                    self._log(
                        "warning",
                        f"Could not click Add for {self.section_name} "
                        f"entry {idx + 1} — stopping here.",
                    )
                    result.skipped_entries = len(entries) - idx
                    break

            # New sub-form may render asynchronously — wait briefly.
            self._wait(700)

            entry_failed_fields = self._fill_sub_form(entry, field_labels)
            if entry_failed_fields:
                result.failed_fields.extend(
                    [f"{self.section_name}[{idx}].{f}" for f in entry_failed_fields]
                )
                if len(entry_failed_fields) < len(entry):
                    result.partial = True

            if entry_failed_fields == list(entry.keys()):
                # Couldn't fill ANY field — likely selectors drifted.
                self._log(
                    "warning",
                    f"No fields filled for {self.section_name} entry "
                    f"{idx + 1} — aborting further additions.",
                )
                result.skipped_entries = len(entries) - idx
                break

            result.filled_entries += 1

            # Save/commit the sub-form if the ATS requires it (most
            # modern ones autosave; Workday doesn't).
            self._click_save(section)
            self._wait(400)

        self._log(
            "info",
            f"{self.section_name} repeating fill done: "
            f"{result.filled_entries}/{result.total_entries} "
            f"(partial={result.partial})",
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_section(self) -> Optional[Locator]:
        """Return a locator scoped to the first matching section.

        We look for any visible element whose text matches one of our
        heading regexes.  The returned locator is the nearest
        ``<section>``/``<fieldset>``/``<div role=group>`` ancestor when
        one exists; otherwise the heading itself (we then walk up to
        the nearest container via JavaScript).
        """
        for root in self.roots:
            for pat in self.section_heading_re:
                try:
                    heading = root.get_by_text(pat, exact=False).first
                    if not heading.is_visible(timeout=800):
                        continue
                except Exception:
                    continue
                try:
                    # Climb to a sensible container: nearest
                    # section/fieldset/div containing BOTH the heading
                    # AND an input/button.  Falling back to the root if
                    # we can't find one keeps the filler functional on
                    # page layouts we haven't seen.
                    container_handle = heading.evaluate_handle(
                        """(el) => {
                            let n = el;
                            for (let i = 0; i < 8 && n && n.parentElement; i++) {
                                n = n.parentElement;
                                if (!n) break;
                                const tag = n.tagName.toLowerCase();
                                if (['section', 'fieldset', 'form', 'main', 'article'].includes(tag)) return n;
                                if (tag === 'div') {
                                    const hasInput = n.querySelector('input, textarea, select, button');
                                    if (hasInput && n.getBoundingClientRect().height > 100) return n;
                                }
                            }
                            return el;
                        }"""
                    )
                    # Convert handle to Locator by scoping back through root.
                    # Playwright doesn't expose a direct handle→locator
                    # conversion, so we use a throwaway data attribute.
                    container_handle.evaluate(
                        "(el) => { el.setAttribute('data-jobcli-repsection', '1'); }"
                    )
                    return root.locator("[data-jobcli-repsection='1']").first
                except Exception:
                    return heading
        return None

    def _click_add(self, section: Locator) -> bool:
        """Click the (next) Add button inside the section scope."""
        for pat in self.add_btn_re:
            try:
                btn = section.get_by_role("button", name=pat).first
                if not btn.is_visible(timeout=500):
                    continue
                btn.scroll_into_view_if_needed(timeout=1500)
                btn.click(timeout=2000)
                self._log("info", f"Clicked Add for {self.section_name}")
                return True
            except Exception:
                continue
        # Fallback: any <button> containing the pattern text.
        for pat in self.add_btn_re:
            try:
                btn = section.locator("button, [role='button']").filter(
                    has_text=pat
                ).first
                if btn.is_visible(timeout=400):
                    btn.click(timeout=2000)
                    self._log("info", f"Clicked Add ({pat.pattern}) via generic button")
                    return True
            except Exception:
                continue
        return False

    def _click_save(self, section: Locator) -> None:
        """Best-effort commit of a sub-form (many ATSes autosave).

        We deliberately skip any button whose name ALSO matches an Add
        pattern: several ATSes render only a single "+ Add" button and
        re-clicking it would create a spurious extra row instead of
        committing the current one.
        """
        for pat in self.save_btn_re:
            try:
                btn = section.get_by_role("button", name=pat).first
                if not btn.is_visible(timeout=400):
                    continue
                # Guard: don't re-click the Add button as if it were Save.
                name_candidates: list[str] = []
                try:
                    handle = btn.evaluate_handle(
                        "(el) => (el.textContent || el.getAttribute('aria-label') || '').trim()"
                    )
                    name = handle.evaluate("(t) => t") if hasattr(handle, "evaluate") else handle
                    if isinstance(name, str):
                        name_candidates.append(name)
                except Exception:
                    pass
                if any(
                    any(add_rx.search(n or "") for add_rx in self.add_btn_re)
                    for n in name_candidates
                ):
                    continue
                btn.click(timeout=1800)
                self._log("info", f"Clicked Save for {self.section_name}")
                return
            except Exception:
                continue

    def _fill_sub_form(
        self,
        entry: dict[str, Any],
        field_labels: dict[str, Sequence[str]],
    ) -> list[str]:
        """Attempt to fill every field in ``entry``. Returns failed keys."""
        failed: list[str] = []
        for name, value in entry.items():
            if value in (None, ""):
                continue
            patterns = field_labels.get(name, [name])
            if not self._fill_one(str(value), patterns):
                failed.append(name)
        return failed

    def _fill_one(self, value: str, label_patterns: Sequence[str]) -> bool:
        """Find the first matching input-by-label and type ``value``."""
        for root in self.roots:
            for p in label_patterns:
                rx = re.compile(p, re.I)
                for locate in (
                    lambda r=rx: root.get_by_label(r).last,
                    lambda r=rx: root.get_by_placeholder(r).last,
                ):
                    try:
                        inp = locate()
                        if not inp.is_visible(timeout=400):
                            continue
                        from jobcli.orchestration.human_interaction import humanized_fill
                        humanized_fill(root, inp, value)
                        return True
                    except Exception:
                        continue
        return False

    # ------------------------------------------------------------------
    # Logging shim
    # ------------------------------------------------------------------

    def _log(self, level: str, msg: str, **extra: Any) -> None:
        if self.logger is None:
            return
        fn = getattr(self.logger, level, None)
        if fn is None:
            return
        try:
            # Project logger uses a ``phase=`` kwarg — we don't want to
            # hard-depend on that import here, so we pass extras as
            # keyword args and rely on the logger's tolerant signature.
            fn(msg, **extra)
        except Exception:
            try:
                fn(msg)
            except Exception:
                pass

    def _wait(self, ms: int) -> None:
        for root in self.roots:
            waiter = getattr(root, "wait_for_timeout", None)
            if callable(waiter):
                try:
                    waiter(ms)
                    return
                except Exception:
                    continue


# ──────────────────────────────────────────────────────────────────────
# Canned label maps for the two universal resume sections
# ──────────────────────────────────────────────────────────────────────

#: Experience field label regexes.  Keys match the ``entry`` dicts
#: produced by :func:`experience_entries_from_resume`.
EXPERIENCE_FIELD_LABELS: dict[str, list[str]] = {
    "title":       [r"^job\s*title$", r"position\s*title", r"^role$", r"^title$"],
    "company":     [r"company\s*name", r"^company$", r"^employer$", r"organization"],
    "start_date":  [r"start\s*date", r"from\s*date", r"^from$"],
    "end_date":    [r"end\s*date", r"to\s*date", r"^to$"],
    "description": [r"description", r"responsibilit", r"duties", r"summary"],
}

#: Education field label regexes.
EDUCATION_FIELD_LABELS: dict[str, list[str]] = {
    "school":          [r"school\s*name", r"^school$", r"university", r"institution", r"college"],
    "degree":          [r"^degree$", r"degree\s*name", r"qualification"],
    "field_of_study":  [r"field\s*of\s*study", r"^major$", r"concentration", r"discipline"],
    "graduation_year": [r"graduation\s*year", r"completion\s*year", r"^year$", r"year\s*completed"],
    "gpa":             [r"^gpa$", r"grade\s*point"],
}

#: Regexes that match the section heading.  We accept the common
#: variations by ATS.
# NOTE: Do not put ``my\\s*experience`` here. On Workday, the *wizard
# step* is often named "My Experience" while the **subsection** under it
# is "Work Experience" with its own [Add] button. Matching the step
# title would scope a huge region (or the wrong [Add]).
EXPERIENCE_SECTION_HEADINGS = [
    r"work\s+experience",
    r"employment\s+history",
    r"professional\s+experience",
    r"^experience$",
    r"work\s+history",
]
EDUCATION_SECTION_HEADINGS = [
    r"^education$",
    r"^education\s+history$",
    r"academic\s+background",
    r"degrees?",
    r"schools?",
]


def experience_entries_from_resume(resume: Any) -> list[dict[str, Any]]:
    """Convert ``resume.experience`` into ``fill_entries``-shaped dicts."""
    out: list[dict[str, Any]] = []
    for ex in (getattr(resume, "experience", None) or []):
        out.append(
            {
                "title":       getattr(ex, "title", None),
                "company":     getattr(ex, "company", None),
                "start_date":  getattr(ex, "start_date", None),
                "end_date":    getattr(ex, "end_date", None) if not getattr(ex, "current", False) else "Present",
                "description": getattr(ex, "description", None),
            }
        )
    return out


def education_entries_from_resume(resume: Any) -> list[dict[str, Any]]:
    """Convert ``resume.education`` into ``fill_entries``-shaped dicts."""
    out: list[dict[str, Any]] = []
    for ed in (getattr(resume, "education", None) or []):
        out.append(
            {
                "school":          getattr(ed, "school", None),
                "degree":          getattr(ed, "degree", None),
                "field_of_study":  getattr(ed, "field_of_study", None),
                "graduation_year": getattr(ed, "graduation_year", None),
                "gpa":             getattr(ed, "gpa", None),
            }
        )
    return out
