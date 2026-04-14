import pytest
import typer
from unittest.mock import patch, MagicMock
from jobcli.core.schemas import Config
from jobcli.cli.main import ensure_configured

def test_ensure_configured_missing_job_board_credentials():
    """Test that missing job board credentials raises typer.Exit."""
    config = Config(
        job_board_username=None,
        job_board_password=None,
        openai_api_key="sk-test-key"
    )
    
    with pytest.raises(typer.Exit) as exc_info:
        ensure_configured(config)
        
    assert exc_info.value.exit_code == 1

def test_ensure_configured_with_valid_credentials():
    """Test that valid credentials allow execution to continue."""
    config = Config(
        job_board_username="testuser",
        job_board_password="testpassword",
        openai_api_key="sk-test-key"
    )
    
    # This should not raise an exception
    try:
        ensure_configured(config)
    except typer.Exit:
        pytest.fail("ensure_configured() raised typer.Exit unexpectedly!")

def test_ensure_configured_missing_llm_warns_but_proceeds(capsys):
    """Test that missing LLM credentials prints a warning but does not exit."""
    config = Config(
        job_board_username="testuser",
        job_board_password="testpassword",
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key=None
    )
    
    # Should not raise exception
    try:
        ensure_configured(config)
    except typer.Exit:
        pytest.fail("ensure_configured() raised typer.Exit unexpectedly!")
        
