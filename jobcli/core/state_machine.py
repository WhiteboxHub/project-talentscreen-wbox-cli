"""LangGraph-based state machine for 3-phase execution."""

from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.memory import AgentMemory
from jobcli.core.schemas import (
    ActionType,
    ApplicationState,
    ApplicationStatus,
    ATSType,
    BrowserAction,
    ExecutionPhase,
    ResumeData,
)
from jobcli.core.synonym_resolver import SynonymResolver
from jobcli.core.url_normalize import normalize_job_url
from jobcli.human.interface import HumanInterface
from jobcli.llm.ax_tree_extractor import AccessibilityTreeExtractor
from jobcli.llm.client import LLMClient
from jobcli.core.tool_executor import ToolExecutor
from jobcli.locators.apply_button import ApplyButtonLocator, adopt_application_page_after_action
from jobcli.locators.ats.handler_factory import ATSHandlerFactory
from jobcli.locators.form_fields import FormFiller
from jobcli.storage.repositories import JobRepository, LearnedLocatorRepository
from jobcli.core.locator_schemas import LearnedLocator


class ApplicationGraphState(TypedDict):
    """State for the application state machine.

    LangGraph nodes (phase_0_memory, phase_2_llm, …) mirror an internal "agent graph";
    this is unrelated to OpenClaw device nodes.
    """

    page: Page
    state: ApplicationState
    resume: ResumeData
    logger: JobLogger
    ats_type: ATSType
    resume_pdf_path: str
    locator_repo: LearnedLocatorRepository
    llm_client: LLMClient | None
    phase_results: dict[str, bool]
    current_phase: ExecutionPhase
    final_status: ApplicationStatus
    job_id: int | None
    job_repo: JobRepository | None
    agent_memory: AgentMemory | None
    job_board_url: str | None
    infer_location_country: bool


class ApplicationStateMachine:
    """LangGraph-based state machine for job applications."""

    def __init__(self) -> None:
        """Initialize state machine."""
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(ApplicationGraphState)

        # Add nodes for each phase
        workflow.add_node("phase_0_memory", self._phase_0_memory)
        workflow.add_node("phase_2_llm", self._phase_2_llm)
        workflow.add_node("phase_1_rules", self._phase_1_rules)
        workflow.add_node("phase_3_human", self._phase_3_human)
        workflow.add_node("finalize", self._finalize)

        # Set entry point to Memory First
        workflow.set_entry_point("phase_0_memory")

        # Routing edges
        workflow.add_conditional_edges(
            "phase_0_memory",
            self._route_after_phase_0,
            {
                "success": "finalize",
                "try_llm": "phase_2_llm",
            },
        )

        workflow.add_conditional_edges(
            "phase_2_llm",
            self._route_after_phase_2,
            {
                "success": "finalize",
                "try_rules": "phase_1_rules",
            },
        )

        workflow.add_conditional_edges(
            "phase_1_rules",
            self._route_after_phase_1,
            {
                "success": "finalize",
                "try_human": "phase_3_human",
            },
        )

        workflow.add_conditional_edges(
            "phase_3_human",
            self._route_after_phase_3,
            {
                "success": "finalize",
                "failed": "finalize",
            },
        )

        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _phase_0_memory(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 0: Memory Retrieval — replay previously-learned LLM locator sequences."""
        logger = state["logger"]
        page = state["page"]
        ats_type = state["ats_type"]
        locator_repo = state["locator_repo"]
        agent_memory = state.get("agent_memory")
        infer_loc = state.get("infer_location_country", True)

        logger.log_phase_start(ExecutionPhase.RULES)
        state["current_phase"] = ExecutionPhase.RULES

        try:
            locators = locator_repo.get_by_purpose_and_ats("find_apply_button_and_fill_form", ats_type)
            llm_locators = [loc for loc in locators if loc.created_by == "llm"]

            if llm_locators:
                logger.info(f"Retrieved {len(llm_locators)} agentic locators from memory.", phase=ExecutionPhase.RULES)

                synonym_resolver = SynonymResolver(infer_location_country=infer_loc)
                executor = ToolExecutor(
                    page,
                    logger,
                    memory=agent_memory,
                    synonym_resolver=synonym_resolver,
                    ats_type=ats_type,
                )
                success_all = True

                n0 = len(page.context.pages)
                u0 = page.url
                pids0 = {id(p) for p in page.context.pages}

                for loc in llm_locators:
                    # Determine action type from stored notes: "LLM Action: fill - First Name"
                    action_type = ActionType.CLICK
                    if loc.notes:
                        notes_lower = loc.notes.lower()
                        if "action: fill" in notes_lower:
                            action_type = ActionType.FILL
                        elif "action: type" in notes_lower:
                            action_type = ActionType.TYPE
                        elif "action: select" in notes_lower:
                            action_type = ActionType.SELECT
                        elif "action: upload" in notes_lower:
                            action_type = ActionType.UPLOAD

                    action = BrowserAction(
                        action=action_type,
                        selector=loc.selector,
                        selector_type=loc.selector_type,
                        confidence=loc.confidence_score,
                    )
                    if not executor.execute_action(action):
                        success_all = False
                        break

                # Adopt any new tab opened by the replayed sequence (e.g. Apply button click)
                adopted = adopt_application_page_after_action(
                    page,
                    page_count_before=n0,
                    url_before=u0,
                    page_ids_before=pids0,
                    logger=logger,
                )
                if id(adopted) != id(page):
                    page = adopted
                    state["page"] = page
                    logger.info(
                        "Memory replay opened a new tab; switched to it.",
                        phase=ExecutionPhase.RULES,
                    )

                state["phase_results"]["memory"] = success_all
                if success_all:
                    logger.log_phase_end(ExecutionPhase.RULES, True)
                    return state

        except Exception as e:
            logger.error(f"Phase 0 failed: {e}", phase=ExecutionPhase.RULES)

        state["phase_results"]["memory"] = False
        return state

    def _persist_resolved_url_if_redirected(self, state: ApplicationGraphState, page: Page) -> None:
        """Record final URL after redirects (aligned with legacy engine URL awareness)."""
        job_repo = state.get("job_repo")
        job_id = state.get("job_id")
        board_url = state.get("job_board_url") or ""
        if not job_repo or not job_id or not page.url or not board_url:
            return
        if normalize_job_url(page.url) != normalize_job_url(board_url):
            job_repo.update_resolved_url(job_id, page.url)
            logger = state["logger"]
            logger.info(
                f"Resolved URL differs from job link; stored resolved_url: {page.url[:120]}",
                phase=ExecutionPhase.LLM,
            )

    def _phase_2_llm(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 2: LLM reasoning with multi-page loop (URL / DOM change detection).

        Matches legacy ``ApplicationEngine`` behavior: after actions, if the page URL
        or form snapshot changes (e.g. Next / Continue), run another LLM pass.
        """
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        ats_type = state["ats_type"]
        llm_client = state.get("llm_client")
        agent_memory = state.get("agent_memory")
        infer_loc = state.get("infer_location_country", True)

        if state.get("current_phase") != ExecutionPhase.LLM:
            logger.log_phase_start(ExecutionPhase.LLM)
            state["current_phase"] = ExecutionPhase.LLM

        if not llm_client:
            logger.warning("No LLM client configured")
            state["phase_results"]["llm"] = False
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return state

        try:
            extractor = AccessibilityTreeExtractor(page)
            ax_tree = extractor.extract()
            self._persist_resolved_url_if_redirected(state, page)

            MAX_PAGES = 5
            page_idx = 0
            overall_llm_success = False
            performed_uploads: set[str] = set()
            synonym_resolver = SynonymResolver(infer_location_country=infer_loc)

            while page_idx < MAX_PAGES:
                page_idx += 1
                self._persist_resolved_url_if_redirected(state, page)

                logger.save_structured_dom(
                    ax_tree.model_dump(),
                    f"ax_tree_snapshot_p{page_idx}",
                    ExecutionPhase.LLM,
                )

                memory_ctx = ""
                if agent_memory:
                    memory_ctx = agent_memory.combined_llm_memory_block(resume, ats_type)

                llm_response = llm_client.analyze_page_from_axtree(
                    ax_tree,
                    resume,
                    task="find_apply_button_and_fill_form",
                    memory_context=memory_ctx,
                    dropdown_options=ax_tree.dropdown_fields,
                    resume_pdf_path=state["resume_pdf_path"] or None,
                )

                if not llm_response:
                    break
                if llm_response.requires_human:
                    state["phase_results"]["llm"] = False
                    logger.log_phase_end(ExecutionPhase.LLM, False)
                    return state

                if not llm_response.actions:
                    logger.info("LLM returned no actions; stopping LLM loop.", phase=ExecutionPhase.LLM)
                    break

                ask_actions = [a for a in llm_response.actions if a.action == ActionType.ASK]
                if ask_actions:
                    logger.warning(
                        "LLM requested clarifications (ASK); skipping autonomous execution this wave.",
                        phase=ExecutionPhase.LLM,
                    )
                    state["phase_results"]["llm"] = False
                    logger.log_phase_end(ExecutionPhase.LLM, False)
                    return state

                executor = ToolExecutor(
                    page,
                    logger,
                    memory=agent_memory,
                    synonym_resolver=synonym_resolver,
                    ats_type=ats_type,
                )

                has_upload = any(a.action == ActionType.UPLOAD for a in llm_response.actions)
                if has_upload:
                    new_uploads = []
                    for act in llm_response.actions:
                        if act.action == ActionType.UPLOAD:
                            upload_key = str(act.value or "").split("/")[-1].split("\\")[-1]
                            if upload_key and upload_key not in performed_uploads:
                                new_uploads.append(act)
                                performed_uploads.add(upload_key)
                    if new_uploads:
                        llm_response.actions = new_uploads
                        logger.info(
                            "Prioritizing resume upload; will re-scan page after wait.",
                            phase=ExecutionPhase.LLM,
                        )
                    else:
                        has_upload = False
                        llm_response.actions = [a for a in llm_response.actions if a.action != ActionType.UPLOAD]

                ctx = page.context
                pids_snap = {id(p) for p in ctx.pages}
                url_snap = page.url
                n_snap = len(ctx.pages)
                results = executor.execute_actions(llm_response)
                adopted = adopt_application_page_after_action(
                    page,
                    page_count_before=n_snap,
                    url_before=url_snap,
                    page_ids_before=pids_snap,
                    logger=logger,
                )
                if id(adopted) != id(page):
                    page = adopted
                    state["page"] = page
                    extractor = AccessibilityTreeExtractor(page)
                    logger.info(
                        "LLM opened a new tab; continuing automation on that page.",
                        phase=ExecutionPhase.LLM,
                        url_preview=(page.url or "")[:200],
                    )
                else:
                    page = adopted

                if results.get("requires_human"):
                    state["phase_results"]["llm"] = False
                    logger.log_phase_end(ExecutionPhase.LLM, False)
                    return state

                bool_results = {k: v for k, v in results.items() if isinstance(v, bool)}
                if bool_results:
                    successes = sum(1 for v in bool_results.values() if v)
                    if successes / len(bool_results) >= 0.5:
                        overall_llm_success = True

                if has_upload:
                    wait_ms = 5000 if "ashby" in page.url.lower() else 3500
                    page.wait_for_timeout(wait_ms)
                    ax_tree = extractor.extract()
                    continue

                for i, action in enumerate(llm_response.actions):
                    if agent_memory and action.field_label and action.value:
                        key = f"action_{i}_{action.action.value}"
                        ok = results.get(key, False) is True
                        if action.action in (ActionType.FILL, ActionType.TYPE, ActionType.SELECT) and ok:
                            agent_memory.save_field_answer(
                                action.field_label,
                                str(action.value),
                                ats_type,
                                success=True,
                                source="llm",
                            )

                all_ok = bool(bool_results) and all(bool_results.values())
                if all_ok:
                    locator_repo = state["locator_repo"]
                    for action in llm_response.actions:
                        if action.selector:
                            loc = LearnedLocator(
                                ats_type=ats_type,
                                selector=action.selector,
                                selector_type=action.selector_type,
                                purpose="find_apply_button_and_fill_form",
                                notes=f"LLM Action: {action.action.value} - {action.field_label or ''}",
                                created_by="llm",
                            )
                            locator_repo.create(loc)
                            logger.info(
                                f"Learned memory saved autonomously: {action.selector}",
                                phase=ExecutionPhase.LLM,
                            )

                page.wait_for_timeout(3000)
                new_ax_tree = extractor.extract()

                url_changed = new_ax_tree.url != ax_tree.url
                fields_changed = False
                if len(new_ax_tree.form_fields) != len(ax_tree.form_fields):
                    fields_changed = True
                else:
                    for i, field in enumerate(new_ax_tree.form_fields):
                        old_field = ax_tree.form_fields[i]
                        if (
                            str(field.get("value", "")).strip()
                            != str(old_field.get("value", "")).strip()
                        ) or bool(field.get("checked")) != bool(old_field.get("checked")):
                            fields_changed = True
                            break

                button_clicked = any(a.action == ActionType.CLICK for a in llm_response.actions)

                if not url_changed and not fields_changed and not button_clicked:
                    logger.info(
                        "No URL or form snapshot change after actions; ending multi-page LLM loop.",
                        phase=ExecutionPhase.LLM,
                    )
                    break

                ax_tree = new_ax_tree

            state["phase_results"]["llm"] = overall_llm_success
            logger.log_phase_end(ExecutionPhase.LLM, overall_llm_success)
            return state

        except Exception as e:
            import traceback

            traceback.print_exc()
            logger.error(f"Phase 2 failed: {e}", phase=ExecutionPhase.LLM)

        state["phase_results"]["llm"] = False
        logger.log_phase_end(ExecutionPhase.LLM, False)
        return state

    def _phase_1_rules(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 1: Rule-based locators (Fallback)."""
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        ats_type = state["ats_type"]
        resume_pdf_path = state["resume_pdf_path"]

        logger.log_phase_start(ExecutionPhase.RULES)
        state["current_phase"] = ExecutionPhase.RULES

        try:
            handler = ATSHandlerFactory.create_handler(ats_type, page, resume, logger)

            if handler:
                logger.info(f"Using {ats_type.value} fallback handler", phase=ExecutionPhase.RULES)

                n0 = len(page.context.pages)
                u0 = page.url
                pids0 = {id(p) for p in page.context.pages}
                if handler.find_apply_button():
                    page = adopt_application_page_after_action(
                        page,
                        page_count_before=n0,
                        url_before=u0,
                        logger=logger,
                        page_ids_before=pids0,
                    )
                    state["page"] = page
                    handler = ATSHandlerFactory.create_handler(ats_type, page, resume, logger)
                    if not handler:
                        state["phase_results"]["rules"] = False
                        logger.log_phase_end(ExecutionPhase.RULES, False)
                        return state
                    handler.fill_form(resume_pdf_path)
                    success = handler.submit_application()

                    state["phase_results"]["rules"] = success
                    logger.log_phase_end(ExecutionPhase.RULES, success)
                    return state

            apply_locator = ApplyButtonLocator(page, logger)
            clicked, page = apply_locator.click_apply_button()
            if clicked:
                state["page"] = page
                form_filler = FormFiller(page, resume, logger)
                fill_results = form_filler.fill_all(resume_pdf_path)

                # Validate: did we actually fill anything?
                personal_results = fill_results.get("personal_info", {})
                fields_filled = sum(1 for v in personal_results.values() if v)
                resume_uploaded = fill_results.get("resume_uploaded", False)

                if fields_filled > 0 or resume_uploaded:
                    logger.info(
                        f"Form fill validated: {fields_filled} fields filled, resume={'yes' if resume_uploaded else 'no'}",
                        phase=ExecutionPhase.RULES,
                    )
                    state["phase_results"]["rules"] = True
                    logger.log_phase_end(ExecutionPhase.RULES, True)
                    return state
                else:
                    logger.warning(
                        "Apply button clicked but form fill failed — 0 fields filled. Falling through to LLM.",
                        phase=ExecutionPhase.RULES,
                    )
                    # Fall through to LLM phase instead of lying

        except Exception as e:
            logger.error(f"Phase 1 failed: {e}", phase=ExecutionPhase.RULES)

        state["phase_results"]["rules"] = False
        logger.log_phase_end(ExecutionPhase.RULES, False)
        return state

    def _phase_3_human(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 3: Human in the loop."""
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        ats_type = state["ats_type"]
        locator_repo = state["locator_repo"]
        resume_pdf_path = state["resume_pdf_path"]

        logger.log_phase_start(ExecutionPhase.HUMAN)
        state["current_phase"] = ExecutionPhase.HUMAN

        try:
            human = HumanInterface(page, locator_repo, logger)

            success, selector, selector_type = human.request_help(
                "find_apply_button",
                ats_type,
            )

            if success and selector:
                if selector_type and selector_type.value == "css":
                    page.click(selector)
                elif selector_type and selector_type.value == "xpath":
                    page.click(f"xpath={selector}")

                form_filler = FormFiller(page, resume, logger)
                form_filler.fill_all(resume_pdf_path)

                if human.confirm_submission():
                    submit_selectors = [
                        "button[type='submit']",
                        "input[type='submit']",
                        "button:has-text('Submit')",
                    ]

                    for selector in submit_selectors:
                        try:
                            page.click(selector)
                            state["phase_results"]["human"] = True
                            logger.log_phase_end(ExecutionPhase.HUMAN, True)
                            return state
                        except:
                            continue

        except Exception as e:
            logger.error(f"Phase 3 failed: {e}", phase=ExecutionPhase.HUMAN)

        state["phase_results"]["human"] = False
        logger.log_phase_end(ExecutionPhase.HUMAN, False)
        return state

    def _finalize(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Finalize application."""
        phase_results = state["phase_results"]
        if any(phase_results.values()):
            state["final_status"] = ApplicationStatus.SUBMITTED
        else:
            state["final_status"] = ApplicationStatus.FAILED
        return state

    def _route_after_phase_0(self, state: ApplicationGraphState) -> Literal["success", "try_llm"]:
        if state["phase_results"].get("memory", False):
            return "success"
        return "try_llm"

    def _route_after_phase_2(self, state: ApplicationGraphState) -> Literal["success", "try_rules"]:
        if state["phase_results"].get("llm", False):
            return "success"
        return "try_rules"

    def _route_after_phase_1(self, state: ApplicationGraphState) -> Literal["success", "try_human"]:
        if state["phase_results"].get("rules", False):
            return "success"
        return "try_human"

    def _route_after_phase_3(self, state: ApplicationGraphState) -> Literal["success", "failed"]:
        if state["phase_results"].get("human", False):
            return "success"
        return "failed"

    def run(
        self,
        page: Page,
        state: ApplicationState,
        resume: ResumeData,
        logger: JobLogger,
        ats_type: ATSType,
        resume_pdf_path: str,
        locator_repo: LearnedLocatorRepository,
        llm_client: LLMClient | None = None,
        agent_memory: AgentMemory | None = None,
        job_id: int | None = None,
        job_repo: JobRepository | None = None,
        job_board_url: str | None = None,
        infer_location_country: bool = True,
    ) -> ApplicationStatus:
        """Run the state machine."""
        initial_state: ApplicationGraphState = {
            "page": page,
            "state": state,
            "resume": resume,
            "logger": logger,
            "ats_type": ats_type,
            "resume_pdf_path": resume_pdf_path,
            "locator_repo": locator_repo,
            "llm_client": llm_client,
            "phase_results": {},
            "current_phase": ExecutionPhase.RULES,
            "final_status": ApplicationStatus.PENDING,
            "job_id": job_id,
            "job_repo": job_repo,
            "agent_memory": agent_memory,
            "job_board_url": job_board_url,
            "infer_location_country": infer_location_country,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state["final_status"]
