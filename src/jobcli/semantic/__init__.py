"""Semantic Field Engine - Multi-signal classification for form fields.

This engine uses 8+ signals to classify form fields with high confidence:
1. Label text patterns
2. Placeholder text
3. ARIA attributes (aria-label, aria-labelledby)
4. DOM ancestry (fieldset, legend, section headers)
5. Neighboring text (descriptions, hints)
6. ATS-specific heuristics (platform-specific patterns)
7. Historical corrections (learned from human feedback)
8. Embeddings (semantic similarity, fallback)

Every classification includes:
- Confidence score [0.0, 1.0]
- Reasoning metadata (which signals contributed)
- Fallback strategies if confidence is low
"""

from jobcli.semantic.engine import SemanticFieldEngine
from jobcli.semantic.models import (
    ClassificationResult,
    ClassificationSignal,
    FieldContext,
)

__all__ = [
    "SemanticFieldEngine",
    "ClassificationResult",
    "ClassificationSignal",
    "FieldContext",
]
