"""LangGraph-based state machine for 3-phase execution."""

from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from playwright.sync_api import Page

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ApplicationState, ApplicationStatus, ATSType, ExecutionPhase, ResumeData
from jobcli.human.interface import HumanInterface
from jobcli.llm.ax_tree_extractor import AccessibilityTreeExtractor
from jobcli.llm.client import LLMClient
from jobcli.core.tool_executor import ToolExecutor
from jobcli.locators.apply_button import ApplyButtonLocator
from jobcli.locators.ats.handler_factory import ATSHandlerFactory
from jobcli.locators.form_fields import FormFiller
from jobcli.storage.repositories import LearnedLocatorRepository


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
        workflow.add_node("phase_1_rules", self._phase_1_rules)
        workflow.add_node("phase_2_llm", self._phase_2_llm)
        workflow.add_node("phase_3_human", self._phase_3_human)
        workflow.add_node("finalize", self._finalize)

        # Set entry point
        workflow.set_entry_point("phase_1_rules")

        # Add conditional edges
        workflow.add_conditional_edges(
            "phase_1_rules",
            self._route_after_phase_1,
            {
                "success": "finalize",
                "try_llm": "phase_2_llm",
                "try_human": "phase_3_human",
            },
        )

        workflow.add_conditional_edges(
            "phase_2_llm",
            self._route_after_phase_2,
            {
                "success": "finalize",
                "try_human": "phase_3_human",
                "failed": "finalize",
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

    def _phase_1_rules(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 1: Rule-based locators."""
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        ats_type = state["ats_type"]
        resume_pdf_path = state["resume_pdf_path"]

        logger.log_phase_start(ExecutionPhase.RULES)
        state["current_phase"] = ExecutionPhase.RULES

        try:
            # Try ATS-specific handler
            handler = ATSHandlerFactory.create_handler(ats_type, page, resume, logger)

            if handler:
                logger.info(f"Using {ats_type.value} handler", phase=ExecutionPhase.RULES)

                if handler.find_apply_button():
                    handler.fill_form(resume_pdf_path)
                    success = handler.submit_application()

                    state["phase_results"]["rules"] = success
                    logger.log_phase_end(ExecutionPhase.RULES, success)
                    return state

            # Fallback to generic locators
            apply_locator = ApplyButtonLocator(page, logger)
            if apply_locator.click_apply_button():
                form_filler = FormFiller(page, resume, logger)
                form_filler.fill_all(resume_pdf_path)

                state["phase_results"]["rules"] = True
                logger.log_phase_end(ExecutionPhase.RULES, True)
                return state

        except Exception as e:
            logger.error(f"Phase 1 failed: {e}", phase=ExecutionPhase.RULES)

        state["phase_results"]["rules"] = False
        logger.log_phase_end(ExecutionPhase.RULES, False)
        return state

    def _phase_2_llm(self, state: ApplicationGraphState) -> ApplicationGraphState:
        """Phase 2: LLM reasoning."""
        logger = state["logger"]
        page = state["page"]
        resume = state["resume"]
        llm_client = state.get("llm_client")

        logger.log_phase_start(ExecutionPhase.LLM)
        state["current_phase"] = ExecutionPhase.LLM

        if not llm_client:
            logger.warning("No LLM client configured")
            state["phase_results"]["llm"] = False
            logger.log_phase_end(ExecutionPhase.LLM, False)
            return state

        try:
            # Extract Accessibility Tree (more efficient than full DOM)
            extractor = AccessibilityTreeExtractor(page)
            ax_tree = extractor.extract()

            logger.save_structured_dom(
                ax_tree.model_dump(),
                "ax_tree",
                ExecutionPhase.LLM,
            )

            # Get actions from LLM
            llm_response = llm_client.analyze_page_from_axtree(
                ax_tree,
                resume,
                task="find_apply_button_and_fill_form",
            )

            if llm_response and not llm_response.requires_human:
                executor = ToolExecutor(page, logger)
                results = executor.execute_actions(llm_response)

                success = all(results.values())
                state["phase_results"]["llm"] = success
                logger.log_phase_end(ExecutionPhase.LLM, success)
                return state

        except Exception as e:
            logger.error(f"Phase 2 failed: {e}", phase=ExecutionPhase.LLM)

        state["phase_results"]["llm"] = False
        logger.log_phase_end(ExecutionPhase.LLM, False)
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

            # Request help
            success, selector, selector_type = human.request_help(
                "find_apply_button",
                ats_type,
            )

            if success and selector:
                # Click apply button
                if selector_type and selector_type.value == "css":
                    page.click(selector)
                elif selector_type and selector_type.value == "xpath":
                    page.click(f"xpath={selector}")

                # Fill form
                form_filler = FormFiller(page, resume, logger)
                form_filler.fill_all(resume_pdf_path)

                # Submit
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

        # Determine final status
        if any(phase_results.values()):
            state["final_status"] = ApplicationStatus.SUBMITTED
        else:
            state["final_status"] = ApplicationStatus.FAILED

        return state

    def _route_after_phase_1(
        self, state: ApplicationGraphState
    ) -> Literal["success", "try_llm", "try_human"]:
        """Route after phase 1."""
        if state["phase_results"].get("rules", False):
            return "success"

        # Try LLM if available
        if state.get("llm_client"):
            return "try_llm"

        # Fall back to human
        return "try_human"

    def _route_after_phase_2(
        self, state: ApplicationGraphState
    ) -> Literal["success", "try_human", "failed"]:
        """Route after phase 2."""
        if state["phase_results"].get("llm", False):
            return "success"

        # Fall back to human
        return "try_human"

    def _route_after_phase_3(
        self, state: ApplicationGraphState
    ) -> Literal["success", "failed"]:
        """Route after phase 3."""
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
            "current_phase": ExecutionPhase.RULES,
            "final_status": ApplicationStatus.PENDING,
        }

        # Run the graph
        final_state = self.graph.invoke(initial_state)

        return final_state["final_status"]
