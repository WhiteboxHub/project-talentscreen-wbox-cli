"""Shared helpers to avoid overwriting fields already filled (extension, rules, or prior pass)."""

from __future__ import annotations

from typing import FrozenSet, Optional

from playwright.sync_api import Locator

# Keep in sync with ApplicationEngine._SNAPSHOT_PLACEHOLDERS and tool_executor._PLACEHOLDER_VALUES.
PLACEHOLDER_VALUES: FrozenSet[str] = frozenset({
    "select",
    "choose",
    "please choose",
    "select...",
    "select an option",
    "-- select --",
    "none",
    "n/a",
    "na",
    "",
})


def is_meaningful_value(value: Optional[str]) -> bool:
    """True when *value* is non-empty and not a dropdown placeholder."""
    if value is None:
        return False
    v = str(value).strip()
    if not v:
        return False
    return v.lower() not in PLACEHOLDER_VALUES


def read_locator_value(locator: Locator, *, timeout_ms: int = 500) -> Optional[str]:
    """Best-effort read of an input/textarea/select/combobox value."""
    try:
        if locator.count() == 0:
            return None
        loc = locator.first
        try:
            val = loc.input_value(timeout=timeout_ms)
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            pass
        try:
            val = loc.evaluate(
                """el => {
                    if (!el) return '';
                    if (el.tagName === 'SELECT' && el.selectedIndex >= 0) {
                        return (el.options[el.selectedIndex].text || '').trim();
                    }
                    if (el.value !== undefined && el.value !== null) {
                        return String(el.value).trim();
                    }
                    if (el.isContentEditable) {
                        return (el.innerText || el.textContent || '').trim();
                    }
                    const combo = el.closest('[role="combobox"]');
                    if (combo) {
                        return (combo.innerText || combo.textContent || '').trim();
                    }
                    return '';
                }"""
            )
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            return None
    except Exception:
        return None
    return None


def should_skip_refill(
    locator: Locator,
    proposed_value: Optional[str] = None,
) -> bool:
    """Return True if the field already has a real value and should not be overwritten."""
    existing = read_locator_value(locator)
    if not is_meaningful_value(existing):
        return False
    if proposed_value is None:
        return True
    target = str(proposed_value).strip()
    if not target:
        return False
    ex_lower = existing.lower()
    tv_lower = target.lower()
    if ex_lower == tv_lower:
        return True
    # Long values: substring match (e.g. full URL already present).
    if len(ex_lower) > 12 and (tv_lower in ex_lower or ex_lower in tv_lower):
        return True
    return True  # Any other non-placeholder existing value — do not clear and retype.
