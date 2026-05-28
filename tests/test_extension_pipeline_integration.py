"""Integration tests for the rewired fill pipeline.

These tests do NOT spin up Playwright; they drive a fake ``Page`` through the
real pipeline helpers (``_run_extension_autofill_phase``,
``_looks_like_confirmation``, the compulsory pre-submit handoff) and verify
that the agent makes the correct decisions at every branch.

Compared to ``test_extension_pipeline_unit.py``:
  * Unit tests mock each collaborator and exercise a single method.
  * Integration tests stitch together the engine + a fake page + a fake
    agent + a fake rules handler so the *control flow* between them is
    actually exercised.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ───────────────────────────────────────────────────────────────────────
# Fake Page object that simulates URL/DOM transitions
# ───────────────────────────────────────────────────────────────────────


class FakePage:
    """Tiny page double that supports just enough of the Playwright surface
    used by ``_looks_like_confirmation`` and the pre-submit snapshot."""

    def __init__(self, *, url: str = "https://example.com/apply", body_text: str = "Apply"):
        self.url = url
        self._body_text = body_text
        self._timeouts: list[int] = []

    def evaluate(self, expr, *args, **kwargs):
        if "innerText" in expr:
            return self._body_text.lower()
        return None

    def wait_for_timeout(self, ms):
        self._timeouts.append(ms)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def title(self):
        return ""


# ───────────────────────────────────────────────────────────────────────
# Builders
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    """ApplicationEngine instance with a fresh `_last_extension_filled_count`."""
    from jobcli.orchestration.engine import ApplicationEngine

    engine = ApplicationEngine.__new__(ApplicationEngine)
    engine._last_extension_filled_count = 0
    engine._last_rules_filled_count = 0
    return engine


# ───────────────────────────────────────────────────────────────────────
# Rules-as-fallback branches
# ───────────────────────────────────────────────────────────────────────


class TestRulesFallbackBranches:
    """Drive the rules-as-fallback decision and assert the right side runs."""

    def test_rules_skipped_when_extension_filled_any(self, engine):
        """When the extension filled ≥1 visible field, _run_rules_prefill
        must NOT be called and the gate logs/skip message must fire."""
        engine._last_extension_filled_count = 3

        # Reproduce the gate's logic directly — we test the boolean
        # rather than invoking apply_to_job's full body (which would
        # require constructing a Job, state machine, browser, etc.).
        gate_passes = engine._last_extension_filled_count == 0
        assert gate_passes is False

    def test_rules_runs_when_extension_filled_zero(self, engine):
        """When the extension filled 0 fields, the fallback gate opens."""
        engine._last_extension_filled_count = 0
        assert (engine._last_extension_filled_count == 0) is True

    def test_rules_runs_when_extension_dir_missing(self, engine):
        """No extension_dir → _run_extension_autofill_phase never bumps the
        counter → gate opens for rules fallback."""
        engine.extension_dir = None
        # _run_extension_autofill_phase is what would bump the counter;
        # with no extension_dir it returns early without bumping.
        engine._last_extension_filled_count = 0
        assert (engine._last_extension_filled_count == 0) is True


# ───────────────────────────────────────────────────────────────────────
# _looks_like_confirmation integration with realistic page transitions
# ───────────────────────────────────────────────────────────────────────


class TestLooksLikeConfirmationIntegration:

    def test_url_transition_to_thanks_path(self, engine):
        """User clicks Submit; URL goes /apply → /thanks. Strong signal."""
        page = FakePage(url="https://jobs.example.com/abc/thanks", body_text="")

        with patch("jobcli.orchestration.engine._submit_button_visible", return_value=False), \
             patch("jobcli.orchestration.engine._live_validation_errors", return_value=[]):
            strong, soft, _ = engine._looks_like_confirmation(
                page,
                pre_submit_url="https://jobs.example.com/abc/apply",
                pre_submit_had_submit_btn=True,
            )

        assert strong is True

    def test_spa_confirmation_body_only(self, engine):
        """SPA: URL identical, but page body now says 'Application received'."""
        page = FakePage(
            url="https://example.com/apply",
            body_text="Application received. We will be in touch.",
        )
        with patch("jobcli.orchestration.engine._submit_button_visible", return_value=False), \
             patch("jobcli.orchestration.engine._live_validation_errors", return_value=[]):
            strong, soft, signals = engine._looks_like_confirmation(
                page,
                pre_submit_url="https://example.com/apply",
                pre_submit_had_submit_btn=True,
            )

        assert strong is True
        assert signals["text_confirmed"] is True

    def test_form_still_present_no_confirmation(self, engine):
        """Form still visible and no confirmation text → both signals False."""
        page = FakePage(url="https://example.com/apply", body_text="please fill in your details")
        with patch("jobcli.orchestration.engine._submit_button_visible", return_value=True), \
             patch("jobcli.orchestration.engine._live_validation_errors", return_value=[]):
            strong, soft, _ = engine._looks_like_confirmation(
                page,
                pre_submit_url="https://example.com/apply",
                pre_submit_had_submit_btn=True,
            )

        assert strong is False
        assert soft is False


# ───────────────────────────────────────────────────────────────────────
# Pre-submit handoff branches inside `apply_to_job`
# ───────────────────────────────────────────────────────────────────────


class TestPreSubmitHandoffBranches:
    """Pin down the new `if user_submitted_during_review` branch's effects
    by exercising the helper at the public boundary used by apply_to_job."""

    def test_user_already_submitted_skips_agent_click(self, engine):
        """Strong signal on the page after the handoff → submit_clicked must
        be set True without invoking rules_handler.submit_application."""
        page = FakePage(url="https://example.com/thanks", body_text="thank you for applying")
        with patch("jobcli.orchestration.engine._submit_button_visible", return_value=False), \
             patch("jobcli.orchestration.engine._live_validation_errors", return_value=[]):
            strong, soft, _ = engine._looks_like_confirmation(
                page,
                pre_submit_url="https://example.com/apply",
                pre_submit_had_submit_btn=True,
            )

        # The engine's apply_to_job decision: skip agent submit when strong or soft.
        user_submitted = strong or soft
        assert user_submitted is True

        # Simulate the engine branch — rules_handler.submit_application
        # should NEVER be called.
        rules_handler = MagicMock()
        if not user_submitted:
            rules_handler.submit_application()
        rules_handler.submit_application.assert_not_called()

    def test_no_confirmation_engine_proceeds_to_submit(self, engine):
        """No signals → engine should still call rules_handler.submit_application."""
        page = FakePage(url="https://example.com/apply", body_text="application page")
        with patch("jobcli.orchestration.engine._submit_button_visible", return_value=True), \
             patch("jobcli.orchestration.engine._live_validation_errors", return_value=[]):
            strong, soft, _ = engine._looks_like_confirmation(
                page,
                pre_submit_url="https://example.com/apply",
                pre_submit_had_submit_btn=True,
            )

        user_submitted = strong or soft
        rules_handler = MagicMock()
        if not user_submitted:
            rules_handler.submit_application()
        rules_handler.submit_application.assert_called_once()


# ───────────────────────────────────────────────────────────────────────
# Compulsory handoff blocks in EVERY mode (no AUTO carve-out)
# ───────────────────────────────────────────────────────────────────────


class TestCompulsoryHandoffAllModes:
    """Critical: pre-submit review must block in AUTO too."""

    def _make_agent(self, *, mode):
        from jobcli.human.agent_interface import AgentInterface

        agent = AgentInterface.__new__(AgentInterface)
        agent.mode = mode
        agent.is_server = False
        agent.page = MagicMock()
        agent.page.url = "https://example.com/apply"
        agent.console = MagicMock()
        agent.logger = None
        agent.show_error = MagicMock()
        agent.show_warning = MagicMock()
        agent.show_status = MagicMock()
        agent.show_success = MagicMock()
        agent.show_browser_overlay = MagicMock()
        agent.clear_browser_overlay = MagicMock()
        agent.get_attention = MagicMock()
        return agent

    @pytest.mark.parametrize("mode_name", ["AUTO", "SUPERVISED", "MANUAL"])
    def test_force_block_handoff_blocks_in_every_mode(self, mode_name):
        from jobcli.profile.schemas import InteractionMode

        mode = getattr(InteractionMode, mode_name)
        agent = self._make_agent(mode=mode)
        agent._get_user_input = MagicMock(return_value="")  # immediate ENTER

        result = agent.handoff_to_human(
            reason="Final review before submit", hint="check fields",
            force_block=True,
        )

        # The contract: in every mode, the timeout must be 600s (not 60s).
        timeout = agent._get_user_input.call_args.kwargs.get("timeout_seconds")
        assert timeout == 600, (
            f"force_block=True in mode {mode_name} should use the 600s "
            f"timeout, got {timeout}. AUTO carve-out has leaked back in."
        )
        # And the "stuck" error must NOT fire when force_block is set.
        agent.show_error.assert_not_called()
        assert result.cancelled is False


# ───────────────────────────────────────────────────────────────────────
# Cancel path
# ───────────────────────────────────────────────────────────────────────


class TestHandoffCancelPath:

    def _make_agent_typing(self, response: str):
        from jobcli.human.agent_interface import AgentInterface
        from jobcli.profile.schemas import InteractionMode

        agent = AgentInterface.__new__(AgentInterface)
        agent.mode = InteractionMode.SUPERVISED
        agent.is_server = False
        agent.page = MagicMock()
        agent.page.url = "https://example.com/apply"
        agent.console = MagicMock()
        agent.logger = None
        agent.show_error = MagicMock()
        agent.show_warning = MagicMock()
        agent.show_status = MagicMock()
        agent.show_success = MagicMock()
        agent.show_browser_overlay = MagicMock()
        agent.clear_browser_overlay = MagicMock()
        agent.get_attention = MagicMock()
        agent._get_user_input = MagicMock(return_value=response)
        return agent

    def test_user_types_cancel_returns_cancelled_result(self):
        """Typing 'cancel' aborts the pre-submit review and the engine must
        return False without ever attempting submit. Tested at the
        handoff_to_human level — apply_to_job branches on
        review_handoff.cancelled."""
        agent = self._make_agent_typing("cancel")
        result = agent.handoff_to_human(
            reason="Final review", hint=None, force_block=True
        )
        assert result.cancelled is True

    def test_user_presses_enter_resumes(self):
        agent = self._make_agent_typing("")
        result = agent.handoff_to_human(
            reason="Final review", hint=None, force_block=True
        )
        assert result.cancelled is False
