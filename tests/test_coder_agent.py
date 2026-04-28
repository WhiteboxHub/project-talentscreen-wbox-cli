import pytest
from unittest.mock import MagicMock, patch

from jobcli.core.schemas import Config
from jobcli.coder.agent import CodingAgent

@pytest.fixture
def agent():
    config = Config()
    config.default_llm_provider = "openai"
    config.openai_api_key = "test_key"
    return CodingAgent(config)

def test_parse_response(agent):
    response_text = """
    [THOUGHT]
    I need to read the file.
    [ACTION]
    read_file(path="app.py")
    """
    thought, action, final = agent._parse_response(response_text)
    assert "I need to read the file." in thought
    assert "read_file(path=\"app.py\")" in action
    assert final is None

    response_text_final = """
    [THOUGHT]
    Done.
    [FINAL_ANSWER]
    Task completed successfully.
    """
    thought, action, final = agent._parse_response(response_text_final)
    assert "Done." in thought
    assert action is None
    assert "Task completed successfully." in final

def test_parse_tool_call(agent):
    func_name, args, kwargs = agent._parse_tool_call("read_file('app.py', start_line=1)")
    assert func_name == "read_file"
    assert args == ["app.py"]
    assert kwargs == {"start_line": 1}
    
    # Test kwargs only
    func_name, args, kwargs = agent._parse_tool_call("list_dir(path='.')")
    assert func_name == "list_dir"
    assert args == []
    assert kwargs == {"path": "."}
    
    # Test positional only
    func_name, args, kwargs = agent._parse_tool_call("run_command('echo test')")
    assert func_name == "run_command"
    assert args == ["echo test"]
    assert kwargs == {}
    
    # Test invalid syntax
    func_name, args, kwargs = agent._parse_tool_call("not_a_function('what")
    assert func_name is None
    assert "error" in kwargs

@patch("jobcli.coder.agent.Confirm.ask")
def test_execute_tool_requires_approval(mock_confirm, agent):
    # Mock user denying permission
    mock_confirm.return_value = False
    
    result = agent._execute_tool("run_command", ["echo test"], {})
    assert "Error: User denied permission" in result
    mock_confirm.assert_called_once()
    
    # Mock user approving
    mock_confirm.reset_mock()
    mock_confirm.return_value = True
    
    # We mock the actual tool to prevent it from running for real
    with patch.dict(agent.tools_map, {"run_command": lambda *args, **kwargs: "Mock executed"}):
        result = agent._execute_tool("run_command", ["echo test"], {})
        assert result == "Mock executed"
        mock_confirm.assert_called_once()

def test_execute_tool_safe(agent):
    # read_file is safe, doesn't require confirmation
    with patch.dict(agent.tools_map, {"read_file": lambda *args, **kwargs: "File content"}):
        result = agent._execute_tool("read_file", ["app.py"], {})
        assert result == "File content"
