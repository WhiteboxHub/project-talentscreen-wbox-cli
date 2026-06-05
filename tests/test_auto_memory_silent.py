"""AUTO mode should reuse memory without blocking on terminal prompts."""

from unittest.mock import MagicMock, patch

import pytest

from jobcli.human.agent_interface import AgentInterface
from jobcli.profile.schemas import ATSType, InteractionMode, PersonalInfo, ResumeData


@pytest.fixture
def agent():
    iface = AgentInterface(
        page=MagicMock(),
        locator_repo=MagicMock(),
        mode=InteractionMode.AUTO,
        resume=ResumeData(
            personal=PersonalInfo(first_name="A", last_name="B", email="a@b.com")
        ),
        ats_type=ATSType.GREENHOUSE,
    )
    iface.memory = MagicMock()
    return iface


class TestAutoMemorySilent:
    def test_resolve_memory_silent_delegates_to_lookup(self, agent):
        agent.memory.get_best_answer.return_value = ("30 days", "saved_memory")
        val, src = agent.resolve_memory_silent("Notice Period")
        assert val == "30 days"
        assert src == "saved_memory"

    def test_request_field_input_returns_cached_in_auto_without_prompt(self, agent):
        agent.memory.get_best_answer.return_value = ("30 days", "saved_memory")
        with patch.object(agent, "_get_user_input") as mock_input:
            with patch("jobcli.utils.form_sync.apply_field_value", return_value=True):
                answer = agent.request_field_input("Notice Period", required=True)
        assert answer == "30 days"
        mock_input.assert_not_called()

    def test_request_field_input_prompts_when_no_cache_and_not_auto(self):
        iface = AgentInterface(
            page=MagicMock(),
            locator_repo=MagicMock(),
            mode=InteractionMode.SUPERVISED,
            resume=ResumeData(
                personal=PersonalInfo(first_name="A", last_name="B", email="a@b.com")
            ),
            ats_type=ATSType.GREENHOUSE,
        )
        iface.memory = MagicMock()
        iface.memory.get_best_answer.return_value = (None, "not_found")
        with patch.object(iface, "_get_user_input", return_value="45 days") as mock_input:
            with patch("jobcli.utils.form_sync.apply_field_value", return_value=True):
                with patch.object(iface, "persist_human_answer", return_value=True):
                    answer = iface.request_field_input("Notice Period", required=True)
        assert answer == "45 days"
        mock_input.assert_called()
