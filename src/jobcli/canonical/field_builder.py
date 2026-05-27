"""Build ApplicationField from various sources with validation and confidence.

This is the main entry point for creating canonical fields during execution.
"""

from datetime import datetime
from typing import Optional

from jobcli.canonical.confidence import calculate_confidence
from jobcli.canonical.mappers import ResumeFieldMapper, infer_semantic_type
from jobcli.canonical.models import (
    ApplicationField,
    ConfidenceScore,
    FieldSemanticType,
    FieldSource,
    ValidationResult,
    ValidationSeverity,
)
from jobcli.canonical.validators import validate_field_value
from jobcli.profile.schemas import ATSType, ResumeData


class FieldBuilder:
    """Builds canonical ApplicationField with validation and confidence.

    Usage:
        builder = FieldBuilder(resume, ats_type, page_index=0)

        # From ATS label (auto-infers semantic type)
        field = builder.from_label(
            field_id="email_input",
            raw_label="Email Address *",
            required=True,
            ats_selector="input[name='email']"
        )

        # From explicit semantic type
        field = builder.from_semantic_type(
            field_id="candidate_email",
            semantic_type=FieldSemanticType.EMAIL,
            raw_label="Email",
            required=True,
            ats_selector="#email"
        )
    """

    def __init__(
        self,
        resume: ResumeData,
        ats_type: ATSType,
        page_index: int = 0,
    ):
        self.resume = resume
        self.ats_type = ats_type
        self.page_index = page_index
        self.mapper = ResumeFieldMapper(resume)

    def from_label(
        self,
        field_id: str,
        raw_label: str,
        required: bool,
        ats_selector: Optional[str] = None,
        input_type: str = "text",
        placeholder: Optional[str] = None,
        options: list[str] | None = None,
    ) -> ApplicationField:
        """Build ApplicationField by inferring semantic type from label.

        Args:
            field_id: Unique ID for this field
            raw_label: Label as it appears on ATS (e.g., "Email Address *")
            required: Is field mandatory?
            ats_selector: CSS/XPath selector for this field
            input_type: HTML input type
            placeholder: Placeholder text if present
            options: For select/radio: available options

        Returns:
            Fully constructed ApplicationField with validation and confidence
        """
        semantic_type = infer_semantic_type(raw_label)
        return self.from_semantic_type(
            field_id=field_id,
            semantic_type=semantic_type,
            raw_label=raw_label,
            required=required,
            ats_selector=ats_selector,
            input_type=input_type,
            placeholder=placeholder,
            options=options,
        )

    def from_semantic_type(
        self,
        field_id: str,
        semantic_type: FieldSemanticType,
        raw_label: str,
        required: bool,
        ats_selector: Optional[str] = None,
        input_type: str = "text",
        placeholder: Optional[str] = None,
        options: list[str] | None = None,
        override_value: Optional[str] = None,
        override_source: Optional[FieldSource] = None,
    ) -> ApplicationField:
        """Build ApplicationField from explicit semantic type.

        Args:
            field_id: Unique ID for this field
            semantic_type: What this field means semantically
            raw_label: Label as it appears on ATS
            required: Is field mandatory?
            ats_selector: CSS/XPath selector
            input_type: HTML input type
            placeholder: Placeholder text
            options: For select/radio: available options
            override_value: Force a specific value (e.g., from memory/LLM)
            override_source: Source for override_value

        Returns:
            Fully constructed ApplicationField
        """
        # Determine value and source
        if override_value is not None:
            value = override_value
            source = override_source or FieldSource.RULE_BASED
        else:
            # Try resume first
            value = self.mapper.get_value(semantic_type)
            source = FieldSource.RESUME_JSON if value else FieldSource.DEFAULT_VALUE

        # Normalize label
        normalized_label = self._normalize_label(raw_label)

        # Validate the value
        validation = validate_field_value(semantic_type, value, required)

        # Calculate confidence
        # TODO: Hook into memory system for historical_success_rate
        confidence = calculate_confidence(
            source=source,
            validation=validation,
            historical_success_rate=None,
        )

        # Build the field
        return ApplicationField(
            field_id=field_id,
            semantic_type=semantic_type,
            raw_label=raw_label,
            normalized_label=normalized_label,
            required=required,
            input_type=input_type,
            placeholder=placeholder,
            options=options or [],
            value=value,
            source=source,
            confidence=confidence,
            validation=validation,
            ats_selector=ats_selector,
            ats_type=self.ats_type,
            page_index=self.page_index,
            timestamp=datetime.utcnow(),
        )

    def update_field_value(
        self,
        field: ApplicationField,
        new_value: str,
        new_source: FieldSource,
        historical_success_rate: Optional[float] = None,
    ) -> ApplicationField:
        """Update a field's value and recalculate confidence/validation.

        Use this when memory or LLM provides a better value after initial construction.

        Args:
            field: Existing ApplicationField
            new_value: New value to set
            new_source: Where new value came from
            historical_success_rate: Optional success rate from memory

        Returns:
            Updated ApplicationField (new instance)
        """
        # Re-validate with new value
        validation = validate_field_value(
            field.semantic_type,
            new_value,
            field.required,
        )

        # Recalculate confidence
        confidence = calculate_confidence(
            source=new_source,
            validation=validation,
            historical_success_rate=historical_success_rate,
        )

        # Return updated field (immutable pattern)
        return field.model_copy(
            update={
                "value": new_value,
                "source": new_source,
                "confidence": confidence,
                "validation": validation,
                "timestamp": datetime.utcnow(),
            }
        )

    @staticmethod
    def _normalize_label(label: str) -> str:
        """Normalize label for matching (lowercase, no punctuation)."""
        normalized = label.lower().strip()
        normalized = normalized.replace("*", "").replace(":", "").replace("?", "")
        return normalized.strip()


def create_empty_field(
    field_id: str,
    raw_label: str,
    required: bool,
    ats_type: ATSType,
    ats_selector: Optional[str] = None,
    page_index: int = 0,
) -> ApplicationField:
    """Create an empty field when semantic type is unknown.

    This is a fallback for fields the system doesn't recognize.
    Confidence will be low, triggering human review.

    Args:
        field_id: Unique ID
        raw_label: Label from ATS
        required: Is mandatory?
        ats_type: ATS platform
        ats_selector: Selector
        page_index: Which wizard page

    Returns:
        ApplicationField with UNKNOWN semantic type and low confidence
    """
    normalized_label = raw_label.lower().strip().replace("*", "").replace(":", "").strip()

    # No value, failed validation
    validation = ValidationResult(
        severity=ValidationSeverity.ERROR if required else ValidationSeverity.WARNING,
        message=f"Unknown field type: '{raw_label}'",
        expected_format="No mapping available",
        actual_value_preview="(empty)",
    )

    confidence = ConfidenceScore(
        value=0.0,
        source_weight=0.0,
        validation_passed=False,
        historical_success_rate=None,
    )

    return ApplicationField(
        field_id=field_id,
        semantic_type=FieldSemanticType.UNKNOWN,
        raw_label=raw_label,
        normalized_label=normalized_label,
        required=required,
        input_type="text",
        placeholder=None,
        options=[],
        value=None,
        source=FieldSource.DEFAULT_VALUE,
        confidence=confidence,
        validation=validation,
        ats_selector=ats_selector,
        ats_type=ats_type,
        page_index=page_index,
        timestamp=datetime.utcnow(),
    )
