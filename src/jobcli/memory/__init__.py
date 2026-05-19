"""Application memory system for JobCLI.

Tracks and learns from every application:
- Company application history
- Prior answers to questions
- Recruiter interactions
- ATS-specific patterns
- Resume variant effectiveness
- Callback outcomes and timing
- Rejection trends and reasons

Provides optimization intelligence:
- Answer suggestions from similar questions
- Resume variant recommendations
- Company opportunity scoring
- Rejection trend analysis
- Timing insights

Usage:
    from jobcli.memory import ApplicationMemory, OptimizationIntelligence

    # Initialize memory
    memory = ApplicationMemory()

    # Create application
    app = memory.create_application(
        company_name="Google",
        position_title="Software Engineer",
        ats_type="greenhouse"
    )

    # Add answers
    memory.add_answer(
        app.application_id,
        "Why do you want to work here?",
        "I'm passionate about...",
        confidence=0.9
    )

    # Update outcome
    memory.update_application(
        app.application_id,
        status="submitted",
        callback_received=True
    )

    # Get insights
    intelligence = OptimizationIntelligence(memory)
    recommendations = intelligence.get_recommendations()

    # Score opportunity
    score = intelligence.score_opportunity(
        "Amazon",
        "Senior Engineer"
    )
"""

from .application_memory import (
    ApplicationMemory,
    ApplicationRecord,
    ApplicationStatus,
    ATSPattern,
    CompanyHistory,
    QuestionAnswer,
    RecruiterInteraction,
    RejectionReason,
    ResumeVariant,
)
from .intelligence import (
    OpportunityScore,
    OptimizationIntelligence,
    Recommendation,
)

__all__ = [
    # Memory
    "ApplicationMemory",
    "ApplicationRecord",
    "ApplicationStatus",
    "CompanyHistory",
    "QuestionAnswer",
    "RecruiterInteraction",
    "ResumeVariant",
    "RejectionReason",
    "ATSPattern",
    # Intelligence
    "OptimizationIntelligence",
    "Recommendation",
    "OpportunityScore",
]
