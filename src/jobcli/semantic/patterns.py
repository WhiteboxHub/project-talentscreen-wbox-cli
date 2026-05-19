"""Pattern libraries for deterministic field classification.

High-confidence patterns for each semantic type, organized by signal strength.
Patterns are tested in order: exact → high-confidence regex → medium → low.
"""

import re
from typing import Pattern

from jobcli.canonical.models import FieldSemanticType


# ── Pattern Confidence Tiers ──────────────────────────────────────────────────

# EXACT: 0.98 confidence (perfect match, no ambiguity)
# HIGH: 0.90 confidence (very strong signal, rare false positives)
# MEDIUM: 0.75 confidence (good signal, some ambiguity)
# LOW: 0.60 confidence (weak signal, requires supporting evidence)


class PatternLibrary:
    """Compiled regex patterns for each semantic type."""

    def __init__(self):
        """Compile all patterns on initialization for performance."""
        self._patterns: dict[FieldSemanticType, dict[str, list[Pattern]]] = {}
        self._compile_all()

    def _compile_all(self) -> None:
        """Compile all patterns."""
        # Email patterns
        self._patterns[FieldSemanticType.EMAIL] = {
            "exact": [
                re.compile(r"^email$", re.IGNORECASE),
                re.compile(r"^e-mail$", re.IGNORECASE),
                re.compile(r"^email address$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bemail\s*address\b", re.IGNORECASE),
                re.compile(r"\be-?mail\b", re.IGNORECASE),
                re.compile(r"\byour\s+email\b", re.IGNORECASE),
                re.compile(r"\bemail\s*id\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bcontact\s*email\b", re.IGNORECASE),
                re.compile(r"\bwork\s*email\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Phone patterns
        self._patterns[FieldSemanticType.PHONE] = {
            "exact": [
                re.compile(r"^phone$", re.IGNORECASE),
                re.compile(r"^phone number$", re.IGNORECASE),
                re.compile(r"^mobile$", re.IGNORECASE),
                re.compile(r"^telephone$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bphone\s*number\b", re.IGNORECASE),
                re.compile(r"\bmobile\s*number\b", re.IGNORECASE),
                re.compile(r"\bcontact\s*number\b", re.IGNORECASE),
                re.compile(r"\bcell\s*phone\b", re.IGNORECASE),
                re.compile(r"\btelephone\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bphone\b", re.IGNORECASE),
                re.compile(r"\bmobile\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # LinkedIn patterns
        self._patterns[FieldSemanticType.LINKEDIN_URL] = {
            "exact": [
                re.compile(r"^linkedin$", re.IGNORECASE),
                re.compile(r"^linkedin profile$", re.IGNORECASE),
                re.compile(r"^linkedin url$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\blinkedin\s*profile\b", re.IGNORECASE),
                re.compile(r"\blinkedin\s*url\b", re.IGNORECASE),
                re.compile(r"\blinkedin\s*link\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\blinkedin\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # GitHub patterns
        self._patterns[FieldSemanticType.GITHUB_URL] = {
            "exact": [
                re.compile(r"^github$", re.IGNORECASE),
                re.compile(r"^github profile$", re.IGNORECASE),
                re.compile(r"^github url$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bgithub\s*profile\b", re.IGNORECASE),
                re.compile(r"\bgithub\s*url\b", re.IGNORECASE),
                re.compile(r"\bgithub\s*username\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bgithub\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Work authorization patterns
        self._patterns[FieldSemanticType.WORK_AUTHORIZED] = {
            "exact": [
                re.compile(r"^authorized to work$", re.IGNORECASE),
                re.compile(r"^legally authorized$", re.IGNORECASE),
                re.compile(r"^work authorization$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bauthorized\s+to\s+work\b", re.IGNORECASE),
                re.compile(r"\blegally\s+authorized\b", re.IGNORECASE),
                re.compile(r"\bwork\s+authorization\b", re.IGNORECASE),
                re.compile(r"\blegal\s+to\s+work\b", re.IGNORECASE),
                re.compile(r"\beligible\s+to\s+work\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bwork\s+permit\b", re.IGNORECASE),
                re.compile(r"\bemployment\s+authorization\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Sponsorship patterns
        self._patterns[FieldSemanticType.REQUIRE_SPONSORSHIP] = {
            "exact": [
                re.compile(r"^require sponsorship$", re.IGNORECASE),
                re.compile(r"^need sponsorship$", re.IGNORECASE),
                re.compile(r"^visa sponsorship$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\brequire.*sponsorship\b", re.IGNORECASE),
                re.compile(r"\bneed.*sponsorship\b", re.IGNORECASE),
                re.compile(r"\bvisa\s*sponsorship\b", re.IGNORECASE),
                re.compile(r"\bsponsorship.*required\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bsponsorship\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Visa status patterns
        self._patterns[FieldSemanticType.VISA_STATUS] = {
            "exact": [
                re.compile(r"^visa status$", re.IGNORECASE),
                re.compile(r"^immigration status$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bvisa\s*status\b", re.IGNORECASE),
                re.compile(r"\bimmigration\s*status\b", re.IGNORECASE),
                re.compile(r"\bcurrent\s*visa\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bvisa\s*type\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Salary patterns
        self._patterns[FieldSemanticType.SALARY_EXPECTATION] = {
            "exact": [
                re.compile(r"^salary$", re.IGNORECASE),
                re.compile(r"^salary expectation$", re.IGNORECASE),
                re.compile(r"^expected salary$", re.IGNORECASE),
                re.compile(r"^desired salary$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bsalary\s*expectation\b", re.IGNORECASE),
                re.compile(r"\bexpected\s*salary\b", re.IGNORECASE),
                re.compile(r"\bdesired\s*salary\b", re.IGNORECASE),
                re.compile(r"\bsalary\s*requirement\b", re.IGNORECASE),
                re.compile(r"\bsalary\s*range\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bsalary\b", re.IGNORECASE),
                re.compile(r"\bcompensation\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Clearance patterns (security clearance)
        self._patterns[FieldSemanticType.CUSTOM_SELECT] = {  # No dedicated clearance type yet
            "exact": [
                re.compile(r"^security clearance$", re.IGNORECASE),
                re.compile(r"^clearance level$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bsecurity\s*clearance\b", re.IGNORECASE),
                re.compile(r"\bclearance\s*level\b", re.IGNORECASE),
                re.compile(r"\btop\s*secret\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bclearance\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Gender patterns
        self._patterns[FieldSemanticType.GENDER] = {
            "exact": [
                re.compile(r"^gender$", re.IGNORECASE),
                re.compile(r"^gender identity$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bgender\s*identity\b", re.IGNORECASE),
                re.compile(r"\bself-identify.*gender\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bgender\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Pronouns patterns
        self._patterns[FieldSemanticType.PRONOUNS] = {
            "exact": [
                re.compile(r"^pronouns$", re.IGNORECASE),
                re.compile(r"^preferred pronouns$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bpreferred\s*pronouns\b", re.IGNORECASE),
                re.compile(r"\byour\s*pronouns\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bpronouns\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Race/Ethnicity patterns
        self._patterns[FieldSemanticType.RACE_ETHNICITY] = {
            "exact": [
                re.compile(r"^race$", re.IGNORECASE),
                re.compile(r"^ethnicity$", re.IGNORECASE),
                re.compile(r"^race/ethnicity$", re.IGNORECASE),
                re.compile(r"^racial identity$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\brace.*ethnicity\b", re.IGNORECASE),
                re.compile(r"\bethnicity\b", re.IGNORECASE),
                re.compile(r"\bracial\s*identity\b", re.IGNORECASE),
                re.compile(r"\bself-identify.*race\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\brace\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Veteran status patterns
        self._patterns[FieldSemanticType.VETERAN_STATUS] = {
            "exact": [
                re.compile(r"^veteran status$", re.IGNORECASE),
                re.compile(r"^military veteran$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bveteran\s*status\b", re.IGNORECASE),
                re.compile(r"\bmilitary\s*veteran\b", re.IGNORECASE),
                re.compile(r"\bprotected\s*veteran\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bveteran\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Disability status patterns
        self._patterns[FieldSemanticType.DISABILITY_STATUS] = {
            "exact": [
                re.compile(r"^disability status$", re.IGNORECASE),
                re.compile(r"^disability$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bdisability\s*status\b", re.IGNORECASE),
                re.compile(r"\bhave.*disability\b", re.IGNORECASE),
                re.compile(r"\bdisabled\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bdisability\b", re.IGNORECASE),
            ],
            "low": [],
        }

        # Location patterns (city/state/country)
        self._patterns[FieldSemanticType.CITY] = {
            "exact": [
                re.compile(r"^city$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bcity\b", re.IGNORECASE),
            ],
            "medium": [],
            "low": [],
        }

        self._patterns[FieldSemanticType.STATE] = {
            "exact": [
                re.compile(r"^state$", re.IGNORECASE),
                re.compile(r"^province$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bstate\b", re.IGNORECASE),
                re.compile(r"\bprovince\b", re.IGNORECASE),
            ],
            "medium": [],
            "low": [],
        }

        self._patterns[FieldSemanticType.COUNTRY] = {
            "exact": [
                re.compile(r"^country$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bcountry\b", re.IGNORECASE),
            ],
            "medium": [],
            "low": [],
        }

        # Education patterns
        self._patterns[FieldSemanticType.SCHOOL_NAME] = {
            "exact": [
                re.compile(r"^school$", re.IGNORECASE),
                re.compile(r"^university$", re.IGNORECASE),
                re.compile(r"^college$", re.IGNORECASE),
                re.compile(r"^institution$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bschool\s*name\b", re.IGNORECASE),
                re.compile(r"\buniversity\s*name\b", re.IGNORECASE),
                re.compile(r"\bcollege\s*name\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bschool\b", re.IGNORECASE),
                re.compile(r"\buniversity\b", re.IGNORECASE),
                re.compile(r"\bcollege\b", re.IGNORECASE),
            ],
            "low": [],
        }

        self._patterns[FieldSemanticType.DEGREE_TYPE] = {
            "exact": [
                re.compile(r"^degree$", re.IGNORECASE),
                re.compile(r"^degree type$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bdegree\s*type\b", re.IGNORECASE),
                re.compile(r"\blevel.*education\b", re.IGNORECASE),
                re.compile(r"\bhighest\s*degree\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bdegree\b", re.IGNORECASE),
            ],
            "low": [],
        }

        self._patterns[FieldSemanticType.GPA] = {
            "exact": [
                re.compile(r"^gpa$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bgpa\b", re.IGNORECASE),
                re.compile(r"\bgrade\s*point\b", re.IGNORECASE),
            ],
            "medium": [],
            "low": [],
        }

        # Employment patterns
        self._patterns[FieldSemanticType.COMPANY_NAME] = {
            "exact": [
                re.compile(r"^company$", re.IGNORECASE),
                re.compile(r"^employer$", re.IGNORECASE),
                re.compile(r"^organization$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bcompany\s*name\b", re.IGNORECASE),
                re.compile(r"\bemployer\s*name\b", re.IGNORECASE),
                re.compile(r"\bcurrent\s*company\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bcompany\b", re.IGNORECASE),
                re.compile(r"\bemployer\b", re.IGNORECASE),
            ],
            "low": [],
        }

        self._patterns[FieldSemanticType.JOB_TITLE] = {
            "exact": [
                re.compile(r"^title$", re.IGNORECASE),
                re.compile(r"^job title$", re.IGNORECASE),
                re.compile(r"^position$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\bjob\s*title\b", re.IGNORECASE),
                re.compile(r"\bposition\s*title\b", re.IGNORECASE),
                re.compile(r"\bcurrent\s*title\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\btitle\b", re.IGNORECASE),
                re.compile(r"\bposition\b", re.IGNORECASE),
                re.compile(r"\brole\b", re.IGNORECASE),
            ],
            "low": [],
        }

        self._patterns[FieldSemanticType.YEARS_OF_EXPERIENCE] = {
            "exact": [
                re.compile(r"^years of experience$", re.IGNORECASE),
                re.compile(r"^experience$", re.IGNORECASE),
            ],
            "high": [
                re.compile(r"\byears.*experience\b", re.IGNORECASE),
                re.compile(r"\btotal\s*experience\b", re.IGNORECASE),
                re.compile(r"\bwork\s*experience\b", re.IGNORECASE),
            ],
            "medium": [
                re.compile(r"\bexperience\b", re.IGNORECASE),
            ],
            "low": [],
        }

    def match(
        self,
        text: str,
        semantic_type: FieldSemanticType,
    ) -> tuple[bool, float, Optional[str]]:
        """Match text against patterns for a semantic type.

        Args:
            text: Text to match (label, placeholder, etc.)
            semantic_type: Which type to check

        Returns:
            (matched, confidence, tier) where tier is "exact", "high", "medium", or "low"
        """
        if not text:
            return False, 0.0, None

        # Get patterns for this type
        type_patterns = self._patterns.get(semantic_type, {})

        # Try tiers in order: exact → high → medium → low
        confidence_map = {
            "exact": 0.98,
            "high": 0.90,
            "medium": 0.75,
            "low": 0.60,
        }

        for tier in ["exact", "high", "medium", "low"]:
            patterns = type_patterns.get(tier, [])
            for pattern in patterns:
                if pattern.search(text):
                    return True, confidence_map[tier], tier

        return False, 0.0, None

    def match_all_types(self, text: str) -> list[tuple[FieldSemanticType, float, str]]:
        """Match text against all semantic types.

        Args:
            text: Text to match

        Returns:
            List of (semantic_type, confidence, tier) for all matches, sorted by confidence desc
        """
        matches: list[tuple[FieldSemanticType, float, str]] = []

        for semantic_type in self._patterns.keys():
            matched, confidence, tier = self.match(text, semantic_type)
            if matched:
                matches.append((semantic_type, confidence, tier or "unknown"))

        # Sort by confidence descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches


# Global instance
PATTERN_LIBRARY = PatternLibrary()
