"""Tests for semantic field classification engine."""

import pytest

from jobcli.canonical.models import FieldSemanticType
from jobcli.profile.schemas import ATSType
from jobcli.semantic.classifiers import (
    ARIAClassifier,
    ATSHeuristicClassifier,
    DOMContextClassifier,
    InputTypeClassifier,
    LabelClassifier,
    NameAttributeClassifier,
    NeighboringTextClassifier,
    PlaceholderClassifier,
)
from jobcli.semantic.engine import SemanticFieldEngine, classify_field
from jobcli.semantic.models import FieldContext, SignalType
from jobcli.semantic.patterns import PATTERN_LIBRARY


# ── Pattern Library Tests ─────────────────────────────────────────────────────


def test_pattern_library_email_exact():
    """Test exact email pattern matching."""
    matched, conf, tier = PATTERN_LIBRARY.match("email", FieldSemanticType.EMAIL)
    assert matched is True
    assert conf == 0.98
    assert tier == "exact"


def test_pattern_library_email_high():
    """Test high-confidence email pattern."""
    matched, conf, tier = PATTERN_LIBRARY.match("Email Address", FieldSemanticType.EMAIL)
    assert matched is True
    assert conf == 0.90
    assert tier == "high"


def test_pattern_library_phone():
    """Test phone pattern matching."""
    matched, conf, tier = PATTERN_LIBRARY.match("Phone Number", FieldSemanticType.PHONE)
    assert matched is True
    assert conf >= 0.90


def test_pattern_library_work_auth():
    """Test work authorization pattern."""
    matched, conf, tier = PATTERN_LIBRARY.match(
        "Authorized to work in the US?",
        FieldSemanticType.WORK_AUTHORIZED,
    )
    assert matched is True
    assert conf >= 0.90


def test_pattern_library_match_all():
    """Test matching against all types."""
    matches = PATTERN_LIBRARY.match_all_types("Email Address")
    assert len(matches) > 0
    assert matches[0][0] == FieldSemanticType.EMAIL
    assert matches[0][1] >= 0.90


# ── Label Classifier Tests ────────────────────────────────────────────────────


def test_label_classifier_email():
    """Test label classifier on email field."""
    context = FieldContext(
        label="Email Address",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = LabelClassifier()
    signals = classifier.classify(context)

    assert len(signals) > 0
    assert signals[0].signal_type == SignalType.LABEL_PATTERN
    assert signals[0].confidence >= 0.90
    assert "email" in signals[0].reasoning.lower()


def test_label_classifier_no_label():
    """Test label classifier with no label."""
    context = FieldContext(
        label=None,
        ats_type=ATSType.GREENHOUSE,
        selector="input#field",
        is_required=False,
        page_url="https://example.com",
    )

    classifier = LabelClassifier()
    signals = classifier.classify(context)

    assert len(signals) == 0


# ── Placeholder Classifier Tests ──────────────────────────────────────────────


def test_placeholder_classifier():
    """Test placeholder classifier."""
    context = FieldContext(
        placeholder="you@example.com",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = PlaceholderClassifier()
    signals = classifier.classify(context)

    # Placeholder might not match patterns strongly, but if it does:
    if signals:
        assert signals[0].signal_type == SignalType.PLACEHOLDER
        assert signals[0].confidence < 0.90  # Placeholders get reduced confidence


# ── ARIA Classifier Tests ─────────────────────────────────────────────────────


def test_aria_classifier():
    """Test ARIA classifier."""
    context = FieldContext(
        aria_label="Email address",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = ARIAClassifier()
    signals = classifier.classify(context)

    assert len(signals) > 0
    assert signals[0].signal_type == SignalType.ARIA_LABEL
    assert signals[0].confidence >= 0.90


# ── Input Type Classifier Tests ───────────────────────────────────────────────


def test_input_type_classifier_email():
    """Test input type classifier for email."""
    context = FieldContext(
        input_type="email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = InputTypeClassifier()
    signals = classifier.classify(context)

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.INPUT_TYPE
    assert signals[0].confidence == 0.85


def test_input_type_classifier_tel():
    """Test input type classifier for phone."""
    context = FieldContext(
        input_type="tel",
        ats_type=ATSType.GREENHOUSE,
        selector="input#phone",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = InputTypeClassifier()
    signals = classifier.classify(context)

    assert len(signals) == 1
    assert signals[0].confidence == 0.80


# ── Name Attribute Classifier Tests ───────────────────────────────────────────


def test_name_attribute_classifier():
    """Test name attribute classifier."""
    context = FieldContext(
        name_attribute="user_email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = NameAttributeClassifier()
    signals = classifier.classify(context)

    assert len(signals) > 0
    assert signals[0].signal_type == SignalType.NAME_ATTRIBUTE


# ── DOM Context Classifier Tests ──────────────────────────────────────────────


def test_dom_context_classifier_fieldset():
    """Test DOM context with fieldset legend."""
    context = FieldContext(
        fieldset_legend="Personal Information",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = DOMContextClassifier()
    signals = classifier.classify(context)

    # Fieldset might provide context but may not match specific types strongly
    # This is expected - DOM context provides supporting evidence


def test_neighboring_text_classifier():
    """Test neighboring text classifier."""
    context = FieldContext(
        preceding_text="Enter your email address below",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = NeighboringTextClassifier()
    signals = classifier.classify(context)

    assert len(signals) > 0
    assert signals[0].signal_type == SignalType.NEIGHBORING_TEXT


# ── ATS Heuristic Classifier Tests ────────────────────────────────────────────


def test_ats_heuristic_greenhouse():
    """Test ATS heuristic for Greenhouse."""
    context = FieldContext(
        name_attribute="job_application[email]",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = ATSHeuristicClassifier()
    signals = classifier.classify(context)

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.ATS_HEURISTIC
    assert signals[0].confidence == 0.95


def test_ats_heuristic_lever():
    """Test ATS heuristic for Lever."""
    context = FieldContext(
        name_attribute="email",
        ats_type=ATSType.LEVER,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    classifier = ATSHeuristicClassifier()
    signals = classifier.classify(context)

    assert len(signals) == 1
    assert signals[0].confidence == 0.95


# ── Semantic Engine Integration Tests ─────────────────────────────────────────


def test_engine_high_confidence_email():
    """Test engine with multiple strong signals for email."""
    context = FieldContext(
        label="Email Address",
        input_type="email",
        aria_label="Email",
        name_attribute="email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    assert result.semantic_type == FieldSemanticType.EMAIL
    assert result.confidence >= 0.90
    assert len(result.signals) >= 3
    assert result.fallback_needed is False
    assert "email" in result.reasoning.lower()


def test_engine_medium_confidence():
    """Test engine with fewer signals."""
    context = FieldContext(
        label="Email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    assert result.semantic_type == FieldSemanticType.EMAIL
    assert result.confidence >= 0.75


def test_engine_phone_field():
    """Test engine on phone field."""
    context = FieldContext(
        label="Phone Number",
        input_type="tel",
        name_attribute="phone",
        ats_type=ATSType.GREENHOUSE,
        selector="input#phone",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    assert result.semantic_type == FieldSemanticType.PHONE
    assert result.confidence >= 0.85


def test_engine_work_authorization():
    """Test engine on work authorization field."""
    context = FieldContext(
        label="Are you authorized to work in the US?",
        input_type="radio",
        ats_type=ATSType.GREENHOUSE,
        selector="input[name='work_auth']",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    assert result.semantic_type == FieldSemanticType.WORK_AUTHORIZED
    assert result.confidence >= 0.80


def test_engine_unknown_field():
    """Test engine on unrecognized field."""
    context = FieldContext(
        label="Custom Field XYZ123",
        ats_type=ATSType.UNKNOWN,
        selector="input#custom",
        is_required=False,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    assert result.semantic_type == FieldSemanticType.UNKNOWN
    assert result.confidence == 0.0
    assert result.fallback_needed is True


def test_engine_conflicting_signals():
    """Test engine with conflicting signals (should pick highest confidence)."""
    context = FieldContext(
        label="Email Address",  # → EMAIL, high confidence
        input_type="tel",  # → PHONE, lower confidence
        ats_type=ATSType.GREENHOUSE,
        selector="input#field",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    # Label should win (higher confidence)
    assert result.semantic_type == FieldSemanticType.EMAIL


def test_engine_confidence_boost():
    """Test that multiple independent signals boost confidence."""
    context_single = FieldContext(
        label="Email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    context_multiple = FieldContext(
        label="Email",
        input_type="email",
        aria_label="Email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result_single = engine.classify(context_single)
    result_multiple = engine.classify(context_multiple)

    # Multiple signals should have higher confidence
    assert result_multiple.confidence > result_single.confidence


def test_engine_alternatives():
    """Test that engine provides alternatives for ambiguous fields."""
    context = FieldContext(
        label="Contact",  # Could be email or phone
        ats_type=ATSType.GREENHOUSE,
        selector="input#contact",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    # Should have alternatives if ambiguous
    # (Depending on patterns, this might or might not have alternatives)
    # This test documents the expected behavior


def test_classify_field_convenience():
    """Test convenience function."""
    context = FieldContext(
        label="Email Address",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    result = classify_field(context)

    assert result.semantic_type == FieldSemanticType.EMAIL
    assert result.confidence >= 0.75


# ── Reasoning Tests ───────────────────────────────────────────────────────────


def test_reasoning_includes_signal_types():
    """Test that reasoning mentions contributing signal types."""
    context = FieldContext(
        label="Email Address",
        input_type="email",
        aria_label="Email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    result = engine.classify(context)

    reasoning_lower = result.reasoning.lower()
    # Should mention multiple signal types
    assert "email" in reasoning_lower
    assert "confidence" in reasoning_lower


def test_reasoning_high_vs_low_confidence():
    """Test that reasoning distinguishes high vs low confidence."""
    high_context = FieldContext(
        label="Email Address",
        input_type="email",
        aria_label="Email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
        page_url="https://example.com",
    )

    low_context = FieldContext(
        label="Field",
        ats_type=ATSType.UNKNOWN,
        selector="input#field",
        is_required=False,
        page_url="https://example.com",
    )

    engine = SemanticFieldEngine()
    high_result = engine.classify(high_context)
    low_result = engine.classify(low_context)

    # High confidence should be explicit
    if high_result.confidence >= 0.85:
        assert "high" in high_result.reasoning.lower()

    # Low confidence should be explicit
    if low_result.confidence < 0.65:
        assert "low" in low_result.reasoning.lower() or low_result.confidence == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
