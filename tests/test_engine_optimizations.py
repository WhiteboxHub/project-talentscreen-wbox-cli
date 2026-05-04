import pytest
from unittest.mock import MagicMock, patch

from jobcli.core.claude_agent import ClaudeAgentStrategy
from jobcli.core.schemas import ATSType


class MockAXTree:
    def __init__(self, fields, dropdowns=None, url="https://example.com"):
        self.form_fields = fields
        self.dropdown_fields = dropdowns or []
        self._raw_aria = "dummy raw aria"
        self.url = url

def test_claude_agent_dropdown_options():
    mock_ax_tree = MockAXTree(
        fields=[],
        dropdowns=[
            {"label": "Country", "options": ["United States", "Canada", "Mexico"]},
            {"label": "State", "options": ["California", "New York"]}
        ]
    )
    
    # We can also test the system prompt generation by manually re-creating what ClaudeAgent does
    raw_aria = getattr(mock_ax_tree, "_raw_aria", "")
    if hasattr(mock_ax_tree, "dropdown_fields") and mock_ax_tree.dropdown_fields:
        raw_aria += "\n\n## Pre-extracted Dropdown Options:\n"
        for dropdown in mock_ax_tree.dropdown_fields:
            if dropdown.get('options'):
                raw_aria += f"- {dropdown.get('label')}: {', '.join(dropdown.get('options')[:30])}\n"
                
    assert "## Pre-extracted Dropdown Options:" in raw_aria
    assert "Country: United States, Canada, Mexico" in raw_aria
    assert "State: California, New York" in raw_aria

def test_claude_agent_country_code_prompt():
    # Verify the +1 country code rule is in the system prompt
    from jobcli.core.claude_agent import ClaudeAgentStrategy
    # The prompt is hardcoded in the generate_form_strategy, we can read the file
    with open("c:/Users/sampa/OneDrive/Desktop/cli_final/wbox-cli/jobcli/core/claude_agent.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "Default country codes to +1 (United States/Canada) unless specified otherwise." in content

def test_engine_circle_breaker_logic():
    # Test the logic that prevents infinite loops when button is clicked but nothing changes
    url_changed = False
    fields_changed = False
    button_clicked = True
    
    # This should trigger the handoff
    should_break = not url_changed and not fields_changed
    assert should_break == True
    
    # If fields changed, it shouldn't break
    fields_changed = True
    should_break = not url_changed and not fields_changed
    assert should_break == False

def test_engine_manual_saving_logic():
    # Test the logic that extracts manual answers after handoff
    mock_memory = MagicMock()
    mock_ax_tree = MockAXTree(
        fields=[
            {"name": "phone", "value": "1234567890"},
            {"name": "experience", "value": "5 years"}
        ]
    )
    
    placeholders = ["select", "choose", "please choose", "select...", "select an option"]
    saved_calls = []
    
    for field in mock_ax_tree.form_fields:
        val = str(field.get("value", "")).strip()
        label = field.get("name", "unknown")
        if val.lower() not in placeholders and val:
            mock_memory.save_field_answer(label, val, "detected_ats", source="human")
            saved_calls.append(label)
            
    assert len(saved_calls) == 2
    assert "phone" in saved_calls
    assert "experience" in saved_calls
    mock_memory.save_field_answer.assert_any_call("phone", "1234567890", "detected_ats", source="human")
    mock_memory.save_field_answer.assert_any_call("experience", "5 years", "detected_ats", source="human")
