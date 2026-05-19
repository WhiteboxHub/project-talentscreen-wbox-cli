"""Confidence score calculation for field values.

Confidence = P(this value will be accepted by the ATS form validation).

Factors:
- Source reliability (resume > memory_high > llm > default)
- Semantic validation result (passed > warning > failed)
- Historical success rate from memory system
"""

from jobcli.canonical.models import (
    ConfidenceScore,
    FieldSource,
    ValidationResult,
    ValidationSeverity,
)


# Source reliability weights [0.0, 1.0]
_SOURCE_WEIGHTS = {
    FieldSource.RESUME_JSON: 0.95,           # Highest trust: user provided
    FieldSource.MEMORY_HIGH_CONFIDENCE: 0.85,  # Learned, validated ≥3 times
    FieldSource.HUMAN_PROVIDED: 0.90,        # Human entered this session
    FieldSource.ATS_PREFILLED: 0.80,         # Extension/browser autofilled
    FieldSource.RULE_BASED: 0.75,            # Deterministic rule matched
    FieldSource.LLM_REASONING: 0.65,         # LLM generated
    FieldSource.MEMORY_LOW_CONFIDENCE: 0.50,  # Learned but < threshold
    FieldSource.DEFAULT_VALUE: 0.30,         # Fallback guess
}


def calculate_confidence(
    source: FieldSource,
    validation: ValidationResult,
    historical_success_rate: float | None = None,
) -> ConfidenceScore:
    """Calculate confidence score for a field value.

    Algorithm:
        base_confidence = SOURCE_WEIGHTS[source]
        validation_modifier = 1.0 (OK) | 0.8 (WARNING) | 0.3 (ERROR)
        historical_modifier = historical_success_rate (if available)
        final = base * validation_modifier * historical_modifier

    Args:
        source: Where the value came from
        validation: Result of semantic validation
        historical_success_rate: Optional past success rate (0.0-1.0)

    Returns:
        ConfidenceScore with computed value
    """
    # Base confidence from source
    base_confidence = _SOURCE_WEIGHTS.get(source, 0.5)

    # Validation modifier
    if validation.severity == ValidationSeverity.OK:
        validation_modifier = 1.0
    elif validation.severity == ValidationSeverity.WARNING:
        validation_modifier = 0.8
    else:  # ERROR
        validation_modifier = 0.3

    # Historical modifier (if available)
    historical_modifier = historical_success_rate if historical_success_rate is not None else 1.0

    # Final score
    final_confidence = base_confidence * validation_modifier * historical_modifier

    # Clamp to [0.0, 1.0]
    final_confidence = max(0.0, min(1.0, final_confidence))

    return ConfidenceScore(
        value=final_confidence,
        source_weight=base_confidence,
        validation_passed=(validation.severity != ValidationSeverity.ERROR),
        historical_success_rate=historical_success_rate,
    )


def should_request_human_override(confidence: ConfidenceScore, required: bool) -> bool:
    """Decide if we should ask the human to review/override this field.

    Heuristic:
    - Required field with confidence < 0.6 → always ask
    - Optional field with confidence < 0.4 → ask
    - Any field that failed validation → ask

    Args:
        confidence: Confidence score for the field
        required: Is this field mandatory?

    Returns:
        True if human should review this field
    """
    # Always ask if validation failed
    if not confidence.validation_passed:
        return True

    # Required fields need higher confidence
    if required and confidence.value < 0.6:
        return True

    # Optional fields can tolerate lower confidence
    if not required and confidence.value < 0.4:
        return True

    return False
