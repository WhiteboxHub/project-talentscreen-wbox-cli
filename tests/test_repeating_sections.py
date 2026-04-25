"""Regression tests for :mod:`jobcli.locators.repeating_sections`.

The repeating-section filler is responsible for turning a resume's
``experience`` and ``education`` arrays into a sequence of **Add → fill →
Save** clicks so Workday-style forms end up with one sub-form row per
entry.  These tests pin down that contract WITHOUT spinning up a real
browser: we feed a tiny in-memory fake that mimics the small subset of
the Playwright ``Locator`` surface that the filler actually uses.

Why the fake-based approach?

* The filler is pure DOM heuristics — no network, no browser primitives
  beyond label/role lookup, click, and fill.  A fake is plenty.
* Running headless Chromium per test is slow and flakey.  The
  existing stealth tests already exercise the real browser.
* The fake makes the test read like the DOM it is emulating.  Each
  test constructs a page with a named section, a configurable "Add"
  button, and a list of labelled inputs; asserts the filler clicked
  Add the expected number of times and typed the right values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Pattern, Union

import pytest

from jobcli.locators.repeating_sections import (
    EDUCATION_FIELD_LABELS,
    EDUCATION_SECTION_HEADINGS,
    EXPERIENCE_FIELD_LABELS,
    EXPERIENCE_SECTION_HEADINGS,
    RepeatingSectionFiller,
    education_entries_from_resume,
    experience_entries_from_resume,
)


# ──────────────────────────────────────────────────────────────────────
# Fake Playwright locator / page
# ──────────────────────────────────────────────────────────────────────

_MISSING = object()


@dataclass
class _Input:
    """A single form input identified by one or more labels."""

    labels: list[str]
    value: str = ""
    visible: bool = True


@dataclass
class _Button:
    """A clickable button identified by its accessible name (text)."""

    name: str
    visible: bool = True
    on_click: Optional[Callable[[], None]] = None
    clicked: int = 0


@dataclass
class FakeSection:
    """A section scope: heading + bag of inputs and buttons."""

    heading: str
    visible: bool = True
    inputs: list[_Input] = field(default_factory=list)
    buttons: list[_Button] = field(default_factory=list)


class _FakeLocator:
    """A tiny subset of Playwright's ``Locator`` API."""

    def __init__(self, page: "FakePage", matches: list[Any]):
        self._page = page
        self._matches = matches

    # Filter chain ------------------------------------------------------

    @property
    def first(self) -> "_FakeLocator":
        return _FakeLocator(self._page, self._matches[:1])

    @property
    def last(self) -> "_FakeLocator":
        return _FakeLocator(self._page, self._matches[-1:])

    def filter(self, has_text: Optional[Pattern] = None) -> "_FakeLocator":
        out = []
        for m in self._matches:
            txt = getattr(m, "name", "") or getattr(m, "heading", "")
            if has_text and has_text.search(txt):
                out.append(m)
        return _FakeLocator(self._page, out)

    def get_by_role(self, role: str, name: Optional[Pattern] = None) -> "_FakeLocator":
        if role != "button":
            return _FakeLocator(self._page, [])
        out = []
        for section in self._sections():
            for btn in section.buttons:
                if name is None or name.search(btn.name):
                    out.append(btn)
        return _FakeLocator(self._page, out)

    def get_by_text(self, pattern: Pattern, exact: bool = False) -> "_FakeLocator":
        out = []
        for s in self._page.sections:
            if pattern.search(s.heading):
                out.append(s)
        return _FakeLocator(self._page, out)

    def get_by_label(self, pattern: Pattern) -> "_FakeLocator":
        out = []
        for section in self._sections():
            for inp in section.inputs:
                for label in inp.labels:
                    if pattern.search(label):
                        out.append(inp)
                        break
        return _FakeLocator(self._page, out)

    def get_by_placeholder(self, pattern: Pattern) -> "_FakeLocator":
        return _FakeLocator(self._page, [])

    def locator(self, selector: str) -> "_FakeLocator":
        # Only two selectors show up in the filler:
        #   "button, [role='button']"
        #   "[data-jobcli-repsection='1']"
        if "data-jobcli-repsection" in selector:
            # After `_find_section` tagged a section, we return the same
            # bag — the fake doesn't care about the DOM attribute.
            return _FakeLocator(self._page, self._matches)
        if "button" in selector:
            out = [b for s in self._sections() for b in s.buttons]
            return _FakeLocator(self._page, out)
        return _FakeLocator(self._page, [])

    # Actions -----------------------------------------------------------

    def is_visible(self, timeout: int = 0) -> bool:
        if not self._matches:
            return False
        return bool(getattr(self._matches[0], "visible", True))

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        return None

    def click(self, timeout: int = 0) -> None:
        if not self._matches:
            raise RuntimeError("no element to click")
        target = self._matches[0]
        if isinstance(target, _Button):
            target.clicked += 1
            if target.on_click:
                target.on_click()
        else:
            raise RuntimeError(f"click target is not a button: {target!r}")

    def fill(self, value: str, timeout: int = 0) -> None:
        if not self._matches:
            raise RuntimeError("no input to fill")
        target = self._matches[0]
        if isinstance(target, _Input):
            target.value = value
        else:
            raise RuntimeError(f"fill target is not an input: {target!r}")

    def evaluate(self, *_: Any, **__: Any) -> Any:
        return None

    def evaluate_handle(self, *_: Any, **__: Any) -> "_FakeLocator":
        return self

    def count(self) -> int:
        return len(self._matches)

    # Helpers -----------------------------------------------------------

    def _sections(self) -> list[FakeSection]:
        # Inside a section-scoped locator we only expose the matched
        # sections; at page level we expose them all.
        sections = [m for m in self._matches if isinstance(m, FakeSection)]
        return sections or self._page.sections


class FakePage:
    """Minimal ``Page`` stand-in with a list of sections."""

    def __init__(self, sections: list[FakeSection]):
        self.sections = sections

    def get_by_text(self, pattern: Pattern, exact: bool = False) -> _FakeLocator:
        return _FakeLocator(self, [s for s in self.sections if pattern.search(s.heading)])

    def get_by_label(self, pattern: Pattern) -> _FakeLocator:
        # Search every input across every section.
        out = []
        for s in self.sections:
            for inp in s.inputs:
                for label in inp.labels:
                    if pattern.search(label):
                        out.append(inp)
                        break
        return _FakeLocator(self, out)

    def get_by_placeholder(self, pattern: Pattern) -> _FakeLocator:
        return _FakeLocator(self, [])

    def locator(self, selector: str) -> _FakeLocator:
        if "data-jobcli-repsection" in selector:
            return _FakeLocator(self, self.sections)
        return _FakeLocator(self, [])

    def wait_for_timeout(self, ms: int) -> None:  # pragma: no cover
        return None


# ──────────────────────────────────────────────────────────────────────
# Fake resume dataclasses that mirror the real schema's attribute names
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _FakeExperience:
    company: str
    title: str
    start_date: str
    end_date: Optional[str] = None
    current: bool = False
    description: Optional[str] = None


@dataclass
class _FakeEducation:
    school: str
    degree: str
    field_of_study: str
    graduation_year: int
    gpa: Optional[float] = None


@dataclass
class _FakeResume:
    experience: list[_FakeExperience] = field(default_factory=list)
    education: list[_FakeEducation] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Test helpers
# ──────────────────────────────────────────────────────────────────────


def _make_work_experience_section(
    field_count_after_add: int = 5,
    add_reveals_inputs: bool = True,
) -> FakeSection:
    """A section with an Add button that reveals a fresh sub-form on each click.

    Each click empties the last sub-form list and appends a fresh set of
    labelled inputs, mimicking Workday's "push a new row" behaviour.
    """
    section = FakeSection(heading="Work Experience")

    def add_inputs() -> None:
        if not add_reveals_inputs:
            return
        labels_for_fields = [
            ("Job Title",),
            ("Company Name",),
            ("Start Date",),
            ("End Date",),
            ("Description",),
        ][:field_count_after_add]
        for labels in labels_for_fields:
            section.inputs.append(_Input(labels=list(labels)))

    section.buttons.append(
        _Button(name="+ Add", on_click=add_inputs)
    )
    return section


def _make_education_section() -> FakeSection:
    section = FakeSection(heading="Education")

    def add_inputs() -> None:
        for labels in [
            ("School Name",),
            ("Degree",),
            ("Field of Study",),
            ("Graduation Year",),
        ]:
            section.inputs.append(_Input(labels=list(labels)))

    section.buttons.append(_Button(name="+ Add Education", on_click=add_inputs))
    return section


# ──────────────────────────────────────────────────────────────────────
# Tests — repeating section filler
# ──────────────────────────────────────────────────────────────────────


class TestRepeatingSectionFiller:
    """The filler clicks Add the right number of times and types correctly."""

    def test_fills_single_experience_entry(self) -> None:
        section = _make_work_experience_section()
        page = FakePage([section])
        filler = RepeatingSectionFiller(
            roots=[page],
            section_name="work experience",
            section_heading_patterns=EXPERIENCE_SECTION_HEADINGS,
        )
        result = filler.fill_entries(
            [{
                "title": "Software Engineer",
                "company": "Acme Corp",
                "start_date": "2022-01",
                "end_date": "2024-05",
                "description": "Built things.",
            }],
            EXPERIENCE_FIELD_LABELS,
        )

        assert result.total_entries == 1
        assert result.filled_entries == 1
        # One Add click per entry.
        assert section.buttons[0].clicked == 1
        # Every input ended up with the resume value.
        by_label = {i.labels[0]: i.value for i in section.inputs}
        assert by_label["Job Title"] == "Software Engineer"
        assert by_label["Company Name"] == "Acme Corp"
        assert by_label["Start Date"] == "2022-01"
        assert by_label["End Date"] == "2024-05"
        assert by_label["Description"] == "Built things."

    def test_fills_multiple_experience_entries_clicks_add_each_time(self) -> None:
        section = _make_work_experience_section()
        page = FakePage([section])
        filler = RepeatingSectionFiller(
            roots=[page],
            section_name="work experience",
            section_heading_patterns=EXPERIENCE_SECTION_HEADINGS,
        )

        entries = [
            {"title": "Engineer",  "company": "Acme",  "start_date": "2020",
             "end_date": "2022",  "description": "A."},
            {"title": "Senior",    "company": "Beta",  "start_date": "2022",
             "end_date": "2024",  "description": "B."},
            {"title": "Staff",     "company": "Gamma", "start_date": "2024",
             "end_date": "2025",  "description": "C."},
        ]
        result = filler.fill_entries(entries, EXPERIENCE_FIELD_LABELS)

        assert result.filled_entries == 3
        # Add must be clicked once per entry.
        assert section.buttons[0].clicked == 3
        # The filler's `.last` selector on inputs ensures the NEWEST row
        # wins for each fill, so the last three Job Title inputs should
        # carry the three titles in order.
        titles = [i.value for i in section.inputs if "Job Title" in i.labels]
        assert titles == ["Engineer", "Senior", "Staff"]

    def test_stops_when_add_button_disappears(self) -> None:
        """If an ATS caps the number of rows, the filler bails cleanly."""
        section = _make_work_experience_section()
        page = FakePage([section])

        # After one click, hide the Add button to simulate a cap.
        original_on_click = section.buttons[0].on_click

        def cap_after_one() -> None:
            if original_on_click:
                original_on_click()
            section.buttons[0].visible = False

        section.buttons[0].on_click = cap_after_one

        filler = RepeatingSectionFiller(
            roots=[page],
            section_name="work experience",
            section_heading_patterns=EXPERIENCE_SECTION_HEADINGS,
        )
        entries = [
            {"title": "A", "company": "A", "start_date": "2020",
             "end_date": "2021", "description": "."},
            {"title": "B", "company": "B", "start_date": "2021",
             "end_date": "2022", "description": "."},
            {"title": "C", "company": "C", "start_date": "2022",
             "end_date": "2023", "description": "."},
        ]
        result = filler.fill_entries(entries, EXPERIENCE_FIELD_LABELS)

        assert result.filled_entries == 1
        assert result.skipped_entries == 2

    def test_handles_missing_section_gracefully(self) -> None:
        """No Work Experience on the page → filler is a no-op."""
        page = FakePage([FakeSection(heading="Personal Information")])
        filler = RepeatingSectionFiller(
            roots=[page],
            section_name="work experience",
            section_heading_patterns=EXPERIENCE_SECTION_HEADINGS,
        )
        result = filler.fill_entries(
            [{"title": "x", "company": "y"}], EXPERIENCE_FIELD_LABELS
        )
        assert result.filled_entries == 0
        assert result.skipped_entries == 1

    def test_fills_education_section(self) -> None:
        section = _make_education_section()
        page = FakePage([section])
        filler = RepeatingSectionFiller(
            roots=[page],
            section_name="education",
            section_heading_patterns=EDUCATION_SECTION_HEADINGS,
        )
        result = filler.fill_entries(
            [
                {"school": "MIT",     "degree": "BS",
                 "field_of_study": "CS", "graduation_year": 2020},
                {"school": "Stanford","degree": "MS",
                 "field_of_study": "AI", "graduation_year": 2022},
            ],
            EDUCATION_FIELD_LABELS,
        )
        assert result.filled_entries == 2
        assert section.buttons[0].clicked == 2
        schools = [i.value for i in section.inputs if "School Name" in i.labels]
        assert schools == ["MIT", "Stanford"]


# ──────────────────────────────────────────────────────────────────────
# Tests — resume → entry converters
# ──────────────────────────────────────────────────────────────────────


class TestResumeEntryConversion:
    """``experience_entries_from_resume`` preserves every job as-is."""

    def test_experience_conversion_marks_current_as_present(self) -> None:
        resume = _FakeResume(
            experience=[
                _FakeExperience(
                    company="Acme",
                    title="Engineer",
                    start_date="2023-01",
                    end_date="2024-01",
                    current=False,
                    description="Work.",
                ),
                _FakeExperience(
                    company="Beta",
                    title="Senior",
                    start_date="2024-02",
                    end_date=None,
                    current=True,
                    description="Now.",
                ),
            ]
        )
        entries = experience_entries_from_resume(resume)
        assert len(entries) == 2
        assert entries[0]["end_date"] == "2024-01"
        # `current=True` → we stamp "Present" so the form shows something.
        assert entries[1]["end_date"] == "Present"

    def test_education_conversion_preserves_all_fields(self) -> None:
        resume = _FakeResume(
            education=[
                _FakeEducation(
                    school="MIT",
                    degree="BS",
                    field_of_study="CS",
                    graduation_year=2020,
                    gpa=3.9,
                ),
                _FakeEducation(
                    school="Stanford",
                    degree="MS",
                    field_of_study="AI",
                    graduation_year=2022,
                    gpa=None,
                ),
            ]
        )
        entries = education_entries_from_resume(resume)
        assert len(entries) == 2
        assert entries[0]["gpa"] == 3.9
        assert entries[1]["gpa"] is None
        assert entries[1]["school"] == "Stanford"

    def test_empty_resume_lists_produce_empty_entries(self) -> None:
        assert experience_entries_from_resume(_FakeResume()) == []
        assert education_entries_from_resume(_FakeResume()) == []


# ──────────────────────────────────────────────────────────────────────
# Tests — constructor and defaults
# ──────────────────────────────────────────────────────────────────────


class TestFillerConstructor:
    def test_rejects_empty_roots(self) -> None:
        with pytest.raises(ValueError):
            RepeatingSectionFiller(
                roots=[],
                section_name="work experience",
                section_heading_patterns=EXPERIENCE_SECTION_HEADINGS,
            )

    def test_default_add_button_patterns_match_common_variants(self) -> None:
        """The default add-button patterns should cover Workday, iCIMS, Greenhouse."""
        filler = RepeatingSectionFiller(
            roots=[FakePage([])],
            section_name="x",
            section_heading_patterns=["^x$"],
        )
        samples = [
            "Add",
            "+ Add",
            "Add Another",
            "Add Experience",
            "Add Work Experience",
            "Add Education",
            "Add Another Experience",
        ]
        for sample in samples:
            assert any(rx.search(sample) for rx in filler.add_btn_re), (
                f"Default add-button patterns did not match '{sample}'"
            )
