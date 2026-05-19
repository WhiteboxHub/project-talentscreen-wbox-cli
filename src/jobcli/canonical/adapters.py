"""Adapters for backward compatibility with existing engine/executor code.

Converts between:
- BrowserAction ↔ ApplicationField
- LLMActionResponse ↔ List[ApplicationField]
- ApplicationField → ExecutionAction

This allows incremental adoption: new code uses canonical model,
existing code continues using BrowserAction until migrated.
"""

from typing import Optional

from jobcli.canonical.models import (
    ApplicationField,
    ExecutionAction,
    FieldSemanticType,
)
from jobcli.canonical.mappers import infer_semantic_type
from jobcli.profile.schemas import (
    ActionType,
    ATSType,
    BrowserAction,
    LLMActionResponse,
    SelectorType,
)


class BrowserActionAdapter:
    """Converts between BrowserAction (legacy) and ApplicationField (canonical)."""

    @staticmethod
    def to_application_field(
        action: BrowserAction,
        ats_type: ATSType,
        page_index: int = 0,
    ) -> Optional[ApplicationField]:
        """Convert BrowserAction → ApplicationField.

        Only converts FILL/TYPE/SELECT actions (those that have semantic meaning).
        CLICK/SCROLL/WAIT actions don't map to fields.

        Args:
            action: Legacy BrowserAction
            ats_type: ATS platform
            page_index: Current wizard page

        Returns:
            ApplicationField if convertible, else None
        """
        # Only convert value-bearing actions
        if action.action not in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT):
            return None

        # Import here to avoid circular dependency
        from jobcli.canonical.field_builder import create_empty_field

        # Generate field_id from selector (strip special chars)
        field_id = action.selector.replace("#", "").replace(".", "").replace("[", "_").replace("]", "")[:50]
        if not field_id:
            field_id = f"field_{hash(action.selector) % 10000}"

        # Infer semantic type from label
        raw_label = action.field_label or action.selector
        semantic_type = infer_semantic_type(raw_label)

        # Determine if required (heuristic: label ends with * or action.required flag)
        required = action.required or (raw_label.endswith("*"))

        # Create empty field (will be filled by FieldBuilder in real usage)
        field = create_empty_field(
            field_id=field_id,
            raw_label=raw_label,
            required=required,
            ats_type=ats_type,
            ats_selector=action.selector,
            page_index=page_index,
        )

        # If action has a value, update the field
        if action.value:
            # Import to avoid circular dependency
            from jobcli.canonical.field_builder import FieldBuilder
            from jobcli.canonical.models import FieldSource
            from jobcli.profile.schemas import ResumeData

            # Can't access resume here, so use DEFAULT_VALUE source
            # Real usage will have access to resume
            field = field.model_copy(update={"value": action.value})

        return field

    @staticmethod
    def from_application_field(field: ApplicationField) -> Optional[BrowserAction]:
        """Convert ApplicationField → BrowserAction.

        Args:
            field: Canonical ApplicationField

        Returns:
            BrowserAction for executor, or None if field has no selector
        """
        if not field.ats_selector or not field.value:
            return None

        # Map input_type to ActionType
        if field.input_type == "select":
            action_type = ActionType.SELECT
        elif field.input_type == "file":
            action_type = ActionType.UPLOAD
        else:
            action_type = ActionType.FILL

        return BrowserAction(
            action=action_type,
            selector=field.ats_selector,
            field_label=field.raw_label,
            value=field.value,
            selector_type=SelectorType.CSS,  # Assume CSS by default
            confidence=field.confidence.value,
            required=field.required,
        )


class LLMResponseAdapter:
    """Converts LLMActionResponse (legacy) to List[ApplicationField]."""

    @staticmethod
    def to_application_fields(
        llm_response: LLMActionResponse,
        ats_type: ATSType,
        page_index: int = 0,
    ) -> list[ApplicationField]:
        """Convert LLM action list → canonical fields.

        Args:
            llm_response: Legacy LLM response with actions
            ats_type: ATS platform
            page_index: Current page

        Returns:
            List of ApplicationField
        """
        fields: list[ApplicationField] = []

        for action in llm_response.actions:
            field = BrowserActionAdapter.to_application_field(
                action=action,
                ats_type=ats_type,
                page_index=page_index,
            )
            if field:
                fields.append(field)

        return fields


class ExecutionActionAdapter:
    """Converts ApplicationField → ExecutionAction for executor."""

    @staticmethod
    def from_application_field(field: ApplicationField) -> Optional[ExecutionAction]:
        """Convert ApplicationField → ExecutionAction.

        Args:
            field: Canonical field

        Returns:
            ExecutionAction ready for executor, or None if field incomplete
        """
        if not field.ats_selector or not field.value:
            return None

        # Map input_type to action_type string
        if field.input_type == "select":
            action_type = "select"
        elif field.input_type == "file":
            action_type = "upload"
        elif field.input_type == "checkbox":
            action_type = "click"
        else:
            action_type = "fill"

        return ExecutionAction(
            action_type=action_type,
            target_field_id=field.field_id,
            selector=field.ats_selector,
            value=field.value,
            confidence=field.confidence.value,
            required_pre_check=True,  # Always check if already filled
            verify_after=True,        # Always verify execution succeeded
        )

    @staticmethod
    def to_browser_action(execution_action: ExecutionAction) -> BrowserAction:
        """Convert ExecutionAction → BrowserAction for legacy executor.

        Args:
            execution_action: Canonical execution action

        Returns:
            BrowserAction
        """
        # Map action_type string to ActionType enum
        action_type_map = {
            "fill": ActionType.FILL,
            "type": ActionType.TYPE,
            "click": ActionType.CLICK,
            "select": ActionType.SELECT,
            "upload": ActionType.UPLOAD,
            "scroll": ActionType.SCROLL,
            "wait": ActionType.WAIT,
        }
        action_type = action_type_map.get(execution_action.action_type, ActionType.FILL)

        return BrowserAction(
            action=action_type,
            selector=execution_action.selector,
            value=execution_action.value,
            confidence=execution_action.confidence,
            selector_type=SelectorType.CSS,
            field_label=execution_action.target_field_id,  # Use field_id as label
            required=False,  # Will be determined by field
        )


def migrate_browser_actions_to_session(
    actions: list[BrowserAction],
    ats_type: ATSType,
    page_index: int = 0,
) -> list[ApplicationField]:
    """Helper: Convert a list of BrowserActions to ApplicationFields.

    Use this when integrating canonical model into existing engine code.

    Args:
        actions: List of legacy BrowserActions
        ats_type: ATS platform
        page_index: Current wizard page

    Returns:
        List of ApplicationField ready to add to ApplicationSession
    """
    fields: list[ApplicationField] = []
    for action in actions:
        field = BrowserActionAdapter.to_application_field(action, ats_type, page_index)
        if field:
            fields.append(field)
    return fields
