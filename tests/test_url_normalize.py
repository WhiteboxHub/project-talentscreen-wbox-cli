"""Tests for canonical job URL normalization."""

from jobcli.core.url_normalize import normalize_job_url


def test_normalize_strips_utm_and_lowercases_host() -> None:
    raw = "HTTPS://Example.COM/path/to/job?utm_source=linkedin&foo=bar"
    out = normalize_job_url(raw)
    assert "utm_" not in out
    assert "example.com" in out
    assert "foo=bar" in out


def test_normalize_trailing_slash() -> None:
    assert normalize_job_url("https://x.com/jobs/1/") == "https://x.com/jobs/1"
