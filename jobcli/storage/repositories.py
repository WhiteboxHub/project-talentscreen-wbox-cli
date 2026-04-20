"""Repository pattern for data access."""

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Integer
from sqlalchemy.orm import Session

from jobcli.core.locator_schemas import LearnedLocator
from jobcli.core.schemas import (
    ATSType,
    ApplicationStatus,
    CommonQuestions,
    Config,
    ExecutionPhase,
    Job,
    ResumeData,
)
from jobcli.core.url_normalize import normalize_job_url
from jobcli.storage.models import (
    ApplicationLogModel,
    ConfigModel,
    DropdownStrategyModel,
    FieldAnswerModel,
    InteractionLogModel,
    JobModel,
    LearnedLocatorModel,
    UserDataModel,
)


class JobRepository:
    """Repository for job operations."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def create(self, job: Job) -> Job:
        """Create a new job."""
        canonical = normalize_job_url(job.url)
        job_model = JobModel(
            url=canonical,
            resolved_url=job.resolved_url,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            ats_type=job.ats_type,
            status=job.status,
        )
        self.session.add(job_model)
        self.session.commit()
        self.session.refresh(job_model)

        job.id = job_model.id
        job.url = canonical
        job.created_at = job_model.created_at
        job.updated_at = job_model.updated_at
        return job

    def get(self, job_id: int) -> Optional[Job]:
        """Get job by ID."""
        job_model = self.session.query(JobModel).filter(JobModel.id == job_id).first()
        if not job_model:
            return None

        return Job(
            id=job_model.id,
            url=job_model.url,
            resolved_url=getattr(job_model, "resolved_url", None),
            title=job_model.title,
            company=job_model.company,
            location=job_model.location,
            description=job_model.description,
            ats_type=job_model.ats_type,
            status=job_model.status,
            created_at=job_model.created_at,
            updated_at=job_model.updated_at,
        )

    def get_by_url(self, url: str) -> Optional[Job]:
        """Get job by URL (exact or normalized match)."""
        canonical = normalize_job_url(url)
        job_model = self.session.query(JobModel).filter(JobModel.url == url).first()
        if not job_model and canonical != url:
            job_model = self.session.query(JobModel).filter(JobModel.url == canonical).first()
        if not job_model:
            return None

        return Job(
            id=job_model.id,
            url=job_model.url,
            resolved_url=getattr(job_model, "resolved_url", None),
            title=job_model.title,
            company=job_model.company,
            location=job_model.location,
            description=job_model.description,
            ats_type=job_model.ats_type,
            status=job_model.status,
            created_at=job_model.created_at,
            updated_at=job_model.updated_at,
        )

    def update_status(self, job_id: int, status: ApplicationStatus) -> None:
        """Update job status."""
        self.session.query(JobModel).filter(JobModel.id == job_id).update(
            {"status": status}
        )
        self.session.commit()

    def update_ats_type(self, job_id: int, ats_type: ATSType) -> None:
        """Update detected ATS type."""
        self.session.query(JobModel).filter(JobModel.id == job_id).update(
            {"ats_type": ats_type}
        )
        self.session.commit()

    def update_resolved_url(self, job_id: int, resolved_url: str) -> None:
        """Store final browser URL after redirects (normalized)."""
        self.session.query(JobModel).filter(JobModel.id == job_id).update(
            {"resolved_url": normalize_job_url(resolved_url)}
        )
        self.session.commit()

    def list_pending(self) -> list[Job]:
        """List all pending jobs."""
        jobs = (
            self.session.query(JobModel)
            .filter(JobModel.status == ApplicationStatus.PENDING)
            .all()
        )
        return [
            Job(
                id=j.id,
                url=j.url,
                resolved_url=getattr(j, "resolved_url", None),
                title=j.title,
                company=j.company,
                location=j.location,
                description=j.description,
                ats_type=j.ats_type,
                status=j.status,
                created_at=j.created_at,
                updated_at=j.updated_at,
            )
            for j in jobs
        ]


class ApplicationLogRepository:
    """Repository for application logs."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def log(
        self,
        job_id: int,
        phase: ExecutionPhase,
        action: str,
        success: bool,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
        dom_snapshot: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create a log entry."""
        log_entry = ApplicationLogModel(
            job_id=job_id,
            phase=phase,
            action=action,
            success=success,
            error=error,
            log_metadata=metadata or {},
            screenshot_path=screenshot_path,
            dom_snapshot=dom_snapshot,
        )
        self.session.add(log_entry)
        self.session.commit()

    def get_logs(self, job_id: int) -> list[ApplicationLogModel]:
        """Get all logs for a job."""
        return (
            self.session.query(ApplicationLogModel)
            .filter(ApplicationLogModel.job_id == job_id)
            .order_by(ApplicationLogModel.timestamp)
            .all()
        )


class LearnedLocatorRepository:
    """Repository for learned locators."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def create(self, locator: LearnedLocator) -> LearnedLocator:
        """Create a new learned locator."""
        locator_model = LearnedLocatorModel(
            ats_type=locator.ats_type,
            selector=locator.selector,
            selector_type=locator.selector_type,
            purpose=locator.purpose,
            success_count=locator.success_count,
            failure_count=locator.failure_count,
            confidence_score=locator.confidence_score,
            domain_pattern=locator.domain_pattern,
            url_pattern=locator.url_pattern,
            notes=locator.notes,
            created_by=locator.created_by,
        )
        self.session.add(locator_model)
        self.session.commit()
        self.session.refresh(locator_model)

        locator.id = locator_model.id
        return locator

    def get_by_ats(self, ats_type: ATSType) -> list[LearnedLocator]:
        """Get all locators for an ATS type."""
        locators = (
            self.session.query(LearnedLocatorModel)
            .filter(LearnedLocatorModel.ats_type == ats_type)
            .order_by(LearnedLocatorModel.confidence_score.desc())
            .all()
        )
        return [
            LearnedLocator(
                id=loc.id,
                ats_type=loc.ats_type,
                selector=loc.selector,
                selector_type=loc.selector_type,
                purpose=loc.purpose,
                success_count=loc.success_count,
                failure_count=loc.failure_count,
                confidence_score=loc.confidence_score,
                domain_pattern=loc.domain_pattern,
                url_pattern=loc.url_pattern,
                notes=loc.notes,
                created_at=loc.created_at,
                updated_at=loc.updated_at,
                created_by=loc.created_by,
            )
            for loc in locators
        ]

    def get_by_purpose_and_ats(self, purpose: str, ats_type: ATSType) -> list[LearnedLocator]:
        """Get all locators for a specific purpose and ATS type."""
        locators = (
            self.session.query(LearnedLocatorModel)
            .filter(LearnedLocatorModel.ats_type == ats_type)
            .filter(LearnedLocatorModel.purpose == purpose)
            .order_by(LearnedLocatorModel.confidence_score.desc())
            .all()
        )
        return [
            LearnedLocator(
                id=loc.id,
                ats_type=loc.ats_type,
                selector=loc.selector,
                selector_type=loc.selector_type,
                purpose=loc.purpose,
                success_count=loc.success_count,
                failure_count=loc.failure_count,
                confidence_score=loc.confidence_score,
                domain_pattern=loc.domain_pattern,
                url_pattern=loc.url_pattern,
                notes=loc.notes,
                created_at=loc.created_at,
                updated_at=loc.updated_at,
                created_by=loc.created_by,
            )
            for loc in locators
        ]

    def upsert_for_field(
        self,
        ats_type: ATSType,
        domain: Optional[str],
        purpose: str,
        selector: str,
        selector_type,
        success: bool = True,
        notes: Optional[str] = None,
        job_id: Optional[int] = None,
    ) -> None:
        """Insert-or-update a learned locator keyed by (ats_type, domain, purpose, selector).

        The row is keyed by ``(ats_type, domain, purpose, selector)`` so that
        the selector we learned on this job can be *reused on the next job
        that lands on the same ATS*.  We additionally record ``first_job_id``
        (the job that originally taught us the selector) and ``last_job_id``
        (the most recent job that confirmed it), so the row has an audit
        trail without compromising cross-job reuse.
        """
        if not selector or not purpose:
            return
        domain_pat = (domain or "").lower().strip() or None

        existing = (
            self.session.query(LearnedLocatorModel)
            .filter(LearnedLocatorModel.ats_type == ats_type)
            .filter(LearnedLocatorModel.purpose == purpose)
            .filter(LearnedLocatorModel.selector == selector)
            .filter(LearnedLocatorModel.domain_pattern == domain_pat)
            .first()
        )
        if existing:
            if success:
                existing.success_count += 1
            else:
                existing.failure_count += 1
            total = existing.success_count + existing.failure_count
            if total > 0:
                existing.confidence_score = existing.success_count / total
            existing.updated_at = datetime.now()
            if notes:
                existing.notes = notes
            if job_id is not None:
                if getattr(existing, "first_job_id", None) is None:
                    existing.first_job_id = job_id
                existing.last_job_id = job_id
        else:
            self.session.add(
                LearnedLocatorModel(
                    ats_type=ats_type,
                    selector=selector,
                    selector_type=selector_type,
                    purpose=purpose,
                    success_count=1 if success else 0,
                    failure_count=0 if success else 1,
                    confidence_score=1.0 if success else 0.0,
                    domain_pattern=domain_pat,
                    notes=notes,
                    created_by="auto",
                    first_job_id=job_id,
                    last_job_id=job_id,
                )
            )
        self.session.commit()

    def get_best_for_field(
        self,
        purpose: str,
        ats_type: ATSType,
        domain: Optional[str] = None,
    ) -> Optional[LearnedLocator]:
        """Look up the best learned locator for a (purpose) on this ATS / domain.

        Search order:
          1. Same ATS  +  same domain  (most specific)
          2. Same ATS  (any domain)    (cross-employer reuse on same ATS)
          3. Same domain (any ATS)     (handles re-skinned/embedded portals)
        Returns the highest-confidence row from the first non-empty bucket.
        """
        if not purpose:
            return None
        domain_pat = (domain or "").lower().strip() or None

        def _q():
            return (
                self.session.query(LearnedLocatorModel)
                .filter(LearnedLocatorModel.purpose == purpose)
                .order_by(
                    LearnedLocatorModel.confidence_score.desc(),
                    LearnedLocatorModel.success_count.desc(),
                )
            )

        row = None
        if domain_pat:
            row = _q().filter(LearnedLocatorModel.ats_type == ats_type).filter(LearnedLocatorModel.domain_pattern == domain_pat).first()
        if not row:
            row = _q().filter(LearnedLocatorModel.ats_type == ats_type).first()
        if not row and domain_pat:
            row = _q().filter(LearnedLocatorModel.domain_pattern == domain_pat).first()
        if not row:
            return None
        return LearnedLocator(
            id=row.id,
            ats_type=row.ats_type,
            selector=row.selector,
            selector_type=row.selector_type,
            purpose=row.purpose,
            success_count=row.success_count,
            failure_count=row.failure_count,
            confidence_score=row.confidence_score,
            domain_pattern=row.domain_pattern,
            url_pattern=row.url_pattern,
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
            created_by=row.created_by,
        )

    def update_feedback(self, locator_id: int, success: bool) -> None:
        """Update locator based on feedback."""
        locator = (
            self.session.query(LearnedLocatorModel)
            .filter(LearnedLocatorModel.id == locator_id)
            .first()
        )
        if locator:
            if success:
                locator.success_count += 1
            else:
                locator.failure_count += 1

            total = locator.success_count + locator.failure_count
            if total > 0:
                locator.confidence_score = locator.success_count / total

            self.session.commit()


class UserDataRepository:
    """Repository for user data (resume, questions)."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def save_resume(self, resume: ResumeData) -> None:
        """Save resume data."""
        user_data = (
            self.session.query(UserDataModel)
            .filter(UserDataModel.data_type == "resume")
            .first()
        )

        if user_data:
            user_data.data = json.loads(resume.model_dump_json())
            user_data.updated_at = datetime.now()
        else:
            user_data = UserDataModel(
                data_type="resume", data=json.loads(resume.model_dump_json())
            )
            self.session.add(user_data)

        self.session.commit()

    def get_resume(self) -> Optional[ResumeData]:
        """Get resume data."""
        user_data = (
            self.session.query(UserDataModel)
            .filter(UserDataModel.data_type == "resume")
            .first()
        )
        if not user_data:
            return None

        return ResumeData(**user_data.data)

    def save_questions(self, questions: CommonQuestions) -> None:
        """Save common questions."""
        user_data = (
            self.session.query(UserDataModel)
            .filter(UserDataModel.data_type == "questions")
            .first()
        )

        if user_data:
            user_data.data = json.loads(questions.model_dump_json())
        else:
            user_data = UserDataModel(
                data_type="questions", data=json.loads(questions.model_dump_json())
            )
            self.session.add(user_data)

        self.session.commit()

    def get_questions(self) -> Optional[CommonQuestions]:
        """Get common questions."""
        user_data = (
            self.session.query(UserDataModel)
            .filter(UserDataModel.data_type == "questions")
            .first()
        )
        if not user_data:
            return None

        return CommonQuestions(**user_data.data)

    def save_dynamic_answers(self, answers: dict[str, str]) -> None:
        """Save user answers for mandatory fields."""
        user_data = (
            self.session.query(UserDataModel)
            .filter(UserDataModel.data_type == "dynamic_answers")
            .first()
        )

        if user_data:
            user_data.data = answers
        else:
            user_data = UserDataModel(
                data_type="dynamic_answers", data=answers
            )
            self.session.add(user_data)

        self.session.commit()

    def get_dynamic_answers(self) -> dict[str, str]:
        """Get user answers for mandatory fields."""
        user_data = (
            self.session.query(UserDataModel)
            .filter(UserDataModel.data_type == "dynamic_answers")
            .first()
        )
        if not user_data:
            return {}

        return user_data.data


class ConfigRepository:
    """Repository for configuration."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def get(self, key: str) -> Optional[str]:
        """Get config value."""
        config = self.session.query(ConfigModel).filter(ConfigModel.key == key).first()
        return config.value if config else None

    def set(self, key: str, value: str, encrypted: bool = False) -> None:
        """Set config value."""
        config = self.session.query(ConfigModel).filter(ConfigModel.key == key).first()

        if config:
            config.value = value
            config.encrypted = encrypted
        else:
            config = ConfigModel(key=key, value=value, encrypted=encrypted)
            self.session.add(config)

        self.session.commit()

    def get_all(self) -> Config:
        """Get all configuration as Config object."""
        configs = self.session.query(ConfigModel).all()
        config_dict: dict[str, Any] = {}

        for config in configs:
            config_dict[config.key] = config.value

        return Config(**config_dict)

    def save_config(self, config: Config) -> None:
        """Save entire config object."""
        config_dict = config.model_dump()
        for key, value in config_dict.items():
            if value is not None:
                self.set(key, str(value))


class FieldAnswerRepository:
    """Repository for managing field-level answer memory."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def save_answer(
        self,
        field_label: str,
        normalized_label: str,
        value: str,
        ats_type: ATSType,
        success: bool = True,
        source: str = "human",
        job_id: Optional[int] = None,
    ) -> None:
        """Save or update an answer with success tracking.

        The answer is stored keyed by ``(normalized_label, ats_type)`` so the
        *next* job on the same ATS can reuse it automatically.  We also
        stamp the originating ``first_job_id`` and the latest ``last_job_id``
        so it's possible to trace (or purge) answers learned on a specific
        job without breaking cross-job reuse.
        """
        existing = (
            self.session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.normalized_label == normalized_label,
                FieldAnswerModel.ats_type == ats_type,
            )
            .first()
        )

        if existing:
            existing.value = value
            existing.source = source
            if success:
                existing.success_count += 1
            else:
                existing.failure_count += 1
            if job_id is not None:
                if getattr(existing, "first_job_id", None) is None:
                    existing.first_job_id = job_id
                existing.last_job_id = job_id
        else:
            new_answer = FieldAnswerModel(
                field_label=field_label,
                normalized_label=normalized_label,
                value=value,
                ats_type=ats_type,
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                source=source,
                first_job_id=job_id,
                last_job_id=job_id,
            )
            self.session.add(new_answer)

        self.session.commit()

    def get_by_normalized_label(self, normalized_label: str, ats_type: ATSType) -> Optional[FieldAnswerModel]:
        """Get best known answer for a normalized label on specific ATS."""
        return (
            self.session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.normalized_label == normalized_label,
                FieldAnswerModel.ats_type == ats_type,
            )
            .order_by(FieldAnswerModel.success_count.desc())
            .first()
        )

    def get_universal(self, normalized_label: str) -> Optional[FieldAnswerModel]:
        """Get universal answer across all ATS types."""
        return (
            self.session.query(FieldAnswerModel)
            .filter(FieldAnswerModel.normalized_label == normalized_label)
            .order_by(FieldAnswerModel.success_count.desc())
            .first()
        )


class InteractionLogRepository:
    """Repository for interaction event tracking."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def log_interaction(
        self,
        ats_type: ATSType,
        action_type: str,
        field_label: str,
        selector: str,
        strategy_name: str,
        success: bool,
        page_url_pattern: str,
        job_id: Optional[int] = None,
    ) -> None:
        """Save interaction attempt (append-only — each row keeps its ``job_id``)."""
        log_entry = InteractionLogModel(
            ats_type=ats_type,
            action_type=action_type,
            field_label=field_label,
            selector=selector,
            strategy_name=strategy_name,
            success=success,
            page_url_pattern=page_url_pattern,
            job_id=job_id,
        )
        self.session.add(log_entry)
        self.session.commit()

    def get_best_strategy(self, ats_type: ATSType, action_type: str) -> Optional[str]:
        """Determine what Playwright strategy works best for an ATS/Action."""
        from sqlalchemy import func

        result = (
            self.session.query(
                InteractionLogModel.strategy_name,
                func.sum(func.cast(InteractionLogModel.success, Integer)).label("successes"),
            )
            .filter(
                InteractionLogModel.ats_type == ats_type,
                InteractionLogModel.action_type == action_type,
            )
            .group_by(InteractionLogModel.strategy_name)
            .order_by(func.sum(func.cast(InteractionLogModel.success, Integer)).desc())
            .first()
        )

        return result[0] if result else None


class DropdownStrategyRepository:
    """Repository for tracking dropdown interaction strategies."""

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def save_strategy(
        self,
        ats_type: ATSType,
        field_label: str,
        strategy_name: str,
        options_json: Optional[list[str]],
        success: bool = True,
        job_id: Optional[int] = None,
    ) -> None:
        """Save or update dropdown strategy, keyed to ``(ats_type, field_label)``
        so the *next* job on this ATS reuses the winning strategy.  Tracks
        ``first_job_id`` / ``last_job_id`` for audit only."""
        existing = (
            self.session.query(DropdownStrategyModel)
            .filter(
                DropdownStrategyModel.ats_type == ats_type,
                DropdownStrategyModel.field_label == field_label,
            )
            .first()
        )

        if existing:
            existing.strategy_name = strategy_name
            if options_json is not None:
                existing.options_json = options_json
            if success:
                existing.success_count += 1
            else:
                existing.failure_count += 1
            if job_id is not None:
                if getattr(existing, "first_job_id", None) is None:
                    existing.first_job_id = job_id
                existing.last_job_id = job_id
        else:
            new_strategy = DropdownStrategyModel(
                ats_type=ats_type,
                field_label=field_label,
                strategy_name=strategy_name,
                options_json=options_json,
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                first_job_id=job_id,
                last_job_id=job_id,
            )
            self.session.add(new_strategy)

        self.session.commit()

    def get_best_strategy(self, ats_type: ATSType, field_label: str) -> Optional[DropdownStrategyModel]:
        """Get best known dropdown strategy for this field."""
        return (
            self.session.query(DropdownStrategyModel)
            .filter(
                DropdownStrategyModel.ats_type == ats_type,
                DropdownStrategyModel.field_label == field_label,
            )
            .order_by(DropdownStrategyModel.success_count.desc())
            .first()
        )
