"""Strict execution action schemas.

Simple, structured actions that the execution engine can deterministically execute.
All actions include target field, validation requirements, and retry policy.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of execution actions."""

    FILL_INPUT = "fill_input"
    CLICK_BUTTON = "click_button"
    SELECT_OPTION = "select_option"
    UPLOAD_FILE = "upload_file"
    WAIT = "wait"
    VERIFY = "verify"


class ExecutionAction(BaseModel):
    """Base execution action with common fields.

    All actions must specify:
    - action: What type of action
    - target: Which field/element (field_id from canonical model)
    - selector: CSS/XPath selector for DOM element
    - verify_after: Should we read back and verify?
    """

    action: ActionType
    target: str = Field(..., description="Target field_id from canonical model")
    selector: str = Field(..., description="CSS/XPath selector for DOM element")
    verify_after: bool = Field(True, description="Verify action succeeded?")
    timeout_ms: int = Field(5000, description="Timeout in milliseconds")
    retry_count: int = Field(3, description="Max retry attempts")


class FillInputAction(ExecutionAction):
    """Fill a text input field.

    Example:
        {
            "action": "fill_input",
            "target": "candidate_email",
            "selector": "input[name='email']",
            "value": "user@email.com",
            "verify_after": true
        }
    """

    action: Literal[ActionType.FILL_INPUT] = ActionType.FILL_INPUT
    value: str = Field(..., description="Value to fill")
    clear_first: bool = Field(True, description="Clear existing value first?")


class ClickAction(ExecutionAction):
    """Click a button or link.

    Example:
        {
            "action": "click_button",
            "target": "submit_button",
            "selector": "button[type='submit']",
            "verify_after": false
        }
    """

    action: Literal[ActionType.CLICK_BUTTON] = ActionType.CLICK_BUTTON
    wait_for_navigation: bool = Field(False, description="Expect page navigation?")


class SelectOptionAction(ExecutionAction):
    """Select an option from dropdown.

    Example:
        {
            "action": "select_option",
            "target": "country_field",
            "selector": "select[name='country']",
            "value": "United States",
            "match_strategy": "exact"
        }
    """

    action: Literal[ActionType.SELECT_OPTION] = ActionType.SELECT_OPTION
    value: str = Field(..., description="Option to select")
    match_strategy: Literal["exact", "contains", "fuzzy"] = Field(
        "exact",
        description="How to match option text",
    )


class UploadFileAction(ExecutionAction):
    """Upload a file.

    Example:
        {
            "action": "upload_file",
            "target": "resume_upload",
            "selector": "input[type='file']",
            "file_path": "/path/to/resume.pdf",
            "verify_after": true
        }
    """

    action: Literal[ActionType.UPLOAD_FILE] = ActionType.UPLOAD_FILE
    file_path: str = Field(..., description="Absolute path to file")


class WaitAction(ExecutionAction):
    """Wait for element or time.

    Example:
        {
            "action": "wait",
            "target": "loading_spinner",
            "selector": ".spinner",
            "wait_type": "disappear",
            "timeout_ms": 10000
        }
    """

    action: Literal[ActionType.WAIT] = ActionType.WAIT
    wait_type: Literal["appear", "disappear", "time"] = Field(
        "appear",
        description="What to wait for",
    )
    verify_after: bool = Field(False, description="Wait actions don't verify")


class VerifyAction(ExecutionAction):
    """Verify element state without modifying.

    Example:
        {
            "action": "verify",
            "target": "email_field",
            "selector": "input[name='email']",
            "expected_value": "user@email.com",
            "check_type": "value"
        }
    """

    action: Literal[ActionType.VERIFY] = ActionType.VERIFY
    check_type: Literal["exists", "visible", "value", "text"] = Field(
        "exists",
        description="What to verify",
    )
    expected_value: Optional[str] = Field(None, description="Expected value (if checking value/text)")
    verify_after: bool = Field(False, description="Verify actions don't need verification")
