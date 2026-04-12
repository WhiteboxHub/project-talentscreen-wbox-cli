"""LLM client with structured output for OpenAI, Anthropic, and Gemini."""

import json
from typing import Literal, Optional

import anthropic
import google.generativeai as genai
import openai
from pydantic import ValidationError

from jobcli.core.logger import JobLogger
from jobcli.core.schemas import DOMSnapshot, ExecutionPhase, LLMActionResponse, ResumeData
from jobcli.llm.ax_tree_extractor import AccessibilityTree


class LLMClient:
    """LLM client with structured output validation."""

    SYSTEM_PROMPT = """You are an expert at analyzing web pages for job applications.
Your task is to identify form fields, buttons, and the correct sequence of actions to complete a job application.

You MUST return valid JSON matching this schema:
{
  "actions": [
    {
      "action": "click" | "type" | "select" | "upload" | "scroll" | "wait",
      "selector": "CSS selector or XPath",
      "selector_type": "css" | "xpath" | "text",
      "value": "value to enter (for type/select actions)",
      "field_label": "human-readable field name",
      "confidence": 0.0 to 1.0
    }
  ],
  "reasoning": "brief explanation of your analysis",
  "detected_ats": "greenhouse" | "lever" | "workday" | null,
  "detected_fields": ["list", "of", "field", "names"],
  "confidence": 0.0 to 1.0,
  "requires_human": false
}

Rules:
1. Only return actions you are confident about (confidence > 0.7)
2. Use CSS selectors when possible (more reliable than XPath)
3. Set requires_human=true if you cannot determine the right actions
4. Return actions in the correct order
5. Be conservative - it's better to ask for human help than make mistakes
"""

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
            self.model = "gpt-4-turbo-preview"
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

        # Call appropriate provider
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
            return self._validate_response(response)

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"LLM request failed: {e}",
                    phase=ExecutionPhase.LLM,
                    provider=self.provider,
                )
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
    ) -> Optional[LLMActionResponse]:
        """Analyze page using Accessibility Tree (more token efficient)."""
        if self.logger:
            self.logger.info(
                f"Requesting LLM analysis from {self.provider} using AXTree",
                phase=ExecutionPhase.LLM,
                task=task,
            )

        # Build prompt with AXTree data (much more efficient)
        user_prompt = self._build_axtree_prompt(ax_tree, resume, task)

        # Call appropriate provider
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
            return self._validate_response(response)

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"LLM request failed: {e}",
                    phase=ExecutionPhase.LLM,
                    provider=self.provider,
                )
            return None

    def _build_axtree_prompt(
        self, ax_tree: AccessibilityTree, resume: ResumeData, task: str
    ) -> str:
        """Build prompt using Accessibility Tree (token efficient)."""
        # Extract summary - much smaller than full DOM
        summary = {
            "url": ax_tree.url,
            "title": ax_tree.title,
            "buttons": ax_tree.buttons[:15],
            "form_fields": ax_tree.form_fields[:20],
            "links": [l for l in ax_tree.links if "apply" in l.get("name", "").lower()][:10],
        }

        # Build user info summary
        user_info = {
            "name": f"{resume.personal.first_name} {resume.personal.last_name}",
            "email": resume.personal.email,
            "phone": resume.personal.phone,
        }

        prompt = f"""Task: {task}

Page Accessibility Tree (optimized):
{json.dumps(summary, indent=2)}

User Information:
{json.dumps(user_info, indent=2)}

Please analyze the page and return the necessary actions to complete the task.
Return valid JSON matching the schema in the system prompt.

Focus on:
- Buttons with names containing "apply", "submit", "continue"
- Form fields that need user information
- The correct sequence of actions
"""

        return prompt
