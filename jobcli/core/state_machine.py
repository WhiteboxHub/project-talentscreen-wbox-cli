"""LangGraph-based state machine for 3-phase execution."""

from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ApplicationState, ApplicationStatus, ATSType, ExecutionPhase, ResumeData, BrowserAction, ActionType
from jobcli.human.interface import HumanInterface
from jobcli.llm.ax_tree_extractor import AccessibilityTreeExtractor
from jobcli.llm.client import LLMClient
from jobcli.core.tool_executor import ToolExecutor
from jobcli.locators.apply_button import ApplyButtonLocator
from jobcli.locators.ats.handler_factory import ATSHandlerFactory
from jobcli.locators.form_fields import FormFiller
from jobcli.storage.repositories import LearnedLocatorRepository
from jobcli.core.locator_schemas import LearnedLocator


class ApplicationGraphState(TypedDict):
    """State for the application state machine."""

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
        """Phase 0: Memory Retrieval for Agentic reasoning."""
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        ats_type = state["ats_type"]
        locator_repo = state["locator_repo"]

        logger.log_phase_start(ExecutionPhase.LLM)
        state["current_phase"] = ExecutionPhase.LLM

        try:
            locators = locator_repo.get_by_purpose_and_ats("find_apply_button_and_fill_form", ats_type)
            llm_locators = [loc for loc in locators if loc.created_by == "llm"]
            
            if llm_locators:
                logger.info(f"Retrieved {len(llm_locators)} agentic locators from memory.", phase=ExecutionPhase.LLM)
                
                # Execute these locators
                executor = ToolExecutor(page, logger)
                success_all = True
                
                # Typically we'd reconstruct BrowserActions from LearnedLocator notes/types
                # But for simplicity, we mock a click sequence for any returned locator
                for loc in llm_locators:
                    action = BrowserAction(
                        action=ActionType.CLICK, # Assumption for simplistic playback
                        selector=loc.selector,
                        selector_type=loc.selector_type,
                        confidence=1.0
                    )
                    if not executor.execute_action(action):
                        success_all = False
                        break
                
                state["phase_results"]["memory"] = success_all
                if success_all:
                    logger.log_phase_end(ExecutionPhase.LLM, True)
                    return state

        except Exception as e:
            logger.error(f"Phase 0 failed: {e}", phase=ExecutionPhase.LLM)

        state["phase_results"]["memory"] = False
        return state

    def _phase_2_llm(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 2: LLM reasoning (Now primary intelligence driver)."""
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        llm_client = state.get("llm_client")

        if not state.get("current_phase") == ExecutionPhase.LLM:
            logger.log_phase_start(ExecutionPhase.LLM)
            state["current_phase"] = ExecutionPhase.LLM

        if not llm_client:
            logger.warning("No LLM client configured")
            state["phase_results"]["llm"] = False
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return state

        try:
            # Extract Accessibility Tree for massive token reduction and semantic analysis
            extractor = AccessibilityTreeExtractor(page)
            ax_tree = extractor.extract()

            logger.save_structured_dom(
                ax_tree.model_dump(),
                "ax_tree_snapshot",
                ExecutionPhase.LLM,
            )

            # Get actions from LLM using optimized AXTree
            llm_response = llm_client.analyze_page_from_axtree(
                ax_tree,
                resume,
                task="find_apply_button_and_fill_form",
            )
            
            print(f"LLM RAW PARSED RESPONSE: {llm_response}", flush=True)

            if llm_response and not llm_response.requires_human:
                executor = ToolExecutor(page, logger)
                results = executor.execute_actions(llm_response)

                success = all(results.values())
                
                # Agentic Self-Learning: Automatically Store Locators on Success
                if success:
                    locator_repo = state["locator_repo"]
                    ats_type = state["ats_type"]
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
                            logger.info(f"Learned memory saved autonomously: {action.selector}", phase=ExecutionPhase.LLM)

                state["phase_results"]["llm"] = success
                logger.log_phase_end(ExecutionPhase.LLM, success)
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

                if handler.find_apply_button():
                    handler.fill_form(resume_pdf_path)
                    success = handler.submit_application()

                    state["phase_results"]["rules"] = success
                    logger.log_phase_end(ExecutionPhase.RULES, success)
                    return state

            apply_locator = ApplyButtonLocator(page, logger)
            if apply_locator.click_apply_button():
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
            "current_phase": ExecutionPhase.LLM,
            "final_status": ApplicationStatus.PENDING,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state["final_status"]
