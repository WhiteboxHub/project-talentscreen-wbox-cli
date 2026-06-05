"""Tests for memory-first gap resolution (MemoryPrefiller)."""

import pytest

from jobcli.intelligence.memory import AgentMemory
from jobcli.intelligence.memory_prefill import MemoryPrefiller
from jobcli.profile.schemas import (
    ATSType,
    ActionType,
    CommonQuestions,
    PersonalInfo,
    ResumeData,
)
from jobcli.storage.models import Database
from jobcli.storage.repositories import FieldAnswerRepository
from jobcli.sync.constants import MIN_SUCCESS_COUNT


@pytest.fixture
def db():
    d = Database("sqlite:///:memory:")
    d.create_tables()
    return d


@pytest.fixture
def session(db):
    s = db.get_session()
    yield s
    s.close()


@pytest.fixture
def memory(session):
    return AgentMemory(session, infer_location_country=False, job_id=1)


@pytest.fixture
def resume():
    return ResumeData(
        personal=PersonalInfo(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
        )
    )


def _seed_notice_period(session, ats: ATSType, value: str = "30 days") -> None:
    repo = FieldAnswerRepository(session)
    for _ in range(MIN_SUCCESS_COUNT):
        repo.save_answer(
            "Notice Period",
            "notice_period",
            value,
            ats,
            success=True,
            source="human",
        )


class TestMemoryPrefiller:
    def test_notice_period_variants_resolve_to_action(self, memory, session, resume):
        _seed_notice_period(session, ATSType.GREENHOUSE)
        prefiller = MemoryPrefiller()
        gaps = [
            {
                "label": "How many days notice do you need?",
                "role": "textbox",
                "required": True,
                "options": [],
                "current_value": "",
            }
        ]
        actions, resolutions = prefiller.gaps_to_actions(
            gaps, memory, resume, ATSType.GREENHOUSE
        )
        assert len(actions) == 1
        assert actions[0].action == ActionType.FILL
        assert actions[0].value == "30 days"
        assert resolutions[0].source == "saved_memory"

    def test_common_questions_notice_used_when_no_db(self, memory, resume):
        prefiller = MemoryPrefiller()
        questions = CommonQuestions(notice_period="2 weeks")
        gaps = [{"label": "Notice Period", "role": "textbox", "required": True, "options": [], "current_value": ""}]
        actions, _ = prefiller.gaps_to_actions(
            gaps, memory, resume, ATSType.LEVER, common_questions=questions
        )
        assert len(actions) == 1
        assert actions[0].value == "2 weeks"

    def test_enrich_gaps_adds_suggested_value(self, memory, session, resume):
        _seed_notice_period(session, ATSType.WORKDAY, "30 days")
        prefiller = MemoryPrefiller()
        gaps = [{"label": "Current notice period", "role": "textbox", "required": True, "options": [], "current_value": ""}]
        enriched = prefiller.enrich_gaps_with_suggestions(
            gaps, memory, resume, ATSType.WORKDAY
        )
        assert enriched[0]["suggested_value"] == "30 days"
        assert enriched[0]["suggested_source"] == "saved_memory"

    def test_dropdown_uses_synonym_option_match(self, memory, session, resume):
        prefiller = MemoryPrefiller()
        gaps = [
            {
                "label": "Gender",
                "role": "combobox",
                "required": True,
                "options": ["Man", "Woman", "Non-binary"],
                "current_value": "",
            }
        ]
        # Gender maps via demographics in resume - seed DB with Male, expect Man option
        repo = FieldAnswerRepository(session)
        for _ in range(MIN_SUCCESS_COUNT):
            repo.save_answer("Gender", "gender", "Male", ATSType.GREENHOUSE, success=True, source="human")
        actions, _ = prefiller.gaps_to_actions(gaps, memory, resume, ATSType.GREENHOUSE)
        assert len(actions) == 1
        assert actions[0].action == ActionType.SELECT
        assert actions[0].value == "Man"

    def test_prefill_only_targets_empty_gaps_from_payload(self, memory, session, resume):
        """build_empty_fields_payload excludes filled fields; prefill only acts on gaps."""
        _seed_notice_period(session, ATSType.GREENHOUSE)
        from jobcli.llm.ax_tree_extractor import AccessibilityTree

        ax = AccessibilityTree(
            url="https://example.com",
            title="Apply",
            root={"role": "WebArea", "name": "", "children": []},
            form_fields=[
                {"name": "First Name", "role": "textbox", "required": True, "value": "Jane"},
                {"name": "Notice Period", "role": "textbox", "required": True, "value": ""},
            ],
        )
        from jobcli.llm.empty_fields import build_empty_fields_payload

        gaps = build_empty_fields_payload(ax)
        assert len(gaps) == 1
        assert gaps[0]["label"] == "Notice Period"
        actions, _ = MemoryPrefiller().gaps_to_actions(
            gaps, memory, resume, ATSType.GREENHOUSE
        )
        assert len(actions) == 1
        assert actions[0].field_label == "Notice Period"
