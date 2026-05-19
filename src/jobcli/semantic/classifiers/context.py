"""Context classifiers using DOM structure and neighboring text."""

from typing import List

from jobcli.semantic.models import ClassificationSignal, FieldContext, SignalType
from jobcli.semantic.patterns import PATTERN_LIBRARY


class DOMContextClassifier:
    """Classify field from DOM ancestry (fieldset/legend, section headers)."""

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from DOM context.

        Fieldset legends and section headers provide valuable context.
        Example:
            <fieldset>
                <legend>Personal Information</legend>
                <input name="email" ...>  ← Context boosts EMAIL confidence
            </fieldset>
        """
        signals: List[ClassificationSignal] = []

        # Fieldset legend
        if context.fieldset_legend:
            matches = PATTERN_LIBRARY.match_all_types(context.fieldset_legend)
            for semantic_type, base_confidence, tier in matches[:2]:
                # Context provides moderate boost
                adjusted_confidence = base_confidence * 0.70

                signals.append(
                    ClassificationSignal(
                        signal_type=SignalType.DOM_ANCESTOR,
                        matched_pattern=f"fieldset: {semantic_type.value}",
                        confidence=adjusted_confidence,
                        reasoning=f"Fieldset legend '{context.fieldset_legend}' suggests {semantic_type.value} context",
                        metadata={
                            "legend": context.fieldset_legend,
                            "semantic_type": semantic_type.value,
                        },
                    )
                )

        # Section header
        if context.section_header:
            matches = PATTERN_LIBRARY.match_all_types(context.section_header)
            for semantic_type, base_confidence, tier in matches[:2]:
                adjusted_confidence = base_confidence * 0.65

                signals.append(
                    ClassificationSignal(
                        signal_type=SignalType.DOM_ANCESTOR,
                        matched_pattern=f"section: {semantic_type.value}",
                        confidence=adjusted_confidence,
                        reasoning=f"Section header '{context.section_header}' suggests {semantic_type.value} context",
                        metadata={
                            "header": context.section_header,
                            "semantic_type": semantic_type.value,
                        },
                    )
                )

        return signals


class NeighboringTextClassifier:
    """Classify field from text before/after the field."""

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from neighboring text.

        Text immediately before/after provides hints.
        Example: "Enter your email address below" → EMAIL
        """
        signals: List[ClassificationSignal] = []

        # Preceding text (often instructions)
        if context.preceding_text:
            matches = PATTERN_LIBRARY.match_all_types(context.preceding_text)
            for semantic_type, base_confidence, tier in matches[:2]:
                # Preceding text is moderately reliable
                adjusted_confidence = base_confidence * 0.70

                signals.append(
                    ClassificationSignal(
                        signal_type=SignalType.NEIGHBORING_TEXT,
                        matched_pattern=f"before: {semantic_type.value}",
                        confidence=adjusted_confidence,
                        reasoning=f"Preceding text '{context.preceding_text[:50]}...' suggests {semantic_type.value}",
                        metadata={
                            "position": "before",
                            "semantic_type": semantic_type.value,
                        },
                    )
                )

        # Following text (often hints or examples)
        if context.following_text:
            matches = PATTERN_LIBRARY.match_all_types(context.following_text)
            for semantic_type, base_confidence, tier in matches[:2]:
                adjusted_confidence = base_confidence * 0.65

                signals.append(
                    ClassificationSignal(
                        signal_type=SignalType.NEIGHBORING_TEXT,
                        matched_pattern=f"after: {semantic_type.value}",
                        confidence=adjusted_confidence,
                        reasoning=f"Following text '{context.following_text[:50]}...' suggests {semantic_type.value}",
                        metadata={
                            "position": "after",
                            "semantic_type": semantic_type.value,
                        },
                    )
                )

        return signals
