"""Memory system for JobCLI agent."""

from typing import Optional

from sqlalchemy.orm import Session

from jobcli.core.schemas import ATSType, ResumeData, SelectorType
from jobcli.core.synonym_resolver import SynonymResolver
from jobcli.storage.models import DropdownStrategyModel
from jobcli.storage.repositories import (
    DropdownStrategyRepository,
    FieldAnswerRepository,
    InteractionLogRepository,
    SyncMetadataRepository,
)
from jobcli.sync.constants import CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT


class AgentMemory:
    """3-layer persistent memory for the agent (Framework, Field, Interaction).

    Decision gate
    -------------
    Memory is only consulted (and its answer used *instead of* the LLM) when
    the stored record satisfies **both** conditions:

    * ``confidence >= CONFIDENCE_THRESHOLD``  (currently 0.6)
    * ``success_count >= MIN_SUCCESS_COUNT``   (currently 3)

    Records that fail either gate still accumulate evidence — they are not
    deleted — but the LLM is called as a fallback until enough evidence exists.

    Sync readiness
    --------------
    ``SyncMetadataRepository`` is wired here so that Phase 2 can track how
    many applications have run since the last push without touching this class.
    """

    def __init__(
        self,
        database_session: Session,
        infer_location_country: bool = True,
        job_id: Optional[int] = None,
    ) -> None:
        """Initialize memory with database session.

        ``job_id`` is stamped on every write so we have an audit trail
        linking each answer / locator / interaction back to the originating
        job.  Lookups still key on ``(normalized_label, ats_type)`` etc. so
        reuse across jobs keeps working.
        """
        self.session = database_session
        self.job_id = job_id
        self.field_answer_repo = FieldAnswerRepository(self.session)
        self.interaction_repo = InteractionLogRepository(self.session)
        self.dropdown_strategy_repo = DropdownStrategyRepository(self.session)
        self.sync_meta_repo = SyncMetadataRepository(self.session)
        self.synonym_resolver = SynonymResolver(
            infer_location_country=infer_location_country,
        )

    def set_job_id(self, job_id: Optional[int]) -> None:
        """Update the current job id (called once the job row is created)."""
        self.job_id = job_id

    # ── Field answers ─────────────────────────────────────────────────────────

    def save_field_answer(
        self, field_label: str, value: str, ats_type: ATSType, success: bool = True, source: str = "human"
    ) -> bool:
        """Save an answer provided for a field. Returns True if saved.

        Dedup check uses ``get_raw_by_label`` (no confidence gate) so that we
        don't re-save an identical value just because the stored record hasn't
        yet crossed the confidence threshold.
        """
        if not field_label or not value:
            return False

        normalized = self.synonym_resolver.resolve_field_label(field_label)
        if not normalized:
            normalized = field_label.lower().strip()

        # Dedup: skip if the DB already holds this exact value for this label
        existing = self.field_answer_repo.get_raw_by_label(normalized, ats_type)
        if existing and existing.value == str(value).strip():
            return False

        self.field_answer_repo.save_answer(
            field_label=field_label,
            normalized_label=normalized,
            value=value,
            ats_type=ats_type,
            success=success,
            source=source,
            job_id=self.job_id,
        )
        return True

    def get_best_answer(
        self, field_label: str, ats_type: ATSType, resume: Optional[ResumeData] = None
    ) -> tuple[Optional[str], str]:
        """Get the best answer for a field following the priority chain.

        Priority 1: Resume JSON
        Priority 2: Saved memory for this ATS  (confidence-gated)
        Priority 3: Universal saved memory      (confidence-gated)
        Priority 4: Not found → caller falls through to LLM

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

        # Priority 2: Saved memory for THIS ATS (confidence-gated via repo)
        saved = self.field_answer_repo.get_by_normalized_label(normalized, ats_type)
        if saved:
            return saved.value, "saved_memory"

        # Priority 3: Universal saved memory (cross-ATS, confidence-gated)
        universal = self.field_answer_repo.get_universal(normalized)
        if universal:
            return universal.value, "universal_memory"

        # Priority 4: Not found — caller should invoke LLM
        return None, "not_found"

    def record_field_outcome(
        self,
        field_label: str,
        value: str,
        success: bool,
        ats_type: ATSType,
    ) -> None:
        """Record actual browser-execution outcome for a previously used field answer.

        Called *after* ``ToolExecutor`` executes a fill/type action so that the
        confidence of the stored answer reflects real-world effectiveness.

        ``value`` is accepted but not used — it is present so callers don't
        have to filter out cases where value is empty before calling us.
        """
        if not field_label:
            return
        normalized = self.synonym_resolver.resolve_field_label(field_label)
        if not normalized:
            normalized = field_label.lower().strip()
        self.field_answer_repo.record_outcome(normalized, ats_type, success)

    # ── Locator outcomes ──────────────────────────────────────────────────────

    def record_locator_outcome(
        self,
        selector: str,
        ats_type: ATSType,
        purpose: str,
        domain: Optional[str],
        success: bool,
        selector_type: Optional[SelectorType] = None,
    ) -> None:
        """Record actual Playwright execution outcome for a learned locator.

        Delegates to ``LearnedLocatorRepository.upsert_for_field`` which already
        recomputes ``confidence_score`` on every call.
        """
        if not selector or not purpose:
            return

        from jobcli.storage.repositories import LearnedLocatorRepository

        locator_repo = LearnedLocatorRepository(self.session)
        locator_repo.upsert_for_field(
            ats_type=ats_type,
            domain=domain,
            purpose=purpose,
            selector=selector,
            selector_type=selector_type or SelectorType.CSS,
            success=success,
            job_id=self.job_id,
        )

    # ── Dropdown strategies ───────────────────────────────────────────────────

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
            job_id=self.job_id,
        )

    def get_dropdown_strategy(
        self, ats_type: ATSType, field_label: str
    ) -> Optional[DropdownStrategyModel]:
        """Get best strategy for a specific dropdown."""
        if not field_label:
            return None
        return self.dropdown_strategy_repo.get_best_strategy(ats_type, field_label)

    # ── Interaction log ───────────────────────────────────────────────────────

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
            job_id=self.job_id,
        )

    # ── Sync metadata ─────────────────────────────────────────────────────────

    def increment_apps_since_sync(self) -> None:
        """Increment the local counter of completed applications since last sync.

        Called once per completed ``apply_to_job`` run by the engine.
        Phase 2 sync client will read this to determine whether a push is due.
        """
        self.sync_meta_repo.increment_apps_since_sync()

    # ── LLM context builders ──────────────────────────────────────────────────

    def build_llm_context(self, ats_type: ATSType) -> str:
        """Build a memory context block to inject into the LLM prompt.

        Returns a string detailing known answers and successful strategies.
        Only includes records that have passed the confidence gate so the LLM
        prompt is not polluted with low-trust data.
        """
        from sqlalchemy import func
        from jobcli.storage.models import FieldAnswerModel

        # Fetch confident answers, prioritizing manual 'human'/'user' source first
        all_answers = (
            self.session.query(
                FieldAnswerModel.field_label,
                FieldAnswerModel.value,
                FieldAnswerModel.source,
                FieldAnswerModel.success_count,
                FieldAnswerModel.confidence,
            )
            .filter(
                (FieldAnswerModel.ats_type == ats_type) | (FieldAnswerModel.ats_type == ATSType.UNKNOWN)
            )
            .filter(
                FieldAnswerModel.confidence >= CONFIDENCE_THRESHOLD,
                FieldAnswerModel.success_count >= MIN_SUCCESS_COUNT,
            )
            .order_by(FieldAnswerModel.source.desc(), FieldAnswerModel.success_count.desc())
            .all()
        )

        unique_answers: dict[str, dict] = {}
        for label, value, source, count, confidence in all_answers:
            if label not in unique_answers:
                unique_answers[label] = {"value": value, "source": source, "confidence": confidence}

        context_lines = []
        if unique_answers:
            context_lines.append(f"### Memory Context for {ats_type.value} (confidence-filtered):")
            for label, data in unique_answers.items():
                source = data["source"]
                prefix = "[MANUAL ENTRY]" if source in ("human", "user") else "[AUTO-LEARNED]"
                context_lines.append(
                    f"- {prefix} '{label}' -> '{data['value']}' (confidence={data['confidence']:.0%})"
                )

        if not context_lines:
            return "No high-confidence memory available for this ATS type."

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
