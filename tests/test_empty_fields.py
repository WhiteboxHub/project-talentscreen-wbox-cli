"""Tests for Form-Filling Auditor gap list builder."""

import pytest

from jobcli.intelligence.memory import AgentMemory
from jobcli.intelligence.memory_prefill import MemoryPrefiller
from jobcli.llm.ax_tree_extractor import AccessibilityTree
from jobcli.llm.empty_fields import build_empty_fields_payload, is_auditor_fill_task
from jobcli.llm.client import LLMClient
from jobcli.profile.schemas import ATSType, PersonalInfo, ResumeData
from jobcli.storage.models import Database
from jobcli.storage.repositories import FieldAnswerRepository
from jobcli.sync.constants import MIN_SUCCESS_COUNT


def test_is_auditor_fill_task():
    assert is_auditor_fill_task("fill_form_fields_only")
    assert is_auditor_fill_task("fill_empty_fields_only")
    assert not is_auditor_fill_task("find_apply_button_and_fill_form")


def test_build_empty_fields_required_only():
    ax = AccessibilityTree(
        url="https://boards.greenhouse.io/test/jobs/1",
        title="Apply",
        root={"role": "WebArea", "name": "", "children": []},
        form_fields=[
            {
                "name": "First Name",
                "role": "textbox",
                "required": True,
                "value": "Ada",
            },
            {
                "name": "Why do you want this role?",
                "role": "textbox",
                "required": True,
                "value": "",
            },
            {
                "name": "Referral source",
                "role": "combobox",
                "required": False,
                "value": "",
            },
        ],
    )
    gaps = build_empty_fields_payload(ax)
    labels = [g["label"] for g in gaps]
    assert "Why do you want this role?" in labels
    assert "First Name" not in labels
    assert "Referral source" not in labels


def test_build_empty_fields_merges_dom_dropdown_gaps():
    ax = AccessibilityTree(
        url="https://example.com",
        title="Form",
        root={"role": "WebArea", "name": "", "children": []},
        form_fields=[],
    )
    gaps = build_empty_fields_payload(
        ax,
        extra_gap_labels=["Work Authorization *"],
        dropdown_options=[
            {"label": "Work Authorization", "options": ["Yes", "No"]},
        ],
    )
    assert len(gaps) == 1
    assert gaps[0]["options"] == ["Yes", "No"]


def test_enrich_gaps_populates_suggested_value():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    session = db.get_session()
    repo = FieldAnswerRepository(session)
    for _ in range(MIN_SUCCESS_COUNT):
        repo.save_answer(
            "Notice Period",
            "notice_period",
            "30 days",
            ATSType.GREENHOUSE,
            success=True,
            source="human",
        )
    memory = AgentMemory(session, infer_location_country=False, job_id=1)
    resume = ResumeData(
        personal=PersonalInfo(first_name="Ada", last_name="Lovelace", email="a@b.com")
    )
    ax = AccessibilityTree(
        url="https://boards.greenhouse.io/test/jobs/1",
        title="Apply",
        root={"role": "WebArea", "name": "", "children": []},
        form_fields=[
            {
                "name": "Notice Period",
                "role": "textbox",
                "required": True,
                "value": "",
            },
        ],
    )
    gaps = build_empty_fields_payload(ax)
    enriched = MemoryPrefiller().enrich_gaps_with_suggestions(
        gaps, memory, resume, ATSType.GREENHOUSE
    )
    assert enriched[0]["suggested_value"] == "30 days"
    assert enriched[0]["suggested_source"] == "saved_memory"
    session.close()


def test_validate_response_wraps_bare_array():
    client = LLMClient(provider="openai", api_key="test")
    raw = """[
      {
        "thought": "Resume shows immediate availability.",
        "field_label": "Notice period",
        "selector": "Notice period",
        "selector_type": "text",
        "action": "FILL",
        "value": "Immediately"
      }
    ]"""
    result = client._validate_response(raw)
    assert result is not None
    assert len(result.actions) == 1
    assert result.actions[0].action.value == "fill"
    assert result.actions[0].thought == "Resume shows immediate availability."
