"""Deterministic classifiers using pattern matching on labels, placeholders, ARIA, etc."""

from typing import Dict, List

from jobcli.canonical.models import FieldSemanticType
from jobcli.semantic.models import ClassificationSignal, FieldContext, SignalType
from jobcli.semantic.patterns import PATTERN_LIBRARY


class LabelClassifier:
    """Classify field from label text using pattern library."""

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from label text."""
        if not context.label:
            return []

        signals: List[ClassificationSignal] = []
        matches = PATTERN_LIBRARY.match_all_types(context.label)

        for semantic_type, confidence, tier in matches[:3]:  # Top 3 matches
            signals.append(
                ClassificationSignal(
                    signal_type=SignalType.LABEL_PATTERN,
                    matched_pattern=f"{semantic_type.value} ({tier})",
                    confidence=confidence,
                    reasoning=f"Label '{context.label}' matches {semantic_type.value} pattern ({tier} confidence)",
                    metadata={"tier": tier, "semantic_type": semantic_type.value},
                )
            )

        return signals


class PlaceholderClassifier:
    """Classify field from placeholder text."""

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from placeholder text.

        Placeholders are hints, so confidence is lower than labels (×0.85).
        """
        if not context.placeholder:
            return []

        signals: List[ClassificationSignal] = []
        matches = PATTERN_LIBRARY.match_all_types(context.placeholder)

        for semantic_type, base_confidence, tier in matches[:3]:
            # Reduce confidence for placeholders (they're hints, not labels)
            adjusted_confidence = base_confidence * 0.85

            signals.append(
                ClassificationSignal(
                    signal_type=SignalType.PLACEHOLDER,
                    matched_pattern=f"{semantic_type.value} ({tier})",
                    confidence=adjusted_confidence,
                    reasoning=f"Placeholder '{context.placeholder}' suggests {semantic_type.value}",
                    metadata={"tier": tier, "semantic_type": semantic_type.value},
                )
            )

        return signals


class ARIAClassifier:
    """Classify field from ARIA attributes (aria-label, aria-labelledby)."""

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from ARIA attributes.

        ARIA labels are high-confidence (accessibility-first).
        """
        signals: List[ClassificationSignal] = []

        # aria-label
        if context.aria_label:
            matches = PATTERN_LIBRARY.match_all_types(context.aria_label)
            for semantic_type, base_confidence, tier in matches[:2]:
                # Boost confidence for ARIA (accessibility-first design)
                adjusted_confidence = min(base_confidence * 1.05, 0.98)

                signals.append(
                    ClassificationSignal(
                        signal_type=SignalType.ARIA_LABEL,
                        matched_pattern=f"{semantic_type.value} ({tier})",
                        confidence=adjusted_confidence,
                        reasoning=f"aria-label '{context.aria_label}' matches {semantic_type.value}",
                        metadata={"tier": tier, "semantic_type": semantic_type.value},
                    )
                )

        # aria-labelledby (would need to resolve the ID, simplified here)
        if context.aria_labelledby:
            # In real implementation, would look up the referenced element's text
            # For now, treat as medium confidence signal
            signals.append(
                ClassificationSignal(
                    signal_type=SignalType.ARIA_LABELLEDBY,
                    matched_pattern=f"id={context.aria_labelledby}",
                    confidence=0.70,
                    reasoning=f"Field references aria-labelledby='{context.aria_labelledby}'",
                    metadata={"referenced_id": context.aria_labelledby},
                )
            )

        return signals


class InputTypeClassifier:
    """Classify field from HTML input type attribute."""

    # Map input types to semantic types with confidence
    TYPE_MAP: Dict[str, tuple[FieldSemanticType, float]] = {
        "email": (FieldSemanticType.EMAIL, 0.85),
        "tel": (FieldSemanticType.PHONE, 0.80),
        "url": (FieldSemanticType.WEBSITE_URL, 0.70),
        "number": (FieldSemanticType.CUSTOM_TEXT, 0.50),  # Ambiguous
        "date": (FieldSemanticType.CUSTOM_TEXT, 0.60),
        "file": (FieldSemanticType.RESUME_UPLOAD, 0.70),  # Could be resume or other
        "checkbox": (FieldSemanticType.CUSTOM_BOOLEAN, 0.60),
        "radio": (FieldSemanticType.CUSTOM_SELECT, 0.60),
    }

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from input type."""
        if context.input_type not in self.TYPE_MAP:
            return []

        semantic_type, confidence = self.TYPE_MAP[context.input_type]

        return [
            ClassificationSignal(
                signal_type=SignalType.INPUT_TYPE,
                matched_pattern=f"input[type='{context.input_type}']",
                confidence=confidence,
                reasoning=f"HTML input type '{context.input_type}' suggests {semantic_type.value}",
                metadata={"input_type": context.input_type, "semantic_type": semantic_type.value},
            )
        ]


class NameAttributeClassifier:
    """Classify field from input name attribute."""

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from name attribute.

        Name attributes often contain semantic hints (e.g., name="user_email").
        """
        if not context.name_attribute:
            return []

        # Clean up name: remove underscores, brackets, array notation
        cleaned = (
            context.name_attribute
            .replace("_", " ")
            .replace("[", " ")
            .replace("]", " ")
            .strip()
        )

        if not cleaned:
            return []

        signals: List[ClassificationSignal] = []
        matches = PATTERN_LIBRARY.match_all_types(cleaned)

        for semantic_type, base_confidence, tier in matches[:2]:
            # Name attributes are somewhat reliable, but not as strong as labels
            adjusted_confidence = base_confidence * 0.80

            signals.append(
                ClassificationSignal(
                    signal_type=SignalType.NAME_ATTRIBUTE,
                    matched_pattern=f"{semantic_type.value} ({tier})",
                    confidence=adjusted_confidence,
                    reasoning=f"Name attribute '{context.name_attribute}' suggests {semantic_type.value}",
                    metadata={"tier": tier, "semantic_type": semantic_type.value},
                )
            )

        return signals
