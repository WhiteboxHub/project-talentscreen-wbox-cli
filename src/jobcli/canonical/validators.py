"""Semantic validation rules for ApplicationField values.

Each FieldSemanticType has specific validation rules that check:
- Format correctness (email regex, phone format, URL structure)
- Value constraints (GPA range, year bounds)
- Required vs optional semantics

Validation is confidence-aware: failures reduce confidence but may not block execution.
"""

import re
from typing import Optional

from jobcli.canonical.models import (
    FieldSemanticType,
    ValidationResult,
    ValidationSeverity,
)


# Regex patterns for common formats
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_PATTERN = re.compile(r"^[\d\s\-\(\)\+\.]+$")  # Loose: allows most phone formats
_URL_PATTERN = re.compile(r"^https?://[^\s]+$")
_LINKEDIN_PATTERN = re.compile(r"linkedin\.com/in/[\w\-]+")
_GITHUB_PATTERN = re.compile(r"github\.com/[\w\-]+")
_ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")  # US ZIP or ZIP+4


def validate_field_value(
    semantic_type: FieldSemanticType,
    value: Optional[str],
    required: bool = False,
) -> ValidationResult:
    """Validate a field value against its semantic type.

    Args:
        semantic_type: What kind of field this is
        value: The value to validate (may be None)
        required: Is this field mandatory?

    Returns:
        ValidationResult with severity and message
    """
    # Empty value handling
    if not value or not str(value).strip():
        if required:
            return ValidationResult(
                severity=ValidationSeverity.ERROR,
                message=f"Required field '{semantic_type.value}' is empty",
                expected_format="non-empty value",
                actual_value_preview="(empty)",
            )
        return ValidationResult(
            severity=ValidationSeverity.OK,
            message="Optional field is empty",
        )

    value_str = str(value).strip()

    # Type-specific validation
    if semantic_type == FieldSemanticType.EMAIL:
        return _validate_email(value_str)

    elif semantic_type == FieldSemanticType.PHONE:
        return _validate_phone(value_str)

    elif semantic_type in (
        FieldSemanticType.LINKEDIN_URL,
        FieldSemanticType.GITHUB_URL,
        FieldSemanticType.PORTFOLIO_URL,
        FieldSemanticType.WEBSITE_URL,
    ):
        return _validate_url(value_str, semantic_type)

    elif semantic_type == FieldSemanticType.ZIP_CODE:
        return _validate_zip_code(value_str)

    elif semantic_type == FieldSemanticType.GPA:
        return _validate_gpa(value_str)

    elif semantic_type == FieldSemanticType.GRADUATION_YEAR:
        return _validate_year(value_str, "graduation")

    elif semantic_type == FieldSemanticType.YEARS_OF_EXPERIENCE:
        return _validate_numeric_range(value_str, 0, 70, "years of experience")

    elif semantic_type in (
        FieldSemanticType.WORK_AUTHORIZED,
        FieldSemanticType.REQUIRE_SPONSORSHIP,
        FieldSemanticType.CURRENT_ROLE,
        FieldSemanticType.WILLING_TO_RELOCATE,
        FieldSemanticType.CUSTOM_BOOLEAN,
    ):
        return _validate_boolean(value_str)

    # Default: accept any non-empty string
    return ValidationResult(
        severity=ValidationSeverity.OK,
        message=f"Field '{semantic_type.value}' accepted",
    )


# ── Type-Specific Validators ──────────────────────────────────────────────────


def _validate_email(value: str) -> ValidationResult:
    """Validate email format."""
    if _EMAIL_PATTERN.match(value):
        return ValidationResult(
            severity=ValidationSeverity.OK,
            message="Valid email format",
        )
    return ValidationResult(
        severity=ValidationSeverity.ERROR,
        message="Invalid email format",
        expected_format="user@example.com",
        actual_value_preview=value[:30],
    )


def _validate_phone(value: str) -> ValidationResult:
    """Validate phone format (loose: most international formats accepted)."""
    if _PHONE_PATTERN.match(value) and len(value) >= 10:
        return ValidationResult(
            severity=ValidationSeverity.OK,
            message="Valid phone format",
        )
    return ValidationResult(
        severity=ValidationSeverity.WARNING,
        message="Phone format looks unusual",
        expected_format="digits, spaces, dashes, parentheses allowed",
        actual_value_preview=value[:20],
    )


def _validate_url(value: str, semantic_type: FieldSemanticType) -> ValidationResult:
    """Validate URL format with optional platform-specific checks."""
    if not _URL_PATTERN.match(value):
        return ValidationResult(
            severity=ValidationSeverity.ERROR,
            message="Invalid URL format",
            expected_format="https://example.com",
            actual_value_preview=value[:50],
        )

    # Platform-specific checks
    if semantic_type == FieldSemanticType.LINKEDIN_URL:
        if not _LINKEDIN_PATTERN.search(value):
            return ValidationResult(
                severity=ValidationSeverity.WARNING,
                message="URL doesn't look like a LinkedIn profile",
                expected_format="https://linkedin.com/in/username",
                actual_value_preview=value[:50],
            )

    elif semantic_type == FieldSemanticType.GITHUB_URL:
        if not _GITHUB_PATTERN.search(value):
            return ValidationResult(
                severity=ValidationSeverity.WARNING,
                message="URL doesn't look like a GitHub profile",
                expected_format="https://github.com/username",
                actual_value_preview=value[:50],
            )

    return ValidationResult(
        severity=ValidationSeverity.OK,
        message="Valid URL format",
    )


def _validate_zip_code(value: str) -> ValidationResult:
    """Validate US ZIP code (5 digits or ZIP+4)."""
    if _ZIP_PATTERN.match(value):
        return ValidationResult(
            severity=ValidationSeverity.OK,
            message="Valid ZIP code",
        )
    return ValidationResult(
        severity=ValidationSeverity.WARNING,
        message="ZIP code format doesn't match US standard",
        expected_format="12345 or 12345-6789",
        actual_value_preview=value,
    )


def _validate_gpa(value: str) -> ValidationResult:
    """Validate GPA (0.0 to 4.0 or 5.0 scale)."""
    try:
        gpa = float(value)
        if 0.0 <= gpa <= 5.0:
            return ValidationResult(
                severity=ValidationSeverity.OK,
                message="Valid GPA",
            )
        return ValidationResult(
            severity=ValidationSeverity.WARNING,
            message=f"GPA {gpa} is outside typical range",
            expected_format="0.0 to 4.0 (or 5.0)",
            actual_value_preview=value,
        )
    except ValueError:
        return ValidationResult(
            severity=ValidationSeverity.ERROR,
            message="GPA must be a number",
            expected_format="numeric value (e.g., 3.5)",
            actual_value_preview=value,
        )


def _validate_year(value: str, field_name: str) -> ValidationResult:
    """Validate a year (1950-2050)."""
    try:
        year = int(value)
        if 1950 <= year <= 2050:
            return ValidationResult(
                severity=ValidationSeverity.OK,
                message=f"Valid {field_name} year",
            )
        return ValidationResult(
            severity=ValidationSeverity.WARNING,
            message=f"{field_name} year {year} seems unusual",
            expected_format="1950-2050",
            actual_value_preview=value,
        )
    except ValueError:
        return ValidationResult(
            severity=ValidationSeverity.ERROR,
            message=f"{field_name} year must be a number",
            expected_format="four-digit year (e.g., 2023)",
            actual_value_preview=value,
        )


def _validate_numeric_range(
    value: str, min_val: float, max_val: float, field_name: str
) -> ValidationResult:
    """Validate a numeric value within a range."""
    try:
        num = float(value)
        if min_val <= num <= max_val:
            return ValidationResult(
                severity=ValidationSeverity.OK,
                message=f"Valid {field_name}",
            )
        return ValidationResult(
            severity=ValidationSeverity.WARNING,
            message=f"{field_name} {num} is outside typical range",
            expected_format=f"{min_val} to {max_val}",
            actual_value_preview=value,
        )
    except ValueError:
        return ValidationResult(
            severity=ValidationSeverity.ERROR,
            message=f"{field_name} must be a number",
            expected_format=f"numeric value ({min_val}-{max_val})",
            actual_value_preview=value,
        )


def _validate_boolean(value: str) -> ValidationResult:
    """Validate boolean-ish values."""
    value_lower = value.lower().strip()
    if value_lower in ("yes", "no", "true", "false", "1", "0", "y", "n"):
        return ValidationResult(
            severity=ValidationSeverity.OK,
            message="Valid boolean value",
        )
    return ValidationResult(
        severity=ValidationSeverity.WARNING,
        message=f"Value '{value}' doesn't look like yes/no",
        expected_format="yes, no, true, false",
        actual_value_preview=value,
    )
