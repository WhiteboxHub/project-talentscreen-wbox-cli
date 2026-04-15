"""Memory system for JobCLI agent."""

from typing import Optional

from sqlalchemy.orm import Session

from jobcli.core.schemas import ATSType, ResumeData
from jobcli.core.synonym_resolver import SynonymResolver
from jobcli.storage.models import DropdownStrategyModel
from jobcli.storage.repositories import (
    DropdownStrategyRepository,
    FieldAnswerRepository,
    InteractionLogRepository,
)


class AgentMemory:
    """3-layer persistent memory for the agent (Framework, Field, Interaction)."""

    def __init__(self, database_session: Session) -> None:
        """Initialize memory with database session."""
        self.session = database_session
        self.field_answer_repo = FieldAnswerRepository(self.session)
        self.interaction_repo = InteractionLogRepository(self.session)
        self.dropdown_strategy_repo = DropdownStrategyRepository(self.session)
        self.synonym_resolver = SynonymResolver()

    def save_field_answer(
        self, field_label: str, value: str, ats_type: ATSType, success: bool = True, source: str = "human"
    ) -> None:
        """Save an answer provided for a field."""
        if not field_label or not value:
            return

        normalized = self.synonym_resolver.resolve_field_label(field_label)
        if not normalized:
            # If we don't have a canonical name, use the lowercase version
            normalized = field_label.lower().strip()

        self.field_answer_repo.save_answer(
            field_label=field_label,
            normalized_label=normalized,
            value=value,
            ats_type=ats_type,
            success=success,
            source=source,
        )

    def get_best_answer(
        self, field_label: str, ats_type: ATSType, resume: Optional[ResumeData] = None
    ) -> tuple[Optional[str], str]:
        """Get the best answer for a field following the priority chain.

        Priority 1: Resume JSON
        Priority 2: Saved memory for this ATS
        Priority 3: Universal saved memory
        Priority 4: Not found

        Returns:
            Tuple of (value, source_type)
        """
        if not field_label:
            return None, "not_found"

        normalized = self.synonym_resolver.resolve_field_label(field_label)
        if not normalized:
            normalized = field_label.lower().strip()

        # Priority 1: Resume JSON
        if resume and normalized:
            resume_val = self.synonym_resolver.get_resume_value(normalized, resume)
            if resume_val:
                return resume_val, "resume_json"

        # Priority 2: Saved memory for THIS ATS
        saved = self.field_answer_repo.get_by_normalized_label(normalized, ats_type)
        if saved and saved.success_count > saved.failure_count:
            return saved.value, "saved_memory"

        # Priority 3: Universal saved memory (cross-ATS)
        universal = self.field_answer_repo.get_universal(normalized)
        if universal and universal.success_count > universal.failure_count:
            return universal.value, "universal_memory"

        # Priority 4: Not found
        return None, "not_found"

    def save_dropdown_strategy(
        self,
        ats_type: ATSType,
        field_label: str,
        strategy_name: str,
        options_json: Optional[list[str]] = None,
        success: bool = True,
    ) -> None:
        """Save outcome of a dropdown strategy."""
        if not field_label or not strategy_name:
            return

        self.dropdown_strategy_repo.save_strategy(
            ats_type=ats_type,
            field_label=field_label,
            strategy_name=strategy_name,
            options_json=options_json,
            success=success,
        )

    def get_dropdown_strategy(
        self, ats_type: ATSType, field_label: str
    ) -> Optional[DropdownStrategyModel]:
        """Get best strategy for a specific dropdown."""
        if not field_label:
            return None
        return self.dropdown_strategy_repo.get_best_strategy(ats_type, field_label)

    def save_interaction(
        self,
        ats_type: ATSType,
        action_type: str,
        field_label: str,
        selector: str,
        strategy_name: str,
        success: bool,
        page_url: str,
    ) -> None:
        """Log Playwright action strategy result."""
        url_pattern = page_url.split("?")[0] if page_url else ""
        self.interaction_repo.log_interaction(
            ats_type=ats_type,
            action_type=action_type,
            field_label=field_label,
            selector=selector,
            strategy_name=strategy_name,
            success=success,
            page_url_pattern=url_pattern,
        )

    def build_llm_context(self, ats_type: ATSType) -> str:
        """Build a memory context block to inject into the LLM prompt.

        Returns a string detailing known answers and successful strategies.
        """
        # We fetch top answers over time to help the LLM.
        # This could be advanced to group by field_label.
        from sqlalchemy import func
        from jobcli.storage.models import FieldAnswerModel

        # Fetch top successful universal answers
        top_answers = (
            self.session.query(
                FieldAnswerModel.field_label, FieldAnswerModel.value, FieldAnswerModel.source
            )
            .filter(
                (FieldAnswerModel.ats_type == ats_type) | (FieldAnswerModel.ats_type == ATSType.UNKNOWN)
            )
            .order_by(FieldAnswerModel.success_count.desc())
            .limit(15)
            .all()
        )

        context_lines = []
        if top_answers:
            context_lines.append(f"### Known Answers (Priority applies to {ats_type.value}):")
            for label, value, source in top_answers:
                if source == "human":
                    context_lines.append(f"- '{label}' -> '{value}' (Learned from previous manual input)")
                else:
                    context_lines.append(f"- '{label}' -> '{value}' (Learned from previous successful run)")

        # Could add high-level strategy notes here (e.g., getting from get_best_strategy method)
        # e.g., "For custom dropdowns, click label first then select option."

        if not context_lines:
            return "No previous memory available for this ATS type."

        return "\n".join(context_lines)
