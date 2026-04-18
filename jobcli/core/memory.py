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

    def __init__(
        self,
        database_session: Session,
        infer_location_country: bool = True,
    ) -> None:
        """Initialize memory with database session."""
        self.session = database_session
        self.field_answer_repo = FieldAnswerRepository(self.session)
        self.interaction_repo = InteractionLogRepository(self.session)
        self.dropdown_strategy_repo = DropdownStrategyRepository(self.session)
        self.synonym_resolver = SynonymResolver(
            infer_location_country=infer_location_country,
        )

    def save_field_answer(
        self, field_label: str, value: str, ats_type: ATSType, success: bool = True, source: str = "human"
    ) -> bool:
        """Save an answer provided for a field. Returns True if saved."""
        if not field_label or not value:
            return False

        normalized = self.synonym_resolver.resolve_field_label(field_label)
        if not normalized:
            # If we don't have a canonical name, use the lowercase version
            normalized = field_label.lower().strip()

        # Check if we already have this exact answer to avoid spamming logs
        best_val, _ = self.get_best_answer(field_label, ats_type)
        if best_val == str(value).strip():
            return False

        self.field_answer_repo.save_answer(
            field_label=field_label,
            normalized_label=normalized,
            value=value,
            ats_type=ats_type,
            success=success,
            source=source,
        )
        return True

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

        # Fetch successful answers, prioritized by manual 'human' source first
        # We group by field_label to avoid duplicates and keep context clean
        all_answers = (
            self.session.query(
                FieldAnswerModel.field_label, 
                FieldAnswerModel.value, 
                FieldAnswerModel.source,
                FieldAnswerModel.success_count
            )
            .filter(
                (FieldAnswerModel.ats_type == ats_type) | (FieldAnswerModel.ats_type == ATSType.UNKNOWN)
            )
            .order_by(FieldAnswerModel.source.desc(), FieldAnswerModel.success_count.desc()) # 'human' comes before 'auto'
            .all()
        )

        # Deduplicate and format
        unique_answers = {}
        for label, value, source, count in all_answers:
            if label not in unique_answers:
                unique_answers[label] = {"value": value, "source": source}

        context_lines = []
        if unique_answers:
            context_lines.append(f"### FULL Memory Context for {ats_type.value}:")
            for label, data in unique_answers.items():
                prefix = "[MANUAL ENTRY]" if data["source"] == "human" else "[AUTO-LEARNED]"
                context_lines.append(f"- {prefix} '{label}' -> '{data['value']}'")

        # Could add high-level strategy notes here (e.g., getting from get_best_strategy method)
        # e.g., "For custom dropdowns, click label first then select option."

        if not context_lines:
            return "No previous memory available for this ATS type."

        return "\n".join(context_lines)

    def build_resolved_fields_context(
        self, resume: ResumeData, ats_type: ATSType
    ) -> str:
        """Human-readable lines: canonical field → value (resume first, then DB memory)."""
        hints = [
            "First Name",
            "Last Name",
            "Email",
            "Phone",
            "City",
            "State",
            "Country",
            "Location",
            "Gender",
            "Pronouns",
            "Sexual orientation",
            "Race",
            "Ethnicity",
            "Veteran",
            "Disability",
            "authorized to work",
            "sponsorship",
            "visa",
        ]
        lines: list[str] = [
            "## Resolved field values (priority: resume JSON → saved memory per ATS → universal memory):"
        ]
        any_line = False
        for hint in hints:
            val, src = self.get_best_answer(hint, ats_type, resume)
            if val:
                any_line = True
                lines.append(f"- **{hint}**: {val} _(source: {src})_")
        if not any_line:
            return "## Resolved field values: _(none yet — use User Information JSON in prompt)_"
        return "\n".join(lines)

    def combined_llm_memory_block(self, resume: ResumeData, ats_type: ATSType) -> str:
        """Full block for LLM prompts: structured resolutions + learned field answers."""
        resolved = self.build_resolved_fields_context(resume, ats_type)
        learned = self.build_llm_context(ats_type)
        return f"{resolved}\n\n{learned}"
