"""Data models for semantic field classification."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from jobcli.canonical.models import FieldSemanticType
from jobcli.profile.schemas import ATSType


class SignalType(str, Enum):
    """Types of classification signals."""

    LABEL_PATTERN = "label_pattern"           # Exact/regex match on label
    PLACEHOLDER = "placeholder"               # Placeholder text match
    ARIA_LABEL = "aria_label"                 # aria-label attribute
    ARIA_LABELLEDBY = "aria_labelledby"       # aria-labelledby reference
    DOM_ANCESTOR = "dom_ancestor"             # Fieldset/legend context
    NEIGHBORING_TEXT = "neighboring_text"     # Nearby descriptions
    ATS_HEURISTIC = "ats_heuristic"          # Platform-specific pattern
    HISTORICAL_CORRECTION = "historical_correction"  # Learned from human
    EMBEDDING_SIMILARITY = "embedding_similarity"    # Semantic similarity
    INPUT_TYPE = "input_type"                 # HTML input type hint
    NAME_ATTRIBUTE = "name_attribute"         # input name= attribute


class ClassificationSignal(BaseModel):
    """A single signal contributing to field classification.

    Example:
        {
            "signal_type": "label_pattern",
            "matched_pattern": "email.*address",
            "confidence": 0.95,
            "reasoning": "Label 'Email Address' matches high-confidence pattern"
        }
    """

    signal_type: SignalType
    matched_pattern: Optional[str] = Field(None, description="Pattern that matched (if applicable)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence [0.0, 1.0]")
    reasoning: str = Field(..., description="Human-readable explanation")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra context")


class FieldContext(BaseModel):
    """Complete context for a form field from DOM/AXTree.

    This is the input to the semantic engine. Contains all available signals.
    """

    # Primary signals
    label: Optional[str] = Field(None, description="Visible label text")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    input_type: str = Field("text", description="HTML input type")
    name_attribute: Optional[str] = Field(None, description="input name= attribute")

    # ARIA attributes
    aria_label: Optional[str] = Field(None, description="aria-label attribute")
    aria_labelledby: Optional[str] = Field(None, description="aria-labelledby ID")
    aria_describedby: Optional[str] = Field(None, description="aria-describedby ID")

    # DOM context
    fieldset_legend: Optional[str] = Field(None, description="Enclosing fieldset <legend>")
    section_header: Optional[str] = Field(None, description="Nearest <h1>-<h6> header")
    parent_labels: list[str] = Field(default_factory=list, description="Parent element labels")

    # Neighboring text
    preceding_text: Optional[str] = Field(None, description="Text immediately before field")
    following_text: Optional[str] = Field(None, description="Text immediately after field")

    # ATS context
    ats_type: ATSType = Field(..., description="Which ATS platform")
    page_url: str = Field(..., description="Current page URL")

    # DOM metadata
    selector: str = Field(..., description="CSS selector for this field")
    is_required: bool = Field(False, description="Required field?")


class ClassificationResult(BaseModel):
    """Result of semantic field classification.

    Example:
        {
            "semantic_type": "email",
            "confidence": 0.95,
            "signals": [
                {"signal_type": "label_pattern", "confidence": 0.95, ...},
                {"signal_type": "input_type", "confidence": 0.80, ...}
            ],
            "reasoning": "High confidence: label matches 'email' pattern, input type is 'email'",
            "fallback_needed": false,
            "alternatives": [
                {"semantic_type": "phone", "confidence": 0.15}
            ]
        }
    """

    # Primary result
    semantic_type: FieldSemanticType = Field(..., description="Classified field type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")

    # Reasoning
    signals: list[ClassificationSignal] = Field(..., description="Signals that contributed")
    reasoning: str = Field(..., description="Human-readable explanation of classification")

    # Fallback strategy
    fallback_needed: bool = Field(False, description="Should we try fallback strategies?")
    alternatives: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Alternative classifications with lower confidence",
    )

    # Metadata
    classified_at: datetime = Field(default_factory=datetime.utcnow)
    classifier_version: str = Field("1.0", description="Semantic engine version")


class HistoricalCorrection(BaseModel):
    """A human correction stored for future learning.

    When confidence is low and human provides the correct type, store this
    for future classifications of similar fields.
    """

    # Field context (for matching)
    label_normalized: str = Field(..., description="Normalized label text")
    ats_type: ATSType = Field(..., description="ATS platform")
    input_type: Optional[str] = Field(None, description="HTML input type")

    # Correction
    correct_semantic_type: FieldSemanticType = Field(..., description="Human-confirmed type")
    original_classification: Optional[FieldSemanticType] = Field(
        None,
        description="What we originally guessed (if any)",
    )
    original_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Original confidence")

    # Metadata
    corrected_at: datetime = Field(default_factory=datetime.utcnow)
    correction_count: int = Field(1, description="How many times this correction was made")
    success_count: int = Field(0, description="How many times this correction was validated")

    def get_correction_confidence(self) -> float:
        """Calculate confidence boost from this correction.

        Returns:
            Float [0.5, 0.95] based on how many times correction was validated
        """
        if self.success_count == 0:
            return 0.5  # First time, moderate confidence
        if self.success_count >= 3:
            return 0.95  # Validated 3+ times, very high confidence
        # Linear interpolation between 0.5 and 0.95
        return 0.5 + (self.success_count / 3) * 0.45
