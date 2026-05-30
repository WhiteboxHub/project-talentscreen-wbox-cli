"""Tests for form sync utilities and highlight gating."""

from unittest.mock import MagicMock, patch

import pytest

from jobcli.utils.form_sync import (
    apply_field_value,
    looks_like_confirmation,
    snapshot_field_values,
)


def test_looks_like_confirmation_strong_on_thank_you_text():
    page = MagicMock()
    page.evaluate.return_value = "thank you for applying to our team"
    page.url = "https://boards.greenhouse.io/acme/jobs/1"
    strong, soft, signals = looks_like_confirmation(page, "https://example.com/form", True)
    assert strong is True
    assert signals["text_confirmed"] is True


def test_looks_like_confirmation_false_on_empty_form():
    page = MagicMock()
    page.evaluate.side_effect = [
        "apply for this job",
        False,  # submit button js
        [],  # validation errors
    ]
    page.url = "https://boards.greenhouse.io/acme/jobs/1/apply"
    strong, _soft, _signals = looks_like_confirmation(
        page, "https://boards.greenhouse.io/acme/jobs/1/apply", True
    )
    assert strong is False


def test_snapshot_field_values_parses_evaluate_result():
    page = MagicMock()
    page.evaluate.return_value = {
        "First Name": "Ada",
        "Email": "ada@example.com",
    }
    snap = snapshot_field_values(page)
    assert snap["First Name"] == "Ada"
    assert snap["Email"] == "ada@example.com"


def test_apply_field_value_returns_true_when_fill_succeeds():
    page = MagicMock()
    loc = MagicMock()
    loc.count.return_value = 1
    first = loc.first
    first.is_visible.return_value = True
    first.evaluate.side_effect = [
        "textbox",
        False,
    ]

    with patch(
        "jobcli.utils.form_sync._locators_for_label",
        return_value=[loc],
    ), patch(
        "jobcli.utils.form_sync._try_select_option",
        return_value=False,
    ), patch(
        "jobcli.utils.form_sync.humanized_fill",
        return_value=True,
    ) as mock_fill:
        ok = apply_field_value(page, "First Name", "Ada")
    assert ok is True
    assert mock_fill.called


def test_maybe_highlight_skipped_by_default():
    from jobcli.orchestration.tool_executor import _maybe_highlight

    loc = MagicMock()
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("JOBCLI_DEBUG_HIGHLIGHT", None)
        _maybe_highlight(loc)
    loc.highlight.assert_not_called()


def test_maybe_highlight_when_env_set():
    from jobcli.orchestration.tool_executor import _maybe_highlight

    loc = MagicMock()
    with patch.dict("os.environ", {"JOBCLI_DEBUG_HIGHLIGHT": "1"}):
        _maybe_highlight(loc)
    loc.highlight.assert_called_once()
