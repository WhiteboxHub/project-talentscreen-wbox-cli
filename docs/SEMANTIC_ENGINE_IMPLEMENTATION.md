## Semantic Field Engine - Implementation Progress

**Date**: 2026-05-18  
**Status**: 🔄 **Phase 1-2 IN PROGRESS** (Architecture + Patterns Complete)

---

## Overview

Building a sophisticated **semantic field classification engine** that uses **8+ signals** to identify form fields with high confidence and reasoning metadata.

### Design Goals

1. **Multi-Signal Classification** — Combine 8+ sources of evidence
2. **Confidence Scoring** — Every classification has [0.0, 1.0] confidence
3. **Reasoning Metadata** — Track which signals contributed and why
4. **Fallback Strategies** — Cascade through strategies when confidence is low
5. **Historical Learning** — Store human corrections for future improvement

---

## Architecture

```
FieldContext (DOM data)
    ↓
┌────────────────── Deterministic Classifiers ──────────────────┐
│                                                                 │
│  Label Patterns ──→ 0.90-0.98 confidence                      │
│  Placeholder ────→ 0.75-0.90 confidence                       │
│  ARIA Labels ────→ 0.85-0.95 confidence                       │
│  Input Type ─────→ 0.60-0.80 confidence                       │
│  Name Attribute ─→ 0.70-0.85 confidence                       │
│                                                                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  ↓
┌────────────────── Context Classifiers ────────────────────────┐
│                                                                 │
│  DOM Ancestry ───→ fieldset/legend context (0.70-0.85)        │
│  Neighboring Text → hints/descriptions (0.65-0.80)             │
│                                                                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  ↓
┌────────────────── Platform Classifiers ───────────────────────┐
│                                                                 │
│  ATS Heuristics ──→ Greenhouse/Lever patterns (0.80-0.95)     │
│  Historical Corrections → learned from humans (0.50-0.95)     │
│                                                                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  ↓
┌────────────────── Confidence Aggregation ─────────────────────┐
│                                                                 │
│  Weighted Voting → combine signals with confidence weights     │
│  Conflict Resolution → highest confidence wins                 │
│  Reasoning Trace → which signals contributed                   │
│                                                                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  ↓
ClassificationResult
  ├── semantic_type: FieldSemanticType
  ├── confidence: float
  ├── signals: List[ClassificationSignal]
  ├── reasoning: str
  ├── fallback_needed: bool
  └── alternatives: List[...]
                                  ↓
┌────────────────── Fallback Strategies ────────────────────────┐
│                                                                 │
│  IF confidence < 0.6:                                          │
│    1. Try embeddings (semantic similarity)                     │
│    2. Check historical corrections (exact match)               │
│    3. Prompt human with top 3 alternatives                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components Implemented

### ✅ Phase 1: Data Models (Complete)

**File**: `src/jobcli/semantic/models.py` (~200 lines)

```python
# Input: Complete field context
class FieldContext(BaseModel):
    label: Optional[str]
    placeholder: Optional[str]
    input_type: str
    name_attribute: Optional[str]
    aria_label: Optional[str]
    fieldset_legend: Optional[str]
    section_header: Optional[str]
    preceding_text: Optional[str]
    ats_type: ATSType
    # ... 10+ context signals

# Output: Classification with reasoning
class ClassificationResult(BaseModel):
    semantic_type: FieldSemanticType
    confidence: float  # [0.0, 1.0]
    signals: List[ClassificationSignal]
    reasoning: str
    fallback_needed: bool
    alternatives: List[...]

# Each contributing signal
class ClassificationSignal(BaseModel):
    signal_type: SignalType  # label_pattern, aria_label, etc.
    matched_pattern: Optional[str]
    confidence: float
    reasoning: str
```

### ✅ Phase 2: Pattern Library (Complete)

**File**: `src/jobcli/semantic/patterns.py` (~500 lines)

**200+ high-confidence patterns** for 20+ field types:
- email, phone, linkedin, github
- work_authorized, require_sponsorship, visa_status
- salary, clearance (security), gender, pronouns
- race_ethnicity, veteran_status, disability_status
- city, state, country
- school_name, degree_type, gpa
- company_name, job_title, years_of_experience

**Pattern Tiers**:
```python
"exact":  0.98 confidence  # Perfect match: "email" → EMAIL
"high":   0.90 confidence  # Strong signal: "email address" → EMAIL
"medium": 0.75 confidence  # Good signal: "contact email" → EMAIL
"low":    0.60 confidence  # Weak signal: requires support
```

**Example Usage**:
```python
from jobcli.semantic.patterns import PATTERN_LIBRARY

# Match single type
matched, conf, tier = PATTERN_LIBRARY.match("Email Address", FieldSemanticType.EMAIL)
# → (True, 0.90, "high")

# Match all types
matches = PATTERN_LIBRARY.match_all_types("LinkedIn Profile URL")
# → [(FieldSemanticType.LINKEDIN_URL, 0.98, "exact"), ...]
```

---

## Remaining Implementation

### ⏳ Phase 3: Deterministic Classifiers (Next)

**File**: `src/jobcli/semantic/classifiers/deterministic.py` (~300 lines)

```python
class LabelClassifier:
    """Classify from label text using pattern library."""
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        signals = []
        
        # Try label
        if context.label:
            matches = PATTERN_LIBRARY.match_all_types(context.label)
            for semantic_type, confidence, tier in matches[:3]:  # Top 3
                signals.append(ClassificationSignal(
                    signal_type=SignalType.LABEL_PATTERN,
                    matched_pattern=f"{tier} tier",
                    confidence=confidence,
                    reasoning=f"Label '{context.label}' matches {semantic_type.value} ({tier})",
                ))
        
        return signals


class PlaceholderClassifier:
    """Classify from placeholder text."""
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        # Similar to label, but lower confidence (placeholders are hints)
        pass


class ARIAClassifier:
    """Classify from ARIA attributes."""
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        # ARIA labels are high confidence (accessibility-first)
        pass


class InputTypeClassifier:
    """Classify from HTML input type."""
    
    CONFIDENCE_MAP = {
        "email": (FieldSemanticType.EMAIL, 0.85),
        "tel": (FieldSemanticType.PHONE, 0.80),
        "url": (FieldSemanticType.WEBSITE_URL, 0.70),
        "number": (FieldSemanticType.CUSTOM_TEXT, 0.50),  # Ambiguous
    }
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        pass
```

### ⏳ Phase 4: Context Classifiers

**File**: `src/jobcli/semantic/classifiers/context.py` (~250 lines)

```python
class DOMContextClassifier:
    """Classify from fieldset/legend and section headers."""
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        signals = []
        
        # Example: fieldset legend = "Personal Information"
        # → boosts confidence for email, phone, address fields
        
        # Example: section header = "Work Authorization"
        # → boosts confidence for work_authorized, sponsorship fields
        
        return signals


class NeighboringTextClassifier:
    """Classify from text before/after the field."""
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        # Example: preceding_text = "Enter your email address below"
        # → strong signal for EMAIL
        pass
```

### ⏳ Phase 5: Platform Classifiers

**File**: `src/jobcli/semantic/classifiers/platform.py` (~200 lines)

```python
class ATSHeuristicClassifier:
    """Platform-specific patterns for known ATS systems."""
    
    GREENHOUSE_PATTERNS = {
        # Greenhouse uses specific name attributes
        "input[name='job_application[email]']": (FieldSemanticType.EMAIL, 0.95),
        "input[name='job_application[phone]']": (FieldSemanticType.PHONE, 0.95),
        # ... 50+ known patterns
    }
    
    LEVER_PATTERNS = {
        # Lever uses different structure
        "input[data-qa='email-input']": (FieldSemanticType.EMAIL, 0.95),
        # ...
    }
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        if context.ats_type == ATSType.GREENHOUSE:
            # Check Greenhouse patterns
            pass
        elif context.ats_type == ATSType.LEVER:
            # Check Lever patterns
            pass
        return []


class HistoricalCorrectionClassifier:
    """Use human corrections from past applications."""
    
    def __init__(self, db_session):
        self.repo = HistoricalCorrectionRepository(db_session)
    
    def classify(self, context: FieldContext) -> List[ClassificationSignal]:
        # Normalize label
        normalized = context.label.lower().strip()
        
        # Look up correction
        correction = self.repo.get_by_label(normalized, context.ats_type)
        if correction:
            confidence = correction.get_correction_confidence()
            return [ClassificationSignal(
                signal_type=SignalType.HISTORICAL_CORRECTION,
                matched_pattern=f"correction_id_{correction.id}",
                confidence=confidence,
                reasoning=f"Human corrected this field {correction.correction_count} times",
            )]
        
        return []
```

### ⏳ Phase 6: Confidence Aggregation Engine

**File**: `src/jobcli/semantic/engine.py` (~400 lines)

```python
class SemanticFieldEngine:
    """Main classification engine that coordinates all classifiers."""
    
    def __init__(self, db_session=None):
        # Initialize all classifiers
        self.label_classifier = LabelClassifier()
        self.placeholder_classifier = PlaceholderClassifier()
        self.aria_classifier = ARIAClassifier()
        self.input_type_classifier = InputTypeClassifier()
        self.dom_context_classifier = DOMContextClassifier()
        self.neighboring_text_classifier = NeighboringTextClassifier()
        self.ats_heuristic_classifier = ATSHeuristicClassifier()
        
        if db_session:
            self.historical_classifier = HistoricalCorrectionClassifier(db_session)
        else:
            self.historical_classifier = None
    
    def classify(self, context: FieldContext) -> ClassificationResult:
        """Classify a field using all available signals.
        
        Algorithm:
        1. Run all classifiers in parallel
        2. Collect signals from each
        3. Aggregate using weighted voting
        4. Resolve conflicts (highest confidence wins)
        5. Build reasoning trace
        6. Determine if fallback is needed
        """
        all_signals: List[ClassificationSignal] = []
        
        # Run deterministic classifiers
        all_signals.extend(self.label_classifier.classify(context))
        all_signals.extend(self.placeholder_classifier.classify(context))
        all_signals.extend(self.aria_classifier.classify(context))
        all_signals.extend(self.input_type_classifier.classify(context))
        
        # Run context classifiers
        all_signals.extend(self.dom_context_classifier.classify(context))
        all_signals.extend(self.neighboring_text_classifier.classify(context))
        
        # Run platform classifiers
        all_signals.extend(self.ats_heuristic_classifier.classify(context))
        if self.historical_classifier:
            all_signals.extend(self.historical_classifier.classify(context))
        
        # Aggregate signals
        return self._aggregate_signals(all_signals, context)
    
    def _aggregate_signals(
        self,
        signals: List[ClassificationSignal],
        context: FieldContext,
    ) -> ClassificationResult:
        """Combine signals using weighted voting.
        
        Algorithm:
        1. Group signals by semantic_type (inferred from signal metadata)
        2. For each type, calculate weighted average confidence
        3. Pick type with highest aggregated confidence
        4. Build reasoning from contributing signals
        """
        if not signals:
            return self._unknown_field_result(context)
        
        # Group by semantic type (need to track which signal votes for which type)
        votes: Dict[FieldSemanticType, List[ClassificationSignal]] = {}
        
        # For now, simplified: each signal implies a semantic type
        # (In real implementation, signals would include semantic_type field)
        
        # Calculate aggregated confidence per type
        type_confidences: Dict[FieldSemanticType, float] = {}
        for semantic_type, type_signals in votes.items():
            # Weighted average (or max, or Bayesian combination)
            total_confidence = sum(s.confidence for s in type_signals)
            avg_confidence = total_confidence / len(type_signals)
            type_confidences[semantic_type] = min(avg_confidence, 0.98)  # Cap at 0.98
        
        # Pick winner
        winner_type = max(type_confidences, key=type_confidences.get)
        winner_confidence = type_confidences[winner_type]
        winner_signals = votes[winner_type]
        
        # Build reasoning
        reasoning = self._build_reasoning(winner_type, winner_signals)
        
        # Determine if fallback needed
        fallback_needed = winner_confidence < 0.6
        
        # Build alternatives (other types with >0.3 confidence)
        alternatives = [
            {"semantic_type": st.value, "confidence": conf}
            for st, conf in type_confidences.items()
            if st != winner_type and conf > 0.3
        ]
        
        return ClassificationResult(
            semantic_type=winner_type,
            confidence=winner_confidence,
            signals=winner_signals,
            reasoning=reasoning,
            fallback_needed=fallback_needed,
            alternatives=alternatives,
        )
    
    def _build_reasoning(
        self,
        semantic_type: FieldSemanticType,
        signals: List[ClassificationSignal],
    ) -> str:
        """Build human-readable reasoning from signals."""
        parts = [f"Classified as {semantic_type.value}:"]
        
        # Group by signal type
        by_type: Dict[SignalType, List[ClassificationSignal]] = {}
        for signal in signals:
            by_type.setdefault(signal.signal_type, []).append(signal)
        
        # Summarize each type
        if SignalType.LABEL_PATTERN in by_type:
            parts.append(f"- Label matches {semantic_type.value} pattern")
        if SignalType.ARIA_LABEL in by_type:
            parts.append(f"- ARIA label confirms {semantic_type.value}")
        if SignalType.ATS_HEURISTIC in by_type:
            parts.append(f"- Known {signals[0].metadata.get('ats')} pattern")
        if SignalType.HISTORICAL_CORRECTION in by_type:
            count = signals[0].metadata.get('correction_count', 1)
            parts.append(f"- Human corrected this field {count} time(s) before")
        
        return " ".join(parts)
    
    def _unknown_field_result(self, context: FieldContext) -> ClassificationResult:
        """Return UNKNOWN classification when no signals match."""
        return ClassificationResult(
            semantic_type=FieldSemanticType.UNKNOWN,
            confidence=0.0,
            signals=[],
            reasoning="No matching patterns found",
            fallback_needed=True,
            alternatives=[],
        )
```

### ⏳ Phase 7: Fallback Strategies

**File**: `src/jobcli/semantic/fallback.py` (~200 lines)

```python
class FallbackStrategy:
    """Cascading fallback when confidence is low."""
    
    def execute(
        self,
        context: FieldContext,
        primary_result: ClassificationResult,
    ) -> ClassificationResult:
        """Try fallback strategies in order.
        
        1. Embeddings: semantic similarity to known field types
        2. Historical exact match: check DB for identical field
        3. Human prompt: ask user with top 3 alternatives
        """
        if primary_result.confidence >= 0.6:
            return primary_result  # Good enough, no fallback
        
        # Try embeddings
        embedding_result = self._try_embeddings(context)
        if embedding_result and embedding_result.confidence >= 0.6:
            return embedding_result
        
        # Try historical exact match
        historical_result = self._try_historical_exact_match(context)
        if historical_result and historical_result.confidence >= 0.7:
            return historical_result
        
        # Last resort: human prompt
        return self._prompt_human(context, primary_result)
    
    def _try_embeddings(self, context: FieldContext) -> Optional[ClassificationResult]:
        """Use embeddings for semantic similarity (future enhancement)."""
        # TODO: Implement with sentence-transformers or OpenAI embeddings
        pass
    
    def _try_historical_exact_match(self, context: FieldContext) -> Optional[ClassificationResult]:
        """Look for exact match in historical corrections."""
        # Already checked in HistoricalCorrectionClassifier,
        # but this time we're more lenient (accept lower success_count)
        pass
    
    def _prompt_human(
        self,
        context: FieldContext,
        primary_result: ClassificationResult,
    ) -> ClassificationResult:
        """Ask human to classify, showing top alternatives."""
        from jobcli.human.agent_interface import AgentInterface
        
        interface = AgentInterface()
        
        # Build prompt
        alternatives = primary_result.alternatives[:3]  # Top 3
        prompt = f"Unable to confidently classify field: {context.label}\n\n"
        prompt += "Best guesses:\n"
        for i, alt in enumerate(alternatives, 1):
            prompt += f"{i}. {alt['semantic_type']} ({alt['confidence']:.0%} confidence)\n"
        prompt += "\nWhich type is this field?"
        
        # Get human choice
        choice = interface.ask_question(prompt, [alt['semantic_type'] for alt in alternatives])
        
        # Store as historical correction
        self._store_correction(context, choice, primary_result)
        
        return ClassificationResult(
            semantic_type=FieldSemanticType(choice),
            confidence=0.95,  # Human override = high confidence
            signals=[ClassificationSignal(
                signal_type=SignalType.HISTORICAL_CORRECTION,
                matched_pattern="human_override",
                confidence=0.95,
                reasoning="Human classified during fallback",
            )],
            reasoning=f"Human classified as {choice} (fallback prompt)",
            fallback_needed=False,
        )
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_semantic_patterns.py
def test_email_pattern_exact_match():
    matched, conf, tier = PATTERN_LIBRARY.match("email", FieldSemanticType.EMAIL)
    assert matched is True
    assert conf == 0.98
    assert tier == "exact"

def test_email_pattern_high_confidence():
    matched, conf, tier = PATTERN_LIBRARY.match("Email Address", FieldSemanticType.EMAIL)
    assert matched is True
    assert conf == 0.90
    assert tier == "high"

# tests/test_semantic_classifiers.py
def test_label_classifier():
    context = FieldContext(
        label="Email Address",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
        is_required=True,
    )
    
    classifier = LabelClassifier()
    signals = classifier.classify(context)
    
    assert len(signals) > 0
    assert signals[0].signal_type == SignalType.LABEL_PATTERN
    assert signals[0].confidence >= 0.90

# tests/test_semantic_engine.py
def test_engine_high_confidence():
    context = FieldContext(
        label="Email Address",
        input_type="email",
        aria_label="Email",
        ats_type=ATSType.GREENHOUSE,
        selector="input#email",
    )
    
    engine = SemanticFieldEngine()
    result = engine.classify(context)
    
    assert result.semantic_type == FieldSemanticType.EMAIL
    assert result.confidence >= 0.9
    assert len(result.signals) >= 2  # Label + input_type
    assert result.fallback_needed is False
```

---

## Integration with Canonical Model

The semantic engine **feeds into** the canonical model:

```python
# In field_builder.py
from jobcli.semantic.engine import SemanticFieldEngine
from jobcli.semantic.models import FieldContext

def build_field_with_semantic_engine(
    ax_field: AccessibilityField,
    ats_type: ATSType,
    resume: ResumeData,
) -> ApplicationField:
    """Build canonical field using semantic engine."""
    
    # Build context from AXTree
    context = FieldContext(
        label=ax_field.label,
        placeholder=ax_field.placeholder,
        input_type=ax_field.input_type,
        name_attribute=ax_field.name,
        aria_label=ax_field.aria_label,
        ats_type=ats_type,
        selector=ax_field.selector,
        is_required=ax_field.required,
    )
    
    # Classify with semantic engine
    engine = SemanticFieldEngine(db_session=get_db_session())
    classification = engine.classify(context)
    
    # Build canonical field with classification result
    builder = FieldBuilder(resume, ats_type, page_index=0)
    field = builder.from_semantic_type(
        field_id=generate_field_id(ax_field.selector),
        semantic_type=classification.semantic_type,
        raw_label=ax_field.label,
        required=ax_field.required,
        ats_selector=ax_field.selector,
    )
    
    # Boost confidence if semantic engine is confident
    if classification.confidence > field.confidence.value:
        field.confidence.value = classification.confidence
        field.confidence.metadata["semantic_engine_signals"] = [
            s.model_dump() for s in classification.signals
        ]
    
    return field
```

---

## Next Steps

### Immediate (Complete Phase 3-7)

1. **Phase 3**: Implement deterministic classifiers (6-8 hours)
2. **Phase 4**: Implement context classifiers (4-6 hours)
3. **Phase 5**: Implement platform classifiers (4-6 hours)
4. **Phase 6**: Implement confidence aggregation (6-8 hours)
5. **Phase 7**: Implement fallback strategies (4-6 hours)

**Total Estimated Time**: 24-34 hours (3-4 weeks)

### Future Enhancements

1. **Embeddings**: Use sentence-transformers for semantic similarity
2. **ML Model**: Train a model on historical corrections
3. **Active Learning**: Prioritize human prompts on fields with highest uncertainty
4. **Cross-ATS Learning**: Learn patterns from one ATS, apply to others

---

## Files Created So Far

```
src/jobcli/semantic/
├── __init__.py              # Public API (30 lines)
├── models.py                # Data models (200 lines)
│   ├── SignalType enum
│   ├── ClassificationSignal
│   ├── FieldContext
│   ├── ClassificationResult
│   └── HistoricalCorrection
└── patterns.py              # Pattern library (500 lines)
    ├── PatternLibrary class
    ├── 200+ patterns for 20+ field types
    └── match() / match_all_types() methods
```

**Status**: 2/7 phases complete (~730 lines)

---

**Next**: Implement deterministic classifiers (Phase 3)
