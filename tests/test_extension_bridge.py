"""Tests for TalentScreen v2 autofill bridge."""

from unittest.mock import MagicMock

import pytest

from jobcli.extension.autofill_bridge import find_autofill_frame, run_extension_autofill
from jobcli.extension.helpers import is_likely_ats_frame_url
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


def test_is_likely_ats_frame_url():
    assert is_likely_ats_frame_url("https://jobs.lever.co/spotify/apply") is True
    assert is_likely_ats_frame_url("https://boards.greenhouse.io/co/jobs/1") is True
    assert (
        is_likely_ats_frame_url(
            "https://newassets.hcaptcha.com/captcha/v1/static/hcaptcha.html"
        )
        is False
    )


def test_find_autofill_frame_prefers_lever_over_hcaptcha():
    page = MagicMock()
    lever = MagicMock()
    lever.url = "https://jobs.lever.co/spotify/apply"
    captcha = MagicMock()
    captcha.url = "https://newassets.hcaptcha.com/captcha/v1/static/hcaptcha.html"
    page.main_frame = lever
    page.frames = [captcha, lever]

    lever.evaluate.return_value = True
    captcha.evaluate.return_value = True

    frame = find_autofill_frame(page)
    assert frame is lever
    assert captcha.evaluate.call_count == 0


def test_run_extension_autofill_calls_inject_configure_fill(sample_resume):
    page = MagicMock()
    frame = MagicMock()
    frame.url = "https://jobs.lever.co/spotify/apply"
    page.main_frame = frame
    page.frames = [frame]
    frame.evaluate.return_value = True
    frame.wait_for_selector.return_value = None
    page.wait_for_function.return_value = None

    inject_result = {"success": True, "schemaVersion": "1.0"}
    fill_result = {
        "mode": "fill",
        "fields": {"filled": [{"field": "email"}], "total": 5},
        "completion": {"percentage": 80},
    }
    report = {"version": "2.0.0"}

    frame.evaluate.side_effect = [
        True,
        inject_result,
        None,
        fill_result,
        report,
    ]

    result = run_extension_autofill(page, sample_resume, logger=None)

    assert result.api_available is True
    assert result.inject_success is True
    assert result.fill_success is True
    assert result.completion_percentage == 80.0
    assert frame.evaluate.call_count >= 4
    assert "injectProfile" in frame.evaluate.call_args_list[1][0][0]


def test_run_extension_autofill_api_unavailable(sample_resume):
    page = MagicMock()
    frame = MagicMock()
    frame.url = "https://jobs.lever.co/spotify/apply"
    page.main_frame = frame
    page.frames = [frame]
    frame.evaluate.return_value = False
    page.wait_for_timeout.return_value = None
    page.wait_for_function.side_effect = Exception("timeout")

    result = run_extension_autofill(page, sample_resume, logger=None)

    assert result.api_available is False
    assert result.inject_success is False
    inject_calls = [
        c for c in frame.evaluate.call_args_list if c[0] and "injectProfile" in c[0][0]
    ]
    assert len(inject_calls) == 0


def test_run_extension_autofill_logs_extension_dir_on_miss(sample_resume):
    page = MagicMock()
    frame = MagicMock()
    frame.url = "https://jobs.lever.co/spotify/apply"
    page.main_frame = frame
    page.frames = [frame]
    frame.evaluate.return_value = False
    page.wait_for_timeout.return_value = None
    page.wait_for_function.side_effect = Exception("timeout")

    logger = MagicMock()
    ext_dir = r"C:\wbox\project-talentscreen-autofill-extension"

    run_extension_autofill(
        page,
        sample_resume,
        logger=logger,
        extension_dir=ext_dir,
    )

    assert logger.warning.called
    warning_msg = logger.warning.call_args[0][0]
    assert "bridge" in warning_msg.lower()
    assert ext_dir in warning_msg
