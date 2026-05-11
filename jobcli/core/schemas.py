"""Core Pydantic schemas for JobCLI."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class ATSType(str, Enum):
    """Supported ATS systems."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ICIMS = "icims"
    TALEO = "taleo"
    SAP_SUCCESSFACTORS = "sap_successfactors"
    SMARTRECRUITERS = "smartrecruiters"
    JOBVITE = "jobvite"
    ASHBY = "ashby"
    BREEZY_HR = "breezy_hr"
    RECRUITEE = "recruitee"
    JAZZ_HR = "jazz_hr"
    BAMBOO_HR = "bamboo_hr"
    WORKABLE = "workable"
    ADP_RECRUITING = "adp_recruiting"
    PAYLOCITY = "paylocity"
    UKG_PRO = "ukg_pro"
    CORNERSTONE = "cornerstone"
    AVATURE = "avature"
    PHENOM_PEOPLE = "phenom_people"
    RIPPLING = "rippling"
    UNKNOWN = "unknown"


class ApplicationStatus(str, Enum):
    """Application lifecycle status."""

    PENDING = "pending"
    EVALUATING = "evaluating"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    REQUIRES_HUMAN = "requires_human"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    OFFER = "offer"


class ExecutionPhase(str, Enum):
    """Execution phase."""

    RULES = "rules"
    LLM = "llm"
    HUMAN = "human"


class InteractionMode(str, Enum):
    """Controls how tightly the human is integrated into the agent loop.

    AUTO      – fully autonomous; only pauses for CAPTCHA or fatal errors.
    SUPERVISED – (default, Claude-Code-style) runs autonomously but pauses
                 for submission confirmation, missing mandatory fields, and
                 low-confidence actions.
    MANUAL    – pauses before every major browser action for approval.
    """

    AUTO = "auto"
    SUPERVISED = "supervised"
    MANUAL = "manual"


class SelectorType(str, Enum):
    """Selector types for browser automation."""

    CSS = "css"
    XPATH = "xpath"
    TEXT = "text"
    ROLE = "role"
    ARIA_LABEL = "aria_label"


class ActionType(str, Enum):
    """Browser action types."""

    CLICK = "click"
    FILL = "fill"
    TYPE = "type"
    SELECT = "select"
    UPLOAD = "upload"
    SCROLL = "scroll"
    WAIT = "wait"
    NAVIGATE = "navigate"
    ASK = "ask"


class PersonalInfo(BaseModel):
    """Personal information."""

    first_name: str
    last_name: str
    email: str
    phone: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zip_code: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    website: Optional[str] = None


class Education(BaseModel):
    """Education entry."""

    school: str
    degree: str
    field_of_study: str
    graduation_year: int
    gpa: Optional[float] = None


class Experience(BaseModel):
    """Work experience entry."""

    company: str
    title: str
    start_date: str
    end_date: Optional[str] = None
    current: bool = False
    description: Optional[str] = None


class WorkAuthorization(BaseModel):
    """Work authorization information."""

    authorized_to_work: bool = True
    require_sponsorship: bool = False
    visa_status: Optional[str] = None


class Demographics(BaseModel):
    """Demographic information (optional)."""

    gender: Optional[str] = None
    pronouns: Optional[str] = None
    sexual_orientation: Optional[str] = None
    race: Optional[str] = None
    veteran_status: Optional[str] = None
    disability_status: Optional[str] = None


class ResumeData(BaseModel):
    """Complete resume data structure.

    Accepts either the internal schema format or the JSON Resume standard
    (https://jsonresume.org/) with top-level keys: basics, work, education, skills.
    """

    personal: PersonalInfo
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    work_authorization: WorkAuthorization = Field(default_factory=WorkAuthorization)
    demographics: Optional[Demographics] = None
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_resume_format(cls, data: Any) -> Any:  # noqa: ANN401
        """Transparently convert JSON Resume standard format to internal schema."""
        if not isinstance(data, dict):
            return data

        # Only transform if this looks like JSON Resume (has 'basics' but not 'personal')
        if "basics" not in data or "personal" in data:
            return data

        transformed: dict[str, Any] = {}

        # --- personal / basics ---
        basics = data.get("basics", {})
        name_parts = (basics.get("name") or "").split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        location = basics.get("location") or {}
        linkedin_url: Optional[str] = None
        github_url: Optional[str] = None
        for profile in basics.get("profiles", []):
            network = (profile.get("network") or "").lower()
            url = profile.get("url") or profile.get("username") or ""
            if not url.startswith("http"):
                url = "https://" + url
            if "linkedin" in network:
                linkedin_url = url
            elif "github" in network:
                github_url = url

        transformed["personal"] = {
            "first_name": first_name,
            "last_name": last_name,
            "email": basics.get("email", ""),
            "phone": basics.get("phone", ""),
            "city": location.get("city"),
            "state": location.get("region"),
            "country": location.get("countryCode"),
            "zip_code": location.get("postalCode"),
            "linkedin": linkedin_url,
            "github": github_url,
            "website": basics.get("url") or basics.get("website"),
        }

        # --- education ---
        edu_list = []
        for edu in data.get("education", []):
            end_raw = edu.get("endDate") or ""
            grad_year: Optional[int] = None
            if end_raw:
                try:
                    grad_year = int(str(end_raw).split("-")[0])
                except (ValueError, IndexError):
                    pass
            edu_list.append({
                "school": edu.get("institution", ""),
                "degree": edu.get("studyType", ""),
                "field_of_study": edu.get("area", ""),
                "graduation_year": grad_year or 0,
                "gpa": edu.get("gpa"),
            })
        transformed["education"] = edu_list

        # --- experience (JSON Resume uses 'work') ---
        exp_list = []
        for job in data.get("work", []):
            highlights = job.get("highlights") or []
            description = "\n".join(highlights) if highlights else job.get("summary", "")
            exp_list.append({
                "company": job.get("name") or job.get("company", ""),
                "title": job.get("position", ""),
                "start_date": job.get("startDate", ""),
                "end_date": job.get("endDate"),
                "current": (job.get("endDate") or "").lower() in ("present", "current", ""),
                "description": description,
            })
        transformed["experience"] = exp_list

        # --- skills: flatten [{name, keywords:[...]}, ...] → [str, ...] ---
        flat_skills: list[str] = []
        for skill_entry in data.get("skills", []):
            if isinstance(skill_entry, str):
                flat_skills.append(skill_entry)
            elif isinstance(skill_entry, dict):
                for kw in skill_entry.get("keywords", []):
                    if kw and isinstance(kw, str):
                        flat_skills.append(kw)
                # Also include the category name itself if no keywords
                if not skill_entry.get("keywords") and skill_entry.get("name"):
                    flat_skills.append(skill_entry["name"])
        transformed["skills"] = flat_skills

        # --- pass-through remaining keys ---
        for key in ("work_authorization", "demographics", "certifications"):
            if key in data:
                transformed[key] = data[key]

        return transformed


class CommonQuestions(BaseModel):
    """Common job application questions."""

    salary_expectations: Optional[str] = None
    notice_period: Optional[str] = None
    willing_to_relocate: Optional[bool] = None
    remote_preference: Optional[str] = None
    start_date: Optional[str] = None
    referral: Optional[str] = None
    cover_letter: Optional[str] = None
    additional_info: Optional[str] = None


class EvaluationReport(BaseModel):
    """A-F scoring evaluation of a job posting."""
    job_url: str
    match_score: str  # A, B, C, D, F
    north_star_alignment: str
    compensation_check: str
    culture_fit: str
    red_flags: list[str]
    summary: str


class Job(BaseModel):
    """Job posting information."""

    id: Optional[int] = None
    url: str
    resolved_url: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    ats_type: ATSType = ATSType.UNKNOWN
    status: ApplicationStatus = ApplicationStatus.PENDING
    score: Optional[float] = None
    scan_source: Optional[str] = None
    evaluation_report_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class BrowserAction(BaseModel):
    """Browser action with structured data."""

    action: ActionType
    selector: str
    selector_type: Optional[SelectorType] = None
    value: Optional[str] = None
    field_label: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    timeout: int = Field(default=5000, description="Timeout in milliseconds")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class LLMActionResponse(BaseModel):
    """LLM response with structured actions."""

    actions: list[BrowserAction]
    reasoning: Optional[str] = None
    detected_ats: Optional[ATSType] = None
    detected_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    requires_human: bool = False


class LocatorResult(BaseModel):
    """Result from locator attempt."""

    success: bool
    selector: Optional[str] = None
    selector_type: Optional[SelectorType] = None
    locator_name: Optional[str] = None
    error: Optional[str] = None
    phase: ExecutionPhase


class ApplicationState(BaseModel):
    """Current application state."""

    job_id: int
    current_url: str
    previous_url: Optional[str] = None
    step_count: int = 0
    attempts: int = 0
    detected_ats: ATSType = ATSType.UNKNOWN
    current_phase: ExecutionPhase = ExecutionPhase.RULES
    status: ApplicationStatus = ApplicationStatus.IN_PROGRESS
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class DOMSnapshot(BaseModel):
    """Structured DOM snapshot for LLM."""

    url: str
    title: str
    interactive_elements: list[dict[str, Any]]
    forms: list[dict[str, Any]]
    buttons: list[dict[str, Any]]
    inputs: list[dict[str, Any]]
    links: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogEntry(BaseModel):
    """Structured log entry."""

    timestamp: datetime = Field(default_factory=datetime.now)
    level: Literal["debug", "info", "warning", "error", "critical"]
    message: str
    job_id: Optional[int] = None
    phase: Optional[ExecutionPhase] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Config(BaseModel):
    """Application configuration."""

    # Job board credentials
    job_board_username: Optional[str] = None
    job_board_password: Optional[str] = None

    # LLM API keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None

    # Preferences
    default_llm_provider: Literal["openai", "anthropic", "gemini", "claude"] = "openai"
    interaction_mode: InteractionMode = InteractionMode.SUPERVISED
    headless: bool = True
    max_retries: int = 3
    screenshot_on_error: bool = True
    screenshot_on_success: bool = False
    random_delay_min: float = 1.0
    random_delay_max: float = 3.0
    user_agent: Optional[str] = None

    # Paths
    resume_pdf_path: Optional[str] = None
    resume_json_path: Optional[str] = None
    extension_path: Optional[str] = None
    log_directory: str = Field(default="~/.jobcli/logs")
    database_path: str = Field(default="~/.jobcli/jobcli.db")

    # Derived profile: infer country from US city/state when country blank
    infer_location_country: bool = True
