import pytest
from unittest.mock import MagicMock, patch

from jobcli.core.state_machine import ApplicationStateMachine, ApplicationGraphState
from jobcli.core.schemas import ApplicationState, ATSType, ExecutionPhase, ResumeData, PersonalInfo, WorkAuthorization

@pytest.fixture
def mock_resume():
    return ResumeData(
        personal=PersonalInfo(first_name="Test", last_name="User", email="test@example.com", phone="1234567890"),
        work_authorization=WorkAuthorization()
    )

@patch('jobcli.core.state_machine.AccessibilityTreeExtractor')
@patch('jobcli.core.state_machine.ToolExecutor')
def test_phase_2_llm_uses_axtree(MockToolExecutor, MockExtractor, mock_resume):
    """Test that the Phase 2 LLM node properly initializes and uses the AXTree Extractor."""
    
    # Setup Mocks
    mock_extractor_instance = MagicMock()
    mock_axtree_obj = MagicMock()
    # Ensure extract() returns our mocked AccessibilityTree object, and model_dump() returns a dict for logger
    mock_extractor_instance.extract.return_value = mock_axtree_obj
    mock_axtree_obj.model_dump.return_value = {"mock": "dump"}
    MockExtractor.return_value = mock_extractor_instance

    mock_llm_client = MagicMock()
    mock_llm_response = MagicMock()
    mock_llm_response.requires_human = False
    mock_llm_response.actions = []
    mock_llm_client.analyze_page_from_axtree.return_value = mock_llm_response

    mock_logger = MagicMock()
    mock_page = MagicMock()
    
    mock_executor_instance = MagicMock()
    mock_executor_instance.execute_actions.return_value = {"action_0": True}
    MockToolExecutor.return_value = mock_executor_instance

    # Initialize state
    state = ApplicationGraphState(
        page=mock_page,
        state=ApplicationState(job_id=1, current_url="http://test.com"),
        resume=mock_resume,
        logger=mock_logger,
        ats_type=ATSType.GREENHOUSE,
        resume_pdf_path="test.pdf",
        locator_repo=MagicMock(),
        llm_client=mock_llm_client,
        phase_results={},
        current_phase=ExecutionPhase.RULES,
        final_status="pending"
    )

    machine = ApplicationStateMachine()
    
    # Execute node
    result_state = machine._phase_2_llm(state)
    
    # Verify Extractor was invoked correctly
    MockExtractor.assert_called_once_with(mock_page)
    mock_extractor_instance.extract.assert_called_once()
    
    # Verify the LLM client specifically used the AXTree payload
    mock_llm_client.analyze_page_from_axtree.assert_called_once_with(
        mock_axtree_obj,
        mock_resume,
        task="find_apply_button_and_fill_form"
    )
    
    # Verify Execution
    MockToolExecutor.assert_called_once_with(mock_page, mock_logger)
    mock_executor_instance.execute_actions.assert_called_once_with(mock_llm_response)
    
    assert result_state["phase_results"]["llm"] is True
