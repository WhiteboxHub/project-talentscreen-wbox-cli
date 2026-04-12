"""Schemas for locator storage and retrieval."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from jobcli.core.schemas import ATSType, SelectorType


class LearnedLocator(BaseModel):
    """A locator learned from human interaction."""

    id: Optional[int] = None
    ats_type: ATSType
    selector: str
    selector_type: SelectorType
    purpose: str = Field(description="e.g., 'apply_button', 'first_name_field'")
    success_count: int = 0
    failure_count: int = 0
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.5)
    domain_pattern: Optional[str] = Field(
        default=None, description="URL domain pattern, e.g., '*.greenhouse.io'"
    )
    url_pattern: Optional[str] = Field(
        default=None, description="URL pattern, e.g., '*/jobs/*/apply'"
    )
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="human", description="human or llm")

    def update_score(self, success: bool) -> None:
        """Update confidence score based on success/failure."""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        total = self.success_count + self.failure_count
        if total > 0:
            self.confidence_score = self.success_count / total
        self.updated_at = datetime.now()


class LocatorStrategy(BaseModel):
    """A locator strategy combining multiple locators."""

    name: str
    description: str
    locators: list[str] = Field(description="List of selector strings to try in order")
    selector_types: list[SelectorType]
    priority: int = Field(default=0, description="Higher priority strategies tried first")
    ats_specific: Optional[ATSType] = None


class FieldMapping(BaseModel):
    """Mapping between resume field and form field locators."""

    resume_field: str = Field(description="Field name in ResumeData")
    common_labels: list[str] = Field(
        description="Common label texts, e.g., ['First Name', 'Given Name']"
    )
    common_ids: list[str] = Field(description="Common input IDs")
    common_names: list[str] = Field(description="Common input names")
    field_type: str = Field(default="text", description="input, select, textarea, file")
