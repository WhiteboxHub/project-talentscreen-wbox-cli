"""Tests for TalentScreen v2 autofill bridge."""

from unittest.mock import MagicMock

import pytest

from jobcli.extension.autofill_bridge import run_extension_autofill
from jobcli.profile.schemas import PersonalInfo, ResumeData


@pytest.fixture
def sample_resume():
    return ResumeData(
        personal=PersonalInfo(
            first_name="Test",
            last_name="User",
            email="test@example.com",
        ),
    )


def test_run_extension_autofill_calls_inject_configure_fill(sample_resume):
    page = MagicMock()
    page.wait_for_function.return_value = None
    page.wait_for_selector.return_value = None

    inject_result = {"success": True, "schemaVersion": "1.0"}
    fill_result = {
        "mode": "fill",
        "fields": {"filled": [{"field": "email"}], "total": 5},
        "completion": {"percentage": 80},
    }
    report = {"version": "2.0.0"}

    page.evaluate.side_effect = [inject_result, None, fill_result, report]

    result = run_extension_autofill(page, sample_resume, logger=None)

    assert result.api_available is True
    assert result.inject_success is True
    assert result.fill_success is True
    assert result.completion_percentage == 80.0

    # injectProfile, configure, fill, exportReport
    assert page.evaluate.call_count == 4
    first_call_arg = page.evaluate.call_args_list[0][0][0]
    assert "injectProfile" in first_call_arg


def test_run_extension_autofill_api_unavailable(sample_resume):
    page = MagicMock()
    page.wait_for_function.side_effect = Exception("timeout")

    result = run_extension_autofill(page, sample_resume, logger=None)

    assert result.api_available is False
    assert result.inject_success is False
    page.evaluate.assert_not_called()
