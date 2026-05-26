"""LLM client with structured output for OpenAI, Anthropic, Gemini, and Claude."""

import json
import time
from typing import Literal, Optional, Any

import anthropic
import httpx
from google import genai
import openai
from pydantic import ValidationError

from jobcli.profile.derived_profile import derived_country_for_resume, derived_pronouns_for_resume
from jobcli.profile.resume_normalize import normalize_linkedin_url
from jobcli.utils.logger import JobLogger
from jobcli.profile.schemas import (
    ActionType,
    DOMSnapshot,
    ExecutionPhase,
    LLMActionResponse,
    ResumeData,
)
from jobcli.utils.tls import httpx_verify, is_insecure, strategy as tls_strategy
from jobcli.llm.ax_tree_extractor import AccessibilityTree


# How long to wait per LLM HTTP call. The OpenAI SDK's default is generous
# (10 min) which means TLS failures can hang for a while before raising.
_LLM_HTTP_TIMEOUT_SECONDS = 60.0


def _build_httpx_client() -> httpx.Client:
    """Build an httpx.Client wired through the JobCLI TLS configuration.

    All three SDKs we use (OpenAI, Anthropic, google-genai) accept a custom
    ``http_client`` / transport, so this single factory keeps trust roots,
    timeouts, and proxy behavior consistent. Honoring
    ``JOBCLI_INSECURE_TLS=1`` here is the difference between "fix-it-with-an-
    env-var" and "user has to reinstall corporate root CAs system-wide".
    """
    return httpx.Client(verify=httpx_verify(), timeout=_LLM_HTTP_TIMEOUT_SECONDS)


def _is_tls_error(exc: BaseException) -> bool:
    """Returns True iff *exc* (or any chained cause) is a TLS verification error.

    The OpenAI SDK wraps TLS failures as ``APIConnectionError("Connection
    error.")`` which is uselessly opaque. We walk ``__cause__`` to find the
    underlying ``SSLCertVerificationError`` / ``ssl.SSLError``.
    """
    import ssl

    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, (ssl.SSLError, ssl.SSLCertVerificationError)):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(cur) or "SSL" in type(cur).__name__:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _tls_remediation_hint() -> str:
    """One-line remediation tailored to the active TLS strategy."""
    s = tls_strategy()
    if s == "insecure":
        return (
            "JOBCLI_INSECURE_TLS is already on but the connection still failed. "
            "Check your network/proxy."
        )
    if s == "ca-bundle":
        return (
            "JOBCLI_SSL_CA_BUNDLE is set but doesn't trust this host. Make sure "
            "the PEM contains your corporate root chain."
        )
    return (
        "TLS certificate verification failed. On Windows, install your corporate "
        "root CA into 'Trusted Root Certification Authorities', or set "
        "JOBCLI_SSL_CA_BUNDLE=<path-to-ca.pem>. As a last resort run with "
        "JOBCLI_INSECURE_TLS=1 (insecure)."
    )


class TLSConnectionError(RuntimeError):
    """Raised when an LLM call fails because of TLS trust issues.

    Carrying this type up the stack lets the caller (the apply engine) surface
    a meaningful "fix your trust store" message instead of the generic AI-
    unavailable hand-off panel.
    """


class LLMClient:
    """LLM client with structured output validation supporting multiple providers."""

    SYSTEM_PROMPT = """You are an expert autonomous UI/UX agent automating job applications.
Your task: Parse the provided Accessibility Snapshot and output the correct sequence of Playwright actions.

# Core Rules
1. ALWAYS ACT: Never set requires_human=true. You must always attempt to fill fields and click buttons.
2. LOCATORS: Use selector_type 'text' (exact accessible name from the snapshot) or 'role'.
3. SEQUENCE: Fill ALL visible form fields first -> upload resume -> click submit/continue.
4. FILL ACTION: Use action="fill" for text inputs, action="click" for buttons/links.
5. MATCH FIELDS: Map user info to form fields by their accessible name (e.g. textbox "First Name" -> first_name).

# Work authorization and legal (mandatory)
- Use ONLY the structured User Information JSON and "Agent Memory Context" for work eligibility, visa/sponsorship, and right-to-work answers. Never contradict those sources.
- If the JSON says the user is not authorized or requires sponsorship, reflect that exactly in the form.
- Do not invent employers, degrees, or government statuses not present in the provided data.

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
        provider: Literal["openai", "anthropic", "gemini", "claude"],
        api_key: str,
        logger: Optional[JobLogger] = None,
    ) -> None:
        """Initialize LLM client.

        Every SDK is constructed with an ``http_client`` (or ``http_options``)
        that honors :func:`jobcli.utils.tls.httpx_verify`. That single seam is
        why ``JOBCLI_INSECURE_TLS=1`` / ``JOBCLI_SSL_CA_BUNDLE`` work uniformly
        across OpenAI, Anthropic, and Gemini without per-SDK monkey patching.
        """
        self.provider = provider
        self.api_key = api_key
        self.logger = logger

        if provider == "openai":
            self.client = openai.OpenAI(api_key=api_key, http_client=_build_httpx_client())
            self.model = "gpt-4o"
        elif provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=api_key, http_client=_build_httpx_client())
            self.model = "claude-3-5-sonnet-20241022"
        elif provider == "gemini":
            # google-genai routes through google.auth's transport. Setting
            # SSL_CERT_FILE / REQUESTS_CA_BUNDLE in configure_tls() is the
            # cross-version-safe knob; with truststore injected (default) the
            # OS root store is already used. JOBCLI_INSECURE_TLS still works
            # via the env-var fallback because google-genai inspects them.
            self.client = genai.Client(api_key=api_key)
            self.model = "gemini-1.5-pro"
        elif provider == "claude":
            self.client = anthropic.Anthropic(api_key=api_key, http_client=_build_httpx_client())
            self.model = "claude-3-5-sonnet-20241022"

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

                if self.logger:
                    self.logger.warning(f"LLM validation failed on attempt {attempt + 1}", phase=ExecutionPhase.LLM)

            except Exception as e:
                # Fail fast on TLS — retrying will never succeed, and the
                # opaque "Connection error." line in the user terminal is
                # frustrating. Raise a typed error so the caller can render
                # a real remediation message.
                if _is_tls_error(e):
                    hint = _tls_remediation_hint()
                    if self.logger:
                        self.logger.error(
                            f"LLM request failed due to TLS trust: {hint}",
                            phase=ExecutionPhase.LLM,
                            provider=self.provider,
                        )
                    raise TLSConnectionError(hint) from e

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

    def _call_openai(self, user_prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        """Call OpenAI API."""
        s_prompt = system_prompt if system_prompt is not None else self.SYSTEM_PROMPT
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": s_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1 if json_mode else 0.7,
            response_format={"type": "json_object"} if json_mode else None,
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

    def _call_anthropic(self, user_prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        """Call Anthropic API."""
        s_prompt = system_prompt if system_prompt is not None else self.SYSTEM_PROMPT
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0.1 if json_mode else 0.7,
            system=s_prompt,
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

    def _call_gemini(self, user_prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        """Call Gemini API."""
        # Use provided system_prompt OR the default one, but don't mix them for chat.
        s_prompt = system_prompt if system_prompt is not None else self.SYSTEM_PROMPT
        
        # Merge if it's the default prompt, otherwise just use the override
        if system_prompt is None:
            full_prompt = f"{s_prompt}\n\n{user_prompt}"
        else:
            full_prompt = f"SYSTEM: {s_prompt}\n\nUSER: {user_prompt}"

        config = genai.types.GenerateContentConfig(
            temperature=0.1 if json_mode else 0.7,
        )
        if json_mode:
            config.response_mime_type = "application/json"

        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config=config,
        )

        content = response.text
        if not content:
            raise ValueError("Empty response from Gemini")

        return content

    def general_chat(self, message: str) -> str:
        """General non-structured chat with the agent."""
        system_prompt = (
            "You are JobCLI, an advanced AI job application assistant. "
            "Help the user with job search strategy, profile optimization, or just general conversation. "
            "Keep responses concise and terminal-friendly (use ANSI colors if helpful, but sparingly)."
        )
        if self.provider == "gemini":
            return self._call_gemini(message, system_prompt=system_prompt, json_mode=False)
        elif self.provider == "openai":
            return self._call_openai(message, system_prompt=system_prompt, json_mode=False)
        elif self.provider in ("anthropic", "claude"):
            return self._call_anthropic(message, system_prompt=system_prompt, json_mode=False)
        return "Chat not implemented for this provider yet."

    @staticmethod
    def _propagate_required_flag(
        validated: "LLMActionResponse",
        ax_tree: "AccessibilityTree",
    ) -> None:
        """Copy ``required=True`` from the AX tree onto each FILL/TYPE/SELECT
        action whose target field is marked required.

        The match is on a normalized lowercase label so it survives the
        LLM's tendency to use the user-visible field title as the selector
        (e.g. ``"First Name"``) rather than the underlying attribute
        (``#first_name``).
        """
        required_labels: set[str] = set()
        for f in getattr(ax_tree, "form_fields", []) or []:
            if not f.get("required"):
                continue
            for key in ("name", "label", "placeholder"):
                val = f.get(key)
                if isinstance(val, str) and val.strip():
                    required_labels.add(val.strip().lower())
        if not required_labels:
            return

        for act in validated.actions:
            if act.action not in (
                ActionType.FILL,
                ActionType.TYPE,
                ActionType.SELECT,
                ActionType.ASK,
            ):
                continue
            lbl = (act.field_label or act.selector or "").strip().lower()
            if not lbl:
                continue
            if "*" in (act.field_label or act.selector or ""):
                act.required = True
                continue
            if lbl in required_labels or any(rl in lbl or lbl in rl for rl in required_labels):
                act.required = True

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
                    # Propagate the ``required`` flag from the AX tree onto
                    # each fill/select action so the human-handoff prompt
                    # can split fields into "must answer" vs "skip with
                    # Enter" without re-inspecting the DOM.
                    self._propagate_required_flag(validated, ax_tree)
                    return validated

                if self.logger:
                    self.logger.warning(f"LLM validation failed on attempt {attempt + 1}", phase=ExecutionPhase.LLM)

            except Exception as e:
                if _is_tls_error(e):
                    hint = _tls_remediation_hint()
                    if self.logger:
                        self.logger.error(
                            f"LLM request failed due to TLS trust: {hint}",
                            phase=ExecutionPhase.LLM,
                            provider=self.provider,
                        )
                    raise TLSConnectionError(hint) from e

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

        # Build user info summary using full resume (+ explicit deterministic hints)
        user_info: dict[str, Any] = json.loads(resume.model_dump_json())
        personal = user_info.get("personal")
        if isinstance(personal, dict):
            li = normalize_linkedin_url(personal.get("linkedin"))
            personal["linkedin"] = li
        derived: dict[str, str] = {}
        if not (resume.personal.country and str(resume.personal.country).strip()):
            dc = derived_country_for_resume(resume)
            if dc:
                derived["inferred_country_from_location"] = dc
        demo = resume.demographics
        if not (demo and demo.pronouns and str(demo.pronouns).strip()):
            pr = derived_pronouns_for_resume(resume)
            if pr:
                derived["inferred_pronouns_from_gender"] = pr
        if derived:
            user_info["_derived_hints"] = derived

        if resume_pdf_path:
            user_info["resume_file_path"] = resume_pdf_path

        dropdown_context = ""
        if dropdown_options:
            dropdown_context = "\n## Pre-extracted Dropdown Options:\n"
            for dropdown in dropdown_options:
                opt_str = ", ".join(f"'{o}'" for o in dropdown["options"])
                dropdown_context += f"- '{dropdown['label']}': [{opt_str}]\n"

        instructions = (
            "0. **APPLY BUTTON RULE (CRITICAL)**: When you need to click an Apply button, "
            "you MUST click ONLY the *native* Apply button on this page — labels like "
            "\"Apply\", \"Apply Now\", \"Apply for this Job\", \"Submit Application\", or "
            "\"Start Application\". You MUST NEVER click third-party / federated apply "
            "variants such as: \"Apply with LinkedIn\", \"Easy Apply\", \"Apply with Indeed\", "
            "\"Apply with Google\", \"Apply with Facebook\", \"Apply via Glassdoor\", "
            "\"Apply with ZipRecruiter\", \"Sign in with …\", \"Continue with …\", or any "
            "button whose visible text, aria-label, class, or surrounding container mentions "
            "linkedin, indeed, glassdoor, google, facebook, ziprecruiter, monster, seek, "
            "naukri, xing, oauth, sso, easy apply, sign in, or continue with. These open "
            "external login flows that the agent cannot drive. If the only apply-style "
            "button available is third-party, output action=\"ask\" with a clarifying "
            "question instead of clicking it.\n"
            "1. You are filling out a job application. Check if the Apply button should be clicked first.\n"
            "2. Fill EVERY SINGLE visible form field. **CRITICAL**: If a field already has a non-empty `value` in the snapshot (meaning it was autofilled), DO NOT emit an action for it. Leave it alone! Only fill fields that are empty. DO NOT GUESS mandatory field values.\n"
            "2b. **OPTIONAL FIELDS**: Do NOT emit actions for optional fields (no * / not required) when you have no value. Leave them blank.\n"
            "3. **DATA PRIORITY CHAIN:** First use 'User Information'. If missing, use 'Known Answers from Agent Memory'.\n"
            "4. For dropdowns, your value MUST exactly match an option from 'Pre-extracted Dropdown Options' or be a valid option string.\n"
            "5. Use action=\"ask\" ONLY for mandatory fields (marked required or with * in the label). "
            "NEVER ask about optional fields — leave them empty. "
            "NEVER use the literal word \"skip\" as a fill value.\n"
            "5b. For mandatory fields with a missing answer, output action=\"ask\", selector=\"<exact field label>\", and value=\"<clarifying question>\".\n"
            "6. Use action=\"fill\" for text, action=\"click\" for buttons, action=\"select\" for dropdowns/comboboxes, action=\"upload\" for files.\n"
            "7. **DROPDOWNS — CRITICAL, READ CAREFULLY**: A field is a dropdown if ANY of the following is true:\n"
            "   - it appears in the 'Pre-extracted Dropdown Options' list above;\n"
            "   - its accessibility role is `combobox`, `listbox`, `menu`, or `select`;\n"
            "   - it has `aria-haspopup`, `aria-autocomplete`, or its name ends with patterns like 'Select…', 'Choose…', a chevron arrow ▾, or shows a placeholder like 'Select an option'.\n"
            "   For EVERY dropdown you MUST use `action=\"select\"`. NEVER use `fill` or `type` on a dropdown — typing into a closed dropdown does NOTHING and the application silently breaks. If you are unsure whether a field is a dropdown, prefer `select`.\n"
            "   The `value` MUST be the visible text of one of the dropdown's options (use the exact option text from 'Pre-extracted Dropdown Options' when listed). For yes/no compliance questions, use 'Yes' / 'No' as written in the option list.\n"
            "7b. **REQUIRED FIELDS FIRST — DO NOT SKIP**: Before emitting ANY click on a Next / Continue / Save & Continue / Submit / Apply / Review button, you MUST verify that EVERY field marked with an asterisk (*) or `required` in the snapshot has a non-empty value. If even ONE required field is empty, DO NOT click Next/Submit. Instead, output `action=\"fill\"`/`\"select\"` for those fields if you can derive the answer, otherwise output `action=\"ask\"` for each missing required field. The system will pause for the human to provide them. Pressing Next while required fields are empty triggers form-validation errors and wastes the application.\n"
            "8. **LOCATION fields**: Build a single value from `personal` in User Information (city, state, zip, country) — "
            "e.g. \"Livermore, CA, 94550, United States\" or at minimum \"City, State\" (e.g. \"San Jose, California\"). "
            "If there is a dedicated *Location* search or typeahead, use that string; if there are separate address fields, "
            "distribute the same data across address line, city, state, postal, country. Never leave Location empty when city "
            "or state exists in the JSON.\n"
            "9. **FILE UPLOAD fields**: For required Resume/Cover Letter upload fields (usually near the bottom), use action=\"upload\" with the selector being the field label and value being the resume_file_path from User Information. **NEVER** upload a resume to a button labelled 'Autofill with Resume', 'Parse Resume', or 'Upload file' if it is inside an 'Autofill' section — these are for extracting text, which we already have in JSON. Only upload where the actual file attachment is requested (usually labeled 'Resume/CV' or 'Resume' with a required asterisk).\n"
            "10. **COMPLIANCE SECTIONS**: You MUST look for and fill: Gender, Ethnicity/Race, Veteran Status, Disability Status, and Work Authorization questions. These are often at the bottom of the form.\n"
            "11. **REQUIRED FIELDS**: Look for 'required' or asterisk (*) markers. You MUST fill ALL required fields.\n"
            "12. After filling all fields, click 'Next', 'Continue', 'Submit', or 'Apply' button if visible.\n"
            "13. Complete all fields and submit the application if on the final page.\n"
            "14. **EDUCATION / SCHOOLING — ITERATE EVERY ENTRY**: The `education` array in User Information contains ONE OR MORE "
            "schools. You MUST fill EVERY entry, not just the first:\n"
            "   a. For entry `education[0]`: if the section is empty, click the section's **Add** / **+ Add Education** button "
            "      FIRST to reveal the sub-form, then fill school, degree, field_of_study, gpa, graduation_year.\n"
            "   b. For entries `education[1]`, `education[2]`, …: emit another `click` on **Add** / **Add Another** / "
            "      **+ Add Education** BEFORE filling that entry's fields. Do not try to overwrite the previous entry.\n"
            "   c. If the sub-form has its own **Save** / **Done** / **OK** button, emit a `click` on it after each entry's "
            "      fields are filled. Many Workday tenants require this per row.\n"
            "   d. Never leave degree, field of study, or graduation_year empty when the JSON has values.\n"
            "15. **WORK EXPERIENCE — ITERATE EVERY ENTRY**: The `experience` array in User Information contains ONE OR MORE "
            "jobs. You MUST fill EVERY entry, not just the first:\n"
            "   a. For entry `experience[0]`: if the section is empty, click **Add** / **+ Add Experience** FIRST, then fill "
            "      company, title (as 'Job Title' / 'Position Title'), start_date, end_date, description.\n"
            "   b. For entries `experience[1]`, `experience[2]`, …: emit another `click` on **Add** / **Add Another** / "
            "      **+ Add Work Experience** BEFORE filling that entry's fields. Do not overwrite the previous job.\n"
            "   c. Use `experience[n].description` for responsibilities / role description / summary / highlights fields. "
            "      If that field is **empty** in the JSON, write 2–4 sentences of **professional highlights** from the same "
            "   User Information: pull from `skills[]`, `education[]`, and other `experience[]` entries — do not leave description "
            "   boxes empty when the profile has any skills or work history.\n"
            "   d. If the sub-form has its own **Save** / **Done** button, emit a `click` on it after each entry.\n"
            "   e. If `experience[n].current` is true, tick any 'I currently work here' / 'Present' checkbox and leave end_date "
            "      blank. Otherwise, always fill end_date.\n"
            "15b. **CERTIFICATIONS / LICENSES**: The `certifications` array in User Information lists named certs only. "
            "   If the array is **absent, empty, or all blank**, do **NOT** type anything into certification/license fields — do "
            "   not invent credentials. If and only if the array has one or more strings, click **Add** (if needed) and enter "
            "   those exact values.\n"
            "16. **LinkedIn (optional)**: Only fill if `personal.linkedin` is a full `https://www.linkedin.com/in/.../` URL in User Information. "
            "If it is null or missing, leave the LinkedIn field **blank** — do not type placeholders or partial handles (ATS validation will fail).\n"
            "17. **COMMON SENSE DEDUCTION & LONG-FORM ANSWERS**: Act as a human proxy using aggressive common sense.\n"
            "   a. If a form asks for a value that is NOT explicitly in the exact form in the JSON, intelligently deduce it. "
            "For example: derive Country (United States) from City (San Francisco); logically deduce pronouns (he/him) & sexual orientation (heterosexual/straight) from Gender (Male); "
            "map raw boolean work auth JSON to exact phrase requirements ('Yes, I am authorized', 'No, I do not need sponsorship'). Do NOT be overly strict.\n"
            "   b. If the form asks an open-ended long-form question (e.g., 'Describe a project you are proud of', 'Why do you want to work here?', 'What are your career goals?'), DO NOT write the same generic robotic answer every time. Tailor a unique, compelling, professional, and thoughtful 2-4 sentence response specifically addressing the exact prompt. Write from the first-person perspective, draw organically upon the user's specific skills and experience from the JSON, and make it sound like a real human wrote it. Do not hallucinate experience that isn't in the JSON.\n"
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
