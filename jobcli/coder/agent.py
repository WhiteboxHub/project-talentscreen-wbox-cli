import re
import sys
from typing import List, Dict, Any, Tuple, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from jobcli.core.schemas import Config
from jobcli.coder.prompts import AGENT_SYSTEM_PROMPT
from jobcli.coder.tools import (
    list_dir,
    search_code,
    read_file,
    read_file_summary,
    replace_in_file,
    run_command
)

console = Console()

class CodingAgent:
    def __init__(self, config: Config):
        self.config = config
        self.provider = config.default_llm_provider
        self.messages: List[Dict[str, str]] = []
        
        # Tools mapping
        self.tools_map = {
            "list_dir": list_dir,
            "search_code": search_code,
            "read_file": read_file,
            "read_file_summary": read_file_summary,
            "replace_in_file": replace_in_file,
            "run_command": run_command
        }
        
    def _call_llm(self) -> str:
        """Sends the conversation history to the LLM and returns the text response."""
        # We instantiate clients inline to avoid messing with JobCLI's LLMClient json_mode
        if self.provider == "anthropic":
            import anthropic
            if not self.config.anthropic_api_key:
                raise ValueError("Anthropic API key is not configured.")
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                temperature=0.0,
                system=AGENT_SYSTEM_PROMPT,
                messages=self.messages
            )
            return response.content[0].text
            
        elif self.provider == "openai":
            import openai
            if not self.config.openai_api_key:
                raise ValueError("OpenAI API key is not configured.")
            client = openai.OpenAI(api_key=self.config.openai_api_key)
            # OpenAI requires system prompt in the messages list
            oai_msgs = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}] + self.messages
            response = client.chat.completions.create(
                model="gpt-4o",
                temperature=0.0,
                messages=oai_msgs
            )
            return response.choices[0].message.content or ""
            
        elif self.provider == "gemini":
            from google import genai
            if not self.config.gemini_api_key:
                raise ValueError("Gemini API key is not configured.")
            client = genai.Client(api_key=self.config.gemini_api_key)
            # Gemini expects system prompt in the first message or specialized config.
            # We'll inject it.
            gemini_msgs = f"SYSTEM: {AGENT_SYSTEM_PROMPT}\n\n"
            for m in self.messages:
                gemini_msgs += f"{m['role'].upper()}: {m['content']}\n\n"
            
            response = client.models.generate_content(
                model="gemini-1.5-pro",
                contents=gemini_msgs,
                config=genai.types.GenerateContentConfig(temperature=0.0)
            )
            return response.text or ""
            
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def _parse_response(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parses [THOUGHT], [ACTION], and [FINAL_ANSWER] blocks."""
        thought, action, final = None, None, None
        
        # Simple string extraction
        if "[THOUGHT]" in text:
            start = text.find("[THOUGHT]") + len("[THOUGHT]")
            end = text.find("[ACTION]")
            if end == -1:
                end = text.find("[FINAL_ANSWER]")
            if end == -1:
                end = len(text)
            thought = text[start:end].strip()
            
        if "[ACTION]" in text:
            start = text.find("[ACTION]") + len("[ACTION]")
            end = text.find("[FINAL_ANSWER]") if "[FINAL_ANSWER]" in text else len(text)
            action = text[start:end].strip()
            
        if "[FINAL_ANSWER]" in text:
            start = text.find("[FINAL_ANSWER]") + len("[FINAL_ANSWER]")
            final = text[start:].strip()
            
        return thought, action, final

    def _parse_tool_call(self, action_str: str) -> Tuple[Optional[str], List[Any], Dict[str, Any]]:
        """Parses 'tool_name(arg1="value", arg2=123)' into function, args, and kwargs."""
        action_str = action_str.strip()
        if not action_str:
            return None, [], {}
            
        try:
            import ast
            tree = ast.parse(action_str, mode='eval')
            if isinstance(tree.body, ast.Call):
                func_name = tree.body.func.id
                args = []
                for arg in tree.body.args:
                    args.append(ast.literal_eval(arg))
                kwargs = {}
                for kw in tree.body.keywords:
                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                return func_name, args, kwargs
        except Exception as e:
            return None, [], {"error": f"Failed to parse tool call. Syntax must be valid Python. Error: {e}"}
            
        return None, [], {}

    def _execute_tool(self, func_name: str, args: List[Any], kwargs: Dict[str, Any]) -> str:
        """Executes the requested tool locally, with safety prompts for dangerous actions."""
        if func_name not in self.tools_map:
            return f"Error: Tool '{func_name}' is not recognized."
            
        if func_name in ("run_command", "replace_in_file", "edit_file"):
            console.print(Panel(f"Tool: {func_name}\nArgs: {args}\nKwargs: {kwargs}", title="[bold red]Requires Approval[/bold red]"))
            if not Confirm.ask("Execute this action?", default=True):
                return "Error: User denied permission to execute this tool."
                
        try:
            func = self.tools_map[func_name]
            result = func(*args, **kwargs)
            return str(result)
        except Exception as e:
            return f"Error executing {func_name}: {e}"

    def run(self, prompt: str, max_steps: int = 12):
        """Runs the main agent loop."""
        console.print(Panel(prompt, title="[bold cyan]User Task[/bold cyan]", expand=False))
        self.messages.append({"role": "user", "content": prompt})
        
        step = 0
        while step < max_steps:
            step += 1
            console.print(f"\n[dim]--- Step {step}/{max_steps} ---[/dim]")
            
            try:
                with console.status(f"[bold cyan]Agent is thinking ({self.provider})...[/bold cyan]"):
                    response_text = self._call_llm()
            except Exception as e:
                console.print(f"[bold red]LLM Error:[/bold red] {e}")
                break
                
            self.messages.append({"role": "assistant", "content": response_text})
            
            thought, action, final = self._parse_response(response_text)
            
            if thought:
                console.print(f"[yellow][THOUGHT][/yellow]\n{thought}")
                
            if final:
                console.print(Panel(final, title="[bold green]Task Complete[/bold green]", expand=False))
                break
                
            if action:
                console.print(f"[blue][ACTION][/blue]\n{action}")
                func_name, args, kwargs = self._parse_tool_call(action)
                
                if func_name:
                    observation = self._execute_tool(func_name, args, kwargs)
                else:
                    observation = kwargs.get("error", "No valid tool call found in ACTION block.")
                    
                console.print(f"[magenta][OBSERVATION][/magenta]\n{str(observation)[:500]}..." if len(str(observation)) > 500 else f"[magenta][OBSERVATION][/magenta]\n{observation}")
                
                # Format exactly as requested
                obs_block = f"[OBSERVATION]\n{observation}\n"
                self.messages.append({"role": "user", "content": obs_block})
            else:
                if not final:
                    self.messages.append({"role": "user", "content": "Error: You must output an [ACTION] or [FINAL_ANSWER] block."})
                    
        if step >= max_steps:
            console.print("[bold red]Agent reached maximum steps and was terminated.[/bold red]")
