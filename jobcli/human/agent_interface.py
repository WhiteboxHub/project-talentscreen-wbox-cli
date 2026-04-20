"""Unified agent interface — integrates human-in-the-loop inline with auto-apply.

Instead of a separate "human phase", this interface is called at checkpoints
throughout the agent loop, similar to how Claude Code works: the agent runs
autonomously but pauses at key moments for human review / input / confirmation.

Key behaviours:
  * Every human-facing prompt first checks ``AgentMemory`` for a similar
    answer.  If found, it is used silently (or shown as default).
  * Every answer the human gives is persisted to the DB via ``AgentMemory``
    with source="human", so the next job's agent loop will reuse it.
  * When asking, the agent loop is expected to STOP filling other fields
    until ``request_field_input()`` returns — see ``_agent_fill_loop`` in
    engine.py for the wait-and-re-scan pattern.
"""

import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from playwright.sync_api import Page
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from jobcli.core.logger import JobLogger
from jobcli.core.locator_schemas import LearnedLocator
from jobcli.core.schemas import (
    ATSType,
    BrowserAction,
    ActionType,
    ExecutionPhase,
    InteractionMode,
    ResumeData,
    SelectorType,
)
from jobcli.storage.repositories import LearnedLocatorRepository

if TYPE_CHECKING:
    from jobcli.core.memory import AgentMemory


@dataclass
class HandoffResult:
    """Result returned after a human takes manual control of the browser.

    The engine uses this to decide whether to *resume from the human's current
    page* (skipping any phase the human already completed) instead of retrying
    whatever the agent originally got stuck on.
    """

    page: Page                 # current page reference (may be a new tab)
    url_before: str            # URL when handoff started
    url_after: str             # URL when human handed control back
    title_after: str           # title of current page after handoff
    advanced: bool             # True if human navigated to a different URL
    cancelled: bool = False    # human chose to abort the application


class AgentInterface:
    """Single entry-point for every human-facing interaction during the agent loop.

    Behaviour adapts to the current ``InteractionMode``:
    * AUTO       – never blocks; returns safe defaults.
    * SUPERVISED – blocks only at safety-critical checkpoints (submit, captcha,
                   missing mandatory info, low-confidence actions).
    * MANUAL     – blocks at every checkpoint for explicit approval.
    """

    def __init__(
        self,
        page: Page,
        locator_repo: LearnedLocatorRepository,
        mode: InteractionMode = InteractionMode.SUPERVISED,
        logger: Optional[JobLogger] = None,
        memory: Optional["AgentMemory"] = None,
        resume: Optional[ResumeData] = None,
        ats_type: ATSType = ATSType.UNKNOWN,
    ) -> None:
        self.page = page
        self.locator_repo = locator_repo
        self.mode = mode
        self.logger = logger
        self.memory = memory
        self.resume = resume
        self.ats_type = ats_type
        self.console = Console()
        # Track which (label, value) pairs we already saved this session — avoids
        # re-saving the same answer many times during multi-page form loops.
        self._saved_this_session: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # DB integration helpers (memory-aware)
    # ------------------------------------------------------------------

    def set_context(
        self,
        *,
        memory: Optional["AgentMemory"] = None,
        resume: Optional[ResumeData] = None,
        ats_type: Optional[ATSType] = None,
    ) -> None:
        """Update memory / resume / ats_type after construction (e.g. once detected)."""
        if memory is not None:
            self.memory = memory
        if resume is not None:
            self.resume = resume
        if ats_type is not None:
            self.ats_type = ats_type

    def lookup_db_answer(self, field_label: str) -> tuple[Optional[str], str]:
        """Check the DB for a previously-saved answer to a similar question.

        Uses ``AgentMemory.get_best_answer`` which already does:
          1. resume JSON match
          2. saved memory for THIS ATS
          3. universal saved memory across all ATSes
        Returns ``(value, source)`` or ``(None, "not_found")``.
        """
        if not self.memory or not field_label:
            return None, "not_found"
        return self.memory.get_best_answer(field_label, self.ats_type, self.resume)

    def persist_human_answer(self, field_label: str, value: str) -> bool:
        """Save a human-supplied answer to the DB so future jobs can reuse it."""
        if not self.memory or not field_label or not value:
            return False
        key = (field_label.strip().lower(), value.strip())
        if key in self._saved_this_session:
            return False
        self._saved_this_session.add(key)
        saved = self.memory.save_field_answer(
            field_label, value, self.ats_type, success=True, source="human"
        )
        if saved and self.logger:
            self.logger.info(
                f"Saved human answer for '{field_label}' to DB.",
                phase=ExecutionPhase.HUMAN,
            )
        return saved

    # ------------------------------------------------------------------
    # Browser-side attention helpers
    # ------------------------------------------------------------------
    #
    # When the terminal needs the human, the human is almost certainly
    # looking at the BROWSER, not the terminal.  These helpers make the
    # request impossible to miss:
    #
    #   * inject a top-of-page yellow banner overlay into the live page
    #   * bring the browser window to the foreground (Mac: dock bounce)
    #   * ring the terminal bell (most terminals flash + dock-bounce)
    #   * (best-effort) show a macOS system notification
    #
    # All steps are wrapped in try/except so headless / closed pages /
    # cross-origin frames never break the agent loop.

    _OVERLAY_ID = "__jobcli_handoff_overlay__"

    def show_browser_overlay(
        self,
        title: str,
        message: str,
        *,
        kind: str = "warning",  # "warning" | "info" | "error"
        fields: Optional[list[str]] = None,
    ) -> None:
        """Inject a fixed top banner into the browser page so the human sees
        a clear visual cue WHILE looking at the form.  The banner persists
        until ``clear_browser_overlay()`` is called or the page navigates."""
        try:
            color = {
                "info":    {"bg": "#1d4ed8", "border": "#1e3a8a"},   # blue
                "warning": {"bg": "#f59e0b", "border": "#b45309"},   # amber
                "error":   {"bg": "#dc2626", "border": "#7f1d1d"},   # red
            }.get(kind, {"bg": "#f59e0b", "border": "#b45309"})

            field_list_html = ""
            if fields:
                items = "".join(f"<li>{self._escape_html(f)}</li>" for f in fields[:8])
                if len(fields) > 8:
                    items += f"<li>… and {len(fields) - 8} more</li>"
                field_list_html = (
                    f"<ul style='margin:6px 0 0 18px;padding:0;font-size:13px;line-height:1.4'>{items}</ul>"
                )

            self.page.evaluate(
                """({id, title, message, color, fieldsHtml}) => {
                    const old = document.getElementById(id);
                    if (old) old.remove();
                    const bar = document.createElement('div');
                    bar.id = id;
                    bar.setAttribute('data-jobcli', 'handoff');
                    bar.style.cssText = `
                        position: fixed !important;
                        top: 0 !important;
                        left: 0 !important;
                        right: 0 !important;
                        z-index: 2147483647 !important;
                        background: ${color.bg} !important;
                        color: #ffffff !important;
                        padding: 14px 20px !important;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
                        font-size: 15px !important;
                        line-height: 1.4 !important;
                        box-shadow: 0 4px 14px rgba(0,0,0,0.35) !important;
                        border-bottom: 4px solid ${color.border} !important;
                        animation: jobcli-pulse 1.4s ease-in-out infinite !important;
                    `;
                    bar.innerHTML = `
                        <div style="max-width:1200px;margin:0 auto;display:flex;align-items:center;gap:14px">
                            <div style="font-size:28px;line-height:1">⏸︎</div>
                            <div style="flex:1">
                                <div style="font-weight:700;font-size:16px;margin-bottom:2px">${title}</div>
                                <div style="opacity:0.95">${message}</div>
                                ${fieldsHtml}
                                <div style="margin-top:6px;font-size:12px;opacity:0.85">
                                    JobCLI is waiting in the terminal — finish here, then return to the terminal and press ENTER.
                                </div>
                            </div>
                        </div>
                    `;
                    if (!document.getElementById(id + '-style')) {
                        const style = document.createElement('style');
                        style.id = id + '-style';
                        style.textContent = `
                            @keyframes jobcli-pulse {
                                0%, 100% { box-shadow: 0 4px 14px rgba(0,0,0,0.35); }
                                50%      { box-shadow: 0 4px 22px ${color.bg}; }
                            }
                            body { padding-top: 0 !important; }
                        `;
                        document.head.appendChild(style);
                    }
                    document.documentElement.appendChild(bar);
                }""",
                {
                    "id": self._OVERLAY_ID,
                    "title": title,
                    "message": message,
                    "color": color,
                    "fieldsHtml": field_list_html,
                },
            )
        except Exception:
            pass

    def clear_browser_overlay(self) -> None:
        """Remove the in-page banner if it's there."""
        try:
            self.page.evaluate(
                """(id) => {
                    const el = document.getElementById(id);
                    if (el) el.remove();
                }""",
                self._OVERLAY_ID,
            )
        except Exception:
            pass

    def get_attention(self) -> None:
        """Make sure the human notices the request — bring the browser to the
        front, ring the terminal bell, and (on macOS) show a system
        notification.  Best-effort, silently fails on unsupported setups."""
        try:
            self.page.bring_to_front()
        except Exception:
            pass
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass
        try:
            if sys.platform == "darwin":
                import subprocess
                subprocess.Popen(
                    [
                        "osascript", "-e",
                        'display notification "Open the browser to continue." with title "JobCLI: human input required" sound name "Glass"',
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    @staticmethod
    def _escape_html(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    # ------------------------------------------------------------------
    # Status / progress helpers
    # ------------------------------------------------------------------

    def show_status(self, message: str, *, phase: Optional[ExecutionPhase] = None) -> None:
        phase_icon = {"rules": "[blue]R[/blue]", "llm": "[magenta]AI[/magenta]", "human": "[yellow]H[/yellow]"}
        prefix = phase_icon.get(phase.value, "[dim]>[/dim]") if phase else "[dim]>[/dim]"
        self.console.print(f"  {prefix} {message}")

    def show_action_plan(self, actions: list[BrowserAction]) -> None:
        """Display what the agent is about to do (like Claude Code's tool-use display)."""
        if not actions:
            return
        table = Table(title="Agent Action Plan", show_lines=True, expand=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Action", style="cyan", width=8)
        table.add_column("Target", style="green")
        table.add_column("Value", style="yellow")
        for i, a in enumerate(actions, 1):
            label = a.field_label or a.selector
            val = (a.value or "")[:60]
            table.add_row(str(i), a.action.value.upper(), label[:50], val)
        self.console.print(table)

    def show_phase_banner(self, phase_name: str) -> None:
        self.console.print(Panel(f"[bold]{phase_name}[/bold]", expand=True, border_style="cyan"))

    def show_success(self, message: str) -> None:
        self.console.print(f"  [bold green]OK[/bold green] {message}")

    def show_warning(self, message: str) -> None:
        self.console.print(f"  [bold yellow]!![/bold yellow] {message}")

    def show_error(self, message: str) -> None:
        self.console.print(f"  [bold red]ERR[/bold red] {message}")

    # ------------------------------------------------------------------
    # Checkpoints — behaviour depends on InteractionMode
    # ------------------------------------------------------------------

    def approve_action_plan(self, actions: list[BrowserAction]) -> bool:
        """MANUAL mode: show plan and wait for approval.  Others: auto-approve."""
        if self.mode == InteractionMode.MANUAL:
            self.show_action_plan(actions)
            return Confirm.ask("  Execute these actions?", default=True)
        if self.mode == InteractionMode.SUPERVISED:
            self.show_action_plan(actions)
        return True

    def confirm_submission(self) -> bool:
        """Before clicking Submit — always confirm in SUPERVISED/MANUAL, skip in AUTO."""
        if self.mode == InteractionMode.AUTO:
            return True
        self.console.print(
            "\n  [bold yellow]Ready to submit application.[/bold yellow]"
        )
        self.show_browser_overlay(
            title="Ready to submit your application",
            message="Confirm in the terminal to send. Hit cancel there to abort.",
            kind="info",
        )
        self.get_attention()
        try:
            return Confirm.ask("  Submit now?", default=True)
        finally:
            self.clear_browser_overlay()

    def pause_for_review(self, message: str, *, timeout_seconds: int = 0) -> None:
        """General-purpose pause. AUTO skips; SUPERVISED auto-continues after timeout;
        MANUAL always waits for Enter."""
        if self.mode == InteractionMode.AUTO:
            return
        self.console.print(f"\n  [dim]{message}[/dim]")
        if self.mode == InteractionMode.MANUAL or timeout_seconds == 0:
            try:
                input("  Press ENTER to continue...")
            except (EOFError, KeyboardInterrupt):
                pass
            return
        # SUPERVISED: auto-continue after timeout, but allow early Enter
        self.console.print(f"  [dim]Auto-continuing in {timeout_seconds}s (press ENTER to skip wait)...[/dim]")
        self._wait_with_early_exit(timeout_seconds)

    def handoff_to_human(
        self,
        reason: str,
        *,
        hint: Optional[str] = None,
        wait_for_navigation_seconds: int = 8,
    ) -> HandoffResult:
        """Hand full browser control to the human and **resume from wherever
        they leave it**.

        This is the canonical "agent is stuck — you take over" checkpoint.
        It:

        1. Snapshots the current URL so we can detect whether the human
           advanced the page.
        2. Shows a prominent modal explaining the situation, what the human
           should do, and how to hand back ("press ENTER when done").
        3. Blocks until the human presses ENTER (or types ``cancel``).
        4. After ENTER, gives the page a moment to finish any in-flight
           navigation the human triggered (e.g. clicked Next), then snapshots
           the new URL/title.
        5. Returns a :class:`HandoffResult` that the engine uses to resume
           **from the human's current page**, *not* from where the agent got
           stuck.

        In ``AUTO`` mode this raises by returning ``cancelled=True`` (the agent
        cannot proceed without human input but is forbidden from blocking).
        """
        url_before = ""
        try:
            url_before = self.page.url or ""
        except Exception:
            pass

        if self.mode == InteractionMode.AUTO:
            self.show_error(
                f"Agent stuck ({reason}) but running in AUTO mode — cannot block."
            )
            return HandoffResult(
                page=self.page,
                url_before=url_before,
                url_after=url_before,
                title_after="",
                advanced=False,
                cancelled=True,
            )

        body_lines: list[str] = []
        body_lines.append(f"[bold]Reason:[/bold] {reason}")
        if hint:
            body_lines.append(f"[bold]Suggested action:[/bold] {hint}")
        body_lines.append("")
        body_lines.append(
            "[bold]>> The browser is yours.[/bold]  Do whatever you need: click, "
            "type, navigate, fill missing fields, advance to the next step, etc."
        )
        body_lines.append(
            "When you're finished, press [bold green]ENTER[/bold green] here and the "
            "agent will continue from [bold]whichever page you ended up on[/bold] "
            "(it will NOT go back to where it got stuck)."
        )
        body_lines.append(
            "Type [bold red]cancel[/bold red] + ENTER to abort this application."
        )

        self.console.print(
            Panel(
                "\n".join(body_lines),
                title="[bold yellow]>>> AGENT HANDED OFF — YOU ARE IN CONTROL <<<[/bold yellow]",
                border_style="yellow",
                expand=True,
            )
        )

        # Browser-side cue so the user notices while looking at the form.
        self.show_browser_overlay(
            title="JobCLI handed control back to you",
            message=reason + (f" — {hint}" if hint else ""),
            kind="warning",
        )
        self.get_attention()

        try:
            response = input("  Press ENTER when done (or type 'cancel'): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = ""

        # Clear the in-page banner now that the human has handed control back.
        self.clear_browser_overlay()

        if response == "cancel":
            return HandoffResult(
                page=self.page,
                url_before=url_before,
                url_after=url_before,
                title_after="",
                advanced=False,
                cancelled=True,
            )

        # Give any in-flight navigation a chance to settle.  If the human just
        # clicked Next/Continue right before pressing ENTER, the page may still
        # be loading.
        try:
            self.page.wait_for_load_state(
                "domcontentloaded", timeout=wait_for_navigation_seconds * 1000
            )
        except Exception:
            pass
        try:
            self.page.wait_for_load_state(
                "networkidle", timeout=max(2, wait_for_navigation_seconds // 2) * 1000
            )
        except Exception:
            pass

        url_after = url_before
        title_after = ""
        try:
            url_after = self.page.url or url_before
        except Exception:
            pass
        try:
            title_after = self.page.title() or ""
        except Exception:
            pass

        advanced = bool(url_after) and url_after != url_before

        if advanced:
            self.show_success(
                f"Resuming from your current page: {title_after or url_after}"
            )
        else:
            self.show_status("Resuming on the same page.", phase=ExecutionPhase.HUMAN)

        if self.logger is not None:
            try:
                self.logger.info(
                    "human_handoff_resumed",
                    phase=ExecutionPhase.HUMAN,
                    url_before=url_before,
                    url_after=url_after,
                    advanced=advanced,
                    reason=reason,
                )
            except Exception:
                pass

        return HandoffResult(
            page=self.page,
            url_before=url_before,
            url_after=url_after,
            title_after=title_after,
            advanced=advanced,
            cancelled=False,
        )

    def handle_captcha(self) -> bool:
        """CAPTCHA detected — always pause for human except in AUTO (which gives up)."""
        if self.mode == InteractionMode.AUTO:
            self.show_error("CAPTCHA detected in auto mode — cannot proceed.")
            return False
        self.show_browser_overlay(
            title="CAPTCHA detected — please solve it in the browser",
            message="JobCLI cannot solve CAPTCHAs. Solve it on this page, then return to the terminal and press ENTER.",
            kind="error",
        )
        self.get_attention()
        self.console.print(
            "\n  [bold red]CAPTCHA or verification detected.[/bold red]"
        )
        self.console.print("  Please solve it in the browser window.")
        try:
            input("  Press ENTER when done: ")
        except (EOFError, KeyboardInterrupt):
            self.clear_browser_overlay()
            return False
        self.clear_browser_overlay()
        return True

    def request_field_input(
        self,
        field_label: str,
        *,
        options: Optional[list[str]] = None,
        current_value: Optional[str] = None,
        question_text: Optional[str] = None,
    ) -> Optional[str]:
        """Ask the human for a missing/failed field value.

        Behaviour:
          1. If a value is already in the DB (any source), return it silently
             — the agent never re-asks a question it has answered before.
          2. AUTO mode skips human prompts entirely (returns None).
          3. SUPERVISED / MANUAL show a modal-style panel and BLOCK until the
             human responds.  The answer is auto-saved to the DB.
        """
        if current_value and current_value.strip():
            return None

        # 1. DB-first: did we already answer this on a previous job?
        cached, source = self.lookup_db_answer(field_label)
        if cached:
            self.console.print(
                f"  [dim]Reusing answer for [cyan]{field_label}[/cyan] from {source}: '{cached}'[/dim]"
            )
            if self.logger:
                self.logger.info(
                    f"DB hit for field '{field_label}' (source={source}).",
                    phase=ExecutionPhase.HUMAN,
                )
            return cached

        if self.mode == InteractionMode.AUTO:
            return None

        # 2. Show a clear modal-style block — the agent has paused.
        question = question_text or f"Please provide a value for: {field_label}"
        body_lines = [
            f"[bold]Question:[/bold] {question}",
            f"[dim]Field label:[/dim] [cyan]{field_label}[/cyan]",
        ]
        if options:
            body_lines.append("")
            body_lines.append("[dim]Available options:[/dim]")
            for i, opt in enumerate(options, 1):
                body_lines.append(f"  {i}. {opt}")
        body_lines.append("")
        body_lines.append(
            "[dim]Your answer will be saved and reused on future applications.[/dim]"
        )
        self.console.print(
            Panel(
                "\n".join(body_lines),
                title="[bold yellow]>>> AGENT PAUSED — INPUT REQUIRED <<<[/bold yellow]",
                border_style="yellow",
                expand=True,
            )
        )

        # Browser-side cue + attention-grabber so the user notices.
        self.show_browser_overlay(
            title=f"JobCLI needs your input: {field_label}",
            message=question,
            kind="warning",
            fields=[field_label] + (options[:5] if options else []),
        )
        self.get_attention()

        answer = Prompt.ask("  Your answer", default="")
        answer = answer.strip()
        self.clear_browser_overlay()
        if not answer:
            return None

        # 3. Persist for reuse next time
        self.persist_human_answer(field_label, answer)
        self.console.print(f"  [green]+[/green] Saved to memory: [cyan]{field_label}[/cyan] = '{answer}'")
        return answer

    def request_help_finding_element(
        self,
        task: str,
        ats_type: ATSType = ATSType.UNKNOWN,
    ) -> tuple[bool, Optional[str], Optional[SelectorType]]:
        """When the agent is stuck finding a button/element, ask the human.

        AUTO mode returns (False, None, None).
        """
        if self.mode == InteractionMode.AUTO:
            return False, None, None

        if self.logger:
            self.logger.info("Agent requesting human assistance", phase=ExecutionPhase.HUMAN, task=task)

        self.console.print(f"\n  [bold yellow]Agent needs help:[/bold yellow] [cyan]{task}[/cyan]")
        self.console.print(f"  URL: [blue]{self.page.url}[/blue]")

        self._show_detected_elements()
        choice = self._get_user_choice()
        if choice == "skip":
            return False, None, None
        elif choice == "manual":
            return self._get_manual_selector(task, ats_type)
        elif choice == "select":
            return self._select_from_elements(task, ats_type)
        return False, None, None

    def ask_continue(self) -> bool:
        """Should the agent continue with this application?  AUTO always says yes."""
        if self.mode == InteractionMode.AUTO:
            return True
        return Confirm.ask("  Continue with this application?", default=True)

    def show_failed_fields(
        self,
        failed_actions: list[BrowserAction],
        *,
        dropdown_options_by_selector: Optional[dict[str, list[str]]] = None,
    ) -> dict[str, str]:
        """For each failed field: try DB first, then prompt human.

        Returns a dict ``{field_label: answer}`` of every value gathered (from
        either the DB or the human).  Every human-supplied answer is saved to
        the DB before being returned.
        """
        if not failed_actions:
            return {}

        actionable = [
            a for a in failed_actions
            if a.action in (ActionType.SELECT, ActionType.FILL, ActionType.TYPE)
            and not (a.value and a.value.strip())
        ]
        if not actionable:
            return {}

        # Header banner — clear "agent stopped" signal
        if self.mode != InteractionMode.AUTO:
            self.console.print(
                Panel(
                    f"[bold]The agent could not fill {len(actionable)} field(s).[/bold]\n"
                    "[dim]Each one will be checked against the DB first; you'll only be\n"
                    "asked for values that have never been answered before. All your\n"
                    "answers are saved and reused on future applications.[/dim]",
                    title="[bold yellow]>>> AGENT PAUSED — REVIEW NEEDED <<<[/bold yellow]",
                    border_style="yellow",
                )
            )

        answers: dict[str, str] = {}
        for act in actionable:
            label = act.field_label or act.selector
            options = (dropdown_options_by_selector or {}).get(act.selector)
            answer = self.request_field_input(label, options=options)
            if answer:
                answers[label] = answer
        return answers

    def final_browser_pause(self) -> None:
        """Keep the browser open for final inspection (non-headless only)."""
        if self.mode == InteractionMode.AUTO:
            return
        self.console.print(
            "\n  [dim]Browser is still open for inspection. Press ENTER to close.[/dim]"
        )
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

    # ------------------------------------------------------------------
    # Internal helpers (unchanged from old HumanInterface, but private)
    # ------------------------------------------------------------------

    def _wait_with_early_exit(self, seconds: int) -> None:
        """Wait for up to *seconds* but return early if the user presses Enter."""
        try:
            import select
            rlist, _, _ = select.select([sys.stdin], [], [], float(seconds))
            if rlist:
                sys.stdin.readline()
        except Exception:
            time.sleep(seconds)

    def _show_detected_elements(self) -> None:
        try:
            buttons = self._get_buttons()
            links = self._get_links()
            if buttons:
                table = Table(title="Detected Buttons")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Text", style="green")
                table.add_column("Visible", style="magenta", width=7)
                for i, btn in enumerate(buttons[:10], 1):
                    table.add_row(str(i), btn.get("text", "")[:50], "Y" if btn.get("visible") else "N")
                self.console.print(table)
            if links:
                table = Table(title="Detected Links")
                table.add_column("#", style="cyan", width=4)
                table.add_column("Text", style="green")
                table.add_column("Visible", style="magenta", width=7)
                for i, link in enumerate(links[:10], 1):
                    table.add_row(str(i), link.get("text", "")[:50], "Y" if link.get("visible") else "N")
                self.console.print(table)
        except Exception as e:
            self.console.print(f"  [red]Error detecting elements: {e}[/red]")

    def _get_buttons(self) -> list[dict]:
        script = """() => {
            const buttons = document.querySelectorAll('button, input[type="submit"], [role="button"]');
            return Array.from(buttons).map(btn => ({
                text: btn.textContent?.trim() || btn.value || '',
                type: btn.type || btn.tagName.toLowerCase(),
                visible: btn.offsetParent !== null,
                selector: btn.id ? `#${btn.id}` : (btn.className ? `.${btn.className.split(' ')[0]}` : ''),
            }));
        }"""
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _get_links(self) -> list[dict]:
        script = """() => {
            const links = document.querySelectorAll('a');
            return Array.from(links).map(link => ({
                text: link.textContent?.trim() || '',
                visible: link.offsetParent !== null,
                selector: link.id ? `#${link.id}` : (link.className ? `.${link.className.split(' ')[0]}` : ''),
            }));
        }"""
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _get_user_choice(self) -> str:
        self.console.print("\n  [bold]What would you like to do?[/bold]")
        self.console.print("  1. Select from detected elements")
        self.console.print("  2. Provide manual selector")
        self.console.print("  3. Skip")
        choice = IntPrompt.ask("  Choice", choices=["1", "2", "3"], default=1)
        return {1: "select", 2: "manual", 3: "skip"}[choice]

    def _select_from_elements(
        self, task: str, ats_type: ATSType,
    ) -> tuple[bool, Optional[str], Optional[SelectorType]]:
        etype = Prompt.ask("  Element type", choices=["button", "link"], default="button")
        elements = self._get_buttons() if etype == "button" else self._get_links()
        if not elements:
            self.console.print("  [red]No elements detected[/red]")
            return False, None, None
        idx = IntPrompt.ask("  Select element #", default=1)
        if 1 <= idx <= len(elements):
            selector = elements[idx - 1].get("selector", "")
            if not selector:
                return self._get_manual_selector(task, ats_type)
            if Confirm.ask("  Save this locator for future use?", default=True):
                self._save_learned_locator(task, ats_type, selector, SelectorType.CSS, "Human selected element")
            return True, selector, SelectorType.CSS
        return False, None, None

    def _get_manual_selector(
        self, task: str, ats_type: ATSType,
    ) -> tuple[bool, Optional[str], Optional[SelectorType]]:
        stype = Prompt.ask("  Selector type", choices=["css", "xpath", "text"], default="css")
        selector = Prompt.ask("  Selector")
        if not selector:
            return False, None, None
        selector_type = SelectorType(stype)
        try:
            if selector_type == SelectorType.CSS:
                el = self.page.query_selector(selector)
            elif selector_type == SelectorType.XPATH:
                el = self.page.query_selector(f"xpath={selector}")
            else:
                el = self.page.get_by_text(selector).first
            if el:
                self.show_success("Selector matched an element")
                if Confirm.ask("  Save for future use?", default=True):
                    notes = Prompt.ask("  Notes (optional)", default="")
                    self._save_learned_locator(task, ats_type, selector, selector_type, notes)
                return True, selector, selector_type
            self.show_error("Selector did not match any element")
            if Confirm.ask("  Try again?", default=True):
                return self._get_manual_selector(task, ats_type)
        except Exception as e:
            self.show_error(f"Error testing selector: {e}")
        return False, None, None

    def _save_learned_locator(
        self, purpose: str, ats_type: ATSType, selector: str,
        selector_type: SelectorType, notes: str,
    ) -> None:
        try:
            locator = LearnedLocator(
                ats_type=ats_type, selector=selector, selector_type=selector_type,
                purpose=purpose, notes=notes, created_by="human",
            )
            self.locator_repo.create(locator)
            self.show_success("Locator saved")
            if self.logger:
                self.logger.info("Learned locator saved", phase=ExecutionPhase.HUMAN, purpose=purpose, selector=selector)
        except Exception as e:
            self.show_error(f"Failed to save locator: {e}")
