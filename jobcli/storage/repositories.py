"""Repository pattern for data access."""

import json
from typing import Any, Optional

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
from jobcli.storage.models import (
    ApplicationLogModel,
    ConfigModel,
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
        job_model = JobModel(
            url=job.url,
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
        """Get job by URL."""
        job_model = self.session.query(JobModel).filter(JobModel.url == url).first()
        if not job_model:
            return None

        return Job(
            id=job_model.id,
            url=job_model.url,
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
            user_data.updated_at = json.loads(resume.model_dump_json())
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
