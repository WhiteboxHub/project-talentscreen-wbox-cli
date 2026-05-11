"""Core Pydantic schemas for JobCLI."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


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

    first_name: Optional[str] = Field(
        None, validation_alias=AliasChoices("first_name", "first_name", "given_name", "forename", "nombre", "first", "fname")
    )
    last_name: Optional[str] = Field(
        None, validation_alias=AliasChoices("last_name", "last_name", "surname", "family_name", "apellido", "last", "lname")
    )
    email: Optional[str] = Field(
        None, validation_alias=AliasChoices("email", "e_mail", "correo", "email_address", "Email ID", "email_id")
    )
    phone: Optional[str] = Field(
        None, validation_alias=AliasChoices("phone", "mobile", "cell", "telephone", "contact_number", "phone_number", "mobile_number", "contact_number")
    )
    address: Optional[str] = Field(
        None, validation_alias=AliasChoices("address", "street_address", "mailing_address")
    )
    city: Optional[str] = Field(None, validation_alias=AliasChoices("city"))
    state: Optional[str] = Field(None, validation_alias=AliasChoices("state", "province", "region"))
    country: Optional[str] = Field(None, validation_alias=AliasChoices("country", "countryCode"))
    zip_code: Optional[str] = Field(
        None, validation_alias=AliasChoices("zip_code", "zip", "postal", "zip code", "postal code", "postalCode")
    )
    linkedin: Optional[str] = Field(
        None, validation_alias=AliasChoices("linkedin", "linkedin url", "linkedin profile", "linkedin_url")
    )
    github: Optional[str] = Field(
        None, validation_alias=AliasChoices("github", "github url", "github profile")
    )
    portfolio: Optional[str] = Field(
        None, validation_alias=AliasChoices("portfolio", "website", "personal website", "personal site")
    )
    website: Optional[str] = Field(None, validation_alias=AliasChoices("website", "url"))


class Education(BaseModel):
    """Education history entry."""

    school: Optional[str] = Field(
        None, validation_alias=AliasChoices("school", "university", "college", "institution", "school_name", "university_name")
    )
    degree: Optional[str] = Field(
        None, validation_alias=AliasChoices("degree", "degree_type", "level_of_education", "education_level", "highest_degree", "studyType")
    )
    field_of_study: Optional[str] = Field(
        None, validation_alias=AliasChoices("field_of_study", "field_of_study", "major", "discipline", "area_of_study", "concentration", "area")
    )
    graduation_year: Optional[int] = Field(
        None, validation_alias=AliasChoices("graduation_year", "graduation", "grad_year", "year_of_graduation", "expected_graduation", "graduation_date")
    )
    gpa: Optional[float] = Field(
        None, validation_alias=AliasChoices("gpa", "grade point", "cumulative gpa", "score")
    )


class Experience(BaseModel):
    """Work experience entry."""

    company: Optional[str] = Field(
        None, validation_alias=AliasChoices("company", "employer", "organization", "company_name", "employer_name", "name_of_employer", "organization_name", "name")
    )
    title: Optional[str] = Field(
        None, validation_alias=AliasChoices("title", "job_title", "role", "position", "position_title", "job_role", "your_title", "position/role")
    )
    start_date: Optional[str] = Field(
        None, validation_alias=AliasChoices("start_date", "startDate", "from", "start", "date started")
    )
    end_date: Optional[str] = Field(
        None, validation_alias=AliasChoices("end_date", "endDate", "to", "end", "date ended")
    )
    current: bool = False
    description: Optional[str] = Field(
        None, validation_alias=AliasChoices("description", "job_description", "responsibilities", "duties", "summary", "roles_and_responsibilities", "role_description", "work_performed")
    )


class WorkAuthorization(BaseModel):
    """Work authorization information."""

    authorized_to_work: Optional[bool] = True
    require_sponsorship: Optional[bool] = False
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
    """Complete resume data structure."""

    personal: PersonalInfo = Field(..., validation_alias=AliasChoices("personal", "basics", "contact_info"))
    education: list[Education] = Field(
        default_factory=list, validation_alias=AliasChoices("education", "academics", "schooling")
    )
    experience: list[Experience] = Field(
        default_factory=list, validation_alias=AliasChoices("experience", "work", "work_experience", "employment", "history")
    )
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
    model_config = ConfigDict(from_attributes=True)

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
