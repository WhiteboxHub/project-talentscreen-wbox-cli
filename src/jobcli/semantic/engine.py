"""Semantic Field Engine - Main classification coordinator with confidence aggregation."""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from jobcli.canonical.models import FieldSemanticType
from jobcli.semantic.classifiers import (
    ARIAClassifier,
    ATSHeuristicClassifier,
    DOMContextClassifier,
    HistoricalCorrectionClassifier,
    InputTypeClassifier,
    LabelClassifier,
    NameAttributeClassifier,
    NeighboringTextClassifier,
    PlaceholderClassifier,
)
from jobcli.semantic.models import (
    ClassificationResult,
    ClassificationSignal,
    FieldContext,
)


class SemanticFieldEngine:
    """Main classification engine coordinating all classifiers.

    Algorithm:
    1. Run all classifiers in parallel
    2. Collect signals from each
    3. Group signals by semantic type
    4. Aggregate using weighted voting
    5. Resolve conflicts (highest confidence wins)
    6. Build reasoning trace
    7. Determine if fallback is needed
    """

    # Confidence threshold for fallback
    FALLBACK_THRESHOLD = 0.6

    # Minimum signals required for high confidence
    MIN_SIGNALS_HIGH_CONFIDENCE = 2

    def __init__(self, db_session=None):
        """Initialize all classifiers.

        Args:
            db_session: Optional SQLAlchemy session for historical corrections
        """
        # Deterministic classifiers
        self.label_classifier = LabelClassifier()
        self.placeholder_classifier = PlaceholderClassifier()
        self.aria_classifier = ARIAClassifier()
        self.input_type_classifier = InputTypeClassifier()
        self.name_attr_classifier = NameAttributeClassifier()

        # Context classifiers
        self.dom_context_classifier = DOMContextClassifier()
        self.neighboring_text_classifier = NeighboringTextClassifier()

        # Platform classifiers
        self.ats_heuristic_classifier = ATSHeuristicClassifier()
        self.historical_classifier = (
            HistoricalCorrectionClassifier(db_session) if db_session else None
        )

    def classify(self, context: FieldContext) -> ClassificationResult:
        """Classify a field using all available signals.

        Args:
            context: Complete field context from DOM/AXTree

        Returns:
            ClassificationResult with confidence, signals, and reasoning
        """
        # Collect all signals
        all_signals = self._collect_signals(context)

        # If no signals, return UNKNOWN
        if not all_signals:
            return self._unknown_result()

        # Aggregate signals by semantic type
        result = self._aggregate_signals(all_signals)

        return result

    def _collect_signals(self, context: FieldContext) -> List[ClassificationSignal]:
        """Run all classifiers and collect signals."""
        all_signals: List[ClassificationSignal] = []

        # Run deterministic classifiers
        all_signals.extend(self.label_classifier.classify(context))
        all_signals.extend(self.placeholder_classifier.classify(context))
        all_signals.extend(self.aria_classifier.classify(context))
        all_signals.extend(self.input_type_classifier.classify(context))
        all_signals.extend(self.name_attr_classifier.classify(context))

        # Run context classifiers
        all_signals.extend(self.dom_context_classifier.classify(context))
        all_signals.extend(self.neighboring_text_classifier.classify(context))

        # Run platform classifiers
        all_signals.extend(self.ats_heuristic_classifier.classify(context))
        if self.historical_classifier:
            all_signals.extend(self.historical_classifier.classify(context))

        return all_signals

    def _aggregate_signals(
        self,
        signals: List[ClassificationSignal],
    ) -> ClassificationResult:
        """Aggregate signals using weighted voting.

        Algorithm:
        1. Group signals by semantic_type (extracted from metadata)
        2. For each type, calculate max confidence (strongest signal)
        3. Count how many different signal types support each semantic type
        4. Boost confidence if multiple independent signals agree
        5. Pick winner: highest confidence with most supporting signals
        """
        # Group signals by semantic type
        votes: Dict[FieldSemanticType, List[ClassificationSignal]] = defaultdict(list)

        for signal in signals:
            # Extract semantic type from signal metadata
            semantic_type_str = signal.metadata.get("semantic_type")
            if semantic_type_str:
                try:
                    semantic_type = FieldSemanticType(semantic_type_str)
                    votes[semantic_type].append(signal)
                except ValueError:
                    continue  # Invalid semantic type, skip

        if not votes:
            return self._unknown_result()

        # Calculate confidence for each semantic type
        type_scores: Dict[FieldSemanticType, float] = {}
        type_signals: Dict[FieldSemanticType, List[ClassificationSignal]] = {}

        for semantic_type, type_signals_list in votes.items():
            # Strategy: Take max confidence among all signals for this type
            max_confidence = max(s.confidence for s in type_signals_list)

            # Boost if multiple independent signal types agree
            unique_signal_types = len(set(s.signal_type for s in type_signals_list))
            if unique_signal_types >= self.MIN_SIGNALS_HIGH_CONFIDENCE:
                # Multiple independent sources agree → boost confidence
                boost = min(0.05 * (unique_signal_types - 1), 0.15)  # Max +15%
                max_confidence = min(max_confidence + boost, 0.98)

            type_scores[semantic_type] = max_confidence
            type_signals[semantic_type] = type_signals_list

        # Pick winner: highest confidence
        winner_type = max(type_scores, key=type_scores.get)
        winner_confidence = type_scores[winner_type]
        winner_signals = type_signals[winner_type]

        # Build reasoning
        reasoning = self._build_reasoning(winner_type, winner_signals, winner_confidence)

        # Determine if fallback needed
        fallback_needed = winner_confidence < self.FALLBACK_THRESHOLD

        # Build alternatives (other types with >30% confidence)
        alternatives = [
            {"semantic_type": st.value, "confidence": round(conf, 3)}
            for st, conf in sorted(
                type_scores.items(), key=lambda x: x[1], reverse=True
            )
            if st != winner_type and conf > 0.30
        ]

        return ClassificationResult(
            semantic_type=winner_type,
            confidence=round(winner_confidence, 3),
            signals=winner_signals,
            reasoning=reasoning,
            fallback_needed=fallback_needed,
            alternatives=alternatives[:3],  # Top 3 alternatives
            classified_at=datetime.utcnow(),
        )

    def _build_reasoning(
        self,
        semantic_type: FieldSemanticType,
        signals: List[ClassificationSignal],
        confidence: float,
    ) -> str:
        """Build human-readable reasoning from signals."""
        confidence_label = (
            "High confidence"
            if confidence >= 0.85
            else "Medium confidence"
            if confidence >= 0.65
            else "Low confidence"
        )

        parts = [f"{confidence_label} ({confidence:.0%}): {semantic_type.value}"]

        # Count signal types
        from collections import Counter

        signal_type_counts = Counter(s.signal_type for s in signals)

        # Summarize contributing signals
        contributors = []
        for signal_type, count in signal_type_counts.most_common(3):
            # Get highest confidence signal of this type
            type_signals = [s for s in signals if s.signal_type == signal_type]
            best = max(type_signals, key=lambda s: s.confidence)

            if signal_type.value == "label_pattern":
                contributors.append("label matches pattern")
            elif signal_type.value == "aria_label":
                contributors.append("ARIA label confirms")
            elif signal_type.value == "ats_heuristic":
                contributors.append(f"known {best.metadata.get('ats', 'ATS')} pattern")
            elif signal_type.value == "historical_correction":
                count = best.metadata.get("correction_count", 1)
                contributors.append(f"learned from {count} correction(s)")
            elif signal_type.value == "input_type":
                contributors.append(f"input type='{best.metadata.get('input_type')}'")
            else:
                contributors.append(signal_type.value.replace("_", " "))

        if contributors:
            parts.append("(" + ", ".join(contributors) + ")")

        return " ".join(parts)

    def _unknown_result(self) -> ClassificationResult:
        """Return UNKNOWN classification when no signals match."""
        return ClassificationResult(
            semantic_type=FieldSemanticType.UNKNOWN,
            confidence=0.0,
            signals=[],
            reasoning="No matching patterns found",
            fallback_needed=True,
            alternatives=[],
            classified_at=datetime.utcnow(),
        )


def classify_field(
    context: FieldContext,
    db_session=None,
) -> ClassificationResult:
    """Convenience function to classify a single field.

    Args:
        context: Field context
        db_session: Optional database session for historical corrections

    Returns:
        ClassificationResult
    """
    engine = SemanticFieldEngine(db_session=db_session)
    return engine.classify(context)
