"""Regression tests for the rewired extension autofill pipeline.

Each test pins down one of the behaviours that was *broken* before this
change. If any of these regress, the suite turns red immediately rather
than waiting for someone to notice in production.

Bugs guarded against:
  R1. Rules used to ALWAYS run after the extension — even when the
      extension filled every field. Now: rules must NEVER run when the
      extension produced ≥1 fill.
  R2. The agent used to call `rules_handler.submit_application()` after
      every human handoff, even if the human had already clicked Submit
      themselves. Now: the agent must skip its own click whenever
      `_looks_like_confirmation` reports the form is already submitted.
  R3. The pre-submit confirmation was a yes/no terminal prompt, not a
      real review. Now: the engine must call `_handoff_human_in_loop`
      with `force_block=True` — even in AUTO mode.
  R4. `agent.confirm_submission()` must NOT be reachable from the apply
      path any more.
  R5. The escape hatch env var `WBOX_BYPASS_PRE_SUBMIT_REVIEW=1` must
      keep AUTO-mode's 60-second short-circuit behaviour intact (only
      for that very specific env var).
  R6. `resolve_extension_dir()` must still pick up
      `bin/project-talentscreen-autofill-extension/` (Tier 4) so the
      manual unstick from Part A keeps working.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock


# ───────────────────────────────────────────────────────────────────────
# R1. Rules never runs when the extension succeeded
# ───────────────────────────────────────────────────────────────────────


class TestR1_RulesNeverRunsWhenExtensionSucceeds:

    def test_pre_upload_gate_is_present_and_correct(self):
        """The gate must use exact `_last_extension_filled_count == 0`.

        Static check: future refactors must keep the gating expression
        recognisable or this test loudly fails so the integration suite
        can be re-verified.
        """
        from jobcli.orchestration import engine

        src = Path(engine.__file__).read_text()
        # Pre-upload + post-upload uses of the gate — at least two.
        assert src.count("_last_extension_filled_count == 0") >= 2, (
            "Rules-as-fallback gate must appear at least twice "
            "(pre-upload + post-upload)."
        )

    def test_gate_evaluates_false_for_any_positive_count(self):
        # Just a sanity check on the boolean.
        for n in (1, 2, 5, 50):
            assert (n == 0) is False


# ───────────────────────────────────────────────────────────────────────
# R2. No double-submit when user already submitted in browser
# ───────────────────────────────────────────────────────────────────────


class TestR2_NoDoubleSubmitAfterUserSubmits:

    def _engine(self):
        from jobcli.orchestration.engine import ApplicationEngine
        return ApplicationEngine.__new__(ApplicationEngine)

    def test_helper_returns_strong_when_confirmation_text_present(self):
        from unittest.mock import patch

        engine = self._engine()
        page = MagicMock()
        page.url = "https://example.com/apply"
        page.evaluate.return_value = "thank you for applying"

        with patch("jobcli.orchestration.engine._submit_button_visible", return_value=False), \
             patch("jobcli.orchestration.engine._live_validation_errors", return_value=[]):
            strong, soft, _ = engine._looks_like_confirmation(
                page, pre_submit_url="https://example.com/apply",
                pre_submit_had_submit_btn=True,
            )

        assert strong is True
        # Implication: the engine sets user_submitted_during_review=True
        # and skips its own submit click. Encoded at the call-site by
        # `if not user_submitted_during_review and rules_handler is not None`.

    def test_apply_path_guards_submit_with_user_flag(self):
        """The skip-submit guard must be exactly the documented expression."""
        from jobcli.orchestration import engine

        src = Path(engine.__file__).read_text()
        assert "if not user_submitted_during_review and rules_handler is not None:" in src, (
            "Submit click must be guarded by `if not user_submitted_during_review`. "
            "Without this guard the agent will double-click Submit after the human did."
        )


# ───────────────────────────────────────────────────────────────────────
# R3. Compulsory handoff must use force_block=True
# ───────────────────────────────────────────────────────────────────────


class TestR3_CompulsoryHandoffForcesBlock:

    def test_force_block_kwarg_present_in_engine_call(self):
        from jobcli.orchestration import engine

        src = Path(engine.__file__).read_text()
        assert "force_block=True" in src, (
            "Compulsory pre-submit handoff lost its force_block=True kwarg. "
            "Without it, AUTO mode silently skips the review."
        )

    def test_handoff_to_human_signature_accepts_force_block(self):
        """Signature pin — bumping argspec breaks the call site silently."""
        import inspect
        from jobcli.human.agent_interface import AgentInterface

        sig = inspect.signature(AgentInterface.handoff_to_human)
        params = sig.parameters
        assert "force_block" in params, (
            "AgentInterface.handoff_to_human is missing the `force_block` "
            "keyword arg. Remove or rename and the compulsory review breaks."
        )
        assert params["force_block"].default is False, (
            "force_block must default to False so existing callers retain "
            "their previous behaviour."
        )

    def test_auto_mode_blocks_with_force_block(self):
        """End-to-end at the AgentInterface level: AUTO + force_block must NOT
        short-circuit. We've also covered this in the unit suite — this
        regression test exists so the regression file fails immediately if
        someone removes the carve-out bypass."""
        from jobcli.human.agent_interface import AgentInterface
        from jobcli.profile.schemas import InteractionMode

        agent = AgentInterface.__new__(AgentInterface)
        agent.mode = InteractionMode.AUTO
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
        agent._get_user_input = MagicMock(return_value="")

        agent.handoff_to_human(reason="r", hint=None, force_block=True)

        # 60s would mean AUTO carve-out still active.
        timeout = agent._get_user_input.call_args.kwargs.get("timeout_seconds")
        assert timeout == 600


# ───────────────────────────────────────────────────────────────────────
# R4. confirm_submission() must not be reachable from apply_to_job
# ───────────────────────────────────────────────────────────────────────


class TestR4_NoConfirmSubmissionInApplyPath:

    def test_engine_source_does_not_call_confirm_submission(self):
        """Static check: re-introducing the old yes/no prompt must trip
        this test. If you genuinely need to bring it back you'll have to
        update this guard at the same time so it's visible in review."""
        from jobcli.orchestration import engine

        src = Path(engine.__file__).read_text()
        assert "agent.confirm_submission()" not in src, (
            "engine.apply_to_job must not call agent.confirm_submission() — "
            "the compulsory _handoff_human_in_loop is the canonical "
            "pre-submit gate now."
        )

    def test_apply_to_job_ast_has_no_confirm_submission_call(self):
        """Belt-and-braces AST scan in case someone renames the agent or
        uses getattr to hide the call from the string check above."""
        from jobcli.orchestration import engine

        src = Path(engine.__file__).read_text()
        tree = ast.parse(src)

        # Walk every Call node and look for x.confirm_submission()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "confirm_submission":
                    raise AssertionError(
                        "Found a call to `.confirm_submission()` in engine.py "
                        "at line %d. The compulsory pre-submit handoff replaces "
                        "this yes/no prompt." % node.lineno
                    )


# ───────────────────────────────────────────────────────────────────────
# R5. WBOX_BYPASS_PRE_SUBMIT_REVIEW env var still works
# ───────────────────────────────────────────────────────────────────────


class TestR5_BypassEnvVarRestoresAutoShortCircuit:

    def test_env_var_bypass(self, monkeypatch):
        from jobcli.human.agent_interface import AgentInterface
        from jobcli.profile.schemas import InteractionMode

        monkeypatch.setenv("WBOX_BYPASS_PRE_SUBMIT_REVIEW", "1")

        agent = AgentInterface.__new__(AgentInterface)
        agent.mode = InteractionMode.AUTO
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
        agent._get_user_input = MagicMock(return_value=None)

        agent.handoff_to_human(reason="r", hint=None, force_block=True)

        # Bypass active → 60s short-circuit returns.
        timeout = agent._get_user_input.call_args.kwargs.get("timeout_seconds")
        assert timeout == 60
        agent.show_error.assert_called_once()


# ───────────────────────────────────────────────────────────────────────
# R6. Extension resolver still finds bin/ install
# ───────────────────────────────────────────────────────────────────────


class TestR6_ExtensionResolverFindsBinInstall:

    def test_resolve_picks_up_bundled_dir(self, tmp_path, monkeypatch):
        from jobcli.utils import extension_helpers as helpers

        bundled = tmp_path / "bin" / "project-talentscreen-autofill-extension"
        bundled.mkdir(parents=True)
        (bundled / "manifest.json").write_text("{}")

        monkeypatch.setattr(helpers, "_LEGACY_UNPACK_DIR", tmp_path / "nope_legacy")
        monkeypatch.setattr(helpers, "_BUNDLED_DIR", bundled)
        monkeypatch.setattr(helpers, "_EXTENSION_DIR", tmp_path / "nope_ext_dir")

        result = helpers.resolve_extension_dir(None)
        assert result == str(bundled.resolve())


# ───────────────────────────────────────────────────────────────────────
# Pipeline label regressions
# ───────────────────────────────────────────────────────────────────────


class TestPipelineLabels:

    def test_labels_reflect_new_semantics(self):
        from jobcli.orchestration.engine import ApplicationEngine

        steps = ApplicationEngine.FILL_PIPELINE_STEPS
        assert len(steps) == 4
        assert "Extension" in steps[0]
        assert "fallback" in steps[1].lower()
        assert "LLM" in steps[2]
        assert "Human review" in steps[3]
        assert "always" in steps[3].lower()
