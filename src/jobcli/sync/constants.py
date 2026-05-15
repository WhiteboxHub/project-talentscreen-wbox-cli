"""Shared constants for the local learning & memory system.

These constants are intentionally defined in ``jobcli/sync/`` so that the
memory layer, repositories, and (future) sync client all import from one
canonical location.  Phase 2 can add a server URL, auth tokens, etc. here
without touching any other module.
"""

# ── Confidence gate ──────────────────────────────────────────────────────────
# A record must have confidence >= CONFIDENCE_THRESHOLD AND at least
# MIN_SUCCESS_COUNT successful uses before it is returned from memory instead
# of falling through to the LLM.
#
# Rationale for 0.6 / 3:
#   0.6  → at least 3 successes out of 5 total attempts (60 %)
#   3    → prevents a single lucky hit from poisoning memory
CONFIDENCE_THRESHOLD: float = 0.6
MIN_SUCCESS_COUNT: int = 3

# ── Personal / PII field labels ───────────────────────────────────────────────
# Answers for these canonical labels are NEVER exported by the extractor.
# The set is checked against the *normalized* label (lower-case, stripped).
# Add company/job-specific PII labels here as they surface in the wild.
PERSONAL_FIELDS: frozenset[str] = frozenset(
    {
        # Identity
        "email",
        "email address",
        "phone",
        "phone number",
        "mobile",
        "mobile number",
        "first name",
        "last name",
        "full name",
        "name",
        "legal name",
        "preferred name",
        "date of birth",
        "dob",
        "birth date",
        "age",
        "gender",
        "pronouns",
        "sexual orientation",
        "race",
        "ethnicity",
        "national origin",
        # Address / location
        "address",
        "street address",
        "address line 1",
        "address line 2",
        "city",
        "state",
        "zip",
        "zip code",
        "postal code",
        "country",
        # Government / financial IDs
        "social security",
        "ssn",
        "passport",
        "national id",
        "tax id",
        "ein",
        # Professional identity / profile URLs
        "linkedin",
        "linkedin url",
        "linkedin profile",
        "github",
        "github url",
        "portfolio",
        "website",
        "personal website",
        # Sensitive compliance
        "salary",
        "salary expectation",
        "current salary",
        "desired salary",
        "compensation",
        "veteran status",
        "disability status",
        "disability",
        "veteran",
    }
)
