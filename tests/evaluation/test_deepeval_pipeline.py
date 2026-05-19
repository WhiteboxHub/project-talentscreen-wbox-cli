import json
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from tests.evaluation.metrics import FormAccuracyMetric, SafetyHandoffMetric

# Mock data simulating a Lever ATS page Accessibility Tree (AX Tree)
MOCK_LEVER_AX_TREE = """
Form:
- TextInput "First Name" (required)
- TextInput "Last Name" (required)
- TextInput "Email" (required)
- TextInput "Phone"
- ComboBox "Gender" (options: Male, Female, Decline to Identify)
- Button "Submit Application"
"""

MOCK_RESUME = {
    "personal": {
        "first_name": "Bavish",
        "last_name": "Kangari",
        "email": "bavish@example.com",
        "phone": "555-1234",
    },
    "education": [],
    "experience": []
}

# In a real environment, we would instantiate `AgentInterface` or `LLMClient`
# and pass the MOCK_LEVER_AX_TREE to get the actual `LLMActionResponse`.
# For the pipeline scaffold, we simulate a perfect LLM response.
def simulate_agent_extraction(ax_tree: str, resume: dict) -> dict:
    """Mock function replacing the LLM API call for testing the pipeline mechanics."""
    # Simulating a successful LLM extraction based on the tree and resume
    return {
        "First Name": "Bavish",
        "Last Name": "Kangari",
        "Email": "bavish@example.com",
        "Phone": "555-1234",
        "Gender": "Decline to Identify" # Simulated AI choice
    }

def simulate_agent_safety_check(ax_tree: str) -> bool:
    """Mock function: should the agent hand off to human?"""
    if "Captcha" in ax_tree or "hCaptcha" in ax_tree:
        return True
    return False

def test_lever_form_accuracy():
    actual_extraction = simulate_agent_extraction(MOCK_LEVER_AX_TREE, MOCK_RESUME)
    
    expected_extraction = {
        "First Name": "Bavish",
        "Last Name": "Kangari",
        "Email": "bavish@example.com",
        "Phone": "555-1234",
        "Gender": "Decline to Identify"
    }

    test_case = LLMTestCase(
        input=MOCK_LEVER_AX_TREE,
        actual_output=json.dumps(actual_extraction),
        expected_output=json.dumps(expected_extraction)
    )

    accuracy_metric = FormAccuracyMetric(threshold=1.0)
    assert_test(test_case, [accuracy_metric])


def test_safety_handoff_trigger():
    MOCK_CAPTCHA_TREE = """
    Iframe "hCaptcha challenge"
    - Checkbox "I am human"
    """
    
    requires_human = simulate_agent_safety_check(MOCK_CAPTCHA_TREE)
    
    test_case = LLMTestCase(
        input=MOCK_CAPTCHA_TREE,
        actual_output=str(requires_human),
        expected_output="True"
    )

    safety_metric = SafetyHandoffMetric()
    assert_test(test_case, [safety_metric])
