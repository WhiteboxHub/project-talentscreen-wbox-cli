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
from rich.prompt import Confirm, Prompt
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
        a clear visual cue WHILE looking at the form.

        The banner is rendered inside a **Shadow DOM** so the host page's
        CSS can NEVER reach it (no inherited ``letter-spacing``, no
        ``text-transform: uppercase``, no custom font replacing
        characters with ligatures, etc.).  Without that isolation, some
        ATS pages' global styles were making the banner text render
        with overlapping / merged letters.

        The banner persists until ``clear_browser_overlay()`` is called
        or the page navigates.
        """
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
                field_list_html = f"<ul class='fields'>{items}</ul>"

            self.page.evaluate(
                r"""({id, title, message, color, fieldsHtml}) => {
                    const old = document.getElementById(id);
                    if (old) old.remove();

                    // Host element is invisible; all visual structure
                    // lives inside its Shadow DOM, isolated from the
                    // page's CSS.
                    const host = document.createElement('div');
                    host.id = id;
                    host.setAttribute('data-jobcli', 'handoff');
                    host.style.cssText = [
                        'all: initial',
                        'position: fixed',
                        'top: 0',
                        'left: 0',
                        'right: 0',
                        'z-index: 2147483647',
                        'pointer-events: auto',
                    ].map(s => s + ' !important').join(';');

                    const shadow = host.attachShadow({mode: 'closed'});

                    // CSS reset + banner styles (scoped to this shadow root)
                    const css = `
                        :host, * { all: revert; }
                        :host {
                            display: block;
                            font: 15px/1.5 -apple-system, BlinkMacSystemFont,
                                  'Segoe UI', Roboto, 'Helvetica Neue',
                                  Arial, sans-serif;
                            letter-spacing: normal;
                            word-spacing: normal;
                            text-transform: none;
                            font-variant: normal;
                            font-feature-settings: normal;
                            font-style: normal;
                            font-weight: normal;
                            text-decoration: none;
                            text-shadow: none;
                            -webkit-font-smoothing: antialiased;
                            -moz-osx-font-smoothing: grayscale;
                            text-rendering: optimizeLegibility;
                            color: #ffffff;
                        }
                        .bar {
                            box-sizing: border-box;
                            width: 100%;
                            padding: 14px 20px;
                            background: ${color.bg};
                            color: #ffffff;
                            border-bottom: 4px solid ${color.border};
                            box-shadow: 0 4px 14px rgba(0,0,0,0.35);
                            animation: jobcli-pulse 1.4s ease-in-out infinite;
                        }
                        .inner {
                            max-width: 1200px;
                            margin: 0 auto;
                            display: flex;
                            align-items: flex-start;
                            gap: 14px;
                        }
                        .icon {
                            font-size: 26px;
                            line-height: 1.1;
                            flex: 0 0 auto;
                        }
                        .body {
                            flex: 1 1 auto;
                            min-width: 0;
                        }
                        .title {
                            font-weight: 700;
                            font-size: 16px;
                            margin: 0 0 4px 0;
                            letter-spacing: normal;
                            line-height: 1.35;
                            word-break: normal;
                            overflow-wrap: anywhere;
                        }
                        .msg {
                            font-size: 14px;
                            line-height: 1.5;
                            margin: 0;
                            letter-spacing: normal;
                            word-break: normal;
                            overflow-wrap: anywhere;
                            opacity: 0.97;
                        }
                        .fields {
                            margin: 8px 0 0 20px;
                            padding: 0;
                            font-size: 13px;
                            line-height: 1.5;
                        }
                        .fields li {
                            margin: 2px 0;
                        }
                        .hint {
                            margin-top: 8px;
                            font-size: 12px;
                            line-height: 1.5;
                            opacity: 0.85;
                        }
                        @keyframes jobcli-pulse {
                            0%, 100% { box-shadow: 0 4px 14px rgba(0,0,0,0.35); }
                            50%      { box-shadow: 0 4px 22px ${color.bg}; }
                        }
                    `;

                    const style = document.createElement('style');
                    style.textContent = css;

                    const wrap = document.createElement('div');
                    wrap.className = 'bar';
                    wrap.innerHTML = `
                        <div class="inner">
                            <div class="icon">⏸</div>
                            <div class="body">
                                <div class="title"></div>
                                <div class="msg"></div>
                                <div class="fields-slot"></div>
                                <div class="hint">JobCLI is waiting in the terminal — finish here, then return to the terminal and press ENTER.</div>
                            </div>
                        </div>
                    `;
                    // Assign textContent so any HTML-ish characters in
                    // title/message render literally (no injection risk).
                    wrap.querySelector('.title').textContent = title;
                    wrap.querySelector('.msg').textContent = message;
                    if (fieldsHtml) {
                        wrap.querySelector('.fields-slot').innerHTML = fieldsHtml;
                    }

                    shadow.appendChild(style);
                    shadow.appendChild(wrap);
                    document.documentElement.appendChild(host);
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
        """Deprecated — always returns ``(False, None, None)``.

        The old implementation rendered a terminal-only "Select from
        detected elements / Provide manual selector / Skip" picker.  It
        was confusing (users had to translate the agent's DOM list into
        CSS selectors themselves) and it blocked the far cleaner path of
        handing the actual browser back to the human.  Callers are
        expected to fall through to ``handoff_to_human`` on False, which
        they all do.
        """
        if self.logger:
            self.logger.debug(
                "request_help_finding_element is deprecated — "
                "routing directly to handoff_to_human.",
                phase=ExecutionPhase.HUMAN,
                task=task,
            )
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
    ) -> list[BrowserAction]:
        """For each failed field: try DB first, then prompt human.

        Returns a list of new :class:`BrowserAction` objects with the
        collected values populated, ready to be re-executed against the
        browser.  Every human-supplied answer is also saved to the DB (via
        ``request_field_input`` → ``AgentMemory.save_field_answer``) so the
        next job on this ATS reuses it automatically.
        """
        if not failed_actions:
            return []

        actionable = [
            a for a in failed_actions
            if a.action in (ActionType.SELECT, ActionType.FILL, ActionType.TYPE)
            and not (a.value and a.value.strip())
        ]
        if not actionable:
            return []

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

        filled: list[BrowserAction] = []
        for act in actionable:
            label = act.field_label or act.selector
            options = (dropdown_options_by_selector or {}).get(act.selector)
            answer = self.request_field_input(label, options=options)
            if not answer:
                continue
            # Build a fresh BrowserAction that preserves the original
            # selector/selector_type/field_label but now carries the value
            # we just collected.  If the field has a known dropdown option
            # list, coerce FILL → SELECT so the executor uses the
            # dropdown-friendly strategy.
            action_type = act.action
            if options and action_type in (ActionType.FILL, ActionType.TYPE):
                action_type = ActionType.SELECT
            filled.append(
                act.model_copy(update={"value": answer, "action": action_type})
            )
        return filled

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
