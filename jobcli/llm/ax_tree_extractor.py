"""Extract Accessibility Tree (AXTree) for efficient LLM processing."""

from typing import Any

from playwright.sync_api import Page
from pydantic import BaseModel, Field


class AccessibilityNode(BaseModel):
    """A node in the accessibility tree."""

    role: str
    name: str = ""
    value: str = ""
    description: str = ""
    focused: bool = False
    focusable: bool = False
    editable: bool = False
    required: bool = False
    disabled: bool = False
    expanded: bool | None = None
    level: int | None = None
    multiselectable: bool = False
    readonly: bool = False
    selected: bool | None = None
    checked: bool | None = None
    pressed: bool | None = None
    invalid: str = ""
    orientation: str = ""
    autocomplete: str = ""
    children: list["AccessibilityNode"] = Field(default_factory=list)


class AccessibilityTree(BaseModel):
    """Complete accessibility tree."""

    url: str
    title: str
    root: AccessibilityNode
    interactive_nodes: list[dict[str, Any]] = Field(default_factory=list)
    form_fields: list[dict[str, Any]] = Field(default_factory=list)
    buttons: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)


class AccessibilityTreeExtractor:
    """Extract accessibility tree from page."""

    def __init__(self, page: Page) -> None:
        """Initialize extractor."""
        self.page = page

    def extract(self) -> AccessibilityTree:
        """Extract full accessibility tree."""
        url = self.page.url
        title = self.page.title()

        # Get accessibility snapshot
        snapshot = self.page.accessibility.snapshot()

        if not snapshot:
            # Return empty tree
            return AccessibilityTree(
                url=url,
                title=title,
                root=AccessibilityNode(role="WebArea", name=title),
            )

        # Parse snapshot into our model
        root = self._parse_node(snapshot)

        # Extract specific elements for LLM
        interactive_nodes = self._extract_interactive_nodes(snapshot)
        form_fields = self._extract_form_fields(snapshot)
        buttons = self._extract_buttons(snapshot)
        links = self._extract_links(snapshot)

        return AccessibilityTree(
            url=url,
            title=title,
            root=root,
            interactive_nodes=interactive_nodes,
            form_fields=form_fields,
            buttons=buttons,
            links=links,
        )

    def _parse_node(self, node: dict[str, Any]) -> AccessibilityNode:
        """Parse accessibility node."""
        children = []
        if "children" in node:
            children = [self._parse_node(child) for child in node["children"]]

        return AccessibilityNode(
            role=node.get("role", ""),
            name=node.get("name", ""),
            value=node.get("value", ""),
            description=node.get("description", ""),
            focused=node.get("focused", False),
            focusable=node.get("focusable", False),
            editable=node.get("editable", False) == "plaintext"
            or node.get("editable", False) == "richtext",
            required=node.get("required", False),
            disabled=node.get("disabled", False),
            expanded=node.get("expanded"),
            level=node.get("level"),
            multiselectable=node.get("multiselectable", False),
            readonly=node.get("readonly", False),
            selected=node.get("selected"),
            checked=node.get("checked"),
            pressed=node.get("pressed"),
            invalid=node.get("invalid", ""),
            orientation=node.get("orientation", ""),
            autocomplete=node.get("autocomplete", ""),
            children=children,
        )

    def _extract_interactive_nodes(self, node: dict[str, Any], path: str = "") -> list[dict[str, Any]]:
        """Extract interactive nodes from tree."""
        nodes = []

        role = node.get("role", "")
        interactive_roles = [
            "button",
            "link",
            "textbox",
            "searchbox",
            "combobox",
            "checkbox",
            "radio",
            "menuitem",
            "tab",
            "switch",
        ]

        if role in interactive_roles:
            nodes.append(
                {
                    "role": role,
                    "name": node.get("name", ""),
                    "value": node.get("value", ""),
                    "description": node.get("description", ""),
                    "focusable": node.get("focusable", False),
                    "disabled": node.get("disabled", False),
                    "path": path,
                }
            )

        # Recursively process children
        for i, child in enumerate(node.get("children", [])):
            child_path = f"{path}/{i}" if path else str(i)
            nodes.extend(self._extract_interactive_nodes(child, child_path))

        return nodes

    def _extract_form_fields(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract form field nodes."""
        fields = []

        role = node.get("role", "")
        field_roles = ["textbox", "searchbox", "combobox", "spinbutton"]

        if role in field_roles:
            fields.append(
                {
                    "role": role,
                    "name": node.get("name", ""),
                    "value": node.get("value", ""),
                    "placeholder": node.get("placeholder", ""),
                    "required": node.get("required", False),
                    "readonly": node.get("readonly", False),
                    "invalid": node.get("invalid", ""),
                    "autocomplete": node.get("autocomplete", ""),
                }
            )

        # Recursively process children
        for child in node.get("children", []):
            fields.extend(self._extract_form_fields(child))

        return fields

    def _extract_buttons(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract button nodes."""
        buttons = []

        role = node.get("role", "")
        if role == "button":
            buttons.append(
                {
                    "name": node.get("name", ""),
                    "description": node.get("description", ""),
                    "pressed": node.get("pressed"),
                    "disabled": node.get("disabled", False),
                }
            )

        # Recursively process children
        for child in node.get("children", []):
            buttons.extend(self._extract_buttons(child))

        return buttons

    def _extract_links(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract link nodes."""
        links = []

        role = node.get("role", "")
        if role == "link":
            links.append(
                {
                    "name": node.get("name", ""),
                    "description": node.get("description", ""),
                    "url": node.get("url", ""),
                }
            )

        # Recursively process children
        for child in node.get("children", []):
            links.extend(self._extract_links(child))

        return links

    def extract_summary(self) -> dict[str, Any]:
        """Extract a summary optimized for LLM token efficiency."""
        tree = self.extract()

        # Return only the most relevant information
        return {
            "url": tree.url,
            "title": tree.title,
            "buttons": tree.buttons[:10],  # Top 10 buttons
            "form_fields": tree.form_fields[:15],  # Top 15 fields
            "links": [link for link in tree.links if "apply" in link["name"].lower()][:5],
            "interactive_count": len(tree.interactive_nodes),
        }
