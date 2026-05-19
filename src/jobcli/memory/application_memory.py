"""Application memory system.

Tracks and learns from every application to optimize future ones:
- Company application history
- Prior answers to questions
- Recruiter interactions
- ATS-specific patterns
- Resume variants and effectiveness
- Callback outcomes
- Rejection trends and reasons
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    """Application status."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    WITHDRAWN = "withdrawn"


class RejectionReason(str, Enum):
    """Common rejection reasons."""

    QUALIFICATIONS = "qualifications"
    EXPERIENCE = "experience"
    LOCATION = "location"
    SALARY = "salary"
    CULTURE_FIT = "culture_fit"
    GHOSTED = "ghosted"
    POSITION_FILLED = "position_filled"
    OTHER = "other"
    UNKNOWN = "unknown"


class ResumeVariant(BaseModel):
    """Resume variant for specific role/company."""

    variant_id: str
    variant_name: str
    file_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Targeting
    targeted_role: Optional[str] = None
    targeted_industry: Optional[str] = None
    targeted_company: Optional[str] = None

    # Effectiveness
    applications_count: int = 0
    callbacks_count: int = 0
    interviews_count: int = 0
    offers_count: int = 0
    callback_rate: float = 0.0

    # Modifications
    modifications: List[str] = Field(
        default_factory=list,
        description="What was changed from base resume",
    )


class QuestionAnswer(BaseModel):
    """Answer to an application question."""

    question_id: str
    question_text: str
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)

    # Context
    field_type: Optional[str] = None
    company_id: Optional[str] = None
    ats_type: Optional[str] = None

    # Effectiveness
    times_used: int = 1
    led_to_callback: Optional[bool] = None
    last_used: datetime = Field(default_factory=datetime.utcnow)


class RecruiterInteraction(BaseModel):
    """Interaction with a recruiter."""

    interaction_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    company_id: str

    interaction_type: str  # email, phone, message, in_person
    sentiment: Optional[str] = None  # positive, neutral, negative
    notes: Optional[str] = None

    # Follow-up
    requires_followup: bool = False
    followup_date: Optional[datetime] = None


class ATSPattern(BaseModel):
    """Learned pattern for specific ATS."""

    ats_type: str
    pattern_type: str  # selector, workflow, timing, quirk

    pattern_data: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)

    # Effectiveness
    success_count: int = 0
    failure_count: int = 0
    last_verified: datetime = Field(default_factory=datetime.utcnow)


class ApplicationRecord(BaseModel):
    """Complete record of a job application."""

    # Identity
    application_id: str
    company_id: str
    company_name: str
    position_title: str
    job_url: Optional[str] = None

    # Application details
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    status: ApplicationStatus = ApplicationStatus.DRAFT
    ats_type: Optional[str] = None

    # Materials
    resume_variant_id: Optional[str] = None
    cover_letter_used: bool = False

    # Answers
    answers: List[QuestionAnswer] = Field(default_factory=list)

    # Interactions
    interactions: List[RecruiterInteraction] = Field(default_factory=list)

    # Outcome
    callback_received: Optional[bool] = None
    callback_date: Optional[datetime] = None
    rejection_received: Optional[bool] = None
    rejection_date: Optional[datetime] = None
    rejection_reason: Optional[RejectionReason] = None
    rejection_details: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class CompanyHistory(BaseModel):
    """Historical data for a company."""

    company_id: str
    company_name: str

    # Applications
    total_applications: int = 0
    applications: List[str] = Field(
        default_factory=list,
        description="Application IDs",
    )

    # Outcomes
    callbacks_received: int = 0
    rejections_received: int = 0
    callback_rate: float = 0.0

    # Patterns
    preferred_ats: Optional[str] = None
    average_response_time_days: Optional[float] = None
    common_rejection_reasons: List[RejectionReason] = Field(default_factory=list)

    # Recruiters
    known_recruiters: List[Dict[str, str]] = Field(default_factory=list)

    # Insights
    best_resume_variant: Optional[str] = None
    successful_question_patterns: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    # Timestamps
    first_application: Optional[datetime] = None
    last_application: Optional[datetime] = None


class ApplicationMemory:
    """Central application memory system.

    Stores and retrieves all application data for learning and optimization.
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        """Initialize application memory.

        Args:
            memory_dir: Directory to store memory data
        """
        self.memory_dir = memory_dir or Path("application_memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Data files
        self.applications_file = self.memory_dir / "applications.json"
        self.companies_file = self.memory_dir / "companies.json"
        self.resumes_file = self.memory_dir / "resume_variants.json"
        self.questions_file = self.memory_dir / "questions.json"
        self.patterns_file = self.memory_dir / "ats_patterns.json"

        # In-memory caches
        self.applications: Dict[str, ApplicationRecord] = {}
        self.companies: Dict[str, CompanyHistory] = {}
        self.resume_variants: Dict[str, ResumeVariant] = {}
        self.questions: Dict[str, QuestionAnswer] = {}
        self.ats_patterns: Dict[str, List[ATSPattern]] = {}

        # Load data
        self._load_all()

    # ── Application Management ────────────────────────────────────────────────

    def create_application(
        self,
        company_name: str,
        position_title: str,
        job_url: Optional[str] = None,
        ats_type: Optional[str] = None,
    ) -> ApplicationRecord:
        """Create new application record.

        Args:
            company_name: Company name
            position_title: Position title
            job_url: Job posting URL
            ats_type: ATS platform type

        Returns:
            ApplicationRecord
        """
        # Generate IDs
        app_id = f"app_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        company_id = self._normalize_company_id(company_name)

        # Create record
        app = ApplicationRecord(
            application_id=app_id,
            company_id=company_id,
            company_name=company_name,
            position_title=position_title,
            job_url=job_url,
            ats_type=ats_type,
        )

        self.applications[app_id] = app

        # Update company history
        self._update_company_history(company_id, company_name, app_id)

        self._save_applications()
        self._save_companies()

        return app

    def update_application(
        self,
        application_id: str,
        **updates,
    ) -> Optional[ApplicationRecord]:
        """Update application record.

        Args:
            application_id: Application ID
            **updates: Fields to update

        Returns:
            Updated ApplicationRecord or None
        """
        app = self.applications.get(application_id)
        if not app:
            return None

        # Update fields
        for key, value in updates.items():
            if hasattr(app, key):
                setattr(app, key, value)

        self._save_applications()

        # Update company history
        if any(k in updates for k in ["callback_received", "rejection_received"]):
            self._recalculate_company_stats(app.company_id)

        return app

    def add_answer(
        self,
        application_id: str,
        question_text: str,
        answer: str,
        confidence: float = 1.0,
        field_type: Optional[str] = None,
    ) -> None:
        """Add answer to application.

        Args:
            application_id: Application ID
            question_text: Question text
            answer: Answer
            confidence: Confidence score
            field_type: Field type
        """
        app = self.applications.get(application_id)
        if not app:
            return

        # Generate question ID
        question_id = self._normalize_question_id(question_text)

        # Create answer
        qa = QuestionAnswer(
            question_id=question_id,
            question_text=question_text,
            answer=answer,
            confidence=confidence,
            field_type=field_type,
            company_id=app.company_id,
            ats_type=app.ats_type,
        )

        # Add to application
        app.answers.append(qa)

        # Add to global questions index
        if question_id in self.questions:
            existing = self.questions[question_id]
            existing.times_used += 1
            existing.last_used = datetime.utcnow()
        else:
            self.questions[question_id] = qa

        self._save_applications()
        self._save_questions()

    def add_interaction(
        self,
        application_id: str,
        interaction_type: str,
        recruiter_name: Optional[str] = None,
        recruiter_email: Optional[str] = None,
        sentiment: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Add recruiter interaction.

        Args:
            application_id: Application ID
            interaction_type: Type of interaction
            recruiter_name: Recruiter name
            recruiter_email: Recruiter email
            sentiment: Sentiment
            notes: Notes
        """
        app = self.applications.get(application_id)
        if not app:
            return

        interaction_id = f"int_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        interaction = RecruiterInteraction(
            interaction_id=interaction_id,
            company_id=app.company_id,
            interaction_type=interaction_type,
            recruiter_name=recruiter_name,
            recruiter_email=recruiter_email,
            sentiment=sentiment,
            notes=notes,
        )

        app.interactions.append(interaction)

        # Update company history
        company = self.companies.get(app.company_id)
        if company and recruiter_email:
            if not any(r["email"] == recruiter_email for r in company.known_recruiters):
                company.known_recruiters.append({
                    "name": recruiter_name or "Unknown",
                    "email": recruiter_email,
                })

        self._save_applications()
        self._save_companies()

    # ── Resume Variants ───────────────────────────────────────────────────────

    def add_resume_variant(
        self,
        variant_name: str,
        file_path: str,
        targeted_role: Optional[str] = None,
        targeted_industry: Optional[str] = None,
        modifications: Optional[List[str]] = None,
    ) -> ResumeVariant:
        """Add resume variant.

        Args:
            variant_name: Variant name
            file_path: Path to resume file
            targeted_role: Targeted role
            targeted_industry: Targeted industry
            modifications: List of modifications

        Returns:
            ResumeVariant
        """
        variant_id = f"resume_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        variant = ResumeVariant(
            variant_id=variant_id,
            variant_name=variant_name,
            file_path=file_path,
            targeted_role=targeted_role,
            targeted_industry=targeted_industry,
            modifications=modifications or [],
        )

        self.resume_variants[variant_id] = variant
        self._save_resumes()

        return variant

    def update_resume_effectiveness(
        self,
        variant_id: str,
        callback: bool = False,
        interview: bool = False,
        offer: bool = False,
    ) -> None:
        """Update resume variant effectiveness.

        Args:
            variant_id: Variant ID
            callback: Got callback?
            interview: Got interview?
            offer: Got offer?
        """
        variant = self.resume_variants.get(variant_id)
        if not variant:
            return

        variant.applications_count += 1
        if callback:
            variant.callbacks_count += 1
        if interview:
            variant.interviews_count += 1
        if offer:
            variant.offers_count += 1

        # Recalculate rate
        if variant.applications_count > 0:
            variant.callback_rate = variant.callbacks_count / variant.applications_count

        self._save_resumes()

    # ── Query & Analytics ─────────────────────────────────────────────────────

    def get_similar_answers(
        self,
        question_text: str,
        company_id: Optional[str] = None,
        ats_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[QuestionAnswer]:
        """Get similar answers to a question.

        Args:
            question_text: Question text
            company_id: Filter by company
            ats_type: Filter by ATS
            limit: Max results

        Returns:
            List of similar QuestionAnswers
        """
        question_id = self._normalize_question_id(question_text)

        # Check for exact match
        exact = self.questions.get(question_id)
        if exact:
            if (not company_id or exact.company_id == company_id) and (
                not ats_type or exact.ats_type == ats_type
            ):
                return [exact]

        # Find similar questions (keyword matching)
        keywords = set(question_text.lower().split())
        candidates = []

        for qa in self.questions.values():
            qa_keywords = set(qa.question_text.lower().split())
            overlap = len(keywords & qa_keywords)

            if overlap > 0:
                # Filter by context
                if company_id and qa.company_id != company_id:
                    continue
                if ats_type and qa.ats_type != ats_type:
                    continue

                candidates.append((overlap, qa))

        # Sort by overlap
        candidates.sort(key=lambda x: x[0], reverse=True)

        return [qa for _, qa in candidates[:limit]]

    def get_company_insights(self, company_id: str) -> Optional[CompanyHistory]:
        """Get insights for a company.

        Args:
            company_id: Company ID

        Returns:
            CompanyHistory or None
        """
        return self.companies.get(company_id)

    def get_best_resume_for_role(self, role: str) -> Optional[ResumeVariant]:
        """Get best resume variant for role.

        Args:
            role: Role name

        Returns:
            Best ResumeVariant or None
        """
        # Find variants targeting this role
        candidates = [
            v
            for v in self.resume_variants.values()
            if v.targeted_role and role.lower() in v.targeted_role.lower()
        ]

        if not candidates:
            return None

        # Sort by callback rate
        candidates.sort(key=lambda v: v.callback_rate, reverse=True)

        return candidates[0]

    def get_rejection_trends(self) -> Dict[str, Any]:
        """Get rejection trends analysis.

        Returns:
            Dict with rejection statistics
        """
        rejected_apps = [
            app
            for app in self.applications.values()
            if app.rejection_received
        ]

        if not rejected_apps:
            return {"total_rejections": 0}

        # Group by reason
        by_reason: Dict[RejectionReason, int] = {}
        for app in rejected_apps:
            reason = app.rejection_reason or RejectionReason.UNKNOWN
            by_reason[reason] = by_reason.get(reason, 0) + 1

        # Calculate rates
        total = len(rejected_apps)

        return {
            "total_rejections": total,
            "by_reason": {k.value: v for k, v in by_reason.items()},
            "top_reason": max(by_reason.items(), key=lambda x: x[1])[0].value,
        }

    def get_callback_rate(self) -> float:
        """Get overall callback rate.

        Returns:
            Callback rate [0.0, 1.0]
        """
        submitted = [
            app
            for app in self.applications.values()
            if app.status != ApplicationStatus.DRAFT
        ]

        if not submitted:
            return 0.0

        callbacks = sum(1 for app in submitted if app.callback_received)

        return callbacks / len(submitted)

    # ── ATS Patterns ──────────────────────────────────────────────────────────

    def record_ats_pattern(
        self,
        ats_type: str,
        pattern_type: str,
        pattern_data: Dict[str, Any],
        confidence: float = 1.0,
    ) -> None:
        """Record ATS pattern.

        Args:
            ats_type: ATS type
            pattern_type: Pattern type
            pattern_data: Pattern data
            confidence: Confidence score
        """
        pattern = ATSPattern(
            ats_type=ats_type,
            pattern_type=pattern_type,
            pattern_data=pattern_data,
            confidence=confidence,
        )

        if ats_type not in self.ats_patterns:
            self.ats_patterns[ats_type] = []

        self.ats_patterns[ats_type].append(pattern)
        self._save_patterns()

    def get_ats_patterns(
        self,
        ats_type: str,
        pattern_type: Optional[str] = None,
    ) -> List[ATSPattern]:
        """Get ATS patterns.

        Args:
            ats_type: ATS type
            pattern_type: Pattern type filter

        Returns:
            List of ATSPatterns
        """
        patterns = self.ats_patterns.get(ats_type, [])

        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]

        return patterns

    # ── Private Methods ───────────────────────────────────────────────────────

    def _normalize_company_id(self, company_name: str) -> str:
        """Normalize company name to ID."""
        return company_name.lower().replace(" ", "_").replace(".", "")

    def _normalize_question_id(self, question_text: str) -> str:
        """Normalize question text to ID."""
        import hashlib

        return hashlib.md5(question_text.lower().encode()).hexdigest()[:16]

    def _update_company_history(
        self,
        company_id: str,
        company_name: str,
        app_id: str,
    ) -> None:
        """Update company history with new application."""
        if company_id not in self.companies:
            self.companies[company_id] = CompanyHistory(
                company_id=company_id,
                company_name=company_name,
                first_application=datetime.utcnow(),
            )

        company = self.companies[company_id]
        company.total_applications += 1
        company.applications.append(app_id)
        company.last_application = datetime.utcnow()

    def _recalculate_company_stats(self, company_id: str) -> None:
        """Recalculate company statistics."""
        company = self.companies.get(company_id)
        if not company:
            return

        # Get all applications for this company
        apps = [
            app
            for app in self.applications.values()
            if app.company_id == company_id
        ]

        # Recalculate counts
        company.callbacks_received = sum(1 for app in apps if app.callback_received)
        company.rejections_received = sum(1 for app in apps if app.rejection_received)

        if company.total_applications > 0:
            company.callback_rate = company.callbacks_received / company.total_applications

        self._save_companies()

    def _load_all(self) -> None:
        """Load all data from files."""
        if self.applications_file.exists():
            with open(self.applications_file) as f:
                data = json.load(f)
                self.applications = {k: ApplicationRecord(**v) for k, v in data.items()}

        if self.companies_file.exists():
            with open(self.companies_file) as f:
                data = json.load(f)
                self.companies = {k: CompanyHistory(**v) for k, v in data.items()}

        if self.resumes_file.exists():
            with open(self.resumes_file) as f:
                data = json.load(f)
                self.resume_variants = {k: ResumeVariant(**v) for k, v in data.items()}

        if self.questions_file.exists():
            with open(self.questions_file) as f:
                data = json.load(f)
                self.questions = {k: QuestionAnswer(**v) for k, v in data.items()}

        if self.patterns_file.exists():
            with open(self.patterns_file) as f:
                data = json.load(f)
                self.ats_patterns = {
                    k: [ATSPattern(**p) for p in v] for k, v in data.items()
                }

    def _save_applications(self) -> None:
        """Save applications to file."""
        with open(self.applications_file, "w") as f:
            json.dump(
                {k: v.model_dump() for k, v in self.applications.items()},
                f,
                indent=2,
                default=str,
            )

    def _save_companies(self) -> None:
        """Save companies to file."""
        with open(self.companies_file, "w") as f:
            json.dump(
                {k: v.model_dump() for k, v in self.companies.items()},
                f,
                indent=2,
                default=str,
            )

    def _save_resumes(self) -> None:
        """Save resume variants to file."""
        with open(self.resumes_file, "w") as f:
            json.dump(
                {k: v.model_dump() for k, v in self.resume_variants.items()},
                f,
                indent=2,
                default=str,
            )

    def _save_questions(self) -> None:
        """Save questions to file."""
        with open(self.questions_file, "w") as f:
            json.dump(
                {k: v.model_dump() for k, v in self.questions.items()},
                f,
                indent=2,
                default=str,
            )

    def _save_patterns(self) -> None:
        """Save ATS patterns to file."""
        with open(self.patterns_file, "w") as f:
            json.dump(
                {k: [p.model_dump() for p in v] for k, v in self.ats_patterns.items()},
                f,
                indent=2,
                default=str,
            )
