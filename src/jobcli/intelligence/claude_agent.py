"""Claude Agent with advanced strategies for job application automation.

This module provides a sophisticated Claude-powered agent that uses tool use
capabilities for multi-step planning, reasoning, and decision-making.

Key features:
  * Planning strategy: Breaks down complex tasks into subtasks
  * Reasoning strategy: Uses Claude's extended thinking for better decisions
  * Tool use: Integrates with browser automation tools and memory retrieval
  * Memory-aware: Learns from past applications and decisions
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import anthropic

from jobcli.utils.logger import JobLogger
from jobcli.profile.schemas import (
    ExecutionPhase,
    LLMActionResponse,
    ResumeData,
)
from jobcli.llm.ax_tree_extractor import AccessibilityTree


@dataclass
class ToolResult:
    """Result from executing a tool."""

    tool_name: str
    success: bool
    data: Any
    error: Optional[str] = None


class ClaudeAgentStrategy:
    """Advanced Claude agent with tool use capabilities."""

    def __init__(
        self,
        api_key: str,
        logger: Optional[JobLogger] = None,
    ) -> None:
        """Initialize Claude agent."""
        self.api_key = api_key
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20241022"
        self.logger = logger
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict[str, Any]]:
        """Define tools available to the agent."""
        return [
            {
                "name": "analyze_form_structure",
                "description": "Analyze the form structure and identify all fields, their types, and requirements",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "accessibility_tree": {
                            "type": "string",
                            "description": "The accessibility tree snapshot of the page",
                        },
                        "focus_on_required": {
                            "type": "boolean",
                            "description": "Whether to focus analysis on required fields only",
                        },
                    },
                    "required": ["accessibility_tree"],
                },
            },
            {
                "name": "retrieve_candidate_memory",
                "description": "Retrieve previously answered questions and application patterns for this candidate",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Question or field type to search for in memory",
                        },
                        "job_title": {
                            "type": "string",
                            "description": "Optional: job title context for memory retrieval",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "generate_form_strategy",
                "description": "Generate a step-by-step strategy for completing the form efficiently",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "form_fields": {
                            "type": "array",
                            "description": "List of form fields identified",
                            "items": {"type": "string"},
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["speed", "accuracy", "compliance"],
                            "description": "Optimization priority",
                        },
                    },
                    "required": ["form_fields"],
                },
            },
            {
                "name": "validate_form_completion",
                "description": "Validate that all required fields have been properly filled",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "completed_fields": {
                            "type": "object",
                            "description": "Dictionary of filled field values",
                        },
                        "required_fields": {
                            "type": "array",
                            "description": "List of required fields that must be filled",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["completed_fields", "required_fields"],
                },
            },
        ]

    def analyze_page_with_planning(
        self,
        ax_tree: AccessibilityTree,
        resume: ResumeData,
        task: str = "fill_form_fields",
        memory_context: Optional[str] = None,
    ) -> Optional[LLMActionResponse]:
        """Analyze page using planning strategy.
        
        This method:
        1. Plans the form completion strategy
        2. Analyzes the form structure
        3. Retrieves relevant memory
        4. Generates precise actions
        """
        if self.logger:
            self.logger.info(
                "Starting Claude agent with planning strategy",
                phase=ExecutionPhase.LLM,
                task=task,
            )

        # Build initial prompt
        raw_aria = getattr(ax_tree, "_raw_aria", "")
        if hasattr(ax_tree, "dropdown_fields") and ax_tree.dropdown_fields:
            raw_aria += "\n\n## Pre-extracted Dropdown Options:\n"
            for dropdown in ax_tree.dropdown_fields:
                if dropdown.get('options'):
                    raw_aria += f"- {dropdown.get('label')}: {', '.join(dropdown.get('options')[:30])}\n"
        user_info = json.loads(resume.model_dump_json())

        system_prompt = """You are an expert autonomous job application agent powered by Claude.
Your capabilities:
  * Multi-step planning and reasoning
  * Tool use for analysis and retrieval
  * Advanced form understanding
  * Memory-aware decision making

Your goal: Complete the job application form accurately and efficiently.

Process:
1. Use analyze_form_structure to understand the form layout
2. Use retrieve_candidate_memory to get previous answers
3. Use generate_form_strategy to plan your approach
4. Generate precise browser actions
5. Use validate_form_completion before submitting

Always prioritize:
  * Compliance and legal accuracy (work authorization, visa sponsorship)
  * Required field completion
  * Consistency with candidate memory
  * User privacy and data minimization
  * Default country codes to +1 (United States/Canada) unless specified otherwise."""

        initial_message = f"""Task: {task}

Page URL: {ax_tree.url}
Page Title: {ax_tree.title}

Accessibility Snapshot:
```
{raw_aria}
```

User Information:
{json.dumps(user_info, indent=2)}

{f"Memory Context: {memory_context}" if memory_context else "No previous memory available."}

Please analyze this form and generate completion actions. Use your available tools to:
1. Understand the form structure
2. Check if we have answers in memory
3. Plan the completion strategy
4. Generate the actions needed

Respond with ONLY a JSON object matching this schema:
{{
  "actions": [
    {{"action": "click|fill|select|upload", "selector": "...", "selector_type": "text|role|aria_label", "value": "...", "field_label": "...", "confidence": 0.95}}
  ],
  "reasoning": "...",
  "detected_ats": "greenhouse|lever|workday|null",
  "detected_fields": ["..."],
  "confidence": 0.95,
  "requires_human": false
}}"""

        # Use tool use with agentic loop
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": initial_message}
        ]

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            if self.logger:
                self.logger.info(
                    f"Claude agent iteration {iteration}",
                    phase=ExecutionPhase.LLM,
                )

            try:
                # Call Claude with tools
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=self.tools,
                    messages=messages,
                )

                # Check if we should stop
                if response.stop_reason == "end_turn":
                    # Extract final response
                    for block in response.content:
                        if hasattr(block, "text"):
                            try:
                                final_data = json.loads(block.text)
                                return self._validate_response(final_data)
                            except json.JSONDecodeError:
                                pass
                    break

                # Process tool use
                if response.stop_reason == "tool_use":
                    # Add assistant response to messages
                    messages.append({"role": "assistant", "content": response.content})

                    # Execute tools
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_result = self._execute_tool(
                                block.name, block.input, ax_tree, resume
                            )
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps(
                                        {
                                            "success": tool_result.success,
                                            "data": tool_result.data,
                                            "error": tool_result.error,
                                        }
                                    ),
                                }
                            )

                    # Add tool results to messages
                    if tool_results:
                        messages.append({"role": "user", "content": tool_results})

                else:
                    # Unknown stop reason, break
                    break

            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Claude agent error: {e}",
                        phase=ExecutionPhase.LLM,
                    )
                break

            time.sleep(0.5)

        if self.logger:
            self.logger.warning(
                "Claude agent did not return valid form completion",
                phase=ExecutionPhase.LLM,
            )

        return None

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        ax_tree: AccessibilityTree,
        resume: ResumeData,
    ) -> ToolResult:
        """Execute a tool requested by Claude."""
        try:
            if tool_name == "analyze_form_structure":
                return self._tool_analyze_form_structure(
                    tool_input, ax_tree
                )
            elif tool_name == "retrieve_candidate_memory":
                return self._tool_retrieve_memory(tool_input, resume)
            elif tool_name == "generate_form_strategy":
                return self._tool_generate_strategy(tool_input)
            elif tool_name == "validate_form_completion":
                return self._tool_validate_completion(tool_input)
            else:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    data=None,
                    error=f"Unknown tool: {tool_name}",
                )
        except Exception as e:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=str(e),
            )

    def _tool_analyze_form_structure(
        self, tool_input: Dict[str, Any], ax_tree: AccessibilityTree
    ) -> ToolResult:
        """Tool: Analyze form structure and identify fields."""
        # Parse the accessibility tree to find form fields
        raw_aria = getattr(ax_tree, "_raw_aria", "")

        # Simple field extraction (can be enhanced)
        fields = {
            "text_inputs": [],
            "dropdowns": [],
            "checkboxes": [],
            "file_uploads": [],
            "buttons": [],
        }

        lines = raw_aria.split("\n")
        for line in lines:
            if "textbox" in line.lower():
                fields["text_inputs"].append(line.strip())
            elif "combobox" in line.lower() or "select" in line.lower():
                fields["dropdowns"].append(line.strip())
            elif "checkbox" in line.lower():
                fields["checkboxes"].append(line.strip())
            elif "file upload" in line.lower():
                fields["file_uploads"].append(line.strip())
            elif "button" in line.lower() and "apply" in line.lower():
                fields["buttons"].append(line.strip())

        return ToolResult(
            tool_name="analyze_form_structure",
            success=True,
            data={
                "total_fields": sum(len(v) for v in fields.values()),
                "fields": fields,
                "url": ax_tree.url,
            },
        )

    def _tool_retrieve_memory(
        self, tool_input: Dict[str, Any], resume: ResumeData
    ) -> ToolResult:
        """Tool: Retrieve candidate memory and previous answers."""
        query = tool_input.get("query", "")

        # Simulate memory retrieval from resume/past applications
        memories = {
            "first_name": resume.personal.first_name,
            "last_name": resume.personal.last_name,
            "email": resume.personal.email,
            "phone": resume.personal.phone,
            "linkedin": resume.personal.linkedin,
            "work_authorized": getattr(resume.work_eligibility, "authorized", None),
            "requires_sponsorship": getattr(
                resume.work_eligibility, "requires_sponsorship", None
            ),
            "years_of_experience": len(resume.experience) if resume.experience else 0,
        }

        # Search for relevant memory
        matches = {
            k: v for k, v in memories.items() if query.lower() in k.lower()
        }

        if not matches:
            matches = memories  # Return all if no specific match

        return ToolResult(
            tool_name="retrieve_candidate_memory",
            success=True,
            data=matches,
        )

    def _tool_generate_strategy(
        self, tool_input: Dict[str, Any]
    ) -> ToolResult:
        """Tool: Generate form completion strategy."""
        form_fields = tool_input.get("form_fields", [])
        priority = tool_input.get("priority", "accuracy")

        strategy = {
            "priority": priority,
            "recommended_order": [
                "Required fields first",
                "Contact information",
                "Work experience",
                "Education",
                "Compliance questions",
                "Submit",
            ],
            "estimated_time_minutes": len(form_fields) // 5 + 2,
            "risk_factors": [],
            "field_count": len(form_fields),
        }

        if "authorization" in str(form_fields).lower():
            strategy["risk_factors"].append(
                "Work authorization question detected - must use resume data"
            )

        if priority == "speed":
            strategy["recommended_order"] = [
                "Contact info",
                "Required fields",
                "Submit",
            ]

        return ToolResult(
            tool_name="generate_form_strategy",
            success=True,
            data=strategy,
        )

    def _tool_validate_completion(
        self, tool_input: Dict[str, Any]
    ) -> ToolResult:
        """Tool: Validate form completion."""
        completed = tool_input.get("completed_fields", {})
        required = tool_input.get("required_fields", [])

        missing = [f for f in required if f not in completed or not completed[f]]
        validation_result = {
            "is_complete": len(missing) == 0,
            "missing_fields": missing,
            "completed_count": len(completed),
            "required_count": len(required),
        }

        return ToolResult(
            tool_name="validate_form_completion",
            success=True,
            data=validation_result,
        )

    def _validate_response(self, response_data: Dict[str, Any]) -> Optional[LLMActionResponse]:
        """Validate and convert response to LLMActionResponse."""
        try:
            from jobcli.profile.schemas import BrowserAction, ActionType

            # Build actions
            actions = []
            for action_data in response_data.get("actions", []):
                action = BrowserAction(
                    action=ActionType(action_data.get("action", "click")),
                    selector=action_data.get("selector", ""),
                    selector_type=action_data.get("selector_type", "text"),
                    value=action_data.get("value", ""),
                    field_label=action_data.get("field_label", ""),
                    confidence=action_data.get("confidence", 0.9),
                )
                actions.append(action)

            response = LLMActionResponse(
                actions=actions,
                reasoning=response_data.get("reasoning", ""),
                detected_ats=response_data.get("detected_ats"),
                detected_fields=response_data.get("detected_fields", []),
                confidence=response_data.get("confidence", 0.9),
                requires_human=response_data.get("requires_human", False),
            )

            if self.logger:
                self.logger.info(
                    "Claude response validated",
                    phase=ExecutionPhase.LLM,
                    action_count=len(actions),
                    confidence=response.confidence,
                )

            return response

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Failed to validate Claude response: {e}",
                    phase=ExecutionPhase.LLM,
                )
            return None
