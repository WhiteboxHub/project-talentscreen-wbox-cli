"""Tests for in-browser human handoff overlay injection."""

from unittest.mock import MagicMock

import pytest

from jobcli.human.agent_interface import AgentInterface


@pytest.fixture
def agent():
    page = MagicMock()
    iface = AgentInterface(
        page=page,
        locator_repo=MagicMock(),
    )
    return iface


class TestShowBrowserOverlay:
    def test_injects_draggable_overlay_script(self, agent):
        agent.show_browser_overlay(
            "JobCLI handed control back to you",
            "Please fill the missing fields.",
            kind="warning",
        )
        agent.page.evaluate.assert_called_once()
        script, payload = agent.page.evaluate.call_args[0]
        assert "drag-handle" in script
        assert "pointerdown" in script
        assert "sessionStorage" in script
        assert "storageKey" in script
        assert payload["storageKey"] == AgentInterface._OVERLAY_STORAGE_KEY
        assert payload["id"] == AgentInterface._OVERLAY_ID

    def test_hint_mentions_drag_handle(self, agent):
        agent.show_browser_overlay("Title", "Message")
        script, _ = agent.page.evaluate.call_args[0]
        assert "Drag the banner by the handle to move it" in script

    def test_clear_removes_overlay_by_id(self, agent):
        agent.clear_browser_overlay()
        agent.page.evaluate.assert_called_once_with(
            agent.page.evaluate.call_args[0][0],
            AgentInterface._OVERLAY_ID,
        )
