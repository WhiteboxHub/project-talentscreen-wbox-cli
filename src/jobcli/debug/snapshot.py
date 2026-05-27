"""DOM snapshot capture for replay and debugging.

Captures complete page state including DOM, styles, screenshots, and metadata.
"""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page
from pydantic import BaseModel, Field


class ElementSnapshot(BaseModel):
    """Snapshot of a single DOM element.

    Captures all information needed to:
    - Locate the element in replay
    - Understand why selector matched/didn't match
    - Debug visual state
    """

    selector: str = Field(..., description="CSS selector used")
    exists: bool = Field(..., description="Did element exist?")
    visible: bool = Field(False, description="Was element visible?")
    enabled: bool = Field(False, description="Was element enabled?")

    # Element properties
    tag_name: Optional[str] = Field(None, description="HTML tag name")
    id: Optional[str] = Field(None, description="Element ID")
    class_name: Optional[str] = Field(None, description="Element classes")
    name: Optional[str] = Field(None, description="Element name attribute")
    type: Optional[str] = Field(None, description="Element type attribute")
    value: Optional[str] = Field(None, description="Element value")
    text: Optional[str] = Field(None, description="Element text content")
    placeholder: Optional[str] = Field(None, description="Placeholder text")

    # Position & size
    x: Optional[float] = Field(None, description="X coordinate")
    y: Optional[float] = Field(None, description="Y coordinate")
    width: Optional[float] = Field(None, description="Width in pixels")
    height: Optional[float] = Field(None, description="Height in pixels")

    # Computed styles
    display: Optional[str] = Field(None, description="CSS display property")
    visibility: Optional[str] = Field(None, description="CSS visibility property")
    opacity: Optional[str] = Field(None, description="CSS opacity property")

    # Context
    parent_tag: Optional[str] = Field(None, description="Parent element tag")
    siblings_count: int = Field(0, description="Number of sibling elements")

    # Screenshot (base64 encoded PNG)
    screenshot_data: Optional[str] = Field(None, description="Base64 screenshot")


class DOMSnapshot(BaseModel):
    """Complete DOM snapshot at a point in time.

    Contains everything needed to reconstruct page state for debugging.
    """

    # Metadata
    snapshot_id: str = Field(..., description="Unique snapshot ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    url: str = Field(..., description="Page URL")
    title: str = Field("", description="Page title")

    # DOM state
    html: str = Field(..., description="Complete HTML source")
    viewport_width: int = Field(..., description="Viewport width")
    viewport_height: int = Field(..., description="Viewport height")
    scroll_x: float = Field(0.0, description="Horizontal scroll position")
    scroll_y: float = Field(0.0, description="Vertical scroll position")

    # Screenshots
    full_screenshot: Optional[str] = Field(None, description="Full page screenshot (base64)")
    viewport_screenshot: Optional[str] = Field(None, description="Viewport screenshot (base64)")

    # Element snapshots (for active fields)
    elements: Dict[str, ElementSnapshot] = Field(
        default_factory=dict,
        description="Element snapshots keyed by field_id",
    )

    # Page metadata
    ats_type: Optional[str] = Field(None, description="Detected ATS type")
    form_count: int = Field(0, description="Number of forms on page")
    input_count: int = Field(0, description="Number of input elements")
    button_count: int = Field(0, description="Number of buttons")

    # Performance
    capture_duration_ms: int = Field(0, description="Time taken to capture snapshot")

    def save(self, directory: Path) -> Path:
        """Save snapshot to directory.

        Args:
            directory: Directory to save snapshot

        Returns:
            Path to saved snapshot file
        """
        directory.mkdir(parents=True, exist_ok=True)

        # Save JSON
        snapshot_file = directory / f"{self.snapshot_id}.json"
        with open(snapshot_file, "w") as f:
            json.dump(self.model_dump(), f, indent=2, default=str)

        # Save HTML separately for easy viewing
        html_file = directory / f"{self.snapshot_id}.html"
        with open(html_file, "w") as f:
            f.write(self.html)

        # Save screenshots if present
        if self.full_screenshot:
            screenshot_file = directory / f"{self.snapshot_id}_full.png"
            screenshot_data = base64.b64decode(self.full_screenshot)
            screenshot_file.write_bytes(screenshot_data)

        if self.viewport_screenshot:
            screenshot_file = directory / f"{self.snapshot_id}_viewport.png"
            screenshot_data = base64.b64decode(self.viewport_screenshot)
            screenshot_file.write_bytes(screenshot_data)

        return snapshot_file

    @classmethod
    def load(cls, snapshot_file: Path) -> "DOMSnapshot":
        """Load snapshot from file.

        Args:
            snapshot_file: Path to snapshot JSON file

        Returns:
            DOMSnapshot instance
        """
        with open(snapshot_file) as f:
            data = json.load(f)
        return cls(**data)


class SnapshotCapture:
    """Capture DOM snapshots from Playwright pages."""

    def __init__(self, page: Page):
        """Initialize snapshot capture.

        Args:
            page: Playwright Page instance
        """
        self.page = page

    def capture(
        self,
        snapshot_id: Optional[str] = None,
        include_full_screenshot: bool = True,
        include_viewport_screenshot: bool = True,
        element_selectors: Optional[Dict[str, str]] = None,
    ) -> DOMSnapshot:
        """Capture a complete DOM snapshot.

        Args:
            snapshot_id: Custom snapshot ID (auto-generated if None)
            include_full_screenshot: Capture full page screenshot?
            include_viewport_screenshot: Capture viewport screenshot?
            element_selectors: Dict of {field_id: selector} to capture

        Returns:
            DOMSnapshot with all captured data
        """
        start_time = datetime.utcnow()

        # Generate snapshot ID
        if not snapshot_id:
            url_hash = hashlib.md5(self.page.url.encode()).hexdigest()[:8]
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            snapshot_id = f"snapshot_{timestamp}_{url_hash}"

        # Capture HTML
        html = self.page.content()

        # Capture viewport info
        viewport = self.page.viewport_size
        viewport_width = viewport["width"] if viewport else 1920
        viewport_height = viewport["height"] if viewport else 1080

        # Capture scroll position
        scroll_position = self.page.evaluate(
            "() => ({ x: window.scrollX, y: window.scrollY })"
        )

        # Capture screenshots
        full_screenshot = None
        viewport_screenshot = None

        if include_full_screenshot:
            try:
                screenshot_bytes = self.page.screenshot(full_page=True, type="png")
                full_screenshot = base64.b64encode(screenshot_bytes).decode("utf-8")
            except Exception:
                pass  # Screenshot failed, continue

        if include_viewport_screenshot:
            try:
                screenshot_bytes = self.page.screenshot(full_page=False, type="png")
                viewport_screenshot = base64.b64encode(screenshot_bytes).decode("utf-8")
            except Exception:
                pass

        # Capture page metadata
        title = self.page.title()
        form_count = self.page.locator("form").count()
        input_count = self.page.locator("input, textarea").count()
        button_count = self.page.locator("button, input[type='submit']").count()

        # Capture element snapshots
        elements = {}
        if element_selectors:
            for field_id, selector in element_selectors.items():
                element_snapshot = self._capture_element(field_id, selector)
                if element_snapshot:
                    elements[field_id] = element_snapshot

        # Calculate duration
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return DOMSnapshot(
            snapshot_id=snapshot_id,
            timestamp=start_time,
            url=self.page.url,
            title=title,
            html=html,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            scroll_x=scroll_position["x"],
            scroll_y=scroll_position["y"],
            full_screenshot=full_screenshot,
            viewport_screenshot=viewport_screenshot,
            elements=elements,
            form_count=form_count,
            input_count=input_count,
            button_count=button_count,
            capture_duration_ms=duration_ms,
        )

    def _capture_element(self, field_id: str, selector: str) -> Optional[ElementSnapshot]:
        """Capture snapshot of a specific element.

        Args:
            field_id: Field identifier
            selector: CSS selector

        Returns:
            ElementSnapshot or None if element doesn't exist
        """
        try:
            locator = self.page.locator(selector).first

            # Check if exists
            count = locator.count()
            if count == 0:
                return ElementSnapshot(selector=selector, exists=False)

            # Basic properties
            exists = True
            visible = locator.is_visible()
            enabled = locator.is_enabled() if visible else False

            # Get element properties
            element_data = locator.evaluate(
                """(el) => ({
                    tagName: el.tagName.toLowerCase(),
                    id: el.id || null,
                    className: el.className || null,
                    name: el.getAttribute('name') || null,
                    type: el.getAttribute('type') || null,
                    value: el.value || null,
                    text: el.textContent?.trim() || null,
                    placeholder: el.getAttribute('placeholder') || null,
                    parentTag: el.parentElement?.tagName.toLowerCase() || null,
                    siblingsCount: el.parentElement?.children.length || 0
                })"""
            )

            # Get bounding box
            bbox = locator.bounding_box()
            x = bbox["x"] if bbox else None
            y = bbox["y"] if bbox else None
            width = bbox["width"] if bbox else None
            height = bbox["height"] if bbox else None

            # Get computed styles
            styles = locator.evaluate(
                """(el) => {
                    const computed = window.getComputedStyle(el);
                    return {
                        display: computed.display,
                        visibility: computed.visibility,
                        opacity: computed.opacity
                    };
                }"""
            )

            # Capture element screenshot (small, just the element)
            screenshot_data = None
            if visible and bbox:
                try:
                    screenshot_bytes = locator.screenshot(type="png")
                    screenshot_data = base64.b64encode(screenshot_bytes).decode("utf-8")
                except Exception:
                    pass  # Screenshot failed

            return ElementSnapshot(
                selector=selector,
                exists=exists,
                visible=visible,
                enabled=enabled,
                tag_name=element_data.get("tagName"),
                id=element_data.get("id"),
                class_name=element_data.get("className"),
                name=element_data.get("name"),
                type=element_data.get("type"),
                value=element_data.get("value"),
                text=element_data.get("text"),
                placeholder=element_data.get("placeholder"),
                x=x,
                y=y,
                width=width,
                height=height,
                display=styles.get("display"),
                visibility=styles.get("visibility"),
                opacity=styles.get("opacity"),
                parent_tag=element_data.get("parentTag"),
                siblings_count=element_data.get("siblingsCount", 0),
                screenshot_data=screenshot_data,
            )

        except Exception as e:
            # Element capture failed
            return ElementSnapshot(
                selector=selector,
                exists=False,
            )

    def capture_before_action(
        self,
        action_target: str,
        action_selector: str,
        related_selectors: Optional[Dict[str, str]] = None,
    ) -> DOMSnapshot:
        """Capture snapshot before executing an action.

        Args:
            action_target: Target field ID
            action_selector: Selector for action
            related_selectors: Additional selectors to capture

        Returns:
            DOMSnapshot
        """
        selectors = {action_target: action_selector}
        if related_selectors:
            selectors.update(related_selectors)

        snapshot_id = f"before_{action_target}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        return self.capture(
            snapshot_id=snapshot_id,
            include_full_screenshot=False,  # Skip full page for performance
            include_viewport_screenshot=True,
            element_selectors=selectors,
        )

    def capture_after_action(
        self,
        action_target: str,
        action_selector: str,
        related_selectors: Optional[Dict[str, str]] = None,
    ) -> DOMSnapshot:
        """Capture snapshot after executing an action.

        Args:
            action_target: Target field ID
            action_selector: Selector for action
            related_selectors: Additional selectors to capture

        Returns:
            DOMSnapshot
        """
        selectors = {action_target: action_selector}
        if related_selectors:
            selectors.update(related_selectors)

        snapshot_id = f"after_{action_target}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        return self.capture(
            snapshot_id=snapshot_id,
            include_full_screenshot=False,
            include_viewport_screenshot=True,
            element_selectors=selectors,
        )

    def capture_failure(
        self,
        action_target: str,
        action_selector: str,
        error_message: str,
    ) -> DOMSnapshot:
        """Capture snapshot when action fails.

        Args:
            action_target: Target field ID
            action_selector: Selector for action
            error_message: Error message

        Returns:
            DOMSnapshot with failure context
        """
        snapshot_id = f"failure_{action_target}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        snapshot = self.capture(
            snapshot_id=snapshot_id,
            include_full_screenshot=True,  # Full page on failure
            include_viewport_screenshot=True,
            element_selectors={action_target: action_selector},
        )

        return snapshot
