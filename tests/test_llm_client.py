import json
import pytest
from unittest.mock import MagicMock, patch

from jobcli.llm.client import LLMClient
from jobcli.core.schemas import PersonalInfo, ResumeData, WorkAuthorization

@pytest.fixture
def mock_resume():
    return ResumeData(
        personal=PersonalInfo(first_name="Test", last_name="User", email="test@example.com", phone="1234567890"),
        work_authorization=WorkAuthorization()
    )

@pytest.fixture
def llm_client():
    return LLMClient(provider="openai", api_key="test-key")

def test_validate_response_valid_json(llm_client):
    """Test parsing a perfectly formatted LLM JSON response."""
    valid_json = '''
    {
      "actions": [
        {
          "action": "click",
          "selector": "Apply Now",
          "selector_type": "text",
          "field_label": "Apply Button",
          "confidence": 0.9
        }
      ],
      "reasoning": "Found the exact matching apply button text",
      "detected_ats": "lever",
      "detected_fields": [],
      "confidence": 0.95,
      "requires_human": false
    }
    '''
    
    result = llm_client._validate_response(valid_json)
    assert result is not None
    assert len(result.actions) == 1
    assert result.actions[0].action.value == "click"
    assert result.actions[0].selector == "Apply Now"
    assert result.requires_human is False

def test_validate_response_invalid_json_formatting(llm_client):
    """Test parsing badly formatted generic text."""
    bad_json = "Here is what I think. You should click the submit button. {bad JSON}"
    
    result = llm_client._validate_response(bad_json)
    assert result is None  # Should cleanly fail and return None instead of crashing

def test_validate_response_schema_validation_error(llm_client):
    """Test parsing JSON that fails Pydantic schema validation."""
    invalid_schema_json = '''
    {
      "actions": [
        {
          "action": "JUMP", 
          "selector": "Apply Now"
        }
      ]
    }
    '''
    
    # Missing fields, invalid Action Enum "JUMP"
    result = llm_client._validate_response(invalid_schema_json)
    assert result is None
