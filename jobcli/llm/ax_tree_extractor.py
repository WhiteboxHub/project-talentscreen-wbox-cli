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
    dropdown_fields: list[dict[str, Any]] = Field(default_factory=list)
    buttons: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)


class AccessibilityTreeExtractor:
    """Extract accessibility tree from page."""

    def __init__(self, page: Page) -> None:
        """Initialize extractor."""
        self.page = page

    def extract(self) -> AccessibilityTree:
        """Extract full accessibility tree using aria_snapshot (primary) or CDP (fallback)."""
        url = self.page.url
        title = self.page.title()

        snapshot = None
        raw_aria = ""

        # Primary: use Playwright's aria_snapshot — reliable across all versions
        try:
            raw_aria = self.page.locator("body").aria_snapshot()
        except Exception:
            pass

        # Also capture any ATS iframe content and append it
        ats_patterns = ["greenhouse.io", "lever.co", "workday.com", "icims.com", "ashby.com"]
        for frame in self.page.frames:
            frame_url = frame.url or ""
            if any(p in frame_url for p in ats_patterns):
                try:
                    iframe_aria = frame.locator("body").aria_snapshot()
                    if iframe_aria:
                        raw_aria += f"\n\n## Application Form (iframe: {frame_url[:60]}):\n{iframe_aria}"
                except Exception:
                    pass

        if raw_aria:
            snapshot = self._parse_aria_text(raw_aria)

        # Fallback: CDP
        if not snapshot:
            try:
                cdp = self.page.context.new_cdp_session(self.page)
                result = cdp.send("Accessibility.getFullAXTree")
                cdp.detach()
                raw_nodes = result.get("nodes", [])
                if raw_nodes:
                    snapshot = self._cdp_to_snapshot(raw_nodes)
            except Exception:
                pass

        if not snapshot:
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
        dropdowns = self._detect_dropdown_fields()

        tree = AccessibilityTree(
            url=url,
            title=title,
            root=root,
            interactive_nodes=interactive_nodes,
            form_fields=form_fields,
            dropdown_fields=dropdowns,
            buttons=buttons,
            links=links,
        )

        # Attach the raw aria text for direct LLM consumption
        tree._raw_aria = raw_aria  # type: ignore[attr-defined]
        return tree

    def _cdp_to_snapshot(self, raw_nodes: list[dict]) -> dict[str, Any] | None:
        """Convert flat CDP AXTree node list into a nested snapshot dict."""
        if not raw_nodes:
            return None

        node_map: dict[str, dict] = {}
        for node in raw_nodes:
            node_id = node.get("nodeId", "")
            role_obj = node.get("role", {})
            name_obj = node.get("name", {})
            value_obj = node.get("value", {})
            desc_obj = node.get("description", {})

            props = {}
            for prop in node.get("properties", []):
                props[prop.get("name", "")] = prop.get("value", {}).get("value")

            parsed = {
                "role": role_obj.get("value", "none"),
                "name": name_obj.get("value", ""),
                "value": value_obj.get("value", "") if value_obj else "",
                "description": desc_obj.get("value", "") if desc_obj else "",
                "focused": props.get("focused", False),
                "focusable": props.get("focusable", False),
                "required": props.get("required", False),
                "disabled": props.get("disabled", False),
                "readonly": props.get("readonly", False),
                "invalid": props.get("invalid", ""),
                "editable": props.get("editable", ""),
                "children": [],
            }
            node_map[node_id] = parsed

            # Wire children
            child_ids = node.get("childIds", [])
            for cid in child_ids:
                if cid in node_map:
                    parsed["children"].append(node_map[cid])

        # Second pass: wire children that were created after their parent
        for node in raw_nodes:
            node_id = node.get("nodeId", "")
            parent = node_map.get(node_id)
            if not parent:
                continue
            for cid in node.get("childIds", []):
                child = node_map.get(cid)
                if child and child not in parent["children"]:
                    parent["children"].append(child)

        # Root is the first node
        root_id = raw_nodes[0].get("nodeId", "")
        return node_map.get(root_id)

    def _aria_fallback(self) -> dict[str, Any] | None:
        """Fallback: use Playwright's aria_snapshot() to build a minimal tree."""
        try:
            aria_text = self.page.locator("body").aria_snapshot()
            if not aria_text:
                return None

            # Parse the YAML-like aria snapshot into our dict format
            return self._parse_aria_text(aria_text)
        except Exception:
            return None

    def _parse_aria_text(self, text: str) -> dict[str, Any]:
        """Parse aria_snapshot text into a basic snapshot dict."""
        root: dict[str, Any] = {"role": "WebArea", "name": "", "children": []}

        for line in text.strip().split("\n"):
            line = line.strip().lstrip("- ")
            if not line:
                continue

            # Parse lines like: heading "Example Domain" [level=1]
            # or: textbox "First Name"
            # or: link "Apply":
            role = line.split(" ", 1)[0] if " " in line else line.rstrip(":")
            name = ""
            if '"' in line:
                parts = line.split('"')
                if len(parts) >= 2:
                    name = parts[1]

            child: dict[str, Any] = {"role": role, "name": name, "children": []}
            root["children"].append(child)

        return root

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

    def _detect_dropdown_fields(self) -> list[dict[str, Any]]:
        """Find all dropdown/select fields and pre-extract their options from the DOM.
        
        This explores native <select> elements and custom ARIA combobox/listbox
        elements to provide options *before* the LLM decides.
        """
        dropdowns = []
        
        # We need to look in both the main document and any iframes
        frames_to_check = [self.page.main_frame] + self.page.frames
        
        for frame in frames_to_check:
            try:
                # 1. Native <select> elements
                select_locators = frame.locator("select").all()
                for sel in select_locators:
                    try:
                        label = self._find_label_for_element(sel, frame)
                        options = []
                        for opt in sel.locator("option").all():
                            text = opt.text_content()
                            if text and text.strip():
                                options.append(text.strip())
                        
                        if options:
                            dropdowns.append({
                                "label": label,
                                "type": "native_select",
                                "options": options,
                            })
                    except Exception:
                        pass
                
                # 2. Custom ARIA comboboxes/listboxes
                aria_dropdowns = frame.locator("[role='combobox'], [role='listbox']").all()
                for cb in aria_dropdowns:
                    try:
                        label = self._find_label_for_element(cb, frame)
                        # We cannot reliably pre-extract options for custom ones if they aren't expanded,
                        # but we can note that the field exists and is a dropdown.
                        dropdowns.append({
                            "label": label,
                            "type": "custom_dropdown",
                            "options": [],
                        })
                    except Exception:
                        pass
            except Exception:
                continue

        return dropdowns

    def _find_label_for_element(self, element, frame) -> str:
        """Attempt to find the associated label text for an element."""
        try:
            # Try aria-label first
            aria_label = element.get_attribute("aria-label")
            if aria_label:
                return aria_label.strip()
                
            # Try aria-labelledby
            aria_labelledby = element.get_attribute("aria-labelledby")
            if aria_labelledby:
                label_el = frame.locator(f"#{aria_labelledby}").first
                if label_el:
                    text = label_el.text_content()
                    if text:
                        return text.strip()
            
            # Try id -> associated <label for="id">
            el_id = element.get_attribute("id")
            if el_id:
                label_el = frame.locator(f"label[for='{el_id}']").first
                if label_el:
                    text = label_el.text_content()
                    if text:
                        return text.strip()
            
            # Try closest <label> ancestor
            # Playwright doesn't have a direct 'closest' but we can evaluate it
            text = element.evaluate("(el) => { const label = el.closest('label'); return label ? label.textContent : ''; }")
            if text and text.strip():
                return text.strip()
                
            # Try preceding text element
            text = element.evaluate("""(el) => { 
                let prev = el.previousElementSibling;
                while (prev && prev.tagName !== 'LABEL' && !prev.textContent.trim()) {
                    prev = prev.previousElementSibling;
                }
                return prev ? prev.textContent : '';
            }""")
            if text and text.strip():
                return text.strip()
                
        except Exception:
            pass
            
        return ""

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
