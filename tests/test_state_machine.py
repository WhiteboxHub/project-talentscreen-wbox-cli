import pytest
from unittest.mock import MagicMock, patch

from jobcli.core.state_machine import ApplicationStateMachine, ApplicationGraphState
from jobcli.core.schemas import (
    ActionType,
    ApplicationState,
    ApplicationStatus,
    ATSType,
    BrowserAction,
    ExecutionPhase,
    PersonalInfo,
    ResumeData,
    SelectorType,
    WorkAuthorization,
)


@pytest.fixture
def mock_resume() -> ResumeData:
    return ResumeData(
        personal=PersonalInfo(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="1234567890",
        ),
        work_authorization=WorkAuthorization(),
    )


def _graph_base(mock_resume: ResumeData, mock_page: MagicMock, mock_logger: MagicMock) -> ApplicationGraphState:
    return ApplicationGraphState(
        page=mock_page,
        state=ApplicationState(job_id=1, current_url="http://test.com"),
        resume=mock_resume,
        logger=mock_logger,
        ats_type=ATSType.GREENHOUSE,
        resume_pdf_path="test.pdf",
        locator_repo=MagicMock(),
        llm_client=MagicMock(),
        phase_results={},
        current_phase=ExecutionPhase.RULES,
        final_status=ApplicationStatus.PENDING,
        job_id=None,
        job_repo=None,
        agent_memory=None,
        job_board_url=None,
        infer_location_country=True,
    )


@patch("jobcli.core.state_machine.AccessibilityTreeExtractor")
@patch("jobcli.core.state_machine.ToolExecutor")
def test_phase_2_llm_uses_axtree(MockToolExecutor, MockExtractor, mock_resume: ResumeData) -> None:
    """Phase 2 LLM uses AXTree, memory context kwargs, and ToolExecutor with memory hooks."""

    mock_extractor_instance = MagicMock()
    mock_axtree_obj = MagicMock()
    mock_axtree_obj.model_dump.return_value = {"mock": "dump"}
    mock_axtree_obj.dropdown_fields = []
    mock_axtree_obj.url = "http://test.com/job"
    mock_axtree_obj.form_fields = []
    mock_extractor_instance.extract.return_value = mock_axtree_obj
    MockExtractor.return_value = mock_extractor_instance

    mock_llm_client = MagicMock()
    mock_llm_response = MagicMock()
    mock_llm_response.requires_human = False
    mock_llm_response.actions = [
        BrowserAction(
            action=ActionType.FILL,
            selector="Email",
            selector_type=SelectorType.TEXT,
            value="test@example.com",
            field_label="Email",
            confidence=0.95,
        )
    ]
    mock_llm_client.analyze_page_from_axtree.return_value = mock_llm_response

    mock_logger = MagicMock()
    mock_page = MagicMock()

    mock_executor_instance = MagicMock()
    mock_executor_instance.execute_actions.return_value = {"action_0_fill": True}
    MockToolExecutor.return_value = mock_executor_instance

    state = _graph_base(mock_resume, mock_page, mock_logger)
    state["llm_client"] = mock_llm_client

    machine = ApplicationStateMachine()
    result_state = machine._phase_2_llm(state)

    MockExtractor.assert_called_once_with(mock_page)
    mock_extractor_instance.extract.assert_called()

    mock_llm_client.analyze_page_from_axtree.assert_called_once()
    call_kw = mock_llm_client.analyze_page_from_axtree.call_args
    assert call_kw.kwargs.get("task") == "find_apply_button_and_fill_form"
    assert "memory_context" in call_kw.kwargs
    assert call_kw.kwargs.get("dropdown_options") == []

    MockToolExecutor.assert_called_once()
    tc_args, tc_kw = MockToolExecutor.call_args
    assert tc_args[0] is mock_page
    assert tc_kw.get("memory") is None
    assert tc_kw.get("ats_type") == ATSType.GREENHOUSE
    mock_executor_instance.execute_actions.assert_called_once_with(mock_llm_response)

    assert result_state["phase_results"]["llm"] is True
