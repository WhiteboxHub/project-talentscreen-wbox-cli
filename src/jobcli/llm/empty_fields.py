"""Build structured gap lists for the Form-Filling Auditor LLM prompt."""

from __future__ import annotations

import re
from typing import Any, Optional

from jobcli.llm.ax_tree_extractor import AccessibilityTree
from jobcli.utils.fill_guard import PLACEHOLDER_VALUES, is_meaningful_value

_EMPTY_DROPDOWN_TOKENS = frozenset(
    s.lower()
    for s in (
        *PLACEHOLDER_VALUES,
        "select...",
        "select an option",
        "select one",
        "select a value",
        "select option",
        "pick one",
        "pick an option",
        "choose...",
        "please choose",
        "please select",
        "choose one",
        "-- select --",
        "- select -",
        "---",
        "none",
        "n/a",
        "—",
        "--",
    )
)


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip().lower())


def _field_is_empty(field: dict[str, Any]) -> bool:
    """True when an AX form_fields entry has no meaningful user value."""
    role = (field.get("role") or "").lower()
    val = str(field.get("value", "") or "").strip()
    checked = field.get("checked")
    placeholder = str(field.get("placeholder", "") or "").strip().lower()
    autocomplete = str(field.get("autocomplete", "") or "").strip().lower()

    # Checkboxes, radios, switches
    if role in ("checkbox", "radio", "switch", "menuitemradio"):
        if checked is True:
            return False
        if isinstance(checked, str) and checked.lower() in ("true", "on", "yes", "1"):
            return False
        # Also check if value is "on" or similar (some browsers report checked as value)
        if val.lower() in ("on", "yes", "true", "1"):
            return False
        return True

    # Comboboxes and listboxes (custom dropdowns)
    if role in ("combobox", "listbox", "menu"):
        if not val:
            return True
        # Check if it's just a placeholder or default text
        if val.lower() in _EMPTY_DROPDOWN_TOKENS:
            return True
        # Check if placeholder attribute suggests it's empty
        if placeholder and placeholder in _EMPTY_DROPDOWN_TOKENS:
            return True
        return not is_meaningful_value(val)

    # Text inputs, textareas, searchboxes
    if role in ("textbox", "searchbox", "spinbutton", "textarea"):
        if not val:
            return True
        # Check placeholder attribute
        if placeholder and placeholder in _EMPTY_DROPDOWN_TOKENS:
            return True
        # Check if value is just whitespace or placeholder-like
        return not is_meaningful_value(val)

    # Buttons that act as dropdowns (common in React/Angular)
    if role == "button":
        # Buttons are typically not "filled" but we check if they have a meaningful label
        # If the button is a dropdown trigger, it might have a placeholder-like text
        if not val:
            return True
        if val.lower() in _EMPTY_DROPDOWN_TOKENS:
            return True
        return not is_meaningful_value(val)

    # Default case: any other role
    if not val:
        return True
    if val.lower() in _EMPTY_DROPDOWN_TOKENS:
        return True
    return not is_meaningful_value(val)


def _strip_required_marker(label: str) -> str:
    return re.sub(r"\s*\*+\s*$", "", (label or "").strip())


def _options_for_label(
    label: str,
    dropdown_options: Optional[list[dict[str, Any]]],
) -> list[str]:
    if not dropdown_options:
        return []
    norm = _normalize_label(_strip_required_marker(label))
    for dp in dropdown_options:
        dp_label = (dp.get("label") or "").strip()
        if not dp_label:
            continue
        dp_norm = _normalize_label(_strip_required_marker(dp_label))
        if dp_norm == norm or norm in dp_norm or dp_norm in norm:
            opts = dp.get("options") or []
            return [str(o) for o in opts if o is not None]
    return []


def build_empty_fields_payload(
    ax_tree: AccessibilityTree,
    *,
    dropdown_options: Optional[list[dict[str, Any]]] = None,
    extra_gap_labels: Optional[list[str]] = None,
    include_optional: bool = True,
) -> list[dict[str, Any]]:
    """Return gap rows for ``<EMPTY_FIELDS>`` in the auditor user prompt.

    Each row:
      label, role, required, options, current_value

  By default only **required** empty fields are included. Set
  ``include_optional=True`` to also list optional empties (the auditor prompt
  tells the model to fill optional only on confident matches).
    """
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()

    for field in getattr(ax_tree, "form_fields", None) or []:
        label = (field.get("name") or field.get("label") or "").strip()
        if not label:
            continue
        norm = _normalize_label(label)
        if norm in seen:
            continue

        is_required = (
            bool(field.get("required"))
            or bool(field.get("aria-required"))
            or "*" in label
            or label.strip().endswith("*")
            or label.strip().startswith("*")
        )
        if not is_required and not include_optional:
            continue
        if not _field_is_empty(field):
            continue

        seen.add(norm)
        role = (field.get("role") or "textbox").lower()
        opts = _options_for_label(label, dropdown_options)
        gaps.append(
            {
                "label": label,
                "role": role,
                "required": is_required,
                "options": opts,
                "current_value": str(field.get("value", "") or "").strip(),
            }
        )

    # DOM-side required combobox placeholders (Greenhouse react-select, etc.)
    for raw_label in extra_gap_labels or []:
        label = (raw_label or "").strip()
        if not label:
            continue
        norm = _normalize_label(label)
        if norm in seen:
            continue
        seen.add(norm)
        opts = _options_for_label(label, dropdown_options)
        gaps.append(
            {
                "label": label,
                "role": "combobox",
                "required": True,
                "options": opts,
                "current_value": "",
            }
        )

    # Sort: required fields first, then optional; alphabetically within each group
    gaps.sort(key=lambda g: (0 if g["required"] else 1, g["label"].lower()))
    return gaps


def is_auditor_fill_task(task: str) -> bool:
    """Tasks that use the Form-Filling Auditor system prompt."""
    return task in (
        "fill_form_fields_only",
        "fill_empty_fields_only",
    )
