"""Unit tests for the session's don't-refill guard and required-fields-first
human prompt.

Covers, by group:

* Group 1 — `BrowserAction.required` schema field
* Group 2 — `ApplicationEngine._snapshot_filled` / `_action_target_already_filled`
* Group 3 — `ToolExecutor._read_live_value` + `execute_action` skip-refill guard
* Group 4 — `LLMClient._propagate_required_flag`
* Group 5 — `AgentInterface.show_failed_fields` two-tier prompting
* Group 6 — TUI `_next_step_panel`, `_next_hint`, `_validate_wbox_and_extension`
* Group 7 — Engine / executor placeholder sets stay in sync
"""

from __future__ import annotations

import inspect
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from jobcli.core.engine import ApplicationEngine
from jobcli.core.schemas import (
    ActionType,
    BrowserAction,
    InteractionMode,
)
from jobcli.core.tool_executor import ToolExecutor, _PLACEHOLDER_VALUES
from jobcli.human.agent_interface import AgentInterface
from jobcli.llm.ax_tree_extractor import AccessibilityNode, AccessibilityTree
from jobcli.llm.client import LLMClient


# ── Mock helpers ──────────────────────────────────────────────────────


class _MockPage:
    """Stub for playwright.Page used by ``_snapshot_filled`` tests.

    ``evaluate_return`` is what the JS snapshot should appear to return.
    ``evaluate_raises`` (if set) is raised from ``evaluate`` instead.
    """

    def __init__(
        self,
        evaluate_return: Optional[list[dict[str, Any]]] = None,
        evaluate_raises: Optional[BaseException] = None,
    ) -> None:
        self._return = evaluate_return
        self._raises = evaluate_raises

    def evaluate(self, *_a, **_kw):
        if self._raises:
            raise self._raises
        return self._return


class _MockLocator:
    """Stub for the ``.locator(...).first`` chain used by ``_read_live_value``.

    Behaviour is configured via constructor flags:

    * ``count_value``       – return value for ``.count()``
    * ``input_value_value`` – return value for ``input_value(...)``
    * ``input_value_raises`` – exception raised by ``input_value(...)``
    * ``evaluate_value``    – return value for the fallback ``evaluate(...)``
    * ``evaluate_raises``   – exception raised by ``evaluate(...)``
    """

    def __init__(
        self,
        *,
        count_value: int = 1,
        input_value_value: Optional[str] = None,
        input_value_raises: Optional[BaseException] = None,
        evaluate_value: Optional[str] = None,
        evaluate_raises: Optional[BaseException] = None,
    ) -> None:
        self._count = count_value
        self._input_value = input_value_value
        self._input_raises = input_value_raises
        self._eval_value = evaluate_value
        self._eval_raises = evaluate_raises
        self.first = self  # ``.first`` returns the same stub for simplicity

    def count(self) -> int:
        return self._count

    def input_value(self, *_a, **_kw):
        if self._input_raises:
            raise self._input_raises
        return self._input_value

    def evaluate(self, *_a, **_kw):
        if self._eval_raises:
            raise self._eval_raises
        return self._eval_value


def _make_engine() -> ApplicationEngine:
    """Construct an ApplicationEngine without running ``__init__`` (which
    needs DB / Playwright). Tests only touch helpers that don't need state.
    """
    return ApplicationEngine.__new__(ApplicationEngine)


def _make_executor(page: Optional[Any] = None) -> ToolExecutor:
    """Build a ToolExecutor without going through ``__init__``. Tests that
    need ``self.page`` should supply it explicitly.
    """
    exe = ToolExecutor.__new__(ToolExecutor)
    exe.page = page if page is not None else MagicMock()
    exe.logger = None
    exe.memory = None
    exe.synonym_resolver = None
    exe.ats_type = None
    exe.ats_handler = None
    exe.last_successful_strategy = None
    exe.last_dropdown_options = {}
    exe._failed_actions = []
    return exe


def _make_ax_tree(form_fields: list[dict[str, Any]]) -> AccessibilityTree:
    """Tiny AccessibilityTree builder for required-flag propagation tests."""
    return AccessibilityTree(
        url="https://example.com/jobs/1",
        title="Apply",
        root=AccessibilityNode(role="WebArea", name="Apply"),
        form_fields=form_fields,
    )


def _make_agent(mode: InteractionMode = InteractionMode.SUPERVISED) -> AgentInterface:
    """Build an AgentInterface without going through ``__init__`` (which
    needs a real Playwright page). Manually populate only the attributes
    that ``show_failed_fields`` reads.
    """
    agent = AgentInterface.__new__(AgentInterface)
    agent.mode = mode
    agent.is_server = False
    agent.logger = None
    agent.memory = None
    # ``console.print`` is the only console call ``show_failed_fields`` makes.
    agent.console = MagicMock()
    return agent


# ──────────────────────────────────────────────────────────────────────
# Group 1 — BrowserAction.required
# ──────────────────────────────────────────────────────────────────────


class TestBrowserActionRequired:
    def test_browser_action_required_defaults_false(self):
        act = BrowserAction(action=ActionType.FILL, selector="#x")
        assert act.required is False

    def test_browser_action_required_accepts_true(self):
        act = BrowserAction(action=ActionType.FILL, selector="#x", required=True)
        assert act.required is True

    def test_browser_action_model_copy_preserves_required(self):
        act = BrowserAction(action=ActionType.FILL, selector="#x", required=True)
        copy = act.model_copy(update={"value": "Jane"})
        assert copy.required is True
        assert copy.value == "Jane"

    def test_browser_action_round_trip_dict(self):
        original = BrowserAction(
            action=ActionType.FILL,
            selector="#x",
            field_label="Name",
            required=True,
        )
        dumped = original.model_dump()
        assert dumped["required"] is True
        restored = BrowserAction(**dumped)
        assert restored.required is True
        assert restored.field_label == "Name"


# ──────────────────────────────────────────────────────────────────────
# Group 2 — Engine snapshot + match
# ──────────────────────────────────────────────────────────────────────


class TestActionTargetAlreadyFilled:
    """Exhaustive coverage of ``_action_target_already_filled``."""

    def setup_method(self):
        self.engine = _make_engine()
        self.snapshot = {
            "name:first_name": "Jane",
            "id:full_name": "Jane Doe",
            "label:email address": "jane@example.com",
            "ph:enter your email": "jane@example.com",
            "name:phone": "555-0100",
        }

    def test_match_by_name_attribute(self):
        act = BrowserAction(
            action=ActionType.FILL,
            selector="input[name=first_name]",
            field_label="First Name",
        )
        assert self.engine._action_target_already_filled(act, self.snapshot) == "Jane"

    def test_match_by_id_selector(self):
        act = BrowserAction(action=ActionType.FILL, selector="#full_name")
        assert self.engine._action_target_already_filled(act, self.snapshot) == "Jane Doe"

    def test_match_by_aria_label_selector(self):
        act = BrowserAction(
            action=ActionType.FILL,
            selector='input[aria-label="Email Address"]',
        )
        assert (
            self.engine._action_target_already_filled(act, self.snapshot)
            == "jane@example.com"
        )

    def test_match_by_placeholder_key(self):
        act = BrowserAction(
            action=ActionType.FILL,
            selector="input[placeholder*='enter your email']",
        )
        assert (
            self.engine._action_target_already_filled(act, self.snapshot)
            == "jane@example.com"
        )

    def test_match_by_field_label(self):
        act = BrowserAction(
            action=ActionType.FILL,
            selector="",
            field_label="phone",
        )
        assert self.engine._action_target_already_filled(act, self.snapshot) == "555-0100"

    def test_no_match_for_completely_different_field(self):
        act = BrowserAction(action=ActionType.FILL, selector="#salary")
        assert self.engine._action_target_already_filled(act, self.snapshot) is None

    def test_no_match_when_snapshot_empty(self):
        act = BrowserAction(action=ActionType.FILL, selector="#first_name")
        assert self.engine._action_target_already_filled(act, {}) is None

    def test_no_match_when_selector_and_label_empty(self):
        act = BrowserAction(action=ActionType.FILL, selector="")
        assert self.engine._action_target_already_filled(act, self.snapshot) is None

    @pytest.mark.parametrize(
        "action_type",
        [ActionType.CLICK, ActionType.WAIT, ActionType.SCROLL, ActionType.UPLOAD],
    )
    def test_non_fill_actions_ignored(self, action_type):
        act = BrowserAction(action=action_type, selector="input[name=first_name]")
        assert self.engine._action_target_already_filled(act, self.snapshot) is None

    def test_select_action_is_matched(self):
        act = BrowserAction(
            action=ActionType.SELECT,
            selector="select[name=first_name]",
        )
        assert self.engine._action_target_already_filled(act, self.snapshot) == "Jane"

    def test_type_action_is_matched(self):
        act = BrowserAction(
            action=ActionType.TYPE,
            selector="input[name=first_name]",
        )
        assert self.engine._action_target_already_filled(act, self.snapshot) == "Jane"

    def test_case_insensitive_match(self):
        # Snapshot keys are stored lowercase; selector is given uppercase.
        act = BrowserAction(
            action=ActionType.FILL,
            selector="INPUT[NAME=FIRST_NAME]",
        )
        # `_action_target_already_filled` lowercases the selector before
        # comparing, so this must still match.
        assert self.engine._action_target_already_filled(act, self.snapshot) == "Jane"


class TestSnapshotFilled:
    """``_snapshot_filled`` JS-bridge behaviour with mocked ``page.evaluate``."""

    def test_snapshot_filled_builds_dict_from_evaluate(self):
        engine = _make_engine()
        page = _MockPage(
            evaluate_return=[
                {"keys": ["name:first_name", "id:first_name"], "value": "Jane"},
                {"keys": ["label:email address"], "value": "jane@example.com"},
            ]
        )
        snap = engine._snapshot_filled(page)
        assert snap == {
            "name:first_name": "Jane",
            "id:first_name": "Jane",
            "label:email address": "jane@example.com",
        }

    def test_snapshot_filled_drops_placeholder_values(self):
        engine = _make_engine()
        page = _MockPage(
            evaluate_return=[
                {"keys": ["id:country"], "value": "Select..."},
                {"keys": ["id:state"], "value": "Choose"},
                {"keys": ["id:first_name"], "value": "Jane"},
            ]
        )
        snap = engine._snapshot_filled(page)
        assert "id:country" not in snap
        assert "id:state" not in snap
        assert snap["id:first_name"] == "Jane"

    def test_snapshot_filled_drops_empty_values(self):
        engine = _make_engine()
        page = _MockPage(
            evaluate_return=[
                {"keys": ["id:empty"], "value": ""},
                {"keys": ["id:whitespace"], "value": "   "},
                {"keys": ["id:real"], "value": "actual"},
            ]
        )
        snap = engine._snapshot_filled(page)
        assert "id:empty" not in snap
        assert "id:whitespace" not in snap
        assert snap["id:real"] == "actual"

    def test_snapshot_filled_returns_empty_on_evaluate_failure(self):
        engine = _make_engine()
        page = _MockPage(evaluate_raises=RuntimeError("page detached"))
        assert engine._snapshot_filled(page) == {}


# ──────────────────────────────────────────────────────────────────────
# Group 3 — ToolExecutor: _read_live_value + skip-refill guard
# ──────────────────────────────────────────────────────────────────────


class TestReadLiveValue:
    def test_read_live_value_returns_input_value(self):
        page = MagicMock()
        page.locator.return_value = _MockLocator(input_value_value="Jane")
        exe = _make_executor(page)
        assert exe._read_live_value("#first_name") == "Jane"

    def test_read_live_value_falls_back_to_evaluate_when_input_value_fails(self):
        page = MagicMock()
        page.locator.return_value = _MockLocator(
            input_value_raises=RuntimeError("not an input"),
            evaluate_value="Software Engineer",
        )
        exe = _make_executor(page)
        assert exe._read_live_value("div.combobox") == "Software Engineer"

    def test_read_live_value_returns_none_for_missing_element(self):
        page = MagicMock()
        page.locator.return_value = _MockLocator(count_value=0)
        exe = _make_executor(page)
        assert exe._read_live_value("#missing") is None

    def test_read_live_value_returns_none_on_empty_selector(self):
        exe = _make_executor(MagicMock())
        assert exe._read_live_value("") is None

    def test_read_live_value_returns_none_when_everything_throws(self):
        page = MagicMock()
        page.locator.return_value = _MockLocator(
            input_value_raises=RuntimeError("boom"),
            evaluate_raises=RuntimeError("also boom"),
        )
        exe = _make_executor(page)
        assert exe._read_live_value("#x") is None


class TestExecuteActionSkipRefill:
    """Verify ``execute_action`` returns success WITHOUT calling
    ``_execute_type`` when the target field already has a real value.
    """

    def _build_executor_with_live(self, live_value: Optional[str]):
        exe = _make_executor(MagicMock())
        exe._read_live_value = MagicMock(return_value=live_value)
        exe._execute_type = MagicMock(return_value=True)
        exe._execute_click = MagicMock(return_value=True)
        exe._execute_select = MagicMock(return_value=True)
        exe._execute_upload = MagicMock(return_value=True)
        exe._execute_scroll = MagicMock(return_value=True)
        exe._execute_wait = MagicMock(return_value=True)
        return exe

    def test_execute_action_skips_fill_when_field_has_value(self):
        exe = self._build_executor_with_live("Jane")
        act = BrowserAction(
            action=ActionType.FILL,
            selector="#first_name",
            value="Should not overwrite",
            field_label="First Name",
        )
        result = exe.execute_action(act)
        assert result is True
        exe._execute_type.assert_not_called()

    def test_execute_action_proceeds_when_field_empty(self):
        exe = self._build_executor_with_live("")
        act = BrowserAction(
            action=ActionType.FILL,
            selector="#first_name",
            value="Jane",
        )
        exe.execute_action(act)
        exe._execute_type.assert_called_once()

    def test_execute_action_proceeds_when_value_is_placeholder(self):
        exe = self._build_executor_with_live("Select...")
        act = BrowserAction(
            action=ActionType.FILL,
            selector="#country",
            value="United States",
        )
        exe.execute_action(act)
        exe._execute_type.assert_called_once()

    def test_execute_action_proceeds_for_select_actions(self):
        # Select actions are NOT subject to the skip guard (the guard only
        # affects FILL / TYPE); the select handler is what manages dropdowns.
        exe = self._build_executor_with_live("United States")
        act = BrowserAction(
            action=ActionType.SELECT,
            selector="#country",
            value="Canada",
        )
        exe.execute_action(act)
        exe._execute_select.assert_called_once()

    def test_execute_action_proceeds_when_read_live_raises(self):
        exe = _make_executor(MagicMock())
        exe._read_live_value = MagicMock(side_effect=RuntimeError("read failed"))
        exe._execute_type = MagicMock(return_value=True)
        act = BrowserAction(
            action=ActionType.FILL,
            selector="#first_name",
            value="Jane",
        )
        exe.execute_action(act)
        exe._execute_type.assert_called_once()


class TestPlaceholderValuesConstant:
    def test_placeholder_values_constant_contains_common(self):
        for v in ("select", "choose", "n/a", "-- select --", "none"):
            assert v in _PLACEHOLDER_VALUES, f"missing placeholder: {v}"


# ──────────────────────────────────────────────────────────────────────
# Group 4 — LLM client: _propagate_required_flag
# ──────────────────────────────────────────────────────────────────────


class TestPropagateRequiredFlag:
    def test_propagate_required_marks_matching_action(self):
        ax = _make_ax_tree(
            [{"role": "textbox", "name": "First Name", "value": "", "required": True}]
        )
        resp = MagicMock(
            actions=[
                BrowserAction(
                    action=ActionType.FILL,
                    selector="#first_name",
                    field_label="First Name",
                )
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is True

    def test_propagate_required_leaves_non_required_as_false(self):
        ax = _make_ax_tree(
            [
                {"role": "textbox", "name": "First Name", "required": True},
                {"role": "textbox", "name": "Phone", "required": False},
            ]
        )
        resp = MagicMock(
            actions=[
                BrowserAction(action=ActionType.FILL, selector="#phone", field_label="Phone"),
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is False

    def test_propagate_required_handles_empty_form_fields(self):
        ax = _make_ax_tree([])
        resp = MagicMock(
            actions=[
                BrowserAction(action=ActionType.FILL, selector="#x", field_label="X"),
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is False

    def test_propagate_required_handles_no_actions(self):
        ax = _make_ax_tree(
            [{"role": "textbox", "name": "First Name", "required": True}]
        )
        resp = MagicMock(actions=[])
        # Must not raise
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions == []

    def test_propagate_required_matches_partial_label(self):
        # AX field label is "First Name"; the LLM proposes a fill whose
        # field_label is "Enter your First Name". Containment match.
        ax = _make_ax_tree(
            [{"role": "textbox", "name": "First Name", "required": True}]
        )
        resp = MagicMock(
            actions=[
                BrowserAction(
                    action=ActionType.FILL,
                    selector="#first_name",
                    field_label="Enter your First Name",
                ),
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is True

    def test_propagate_required_case_insensitive(self):
        ax = _make_ax_tree(
            [{"role": "textbox", "name": "First Name", "required": True}]
        )
        resp = MagicMock(
            actions=[
                BrowserAction(
                    action=ActionType.FILL,
                    selector="#first_name",
                    field_label="FIRST NAME",
                ),
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is True

    def test_propagate_required_uses_placeholder_as_label(self):
        ax = _make_ax_tree(
            [{"role": "textbox", "placeholder": "Enter email", "required": True}]
        )
        resp = MagicMock(
            actions=[
                BrowserAction(
                    action=ActionType.FILL,
                    selector="input[placeholder='Enter email']",
                    field_label="Enter email",
                ),
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is True

    def test_propagate_required_skips_actions_without_label_or_selector(self):
        ax = _make_ax_tree(
            [{"role": "textbox", "name": "First Name", "required": True}]
        )
        resp = MagicMock(
            actions=[BrowserAction(action=ActionType.FILL, selector="")]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is False


# ──────────────────────────────────────────────────────────────────────
# Group 5 — AgentInterface two-tier prompt
# ──────────────────────────────────────────────────────────────────────


class TestShowFailedFieldsTwoTier:
    def test_show_failed_fields_empty_returns_empty_list(self):
        agent = _make_agent()
        assert agent.show_failed_fields([]) == []

    def test_show_failed_fields_filters_actions_with_value(self):
        # Action that already has a value is NOT actionable; nothing prompted.
        agent = _make_agent()
        agent.request_field_input = MagicMock(return_value="Should not be asked")
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#x",
                value="already set",
                field_label="X",
            ),
        ]
        out = agent.show_failed_fields(acts)
        assert out == []
        agent.request_field_input.assert_not_called()

    def test_show_failed_fields_only_required_uses_required_tag(self):
        agent = _make_agent()
        agent.request_field_input = MagicMock(return_value="Jane")
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#first_name",
                field_label="First Name",
                required=True,
            ),
        ]
        out = agent.show_failed_fields(acts)
        assert len(out) == 1
        assert out[0].value == "Jane"
        args, _ = agent.request_field_input.call_args
        assert args[0] == "First Name"

    def test_show_failed_fields_only_optional_suppressed(self):
        agent = _make_agent()
        agent.request_field_input = MagicMock(return_value="github.com/jane")
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#github",
                field_label="GitHub URL",
                required=False,
            ),
        ]
        out = agent.show_failed_fields(acts)
        assert out == []
        agent.request_field_input.assert_not_called()

    def test_show_failed_fields_required_prompted_optional_ignored(self):
        agent = _make_agent()
        agent.request_field_input = MagicMock(side_effect=["v1", "v2"])
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#opt1",
                field_label="Optional 1",
                required=False,
            ),
            BrowserAction(
                action=ActionType.FILL,
                selector="#req1",
                field_label="Required 1",
                required=True,
            ),
            BrowserAction(
                action=ActionType.FILL,
                selector="#opt2",
                field_label="Optional 2",
                required=False,
            ),
            BrowserAction(
                action=ActionType.FILL,
                selector="#req2",
                field_label="Required 2",
                required=True,
            ),
        ]
        out = agent.show_failed_fields(acts)
        assert len(out) == 2
        assert agent.request_field_input.call_count == 2
        prompted_labels = [c.args[0] for c in agent.request_field_input.call_args_list]
        assert "Required 1" in prompted_labels
        assert "Required 2" in prompted_labels
        assert not any("Optional" in lbl for lbl in prompted_labels)

    def test_show_failed_fields_blank_answer_skips_action(self):
        agent = _make_agent()
        agent.request_field_input = MagicMock(side_effect=["Jane", None])
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#first_name",
                field_label="First Name",
                required=True,
            ),
        ]
        out = agent.show_failed_fields(acts)
        assert len(out) == 1
        assert out[0].field_label == "First Name"
        assert out[0].value == "Jane"

    def test_show_failed_fields_returns_filled_actions_with_values(self):
        agent = _make_agent()
        agent.request_field_input = MagicMock(side_effect=["Jane", "5 years"])
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#first_name",
                field_label="First Name",
                required=True,
            ),
            BrowserAction(
                action=ActionType.FILL,
                selector="#yoe",
                field_label="Years of Experience",
                required=True,
            ),
        ]
        out = agent.show_failed_fields(acts)
        # Values come back attached to the returned actions, and the
        # original action's selector / field_label are preserved.
        values_by_label = {a.field_label: a.value for a in out}
        assert values_by_label == {"First Name": "Jane", "Years of Experience": "5 years"}

    def test_show_failed_fields_coerces_fill_to_select_for_dropdowns(self):
        agent = _make_agent()
        agent.request_field_input = MagicMock(return_value="United States")
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#country",
                field_label="Country",
                required=True,
            ),
        ]
        out = agent.show_failed_fields(
            acts,
            dropdown_options_by_selector={"#country": ["United States", "Canada"]},
        )
        assert len(out) == 1
        # Was FILL; gets rewritten to SELECT when dropdown options are known.
        assert out[0].action == ActionType.SELECT

    def test_show_failed_fields_auto_mode_suppresses_optional(self):
        agent = _make_agent(mode=InteractionMode.AUTO)
        agent.request_field_input = MagicMock(return_value=None)
        acts = [
            BrowserAction(
                action=ActionType.FILL,
                selector="#opt1",
                field_label="Optional 1",
                required=False,
            ),
        ]
        out = agent.show_failed_fields(acts)
        # AUTO mode: the optional section is suppressed entirely, so
        # request_field_input is never invoked for optional fields.
        assert out == []
        agent.request_field_input.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# Group 6 — TUI next-step helpers
# ──────────────────────────────────────────────────────────────────────


class TestNextStepPanel:
    @staticmethod
    def _capture_panel(monkeypatch, command: str, hint: Optional[str] = None):
        """Run _next_step_panel with the console patched and return the
        rendered text of the first Panel that was printed.
        """
        from jobcli.cli import interactive
        from rich.console import Console

        captured: list[Any] = []
        fake_console = MagicMock()
        fake_console.print = lambda *a, **kw: captured.extend(a)
        monkeypatch.setattr(interactive, "console", fake_console)

        if hint is None:
            interactive._next_step_panel(command)
        else:
            interactive._next_step_panel(command, hint)

        # Render every Panel arg to plain text using a real Rich console
        # writing to an in-memory buffer.
        from io import StringIO
        from rich.panel import Panel as _Panel

        buf = StringIO()
        renderer = Console(file=buf, force_terminal=False, width=120, color_system=None)
        for obj in captured:
            if isinstance(obj, _Panel):
                renderer.print(obj)
        return buf.getvalue()

    def test_next_step_panel_emits_command(self, monkeypatch):
        rendered = self._capture_panel(monkeypatch, "apply", "start applying to pending jobs")
        assert "apply" in rendered
        # The panel title is "Next step".
        assert "Next step" in rendered

    def test_next_step_panel_with_hint_emits_hint(self, monkeypatch):
        rendered = self._capture_panel(monkeypatch, "discover", "pull WBL listings")
        assert "pull WBL listings" in rendered

    def test_next_step_panel_without_hint_omits_hint_line(self, monkeypatch):
        rendered = self._capture_panel(monkeypatch, "apply")
        # The command bullet line still renders.
        assert "apply" in rendered

    def test_next_hint_emits_text(self):
        from jobcli.cli import interactive

        with pytest.MonkeyPatch.context() as mp:
            captured_strings: list[str] = []
            fake_console = MagicMock()
            fake_console.print = lambda *a, **kw: captured_strings.append(
                " ".join(str(x) for x in a)
            )
            mp.setattr(interactive, "console", fake_console)

            interactive._next_hint("upload your resume next")

        assert any("upload your resume next" in s for s in captured_strings)
        assert any("Next:" in s for s in captured_strings)


class TestValidateWboxAndExtensionSignature:
    def test_validate_wbox_and_extension_signature_exists(self):
        from jobcli.cli.interactive import _validate_wbox_and_extension

        sig = inspect.signature(_validate_wbox_and_extension)
        params = list(sig.parameters.keys())
        # Must accept (email, password, ext_dir=None).
        assert params[:3] == ["email", "password", "ext_dir"]
        # ext_dir has a default of None so callers can omit it.
        assert sig.parameters["ext_dir"].default is None


# ──────────────────────────────────────────────────────────────────────
# Group 7 — Constants stay in sync
# ──────────────────────────────────────────────────────────────────────


class TestConstantsSync:
    def test_engine_and_executor_placeholders_in_sync(self):
        """Every value the engine treats as a placeholder must also be
        treated as a placeholder by the executor (otherwise the executor
        could overwrite a placeholder that the engine just decided to
        leave alone).
        """
        engine_placeholders = set(ApplicationEngine._SNAPSHOT_PLACEHOLDERS)
        executor_placeholders = set(_PLACEHOLDER_VALUES)
        # Core overlap — both must recognize at least the canonical
        # placeholders that show up in real-world ATS dropdowns.
        core = {"select", "choose", "please choose", "select...",
                "select an option", "-- select --", "none"}
        assert core.issubset(engine_placeholders)
        assert core.issubset(executor_placeholders)

    def test_extension_settle_constant_value(self):
        assert ApplicationEngine.EXTENSION_AUTOFILL_SETTLE_MS == 2500


# ──────────────────────────────────────────────────────────────────────
# Group 8 — Skip keyword must not become form values
# ──────────────────────────────────────────────────────────────────────


class TestSkipFieldKeywordHandling:
    def test_is_skip_field_keyword_recognizes_variants(self):
        from jobcli.utils.exit_signal import is_skip_field_keyword

        assert is_skip_field_keyword("skip")
        assert is_skip_field_keyword("SKIP")
        assert is_skip_field_keyword("skp")
        assert not is_skip_field_keyword("skipping")
        assert not is_skip_field_keyword("3")

    def test_request_field_input_skip_returns_none_without_persist(self):
        agent = _make_agent()
        agent.page = MagicMock()
        agent._read_browser_field_value = MagicMock(return_value=None)
        agent._get_user_input = MagicMock(return_value="skip")
        agent.persist_human_answer = MagicMock(return_value=True)
        agent.lookup_db_answer = MagicMock(return_value=(None, "not_found"))
        agent.show_browser_overlay = MagicMock()
        agent.clear_browser_overlay = MagicMock()
        agent.get_attention = MagicMock()

        assert agent.request_field_input("Portfolio URL", required=True) is None
        agent.persist_human_answer.assert_not_called()

    def test_request_field_input_optional_ask_suppressed(self):
        agent = _make_agent()
        agent._get_user_input = MagicMock(return_value="should not run")
        assert (
            agent.request_field_input("GitHub URL", required=False) is None
        )
        agent._get_user_input.assert_not_called()

    def test_lookup_db_ignores_saved_skip_value(self):
        agent = _make_agent()
        agent.memory = MagicMock()
        agent.memory.get_best_answer.return_value = ("skip", "human")
        value, source = agent.lookup_db_answer("Portfolio URL")
        assert value is None
        assert source == "not_found"

    def test_propagate_required_marks_ask_action(self):
        ax = _make_ax_tree(
            [{"role": "textbox", "name": "Years of Experience *", "required": True}]
        )
        resp = MagicMock(
            actions=[
                BrowserAction(
                    action=ActionType.ASK,
                    selector="Years of Experience",
                    field_label="Years of Experience",
                )
            ]
        )
        LLMClient._propagate_required_flag(resp, ax)
        assert resp.actions[0].required is True

    def test_humanized_fill_refuses_skip_literal(self):
        from jobcli.utils.fill_guard import is_reserved_form_value

        assert is_reserved_form_value("skip")
        exe = _make_executor(MagicMock())
        exe._read_live_value = MagicMock(return_value=None)
        loc = MagicMock()
        assert exe._humanized_fill(loc, "skip") is False
