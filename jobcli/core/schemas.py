"""Core Pydantic schemas for JobCLI."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


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
    UNKNOWN = "unknown"


class ApplicationStatus(str, Enum):
    """Application status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    REQUIRES_HUMAN = "requires_human"


class ExecutionPhase(str, Enum):
    """Execution phase."""

    RULES = "rules"
    LLM = "llm"
    HUMAN = "human"


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
    TYPE = "type"
    SELECT = "select"
    UPLOAD = "upload"
    SCROLL = "scroll"
    WAIT = "wait"
    NAVIGATE = "navigate"


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
    race: Optional[str] = None
    veteran_status: Optional[str] = None
    disability_status: Optional[str] = None


class ResumeData(BaseModel):
    """Complete resume data structure."""

    personal: PersonalInfo
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    work_authorization: WorkAuthorization = Field(default_factory=WorkAuthorization)
    demographics: Optional[Demographics] = None
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


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


class Job(BaseModel):
    """Job posting information."""

    id: Optional[int] = None
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    ats_type: ATSType = ATSType.UNKNOWN
    status: ApplicationStatus = ApplicationStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class BrowserAction(BaseModel):
    """Browser action with structured data."""

    action: ActionType
    selector: str
    selector_type: SelectorType
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

    # Preferences
    default_llm_provider: Literal["openai", "anthropic", "gemini"] = "openai"
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
    log_directory: str = Field(default="logs")
    database_path: str = Field(default="~/.jobcli/jobcli.db")
