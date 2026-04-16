"""LLM client with structured output for OpenAI, Anthropic, and Gemini."""

import json
import time
from typing import Literal, Optional, Any

import anthropic
import google.generativeai as genai
import openai
from pydantic import ValidationError

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import DOMSnapshot, ExecutionPhase, LLMActionResponse, ResumeData
from jobcli.llm.ax_tree_extractor import AccessibilityTree


class LLMClient:
    """LLM client with structured output validation."""

    SYSTEM_PROMPT = """You are an expert autonomous UI/UX agent automating job applications.
Your task: Parse the provided Accessibility Snapshot and output the correct sequence of Playwright actions.

# Core Rules
1. ALWAYS ACT: Never set requires_human=true. You must always attempt to fill fields and click buttons.
2. LOCATORS: Use selector_type 'text' (exact accessible name from the snapshot) or 'role'.
3. SEQUENCE: Fill ALL visible form fields first -> upload resume -> click submit/continue.
4. FILL ACTION: Use action="fill" for text inputs, action="click" for buttons/links.
5. MATCH FIELDS: Map user info to form fields by their accessible name (e.g. textbox "First Name" -> first_name).

# Output Schema (Strict JSON)
{
  "actions": [
    {
      "action": "click" | "fill" | "type" | "select" | "upload" | "scroll" | "wait" | "ask",
      "selector": "<exact accessible name from snapshot>",
      "selector_type": "text" | "role" | "aria_label",
      "value": "<input value if filling/typing/selecting/asking>",
      "field_label": "<human readable field name>",
      "confidence": 0.95
    }
  ],
  "reasoning": "<1-2 sentence logic explanation>",
  "detected_ats": "greenhouse" | "lever" | "workday" | null,
  "detected_fields": ["<identified fields>"],
  "confidence": 0.95,
  "requires_human": false
}"""

    def __init__(
        self,
        provider: Literal["openai", "anthropic", "gemini"],
        api_key: str,
        logger: Optional[JobLogger] = None,
    ) -> None:
        """Initialize LLM client."""
        self.provider = provider
        self.api_key = api_key
        self.logger = logger

        if provider == "openai":
            self.client = openai.OpenAI(api_key=api_key)
            self.model = "gpt-4o"
        elif provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = "claude-3-5-sonnet-20241022"
        elif provider == "gemini":
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel("gemini-1.5-pro")
            self.model = "gemini-1.5-pro"

    def analyze_page(
        self,
        dom_snapshot: DOMSnapshot,
        resume: ResumeData,
        task: str = "find_apply_button",
    ) -> Optional[LLMActionResponse]:
        """Analyze page and return structured actions."""
        if self.logger:
            self.logger.info(
                f"Requesting LLM analysis from {self.provider}",
                phase=ExecutionPhase.LLM,
                task=task,
            )

        # Build prompt
        user_prompt = self._build_prompt(dom_snapshot, resume, task)

        max_retries = 3
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                if self.provider == "openai":
                    response = self._call_openai(user_prompt)
                elif self.provider == "anthropic":
                    response = self._call_anthropic(user_prompt)
                elif self.provider == "gemini":
                    response = self._call_gemini(user_prompt)
                else:
                    return None

                # Validate and parse response
                validated = self._validate_response(response)
                if validated:
                    return validated

                self.logger.warning(f"LLM validation failed on attempt {attempt + 1}", phase=ExecutionPhase.LLM)

            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"LLM request failed (attempt {attempt + 1}/{max_retries}): {e}",
                        phase=ExecutionPhase.LLM,
                        provider=self.provider,
                    )

            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))

        if self.logger:
            self.logger.error("All LLM attempts failed", phase=ExecutionPhase.LLM)
        return None

    def _build_prompt(
        self, dom_snapshot: DOMSnapshot, resume: ResumeData, task: str
    ) -> str:
        """Build prompt for LLM."""
        # Simplified DOM for token efficiency
        simplified_dom = {
            "url": dom_snapshot.url,
            "title": dom_snapshot.title,
            "buttons": dom_snapshot.buttons[:20],  # Limit to first 20
            "inputs": dom_snapshot.inputs[:20],
            "forms": dom_snapshot.forms[:5],
            "links": [l for l in dom_snapshot.links if "apply" in l.get("text", "").lower()][
                :10
            ],
        }

        # Build user info summary
        user_info = {
            "name": f"{resume.personal.first_name} {resume.personal.last_name}",
            "email": resume.personal.email,
            "phone": resume.personal.phone,
        }

        prompt = f"""Task: {task}

Page Information:
{json.dumps(simplified_dom, indent=2)}

User Information:
{json.dumps(user_info, indent=2)}

Please analyze the page and return the necessary actions to complete the task.
Remember to return valid JSON matching the schema in the system prompt.
"""

        return prompt

    def _call_openai(self, user_prompt: str) -> str:
        """Call OpenAI API."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from OpenAI")

        if self.logger:
            self.logger.info(
                "Received OpenAI response",
                phase=ExecutionPhase.LLM,
                tokens=response.usage.total_tokens if response.usage else 0,
            )

        return content

    def _call_anthropic(self, user_prompt: str) -> str:
        """Call Anthropic API."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0.1,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        content = response.content[0].text if response.content else ""
        if not content:
            raise ValueError("Empty response from Anthropic")

        if self.logger:
            self.logger.info(
                "Received Anthropic response",
                phase=ExecutionPhase.LLM,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        return content

    def _call_gemini(self, user_prompt: str) -> str:
        """Call Gemini API."""
        full_prompt = f"{self.SYSTEM_PROMPT}\n\n{user_prompt}"

        response = self.client.generate_content(
            full_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        content = response.text
        if not content:
            raise ValueError("Empty response from Gemini")

        if self.logger:
            self.logger.info(
                "Received Gemini response",
                phase=ExecutionPhase.LLM,
            )

        return content

    def _validate_response(self, response_text: str) -> Optional[LLMActionResponse]:
        """Validate and parse LLM response."""
        try:
            # Parse JSON
            data = json.loads(response_text)

            # Validate with Pydantic
            validated = LLMActionResponse(**data)

            if self.logger:
                self.logger.info(
                    "LLM response validated successfully",
                    phase=ExecutionPhase.LLM,
                    action_count=len(validated.actions),
                    confidence=validated.confidence,
                    requires_human=validated.requires_human,
                )

            return validated

        except json.JSONDecodeError as e:
            if self.logger:
                self.logger.error(
                    f"Failed to parse LLM response as JSON: {e}",
                    phase=ExecutionPhase.LLM,
                    response=response_text[:500],
                )
            return None

        except ValidationError as e:
            if self.logger:
                self.logger.error(
                    f"LLM response failed validation: {e}",
                    phase=ExecutionPhase.LLM,
                    response=response_text[:500],
                )
            return None

    def analyze_page_from_axtree(
        self,
        ax_tree: AccessibilityTree,
        resume: ResumeData,
        task: str = "find_apply_button",
        memory_context: Optional[str] = None,
        dropdown_options: Optional[list[dict[str, Any]]] = None,
        resume_pdf_path: Optional[str] = None,
    ) -> Optional[LLMActionResponse]:
        """Analyze page using Accessibility Tree (more token efficient)."""
        if self.logger:
            self.logger.info(
                f"Requesting LLM analysis from {self.provider} using AXTree",
                phase=ExecutionPhase.LLM,
                task=task,
            )

        # Build prompt with AXTree data (much more efficient)
        user_prompt = self._build_axtree_prompt(
            ax_tree, resume, task, memory_context, dropdown_options, resume_pdf_path
        )

        max_retries = 3
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                if self.provider == "openai":
                    response = self._call_openai(user_prompt)
                elif self.provider == "anthropic":
                    response = self._call_anthropic(user_prompt)
                elif self.provider == "gemini":
                    response = self._call_gemini(user_prompt)
                else:
                    return None

                # Validate and parse response
                validated = self._validate_response(response)
                if validated:
                    return validated

                self.logger.warning(f"LLM validation failed on attempt {attempt + 1}", phase=ExecutionPhase.LLM)

            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"LLM request failed (attempt {attempt + 1}/{max_retries}): {e}",
                        phase=ExecutionPhase.LLM,
                        provider=self.provider,
                    )

            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))

        if self.logger:
            self.logger.error("All LLM attempts failed via AXTree", phase=ExecutionPhase.LLM)
        return None

    def _build_axtree_prompt(
        self,
        ax_tree: AccessibilityTree,
        resume: ResumeData,
        task: str,
        memory_context: Optional[str] = None,
        dropdown_options: Optional[list[dict[str, Any]]] = None,
        resume_pdf_path: Optional[str] = None,
    ) -> str:
        """Build prompt using Accessibility Tree (token efficient)."""
        # Get the raw aria snapshot text if available — best for LLM reasoning
        raw_aria = getattr(ax_tree, "_raw_aria", "")

        # Build user info summary using full resume
        user_info = json.loads(resume.model_dump_json())
        
        if resume_pdf_path:
            user_info["resume_file_path"] = resume_pdf_path

        dropdown_context = ""
        if dropdown_options:
            dropdown_context = "\n## Pre-extracted Dropdown Options:\n"
            for dropdown in dropdown_options:
                opt_str = ", ".join(f"'{o}'" for o in dropdown["options"])
                dropdown_context += f"- '{dropdown['label']}': [{opt_str}]\n"

        instructions = (
            "1. You are filling out a job application. Check if the Apply button should be clicked first.\n"
            "2. Fill EVERY SINGLE visible form field with user info. DO NOT GUESS mandatory field values.\n"
            "3. **DATA PRIORITY CHAIN:** First use 'User Information'. If missing, use 'Known Answers from Agent Memory'.\n"
            "4. For dropdowns, your value MUST exactly match an option from 'Pre-extracted Dropdown Options' or be a valid option string.\n"
            "5. If a mandatory field answer is entirely missing, output action=\"ask\", selector=\"<exact field label>\", and value=\"<clarifying question>\".\n"
            "6. Use action=\"fill\" for text, action=\"click\" for buttons, action=\"select\" for dropdowns/comboboxes, action=\"upload\" for files.\n"
            "7. **DROPDOWNS**: If a field is a dropdown/select, you MUST use action=\"select\" and provide the exact option text as the value.\n"
            "8. **LOCATION fields**: For any Location/City/Address autocomplete field, use action=\"fill\" with value=\"City, State\" (e.g., \"Livermore, CA\").\n"
            "9. **FILE UPLOAD fields**: For Resume/Cover Letter upload fields, use action=\"upload\" with the selector being the field label and value being the resume_file_path from User Information.\n"
            "10. **COMPLIANCE SECTIONS**: You MUST look for and fill: Gender, Ethnicity/Race, Veteran Status, Disability Status, and Work Authorization questions. These are often at the bottom of the form.\n"
            "11. **REQUIRED FIELDS**: Look for 'required' or asterisk (*) markers. You MUST fill ALL required fields.\n"
            "12. After filling all fields, click 'Next', 'Continue', 'Submit', or 'Apply' button if visible.\n"
            "13. Complete all fields and submit the application if on the final page.\n"
        )
        if task == "fill_form_fields_only":
            instructions = "IMPORTANT - Target the Form directly. DO NOT CLICK APPLY.\n" + instructions
        elif task == "fill_empty_fields_only":
            instructions = "IMPORTANT - ONLY fill fields that are currently EMPTY or UNSELECTED. DO NOT re-fill fields that already have values unless they are incorrect.\n" + instructions

        prompt = f"""Task: {task}

Page URL: {ax_tree.url}
Page Title: {ax_tree.title}

## Accessibility Snapshot (screen-reader view of the page):
```
{raw_aria}
```

## Agent Memory Context (Known Answers & Strategies):
{memory_context or "No previous memory available."}
{dropdown_context}

## User Information to Fill:
{json.dumps(user_info, indent=2)}

## Instructions:
{instructions}
"""

        return prompt
