"""Canonical Application Model - Internal protocol for all ATS systems.

This module defines the normalized internal representation that all ATS-specific
implementations must map into. It provides semantic understanding, validation,
and confidence tracking independent of any specific ATS platform.

Architecture:
    ATS Page → Field Detection → Semantic Understanding → Canonical Model
    → Validation → Execution → Telemetry

The canonical model is the single source of truth during an application session.
"""

from jobcli.canonical.models import (
    ApplicationField,
    ApplicationSession,
    ConfidenceScore,
    ExecutionAction,
    FieldSemanticType,
    FieldSource,
    ValidationResult,
    ValidationSeverity,
)

__all__ = [
    "ApplicationField",
    "ApplicationSession",
    "ConfidenceScore",
    "ExecutionAction",
    "FieldSemanticType",
    "FieldSource",
    "ValidationResult",
    "ValidationSeverity",
]
