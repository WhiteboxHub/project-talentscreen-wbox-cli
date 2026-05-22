"""Tests for don't-refill helpers."""

from unittest.mock import MagicMock

from jobcli.utils.fill_guard import (
    is_meaningful_value,
    should_skip_refill,
)


def test_is_meaningful_value_rejects_placeholders():
    assert is_meaningful_value("Select...") is False
    assert is_meaningful_value("John Doe") is True


def test_should_skip_refill_when_value_present():
    loc = MagicMock()
    loc.count.return_value = 1
    loc.first = loc
    loc.input_value.return_value = "harish@test.com"
    assert should_skip_refill(loc, "other@email.com") is True


def test_should_not_skip_when_empty():
    loc = MagicMock()
    loc.count.return_value = 1
    loc.first = loc
    loc.input_value.return_value = ""
    loc.evaluate.return_value = ""
    assert should_skip_refill(loc, "John") is False
