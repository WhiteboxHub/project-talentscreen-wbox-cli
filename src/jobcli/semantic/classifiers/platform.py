"""Platform-specific classifiers using ATS heuristics and historical corrections."""

from typing import Dict, List, Optional, Tuple

from jobcli.canonical.models import FieldSemanticType
from jobcli.profile.schemas import ATSType
from jobcli.semantic.models import (
    ClassificationSignal,
    FieldContext,
    HistoricalCorrection,
    SignalType,
)


class ATSHeuristicClassifier:
    """Platform-specific patterns for known ATS systems."""

    # Greenhouse patterns (high confidence - these are known field structures)
    GREENHOUSE_PATTERNS: Dict[str, Tuple[FieldSemanticType, float]] = {
        "job_application[email]": (FieldSemanticType.EMAIL, 0.95),
        "job_application[phone]": (FieldSemanticType.PHONE, 0.95),
        "job_application[first_name]": (FieldSemanticType.FIRST_NAME, 0.95),
        "job_application[last_name]": (FieldSemanticType.LAST_NAME, 0.95),
        "job_application[location]": (FieldSemanticType.CITY, 0.85),
        "job_application[resume]": (FieldSemanticType.RESUME_UPLOAD, 0.95),
        "job_application[cover_letter]": (FieldSemanticType.COVER_LETTER_UPLOAD, 0.95),
        "job_application[linkedin_profile]": (FieldSemanticType.LINKEDIN_URL, 0.95),
        "job_application[website]": (FieldSemanticType.WEBSITE_URL, 0.90),
    }

    # Lever patterns
    LEVER_PATTERNS: Dict[str, Tuple[FieldSemanticType, float]] = {
        "email": (FieldSemanticType.EMAIL, 0.95),
        "phone": (FieldSemanticType.PHONE, 0.95),
        "name": (FieldSemanticType.FULL_NAME, 0.95),
        "resume": (FieldSemanticType.RESUME_UPLOAD, 0.95),
        "urls[LinkedIn]": (FieldSemanticType.LINKEDIN_URL, 0.95),
        "urls[GitHub]": (FieldSemanticType.GITHUB_URL, 0.95),
    }

    # Workday patterns (more complex, nested structure)
    WORKDAY_PATTERNS: Dict[str, Tuple[FieldSemanticType, float]] = {
        "EMAIL_ADDRESS": (FieldSemanticType.EMAIL, 0.95),
        "PHONE_NUMBER": (FieldSemanticType.PHONE, 0.95),
        "FIRST_NAME": (FieldSemanticType.FIRST_NAME, 0.95),
        "LAST_NAME": (FieldSemanticType.LAST_NAME, 0.95),
    }

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from ATS-specific patterns."""
        if not context.name_attribute:
            return []

        signals: List[ClassificationSignal] = []

        # Select pattern library based on ATS type
        if context.ats_type == ATSType.GREENHOUSE:
            patterns = self.GREENHOUSE_PATTERNS
        elif context.ats_type == ATSType.LEVER:
            patterns = self.LEVER_PATTERNS
        elif context.ats_type == ATSType.WORKDAY:
            patterns = self.WORKDAY_PATTERNS
        else:
            return []  # No heuristics for this ATS

        # Check for exact match
        for pattern, (semantic_type, confidence) in patterns.items():
            if pattern in context.name_attribute:
                signals.append(
                    ClassificationSignal(
                        signal_type=SignalType.ATS_HEURISTIC,
                        matched_pattern=pattern,
                        confidence=confidence,
                        reasoning=f"Known {context.ats_type.value} pattern '{pattern}' → {semantic_type.value}",
                        metadata={
                            "ats": context.ats_type.value,
                            "pattern": pattern,
                            "semantic_type": semantic_type.value,
                        },
                    )
                )
                break  # First match wins (patterns are specific)

        return signals


class HistoricalCorrectionClassifier:
    """Use human corrections from past applications.

    When a human corrects a field classification, store it and use it
    to boost confidence for similar fields in the future.
    """

    def __init__(self, db_session=None):
        """Initialize with optional database session.

        Args:
            db_session: SQLAlchemy session for querying corrections
        """
        self.db_session = db_session
        # In-memory cache for this session
        self._cache: Dict[str, HistoricalCorrection] = {}

    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        """Extract signals from historical corrections."""
        if not self.db_session:
            return []  # No database, no corrections

        if not context.label:
            return []

        # Normalize label for matching
        normalized = context.label.lower().strip()

        # Check cache first
        cache_key = f"{normalized}_{context.ats_type.value}"
        if cache_key in self._cache:
            correction = self._cache[cache_key]
            return self._build_signals(correction, context)

        # Query database (would be implemented in actual repository)
        # For now, return empty (this is where DB lookup would happen)
        correction = self._lookup_correction(normalized, context.ats_type)
        if correction:
            self._cache[cache_key] = correction
            return self._build_signals(correction, context)

        return []

    def _lookup_correction(
        self,
        normalized_label: str,
        ats_type: ATSType,
    ) -> Optional[HistoricalCorrection]:
        """Look up correction from database (stub for now).

        In real implementation:
            return self.db_session.query(HistoricalCorrectionModel).filter_by(
                label_normalized=normalized_label,
                ats_type=ats_type,
            ).first()
        """
        # TODO: Implement database lookup
        return None

    def _build_signals(
        self,
        correction: HistoricalCorrection,
        context: FieldContext,
    ) -> List[ClassificationSignal]:
        """Build signals from a historical correction."""
        confidence = correction.get_correction_confidence()

        return [
            ClassificationSignal(
                signal_type=SignalType.HISTORICAL_CORRECTION,
                matched_pattern=f"correction_{correction.correction_count}x",
                confidence=confidence,
                reasoning=(
                    f"Human corrected this field to {correction.correct_semantic_type.value} "
                    f"({correction.correction_count} time(s), "
                    f"{correction.success_count} validated)"
                ),
                metadata={
                    "correction_count": correction.correction_count,
                    "success_count": correction.success_count,
                    "semantic_type": correction.correct_semantic_type.value,
                },
            )
        ]

    def store_correction(
        self,
        context: FieldContext,
        correct_type: FieldSemanticType,
        original_type: Optional[FieldSemanticType] = None,
        original_confidence: float = 0.0,
    ) -> None:
        """Store a human correction for future learning.

        Args:
            context: Field context that was corrected
            correct_type: Human-confirmed semantic type
            original_type: What we originally guessed (if any)
            original_confidence: Original confidence score
        """
        if not self.db_session or not context.label:
            return

        normalized = context.label.lower().strip()

        # Check if correction already exists
        existing = self._lookup_correction(normalized, context.ats_type)

        if existing:
            # Update existing correction
            existing.correction_count += 1
            # Would commit to database here
        else:
            # Create new correction
            correction = HistoricalCorrection(
                label_normalized=normalized,
                ats_type=context.ats_type,
                input_type=context.input_type,
                correct_semantic_type=correct_type,
                original_classification=original_type,
                original_confidence=original_confidence,
            )
            # Would add to database session and commit here

        # Clear cache to force reload
        cache_key = f"{normalized}_{context.ats_type.value}"
        if cache_key in self._cache:
            del self._cache[cache_key]

    def validate_correction(
        self,
        context: FieldContext,
        success: bool,
    ) -> None:
        """Update success count when a correction is validated.

        Call this after a field with a historical correction is successfully filled.

        Args:
            context: Field context
            success: True if field was successfully filled
        """
        if not self.db_session or not context.label:
            return

        normalized = context.label.lower().strip()
        correction = self._lookup_correction(normalized, context.ats_type)

        if correction and success:
            correction.success_count += 1
            # Would commit to database here
