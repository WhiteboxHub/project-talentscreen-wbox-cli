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
    SelectorType,
)
from jobcli.core.url_normalize import normalize_job_url
from jobcli.core.constants import DASHBOARD_SUMMARY_DAYS, REFERENCE_LINKS_COUNT, SUPPORTED_DOMAINS
from jobcli.storage.models import (
    ApplicationLogModel,
    ConfigModel,
    DropdownStrategyModel,
    FieldAnswerModel,
    InteractionLogModel,
    JobModel,
    LearnedLocatorModel,
    SyncMetadataModel,
    UserDataModel,
)
from jobcli.sync.constants import CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT

# Source values considered "high trust" — they cannot be silently overwritten
# by low-trust (LLM / auto-learned) sources.
_HIGH_TRUST_SOURCES: frozenset[str] = frozenset({"human", "user"})


def _compute_confidence(success_count: int, failure_count: int) -> float:
    """Return Bayesian-style confidence ratio, clamped to [0.0, 1.0]."""
    total = success_count + failure_count
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, success_count / total))


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
            .order_by(JobModel.created_at.asc())
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

    def list_recent_activity(self, since: Optional[datetime] = None) -> list[Job]:
        """List all jobs with status changes since a given datetime."""
        query = self.session.query(JobModel).filter(
            JobModel.status.in_(
                [ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED]
            )
        )
        if since:
            query = query.filter(JobModel.updated_at > since)
        
    def deduplicate_jobs(self) -> int:
        """Find and erase duplicate jobs by normalized URL.
        
        Returns the number of duplicates removed.
        """
        all_jobs = self.session.query(JobModel).all()
        seen_urls = {} # canonical_url -> job_model
        to_delete = []
        
        # Priority mapping for statuses (higher number = more important to keep)
        status_priority = {
            ApplicationStatus.OFFER: 10,
            ApplicationStatus.INTERVIEW: 9,
            ApplicationStatus.SUBMITTED: 8,
            ApplicationStatus.IN_PROGRESS: 7,
            ApplicationStatus.REQUIRES_HUMAN: 6,
            ApplicationStatus.EVALUATING: 5,
            ApplicationStatus.PENDING: 4,
            ApplicationStatus.FAILED: 3,
            ApplicationStatus.SKIPPED: 2,
            ApplicationStatus.REJECTED: 1
        }

        for job in all_jobs:
            # Auto-tag existing jobs as 'wbox' if source is missing
            if not getattr(job, "scan_source", True): # handle missing column gracefully
                try:
                    job.scan_source = "wbox"
                except:
                    pass

            canonical = normalize_job_url(job.url)
            
            if canonical in seen_urls:
                existing = seen_urls[canonical]
                
                # Compare priorities to decide which to keep
                existing_prio = status_priority.get(existing.status, 0)
                current_prio = status_priority.get(job.status, 0)
                
                if current_prio > existing_prio:
                    # Keep current, delete existing
                    to_delete.append(existing)
                    seen_urls[canonical] = job
                else:
                    # Keep existing, delete current
                    to_delete.append(job)
            else:
                seen_urls[canonical] = job

        deleted_count = 0
        for job in to_delete:
            # Re-link logs if any to the kept job
            winner = seen_urls[normalize_job_url(job.url)]
            if winner.id != job.id:
                self.session.query(ApplicationLogModel).filter(ApplicationLogModel.job_id == job.id).update(
                    {"job_id": winner.id}
                )
                self.session.delete(job)
                deleted_count += 1
        
        # Flush deletions first to free up URLs for the UNIQUE constraint
        if deleted_count > 0:
            self.session.flush()
        
        # After deleting duplicates, normalize the URLs of the remaining "winners"
        for canonical, winner in seen_urls.items():
            if winner.url != canonical:
                winner.url = canonical
        
        if deleted_count > 0 or any(w.url != c for c, w in seen_urls.items()):
            self.session.commit()
        
        return deleted_count

    def get_dashboard_stats(self, days: int = 7) -> dict:
        """Calculate dashboard statistics for the last N days."""
        from datetime import datetime, timedelta
        since = datetime.now() - timedelta(days=days)
        
        # 1. Total jobs in WBL for last 7 days
        # We assume scan_source='wbox' for Whitebox Learning jobs
        total_wbl = self.session.query(JobModel).filter(
            JobModel.created_at >= since
        ).count()
        
        # 2. Already applied for you
        applied_statuses = [
            ApplicationStatus.SUBMITTED, 
            ApplicationStatus.INTERVIEW, 
            ApplicationStatus.OFFER,
            ApplicationStatus.IN_PROGRESS
        ]
        applied_count = self.session.query(JobModel).filter(
            JobModel.status.in_(applied_statuses)
        ).count()
        
        # 3. Remaining total jobs (PENDING)
        remaining_count = self.session.query(JobModel).filter(
            JobModel.status == ApplicationStatus.PENDING
        ).count()
        
        # 4. CLI friendly (PENDING + supported domains)
        SUPPORTED_DOMAINS = [
            "lever.co", "greenhouse.io", "ashbyhq.com", "breezy.hr", "workable.com",
            "recruitee.com", "pinpointhq.com", "rippling-ats.com", "rippling.com", "smartrecruiters.com",
            "jobvite.com", "applytojob.com", "linkedin.com"
        ]
        cli_friendly = 0
        pending_jobs = self.session.query(JobModel).filter(
            JobModel.status == ApplicationStatus.PENDING
        ).all()
        
        for job in pending_jobs:
            if any(domain in job.url.lower() for domain in SUPPORTED_DOMAINS):
                # Extra check to exclude workday logins which are NOT CLI friendly yet
                if "myworkdayjobs.com" not in job.url.lower():
                    cli_friendly += 1
        
        # 5. Latest 100 job links for reference
        latest_jobs = (
            self.session.query(JobModel)
            .order_by(JobModel.created_at.desc())
            .limit(100)
            .all()
        )
        
        latest_links = [
            {"title": j.title, "url": j.url, "created_at": j.created_at} 
            for j in latest_jobs
        ]
        
        return {
            "total_wbl": total_wbl,
            "applied_count": applied_count,
            "remaining_count": remaining_count,
            "cli_friendly": cli_friendly,
            "latest_links": latest_links
        }

    def deduplicate_jobs(self) -> int:
        """Find and erase duplicate jobs by normalized URL.
        
        Returns the number of duplicates removed.
        """
        all_jobs = self.session.query(JobModel).all()
        seen_urls = {} # canonical_url -> job_model
        to_delete = []
        
        # Priority mapping for statuses (higher number = more important to keep)
        status_priority = {
            ApplicationStatus.OFFER: 10,
            ApplicationStatus.INTERVIEW: 9,
            ApplicationStatus.SUBMITTED: 8,
            ApplicationStatus.IN_PROGRESS: 7,
            ApplicationStatus.REQUIRES_HUMAN: 6,
            ApplicationStatus.EVALUATING: 5,
            ApplicationStatus.PENDING: 4,
            ApplicationStatus.FAILED: 3,
            ApplicationStatus.SKIPPED: 2,
            ApplicationStatus.REJECTED: 1
        }

        for job in all_jobs:
            # Auto-tag existing jobs as 'wbox' if source is missing
            if not job.scan_source:
                job.scan_source = "wbox"

            canonical = normalize_job_url(job.url)
            
            if canonical in seen_urls:
                existing = seen_urls[canonical]
                
                # Compare priorities to decide which to keep
                existing_prio = status_priority.get(existing.status, 0)
                current_prio = status_priority.get(job.status, 0)
                
                if current_prio > existing_prio:
                    # Keep current, delete existing
                    to_delete.append(existing)
                    seen_urls[canonical] = job
                else:
                    # Keep existing, delete current
                    to_delete.append(job)
            else:
                seen_urls[canonical] = job

        deleted_count = 0
        for job in to_delete:
            # Re-link logs if any to the kept job
            winner = seen_urls[normalize_job_url(job.url)]
            if winner.id != job.id:
                self.session.query(ApplicationLogModel).filter(ApplicationLogModel.job_id == job.id).update(
                    {"job_id": winner.id}
                )
                self.session.delete(job)
                deleted_count += 1
        
        # Flush deletions first to free up URLs for the UNIQUE constraint
        if deleted_count > 0:
            self.session.flush()
        
        # After deleting duplicates, normalize the URLs of the remaining "winners"
        for canonical, winner in seen_urls.items():
            if winner.url != canonical:
                winner.url = canonical
        
        if deleted_count > 0 or any(w.url != c for c, w in seen_urls.items()):
            self.session.commit()
        
        return deleted_count

    def get_dashboard_stats(self, days: int = DASHBOARD_SUMMARY_DAYS) -> dict:
        """Calculate dashboard statistics for the last N days."""
        from datetime import datetime, timedelta
        since = datetime.now() - timedelta(days=days)
        
        # 1. Total jobs in WBL for last 7 days
        # We assume scan_source='wbox' for Whitebox Learning jobs
        total_wbl = self.session.query(JobModel).filter(
            JobModel.created_at >= since,
            JobModel.scan_source == "wbox"
        ).count()
        
        # 2. Already applied for you
        applied_statuses = [
            ApplicationStatus.SUBMITTED, 
            ApplicationStatus.INTERVIEW, 
            ApplicationStatus.OFFER,
            ApplicationStatus.IN_PROGRESS
        ]
        applied_count = self.session.query(JobModel).filter(
            JobModel.status.in_(applied_statuses)
        ).count()
        
        # 3. Remaining total jobs (PENDING)
        remaining_count = self.session.query(JobModel).filter(
            JobModel.status == ApplicationStatus.PENDING
        ).count()
        
        # 4. CLI friendly (PENDING + supported domains)
        cli_friendly = 0
        pending_jobs = self.session.query(JobModel).filter(
            JobModel.status == ApplicationStatus.PENDING
        ).all()
        
        for job in pending_jobs:
            if any(domain in job.url.lower() for domain in SUPPORTED_DOMAINS):
                # Extra check to exclude workday logins which are NOT CLI friendly yet
                if "myworkdayjobs.com" not in job.url.lower():
                    cli_friendly += 1
        
        # 5. Latest 100 job links for reference
        latest_jobs = (
            self.session.query(JobModel)
            .order_by(JobModel.created_at.desc())
            .limit(REFERENCE_LINKS_COUNT)
            .all()
        )
        
        latest_links = [
            {"title": j.title, "url": j.url, "created_at": j.created_at} 
            for j in latest_jobs
        ]
        
        return {
            "total_wbl": total_wbl,
            "applied_count": applied_count,
            "remaining_count": remaining_count,
            "cli_friendly": cli_friendly,
            "latest_links": latest_links
        }


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
        selector_type: Any,
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

        Only returns records that meet the confidence threshold AND the minimum
        success count — preventing low-data or unlucky rows from being used.

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
                # Confidence gate — only return records above threshold with enough evidence
                .filter(LearnedLocatorModel.confidence_score >= CONFIDENCE_THRESHOLD)
                .filter(LearnedLocatorModel.success_count >= MIN_SUCCESS_COUNT)
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
            val = config.value
            # Migration/Robustness: Fix interaction_mode if it was saved as a stringified Enum object
            if config.key == "interaction_mode" and val and "." in val:
                val = val.split(".")[-1].lower()
            
            # Handle boolean strings stored by old save_config(str(value))
            if val == "True": val = True
            if val == "False": val = False
            
            config_dict[config.key] = val

        return Config(**config_dict)

    def save_config(self, config: Config) -> None:
        """Save entire config object."""
        # Use mode='json' so Enums become their string values
        config_dict = config.model_dump(mode='json')
        for key, value in config_dict.items():
            if value is not None:
                self.set(key, str(value))


class FieldAnswerRepository:
    """Repository for managing field-level answer memory.

    Confidence system
    -----------------
    Every row stores a ``confidence`` float = success_count / (success_count +
    failure_count).  Retrieval methods apply two gates from ``sync.constants``:

    * ``confidence >= CONFIDENCE_THRESHOLD``  (default 0.6)
    * ``success_count >= MIN_SUCCESS_COUNT``   (default 3)

    A record that does not meet both gates is still stored (learning keeps
    happening) but is treated as "not yet trustworthy" — the caller falls
    through to the LLM instead.

    Merge protection
    ----------------
    High-trust sources ("human", "user") can never be silently overwritten
    by low-trust sources ("auto", "local").  The value is only replaced when
    the incoming source is of equal or higher trust.
    """

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
        """Save or update an answer with confidence tracking and merge protection.

        The answer is stored keyed by ``(normalized_label, ats_type)`` so the
        *next* job on the same ATS can reuse it automatically.

        Merge-protection rules
        ~~~~~~~~~~~~~~~~~~~~~~
        1. If a high-trust row exists and the incoming source is low-trust,
           the *value* is kept as-is; only success/failure counts are updated.
        2. Confidence is recomputed on every write.
        3. ``first_job_id`` is stamped once; ``last_job_id`` is always updated.
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
            # ── Merge protection ──────────────────────────────────────────
            # Only overwrite the stored value when the incoming source is at
            # least as trusted as the existing one.
            existing_is_high_trust = existing.source in _HIGH_TRUST_SOURCES
            incoming_is_high_trust = source in _HIGH_TRUST_SOURCES
            if not existing_is_high_trust or incoming_is_high_trust:
                # Safe to update the value
                existing.value = value
                existing.source = source

            # Always update counts and recompute confidence
            if success:
                existing.success_count += 1
            else:
                existing.failure_count += 1
            existing.confidence = _compute_confidence(
                existing.success_count, existing.failure_count
            )
            existing.updated_at = datetime.now()

            if job_id is not None:
                if getattr(existing, "first_job_id", None) is None:
                    existing.first_job_id = job_id
                existing.last_job_id = job_id
        else:
            # ── Seed counts for new rows ──────────────────────────────────
            # High-trust sources (human / user) are treated as immediately
            # reliable: seed at MIN_SUCCESS_COUNT so the row passes the
            # confidence gate on the very first run.  Low-trust sources
            # (LLM / auto) still start at 1 and must accumulate evidence.
            if source in _HIGH_TRUST_SOURCES and success:
                initial_success = MIN_SUCCESS_COUNT
            else:
                initial_success = 1 if success else 0
            initial_failure = 0 if success else 1
            new_answer = FieldAnswerModel(
                field_label=field_label,
                normalized_label=normalized_label,
                value=value,
                ats_type=ats_type,
                success_count=initial_success,
                failure_count=initial_failure,
                confidence=_compute_confidence(initial_success, initial_failure),
                source=source,
                first_job_id=job_id,
                last_job_id=job_id,
            )
            self.session.add(new_answer)

        self.session.commit()

    @classmethod
    def repair_confidence_column(cls, session: Session) -> int:
        """Backfill confidence=0.0 rows that have a non-zero success_count.

        These rows were created before the ``confidence`` column existed (the
        SQLite migration adds it with DEFAULT 0.0).  Since ``save_answer`` dedupes
        on ``(normalized_label, ats_type)`` before re-inserting, these rows are
        never re-written and their confidence stays stuck at 0.0 forever.

        Returns the number of rows fixed.
        """
        rows = (
            session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.confidence == 0.0,
                FieldAnswerModel.success_count > 0,
            )
            .all()
        )
        fixed = 0
        for row in rows:
            new_conf = _compute_confidence(row.success_count or 0, row.failure_count or 0)
            if new_conf != row.confidence:
                row.confidence = new_conf
                row.updated_at = datetime.now()
                fixed += 1
        if fixed:
            session.commit()
        return fixed

    def record_outcome(
        self,
        normalized_label: str,
        ats_type: ATSType,
        success: bool,
    ) -> None:
        """Increment success/failure and recompute confidence without changing the value.

        Called after an answer retrieved from memory is actually executed in the
        browser so the record reflects real-world effectiveness, not just the
        source that wrote it.
        """
        existing = (
            self.session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.normalized_label == normalized_label,
                FieldAnswerModel.ats_type == ats_type,
            )
            .first()
        )
        if not existing:
            return
        if success:
            existing.success_count += 1
        else:
            existing.failure_count += 1
        existing.confidence = _compute_confidence(
            existing.success_count, existing.failure_count
        )
        existing.updated_at = datetime.now()
        self.session.commit()

    def get_by_normalized_label(
        self, normalized_label: str, ats_type: ATSType
    ) -> Optional[FieldAnswerModel]:
        """Get best known answer for a normalized label on specific ATS.

        Returns ``None`` if no record meets the confidence gate — the caller
        should fall through to the LLM in that case.
        """
        return (
            self.session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.normalized_label == normalized_label,
                FieldAnswerModel.ats_type == ats_type,
                FieldAnswerModel.confidence >= CONFIDENCE_THRESHOLD,
                FieldAnswerModel.success_count >= MIN_SUCCESS_COUNT,
            )
            .order_by(FieldAnswerModel.confidence.desc(), FieldAnswerModel.success_count.desc())
            .first()
        )

    def get_raw_by_label(
        self, normalized_label: str, ats_type: ATSType
    ) -> Optional[FieldAnswerModel]:
        """Get any existing record without the confidence gate.

        Used by AgentMemory for deduplication checks — we need to know if the
        value *exists* in the DB even when it hasn't yet earned enough trust to
        be returned by ``get_by_normalized_label``.
        """
        return (
            self.session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.normalized_label == normalized_label,
                FieldAnswerModel.ats_type == ats_type,
            )
            .first()
        )

    def get_universal(self, normalized_label: str) -> Optional[FieldAnswerModel]:
        """Get universal answer across all ATS types.

        Returns ``None`` if no record meets the confidence gate.
        """
        return (
            self.session.query(FieldAnswerModel)
            .filter(
                FieldAnswerModel.normalized_label == normalized_label,
                FieldAnswerModel.confidence >= CONFIDENCE_THRESHOLD,
                FieldAnswerModel.success_count >= MIN_SUCCESS_COUNT,
            )
            .order_by(FieldAnswerModel.confidence.desc(), FieldAnswerModel.success_count.desc())
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


class SyncMetadataRepository:
    """Repository for tracking local sync state.

    Only one row (id=1) ever exists.  All methods are idempotent.

    Phase 2 will add a ``push_to_server()`` method that reads the rows
    produced by ``jobcli.sync.extractor`` and POSTs them; the schema here
    will not change.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository."""
        self.session = session

    def get_or_create(self) -> SyncMetadataModel:
        """Return the singleton sync-metadata row, creating it if absent."""
        row = self.session.query(SyncMetadataModel).filter(SyncMetadataModel.id == 1).first()
        if not row:
            row = SyncMetadataModel(id=1, apps_since_sync=0, downloaded_count=0, last_version="0.0.0")
            self.session.add(row)
            self.session.commit()
            self.session.refresh(row)
        return row

    def increment_apps_since_sync(self) -> None:
        """Increment the counter of applications completed since the last sync."""
        row = self.get_or_create()
        row.apps_since_sync = (row.apps_since_sync or 0) + 1
        row.updated_at = datetime.now()
        self.session.commit()

    def record_sync(self, version: str = "0.0.0", downloaded_count: int = 0) -> None:
        """Record that a sync has just completed (called by Phase 2 sync client)."""
        row = self.get_or_create()
        row.last_sync_at = datetime.now()
        row.last_version = version
        row.downloaded_count = int(downloaded_count)  # type: ignore
        row.apps_since_sync = 0
        row.updated_at = datetime.now()
        self.session.commit()

    def get_apps_since_sync(self) -> int:
        """Return the number of applications completed since the last sync."""
        row = self.get_or_create()
        return row.apps_since_sync or 0
