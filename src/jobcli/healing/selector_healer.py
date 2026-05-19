"""Self-healing selector system.

Automatically fixes broken selectors using:
- Semantic matching (labels, placeholders, aria attributes)
- DOM similarity (structure, attributes, position)
- Historical patterns (previously successful selectors)
- Adaptive fallbacks
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Page
from pydantic import BaseModel, Field


class SelectorCandidate(BaseModel):
    """A candidate selector with confidence score."""

    selector: str = Field(..., description="CSS selector")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    strategy: str = Field(..., description="Strategy that generated this selector")
    element_count: int = Field(0, description="Number of matching elements")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SelectorHealingResult(BaseModel):
    """Result of selector healing attempt."""

    original_selector: str
    healed_selector: Optional[str] = None
    success: bool = False
    confidence: float = 0.0
    strategy: Optional[str] = None
    candidates: List[SelectorCandidate] = Field(default_factory=list)
    attempts: int = 0


class HistoricalPattern(BaseModel):
    """Historical successful selector pattern."""

    field_type: str
    selector: str
    success_count: int = 0
    last_used: datetime = Field(default_factory=datetime.utcnow)
    ats_type: Optional[str] = None


class SelectorHealer:
    """Self-healing selector system with multiple fallback strategies."""

    def __init__(
        self,
        page: Page,
        patterns_file: Optional[Path] = None,
    ):
        """Initialize selector healer.

        Args:
            page: Playwright Page instance
            patterns_file: Path to historical patterns file
        """
        self.page = page
        self.patterns_file = patterns_file or Path("selector_patterns.json")
        self.patterns: List[HistoricalPattern] = []
        self._load_patterns()

    def heal_selector(
        self,
        original_selector: str,
        field_type: str,
        semantic_context: Optional[Dict[str, Any]] = None,
    ) -> SelectorHealingResult:
        """Attempt to heal a broken selector.

        Args:
            original_selector: Original broken selector
            field_type: Type of field (email, phone, name, etc.)
            semantic_context: Additional context (label, placeholder, etc.)

        Returns:
            SelectorHealingResult with healed selector or None
        """
        result = SelectorHealingResult(
            original_selector=original_selector,
            attempts=0,
        )

        # Try multiple strategies in order of confidence
        strategies = [
            self._try_semantic_matching,
            self._try_historical_patterns,
            self._try_dom_similarity,
            self._try_attribute_variations,
            self._try_positional_matching,
        ]

        for strategy in strategies:
            result.attempts += 1
            candidates = strategy(original_selector, field_type, semantic_context or {})

            # Add to candidates list
            result.candidates.extend(candidates)

            # Check if any candidate works
            for candidate in sorted(candidates, key=lambda c: c.confidence, reverse=True):
                if self._validate_candidate(candidate):
                    result.healed_selector = candidate.selector
                    result.success = True
                    result.confidence = candidate.confidence
                    result.strategy = candidate.strategy
                    return result

        return result

    def _try_semantic_matching(
        self,
        original_selector: str,
        field_type: str,
        context: Dict[str, Any],
    ) -> List[SelectorCandidate]:
        """Try to find element using semantic attributes.

        Strategy: Look for labels, placeholders, aria attributes, data attributes
        that match the field type.
        """
        candidates = []

        # Common semantic patterns per field type
        semantic_patterns = {
            "email": ["email", "e-mail", "mail"],
            "phone": ["phone", "telephone", "tel", "mobile"],
            "first_name": ["first name", "firstname", "fname", "given name"],
            "last_name": ["last name", "lastname", "lname", "surname", "family name"],
            "address": ["address", "street"],
            "city": ["city", "town"],
            "state": ["state", "province", "region"],
            "zip": ["zip", "postal", "postcode"],
            "country": ["country", "nation"],
        }

        patterns = semantic_patterns.get(field_type, [field_type])

        for pattern in patterns:
            # Try various semantic selectors
            semantic_selectors = [
                # Name attribute
                f"input[name*='{pattern}' i]",
                f"textarea[name*='{pattern}' i]",
                # ID attribute
                f"input[id*='{pattern}' i]",
                f"textarea[id*='{pattern}' i]",
                # Placeholder
                f"input[placeholder*='{pattern}' i]",
                f"textarea[placeholder*='{pattern}' i]",
                # Aria-label
                f"input[aria-label*='{pattern}' i]",
                f"textarea[aria-label*='{pattern}' i]",
                # Data attributes
                f"input[data-field*='{pattern}' i]",
                f"input[data-testid*='{pattern}' i]",
                # Class names
                f"input[class*='{pattern}' i]",
            ]

            for selector in semantic_selectors:
                try:
                    count = self.page.locator(selector).count()
                    if count > 0:
                        candidates.append(
                            SelectorCandidate(
                                selector=selector,
                                confidence=0.85 if count == 1 else 0.70,
                                strategy="semantic_matching",
                                element_count=count,
                                metadata={"pattern": pattern},
                            )
                        )
                except Exception:
                    pass

        return candidates

    def _try_historical_patterns(
        self,
        original_selector: str,
        field_type: str,
        context: Dict[str, Any],
    ) -> List[SelectorCandidate]:
        """Try selectors that worked historically for this field type.

        Strategy: Use patterns that have high success rate for this field type.
        """
        candidates = []

        # Get historical patterns for this field type
        field_patterns = [p for p in self.patterns if p.field_type == field_type]

        # Sort by success count
        field_patterns.sort(key=lambda p: p.success_count, reverse=True)

        for pattern in field_patterns[:5]:  # Top 5 patterns
            try:
                count = self.page.locator(pattern.selector).count()
                if count > 0:
                    # Confidence based on success count and recency
                    base_confidence = 0.80
                    success_boost = min(pattern.success_count / 10, 0.15)
                    confidence = base_confidence + success_boost

                    candidates.append(
                        SelectorCandidate(
                            selector=pattern.selector,
                            confidence=confidence,
                            strategy="historical_patterns",
                            element_count=count,
                            metadata={
                                "success_count": pattern.success_count,
                                "last_used": pattern.last_used.isoformat(),
                            },
                        )
                    )
            except Exception:
                pass

        return candidates

    def _try_dom_similarity(
        self,
        original_selector: str,
        field_type: str,
        context: Dict[str, Any],
    ) -> List[SelectorCandidate]:
        """Try to find similar elements in the DOM.

        Strategy: Find elements with similar structure/attributes as the
        original selector (even if selector is now invalid).
        """
        candidates = []

        # Extract selector components
        # e.g., "input[name='email']" -> tag=input, attrs={name: email}
        selector_parts = self._parse_selector(original_selector)

        if not selector_parts:
            return candidates

        tag = selector_parts.get("tag", "input")
        attrs = selector_parts.get("attrs", {})

        # Try relaxed versions of the selector
        if attrs:
            # Try each attribute individually
            for attr, value in attrs.items():
                relaxed_selectors = [
                    f"{tag}[{attr}='{value}']",
                    f"{tag}[{attr}*='{value}']",  # Contains
                    f"{tag}[{attr}^='{value}']",  # Starts with
                ]

                for selector in relaxed_selectors:
                    try:
                        count = self.page.locator(selector).count()
                        if count > 0:
                            candidates.append(
                                SelectorCandidate(
                                    selector=selector,
                                    confidence=0.75 if count == 1 else 0.60,
                                    strategy="dom_similarity",
                                    element_count=count,
                                    metadata={"relaxed_attr": attr},
                                )
                            )
                    except Exception:
                        pass

        return candidates

    def _try_attribute_variations(
        self,
        original_selector: str,
        field_type: str,
        context: Dict[str, Any],
    ) -> List[SelectorCandidate]:
        """Try variations of attributes (name, id, class).

        Strategy: Some ATS platforms add prefixes/suffixes or use slightly
        different attribute names.
        """
        candidates = []

        # Common attribute variations per field type
        variations = {
            "email": ["email", "Email", "userEmail", "user_email", "emailAddress"],
            "phone": ["phone", "Phone", "phoneNumber", "phone_number", "tel"],
            "first_name": ["firstName", "firstname", "fname", "first_name"],
            "last_name": ["lastName", "lastname", "lname", "last_name"],
        }

        field_variations = variations.get(field_type, [field_type])

        for variation in field_variations:
            attribute_selectors = [
                f"input[name='{variation}']",
                f"input[id='{variation}']",
                f"input[name*='{variation}']",
                f"input[id*='{variation}']",
            ]

            for selector in attribute_selectors:
                try:
                    count = self.page.locator(selector).count()
                    if count > 0:
                        candidates.append(
                            SelectorCandidate(
                                selector=selector,
                                confidence=0.70 if count == 1 else 0.55,
                                strategy="attribute_variations",
                                element_count=count,
                                metadata={"variation": variation},
                            )
                        )
                except Exception:
                    pass

        return candidates

    def _try_positional_matching(
        self,
        original_selector: str,
        field_type: str,
        context: Dict[str, Any],
    ) -> List[SelectorCandidate]:
        """Try to find element by position in form.

        Strategy: Use label text or position in form to locate field.
        """
        candidates = []

        # Try finding by associated label
        if context.get("label_text"):
            label_text = context["label_text"]

            # Find label, then find associated input
            label_selectors = [
                f"label:has-text('{label_text}') + input",
                f"label:has-text('{label_text}') ~ input",
                f"label:has-text('{label_text}') input",  # Nested
            ]

            for selector in label_selectors:
                try:
                    count = self.page.locator(selector).count()
                    if count > 0:
                        candidates.append(
                            SelectorCandidate(
                                selector=selector,
                                confidence=0.80 if count == 1 else 0.65,
                                strategy="positional_matching",
                                element_count=count,
                                metadata={"label": label_text},
                            )
                        )
                except Exception:
                    pass

        # Try nth-child based on field type common positions
        # (e.g., email is often first, phone second)
        position_hints = {
            "email": [1, 2],
            "phone": [2, 3],
            "first_name": [1],
            "last_name": [2],
        }

        positions = position_hints.get(field_type, [])
        for position in positions:
            selector = f"form input:nth-child({position})"
            try:
                count = self.page.locator(selector).count()
                if count > 0:
                    candidates.append(
                        SelectorCandidate(
                            selector=selector,
                            confidence=0.50,  # Low confidence for positional
                            strategy="positional_matching",
                            element_count=count,
                            metadata={"position": position},
                        )
                    )
            except Exception:
                pass

        return candidates

    def _validate_candidate(self, candidate: SelectorCandidate) -> bool:
        """Validate that a candidate selector works.

        Args:
            candidate: Selector candidate to validate

        Returns:
            True if candidate is valid
        """
        try:
            locator = self.page.locator(candidate.selector).first
            count = locator.count()

            if count == 0:
                return False

            # Check if element is visible and enabled
            is_visible = locator.is_visible()
            is_enabled = locator.is_enabled() if is_visible else False

            return is_visible and is_enabled

        except Exception:
            return False

    def record_success(
        self,
        selector: str,
        field_type: str,
        ats_type: Optional[str] = None,
    ) -> None:
        """Record a successful selector for future use.

        Args:
            selector: Successful selector
            field_type: Field type
            ats_type: ATS platform type
        """
        # Find existing pattern or create new
        pattern = next(
            (
                p
                for p in self.patterns
                if p.field_type == field_type and p.selector == selector
            ),
            None,
        )

        if pattern:
            pattern.success_count += 1
            pattern.last_used = datetime.utcnow()
        else:
            pattern = HistoricalPattern(
                field_type=field_type,
                selector=selector,
                success_count=1,
                ats_type=ats_type,
            )
            self.patterns.append(pattern)

        # Save patterns
        self._save_patterns()

    def _parse_selector(self, selector: str) -> Dict[str, Any]:
        """Parse a CSS selector into components.

        Args:
            selector: CSS selector string

        Returns:
            Dict with tag, attrs, etc.
        """
        parts: Dict[str, Any] = {}

        try:
            # Simple parsing for common cases
            # e.g., "input[name='email']" -> {tag: "input", attrs: {name: "email"}}

            if "[" in selector:
                tag, rest = selector.split("[", 1)
                parts["tag"] = tag.strip()

                # Parse attributes
                attrs = {}
                attr_str = rest.rstrip("]")

                # Handle single attribute
                if "=" in attr_str:
                    key, value = attr_str.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    attrs[key] = value

                parts["attrs"] = attrs
            else:
                parts["tag"] = selector.strip()

        except Exception:
            pass

        return parts

    def _load_patterns(self) -> None:
        """Load historical patterns from file."""
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file) as f:
                    data = json.load(f)
                    self.patterns = [HistoricalPattern(**p) for p in data]
            except Exception:
                self.patterns = []
        else:
            self.patterns = []

    def _save_patterns(self) -> None:
        """Save historical patterns to file."""
        self.patterns_file.parent.mkdir(parents=True, exist_ok=True)

        # Sort by success count
        self.patterns.sort(key=lambda p: p.success_count, reverse=True)

        # Keep only top 100 patterns per field type
        field_types = set(p.field_type for p in self.patterns)
        filtered_patterns = []

        for field_type in field_types:
            field_patterns = [p for p in self.patterns if p.field_type == field_type]
            filtered_patterns.extend(field_patterns[:100])

        with open(self.patterns_file, "w") as f:
            json.dump(
                [p.model_dump() for p in filtered_patterns],
                f,
                indent=2,
                default=str,
            )

    def get_patterns_summary(self) -> Dict[str, Any]:
        """Get summary of historical patterns.

        Returns:
            Dict with statistics
        """
        if not self.patterns:
            return {"total_patterns": 0}

        by_field_type = {}
        for pattern in self.patterns:
            if pattern.field_type not in by_field_type:
                by_field_type[pattern.field_type] = []
            by_field_type[pattern.field_type].append(pattern)

        return {
            "total_patterns": len(self.patterns),
            "field_types": list(by_field_type.keys()),
            "patterns_by_type": {
                ft: len(patterns) for ft, patterns in by_field_type.items()
            },
            "top_patterns": [
                {
                    "field_type": p.field_type,
                    "selector": p.selector,
                    "success_count": p.success_count,
                }
                for p in self.patterns[:10]
            ],
        }
