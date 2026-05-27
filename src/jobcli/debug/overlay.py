"""Field overlay debugger for visual inspection.

Renders overlay on page showing detected fields, confidence, and actions.
"""

from typing import Dict, List, Optional

from playwright.sync_api import Page
from pydantic import BaseModel, Field


class FieldOverlay(BaseModel):
    """Overlay information for a single field."""

    field_id: str
    selector: str
    semantic_type: str
    confidence: float
    value: Optional[str] = None
    required: bool = False
    status: str = "pending"  # pending, success, failed, skipped
    error: Optional[str] = None


class OverlayDebugger:
    """Render debug overlay on page for visual field inspection."""

    def __init__(self, page: Page):
        """Initialize overlay debugger.

        Args:
            page: Playwright Page instance
        """
        self.page = page
        self._overlay_injected = False

    def inject_overlay_script(self) -> None:
        """Inject overlay CSS and JS into page."""
        if self._overlay_injected:
            return

        # Inject CSS
        css = """
        <style id="jobcli-debug-overlay-css">
            .jobcli-overlay {
                position: fixed;
                pointer-events: none;
                z-index: 999999;
                border: 2px solid;
                box-sizing: border-box;
            }
            .jobcli-overlay.pending {
                border-color: #ffaa00;
                background: rgba(255, 170, 0, 0.1);
            }
            .jobcli-overlay.success {
                border-color: #00ff00;
                background: rgba(0, 255, 0, 0.1);
            }
            .jobcli-overlay.failed {
                border-color: #ff0000;
                background: rgba(255, 0, 0, 0.1);
            }
            .jobcli-overlay.skipped {
                border-color: #888888;
                background: rgba(136, 136, 136, 0.1);
            }
            .jobcli-label {
                position: fixed;
                z-index: 9999999;
                background: rgba(0, 0, 0, 0.9);
                color: white;
                padding: 4px 8px;
                border-radius: 3px;
                font-family: 'Monaco', 'Menlo', monospace;
                font-size: 11px;
                pointer-events: none;
                white-space: nowrap;
            }
            .jobcli-label.pending {
                background: rgba(255, 170, 0, 0.95);
                color: black;
            }
            .jobcli-label.success {
                background: rgba(0, 255, 0, 0.95);
                color: black;
            }
            .jobcli-label.failed {
                background: rgba(255, 0, 0, 0.95);
                color: white;
            }
            .jobcli-panel {
                position: fixed;
                top: 10px;
                right: 10px;
                width: 300px;
                max-height: 80vh;
                overflow-y: auto;
                background: rgba(0, 0, 0, 0.95);
                color: white;
                padding: 15px;
                border-radius: 5px;
                font-family: 'Monaco', 'Menlo', monospace;
                font-size: 12px;
                z-index: 99999999;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            }
            .jobcli-panel h3 {
                margin: 0 0 10px 0;
                font-size: 14px;
                border-bottom: 1px solid #444;
                padding-bottom: 5px;
            }
            .jobcli-panel .field-item {
                padding: 8px;
                margin: 5px 0;
                background: rgba(255,255,255,0.05);
                border-radius: 3px;
                border-left: 3px solid #888;
            }
            .jobcli-panel .field-item.pending {
                border-left-color: #ffaa00;
            }
            .jobcli-panel .field-item.success {
                border-left-color: #00ff00;
            }
            .jobcli-panel .field-item.failed {
                border-left-color: #ff0000;
            }
            .jobcli-panel .field-name {
                font-weight: bold;
                color: #4fc1ff;
            }
            .jobcli-panel .field-confidence {
                color: #dcdcaa;
                font-size: 10px;
            }
            .jobcli-panel .field-status {
                color: #ce9178;
                font-size: 10px;
            }
            .jobcli-panel .field-error {
                color: #f48771;
                font-size: 10px;
                margin-top: 3px;
            }
        </style>
        """

        self.page.evaluate(
            f"""
            () => {{
                const style = document.createElement('div');
                style.innerHTML = `{css}`;
                document.head.appendChild(style);
            }}
        """
        )

        self._overlay_injected = True

    def highlight_field(
        self,
        field_id: str,
        selector: str,
        status: str = "pending",
        label: Optional[str] = None,
    ) -> None:
        """Highlight a field with overlay.

        Args:
            field_id: Field identifier
            selector: CSS selector
            status: Field status (pending, success, failed, skipped)
            label: Optional label text
        """
        self.inject_overlay_script()

        if label is None:
            label = field_id

        # Inject overlay for this field
        self.page.evaluate(
            f"""
            (selector, fieldId, status, label) => {{
                // Remove existing overlay for this field
                const existing = document.querySelector(`[data-jobcli-field="${{fieldId}}"]`);
                if (existing) existing.remove();

                const existingLabel = document.querySelector(`[data-jobcli-label="${{fieldId}}"]`);
                if (existingLabel) existingLabel.remove();

                // Find element
                const element = document.querySelector(selector);
                if (!element) return;

                const rect = element.getBoundingClientRect();

                // Create overlay
                const overlay = document.createElement('div');
                overlay.className = `jobcli-overlay ${{status}}`;
                overlay.setAttribute('data-jobcli-field', fieldId);
                overlay.style.left = rect.left + window.scrollX + 'px';
                overlay.style.top = rect.top + window.scrollY + 'px';
                overlay.style.width = rect.width + 'px';
                overlay.style.height = rect.height + 'px';
                document.body.appendChild(overlay);

                // Create label
                const labelDiv = document.createElement('div');
                labelDiv.className = `jobcli-label ${{status}}`;
                labelDiv.setAttribute('data-jobcli-label', fieldId);
                labelDiv.textContent = label;
                labelDiv.style.left = rect.left + window.scrollX + 'px';
                labelDiv.style.top = (rect.top + window.scrollY - 22) + 'px';
                document.body.appendChild(labelDiv);
            }}
        """,
            selector,
            field_id,
            status,
            label,
        )

    def update_field_status(
        self,
        field_id: str,
        status: str,
        label: Optional[str] = None,
    ) -> None:
        """Update field overlay status.

        Args:
            field_id: Field identifier
            status: New status (pending, success, failed, skipped)
            label: Updated label text
        """
        self.page.evaluate(
            f"""
            (fieldId, status, label) => {{
                const overlay = document.querySelector(`[data-jobcli-field="${{fieldId}}"]`);
                if (overlay) {{
                    overlay.className = `jobcli-overlay ${{status}}`;
                }}

                const labelDiv = document.querySelector(`[data-jobcli-label="${{fieldId}}"]`);
                if (labelDiv) {{
                    labelDiv.className = `jobcli-label ${{status}}`;
                    if (label) {{
                        labelDiv.textContent = label;
                    }}
                }}
            }}
        """,
            field_id,
            status,
            label or "",
        )

    def remove_field_highlight(self, field_id: str) -> None:
        """Remove overlay for a field.

        Args:
            field_id: Field identifier
        """
        self.page.evaluate(
            f"""
            (fieldId) => {{
                const overlay = document.querySelector(`[data-jobcli-field="${{fieldId}}"]`);
                if (overlay) overlay.remove();

                const label = document.querySelector(`[data-jobcli-label="${{fieldId}}"]`);
                if (label) label.remove();
            }}
        """,
            field_id,
        )

    def show_fields_panel(self, fields: List[FieldOverlay]) -> None:
        """Show debug panel with all fields.

        Args:
            fields: List of field overlays to display
        """
        self.inject_overlay_script()

        # Build panel HTML
        fields_html = ""
        for field in fields:
            confidence_pct = f"{field.confidence:.0%}"
            status_icon = {
                "pending": "⏳",
                "success": "✓",
                "failed": "✗",
                "skipped": "○",
            }.get(field.status, "?")

            fields_html += f"""
            <div class="field-item {field.status}">
                <div class="field-name">{status_icon} {field.field_id}</div>
                <div class="field-confidence">
                    {field.semantic_type} · {confidence_pct} confidence
                    {' · required' if field.required else ''}
                </div>
                <div class="field-status">{field.status}</div>
                {f'<div class="field-error">{field.error}</div>' if field.error else ''}
            </div>
            """

        panel_html = f"""
        <div id="jobcli-debug-panel" class="jobcli-panel">
            <h3>JobCLI Debug Panel</h3>
            <div>Fields: {len(fields)}</div>
            <div style="margin-top: 10px;">
                {fields_html}
            </div>
        </div>
        """

        # Remove existing panel
        self.page.evaluate("() => { const p = document.getElementById('jobcli-debug-panel'); if (p) p.remove(); }")

        # Inject panel
        self.page.evaluate(
            f"""
            () => {{
                const panel = document.createElement('div');
                panel.innerHTML = `{panel_html}`;
                document.body.appendChild(panel);
            }}
        """
        )

    def clear_overlays(self) -> None:
        """Clear all overlays from page."""
        self.page.evaluate(
            """
            () => {
                document.querySelectorAll('.jobcli-overlay').forEach(el => el.remove());
                document.querySelectorAll('.jobcli-label').forEach(el => el.remove());
                const panel = document.getElementById('jobcli-debug-panel');
                if (panel) panel.remove();
            }
        """
        )

    def highlight_all_inputs(self) -> None:
        """Highlight all input elements on page for debugging."""
        self.inject_overlay_script()

        self.page.evaluate(
            """
            () => {
                const inputs = document.querySelectorAll('input, textarea, select');
                inputs.forEach((input, index) => {
                    const rect = input.getBoundingClientRect();

                    const overlay = document.createElement('div');
                    overlay.className = 'jobcli-overlay pending';
                    overlay.setAttribute('data-jobcli-field', `input_${index}`);
                    overlay.style.left = rect.left + window.scrollX + 'px';
                    overlay.style.top = rect.top + window.scrollY + 'px';
                    overlay.style.width = rect.width + 'px';
                    overlay.style.height = rect.height + 'px';
                    document.body.appendChild(overlay);

                    const label = `${input.tagName}[${input.type || 'text'}]${input.name ? `[name="${input.name}"]` : ''}`;
                    const labelDiv = document.createElement('div');
                    labelDiv.className = 'jobcli-label pending';
                    labelDiv.setAttribute('data-jobcli-label', `input_${index}`);
                    labelDiv.textContent = label;
                    labelDiv.style.left = rect.left + window.scrollX + 'px';
                    labelDiv.style.top = (rect.top + window.scrollY - 22) + 'px';
                    document.body.appendChild(labelDiv);
                });
            }
        """
        )


def create_overlay_from_canonical(canonical_fields: List[Dict]) -> List[FieldOverlay]:
    """Create field overlays from canonical model fields.

    Args:
        canonical_fields: List of canonical field dicts

    Returns:
        List of FieldOverlay instances
    """
    overlays = []

    for field in canonical_fields:
        overlay = FieldOverlay(
            field_id=field.get("field_id", "unknown"),
            selector=field.get("selector", ""),
            semantic_type=field.get("semantic_type", "unknown"),
            confidence=field.get("confidence", 0.0),
            value=field.get("value"),
            required=field.get("required", False),
            status="pending",
        )
        overlays.append(overlay)

    return overlays
