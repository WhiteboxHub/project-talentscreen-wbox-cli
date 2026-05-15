"""Unified user-initiated exit signaling for the apply / discover flows.

Why this module exists
----------------------
Long-running JobCLI commands (``apply`` especially) stop at multiple
interactive prompts: yes/no confirms (LinkedIn skip, Submit now?), free-text
prompts (handoff to human, ASK actions), and the "Press ENTER when done"
manual-fallback. We want the user to be able to **abandon the entire run at
any of those prompts**, regardless of which prompt is active or which thread
is blocked on stdin, and have the engine shut down cleanly: close the
browser, save the session, write a summary, exit 0.

Mechanism
---------
``ExitRequested`` is the single signal that bubbles up to the top-level
``_run_apply`` job loop. Every interactive seam (``_get_user_input``,
``ask_yes_no``, ``Prompt.ask`` wrappers) translates the universal quit
keywords (``q``, ``quit``, ``exit``, ``:q``) and Ctrl+C into this exception.

The keyword set is deliberately small and unambiguous so it does not collide
with legitimate text answers — anyone actually answering "quit" as a form
value can press a single letter different (``Q``, ``EXIT``, etc. are all
treated as exit; if a form ever genuinely needs the word "quit" as input,
the same human can paste it via right-click or type ``"quit"`` quoted).

Ctrl+C semantics on Windows PowerShell
--------------------------------------
On Windows + PowerShell, ``Ctrl+C`` generates ``CTRL_C_EVENT`` which Python
delivers as ``KeyboardInterrupt`` **in the main thread only**. Daemon
threads blocked on ``input()`` keep blocking until either (a) the user types
something or (b) the process exits. We mitigate this by:

* Installing a SIGINT handler that — on the FIRST Ctrl+C — sets a
  process-wide ``exit_requested`` flag *and* unblocks any thread waiting on
  the per-AgentInterface input event (registered via
  :func:`register_input_event`). The next time the agent's input pipeline
  wakes, it sees the flag and raises ``ExitRequested``.
* On a SECOND Ctrl+C within 2 seconds we hard-exit via ``os._exit(130)`` —
  the conventional UNIX SIGINT exit code — so the user is never trapped.

This module is import-side-effect free until ``install_global_sigint_handler``
is called explicitly (the CLI calls it at the top of ``_run_apply``).
"""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import List, Optional

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class ExitRequested(BaseException):
    """Raised when the user asks to abandon the current command.

    Inherits from :class:`BaseException` (not :class:`Exception`) — same
    rationale as :class:`KeyboardInterrupt` and :class:`SystemExit`. The
    engine has ~80 generic ``except Exception:`` clauses around browser /
    LLM / database operations; making this a BaseException ensures those
    cannot accidentally swallow a user-initiated quit. Only code that
    explicitly catches ``ExitRequested`` or ``BaseException`` will see it.

    The reason string is logged on shutdown (e.g. ``"quit keyword at
    handoff prompt"``, ``"Ctrl+C in apply loop"``). The CLI's
    ``_run_apply`` catches this, closes the browser, persists state,
    prints a tally, and exits 0 — distinct from an unexpected crash.
    """

    def __init__(self, reason: str = "user requested exit") -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Quit-keyword detection — the single source of truth used everywhere
# ---------------------------------------------------------------------------

# Lowercase canonical set. Anything matching this (after strip + lower) is
# treated as "user wants to bail out of the entire apply run".
_QUIT_KEYWORDS = frozenset({"q", "quit", "exit", ":q", "quit-all", "qq"})


def is_quit_keyword(value: Optional[str]) -> bool:
    """Returns True iff *value* is one of the canonical quit keywords."""
    if value is None:
        return False
    return value.strip().lower() in _QUIT_KEYWORDS


# ---------------------------------------------------------------------------
# Global flag + input-event registry so SIGINT can wake blocked prompts
# ---------------------------------------------------------------------------


_exit_requested = threading.Event()
_last_sigint_at: float = 0.0
_input_events: List[threading.Event] = []
_input_events_lock = threading.Lock()


def is_exit_requested() -> bool:
    """Returns True if the global SIGINT handler has flipped the flag."""
    return _exit_requested.is_set()


def request_exit() -> None:
    """Programmatic equivalent of Ctrl+C — flips the flag and wakes prompts."""
    _exit_requested.set()
    _wake_input_events()


def reset_exit_flag() -> None:
    """Test-only: clears the flag between runs."""
    _exit_requested.clear()


def register_input_event(ev: threading.Event) -> None:
    """Register an Event() that should be woken on Ctrl+C.

    Called by ``AgentInterface._get_user_input`` so a Ctrl+C while the
    agent is waiting on stdin unblocks the wait immediately (instead of
    leaving the user staring at a frozen prompt).
    """
    with _input_events_lock:
        if ev not in _input_events:
            _input_events.append(ev)


def unregister_input_event(ev: threading.Event) -> None:
    """Mirror of :func:`register_input_event`. Safe if ev was never added."""
    with _input_events_lock:
        try:
            _input_events.remove(ev)
        except ValueError:
            pass


def _wake_input_events() -> None:
    with _input_events_lock:
        for ev in _input_events:
            try:
                ev.set()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# SIGINT handler
# ---------------------------------------------------------------------------


def _handle_sigint(_signum: int, _frame) -> None:
    """First Ctrl+C → flag + wake prompts. Second within 2s → hard-exit."""
    global _last_sigint_at
    now = time.monotonic()
    if _exit_requested.is_set() and (now - _last_sigint_at) < 2.0:
        # User is impatient — bail out immediately.
        try:
            # Stderr (not stdout) so it shows even if stdout is buffered.
            os.write(2, b"\n[jobcli] Force quit (SIGINT x2). Exiting now.\n")
        except Exception:
            pass
        os._exit(130)  # conventional 128 + SIGINT
    _last_sigint_at = now
    _exit_requested.set()
    _wake_input_events()
    try:
        os.write(
            2,
            b"\n[jobcli] Ctrl+C received. Finishing the current step and exiting cleanly...\n"
            b"         Press Ctrl+C again within 2s to force quit.\n",
        )
    except Exception:
        pass


def install_global_sigint_handler() -> None:
    """Wire the JobCLI SIGINT handler. Safe to call multiple times.

    The handler is process-wide; callers that want the old behavior (raise
    KeyboardInterrupt) can call :func:`uninstall_global_sigint_handler`.
    """
    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except (ValueError, OSError) as e:
        # signal.signal() only works in the main thread; in a background
        # thread it raises ValueError. Not fatal — Ctrl+C will fall back
        # to Python's default KeyboardInterrupt path, which the CLI also
        # catches.
        logger.debug(f"Could not install SIGINT handler: {e}")


def uninstall_global_sigint_handler() -> None:
    """Restore Python's default SIGINT handler. Test/cleanup helper."""
    try:
        signal.signal(signal.SIGINT, signal.default_int_handler)
    except (ValueError, OSError):
        pass
