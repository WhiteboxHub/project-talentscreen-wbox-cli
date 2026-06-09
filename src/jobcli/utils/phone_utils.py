"""Phone number utilities: normalization and country-code dropdown filling.

Two public helpers:

* ``normalize_phone_number(raw)``        — strips formatting, strips +1, returns
  bare 10-digit US number (or cleaned international number).
* ``fill_phone_with_country_code(page, phone, logger)`` — detects the pattern
  of a country-code dropdown adjacent to a phone input and fills both, with
  ``+1`` (United States) selected in the dropdown and the bare number typed
  into the input.

Root-cause note: leading-zero bug
----------------------------------
Many ATS phone inputs use ``intl-tel-input`` or a similar masking library.
These libraries render the country flag/dial-code as a visual overlay or a
separate ``<select>`` element, while the ``<input type="tel">`` itself only
expects the *national* part (e.g. 10 digits for US, no ``+1``).

When code passes the full ``+14155550192`` string through ``keyboard.type()``:
  1. The ``+`` and ``1`` get typed into the input.
  2. The masking library interprets the leading ``1`` as the US country prefix
     already handled by the overlay, converts the number to international
     format, and inserts a ``0`` before the national digits → ``014155...``.

Fix: ALWAYS fill phone inputs with the bare national digits only
(``4155550192``, never ``+14155550192`` or ``14155550192``).  The country-
code dropdown/overlay handles the ``+1`` part separately.
"""

from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import Page


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_LEADING_COUNTRY = re.compile(r"^\+?1(\d{10})$")   # +1XXXXXXXXXX or 1XXXXXXXXXX
_DIGITS_ONLY = re.compile(r"[^\d+]")


def normalize_phone_number(raw: Optional[str]) -> str:
    """Return the E.164 form of *raw* with the +1 prefix guaranteed.

    Examples
    --------
    >>> normalize_phone_number("(415) 555-0192")
    '+14155550192'
    >>> normalize_phone_number("+14155550192")
    '+14155550192'
    >>> normalize_phone_number("14155550192")
    '+14155550192'
    >>> normalize_phone_number("4155550192")
    '+14155550192'
    >>> normalize_phone_number("04155550192")
    '+14155550192'
    """
    if not raw:
        return ""
    # Keep + and digits only
    cleaned = re.sub(r"[^\d+]", "", raw.strip())
    if not cleaned:
        return raw.strip()

    # Already international with +1?
    if cleaned.startswith("+1") and len(cleaned) == 12:
        return cleaned                   # already perfect
    # 1 + 10 digits (no +)?
    if cleaned.startswith("1") and len(cleaned) == 11:
        return "+" + cleaned
    # Bare 10-digit US number?
    if len(cleaned) == 10 and not cleaned.startswith("+"):
        return "+1" + cleaned
    # 11 digits starting with 0 — accidental leading zero on a US number
    # (e.g. "04155550192" stored in some resume JSONs)
    if len(cleaned) == 11 and cleaned.startswith("0") and not cleaned.startswith("+"):
        return "+1" + cleaned[1:]        # strip the 0, prepend +1
    # Something else (international, malformed) — return as-is with + prefix
    return cleaned if cleaned.startswith("+") else "+" + cleaned


def strip_country_code(raw: Optional[str]) -> str:
    """Return just the national number, stripping the country code prefix.

    For US/Canada: returns bare 10 digits (e.g. ``4155550192``).
    For other countries: strips the international prefix and returns remaining.

    This is the value that should be typed into the phone input field
    on forms that have a separate country-code dropdown/overlay.
    """
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d+]", "", raw.strip())

    # US/Canada: +1XXXXXXXXXX or 1XXXXXXXXXX (exactly 12 or 11 chars)
    m = _LEADING_COUNTRY.match(cleaned)
    if m:
        return m.group(1)           # bare 10 digits, guaranteed no leading zero

    # International with + prefix: for US/Canada we already handled it above.
    # For other international numbers, we don't have a country-code database,
    # so return everything after the leading '+' unchanged — callers should
    # only depend on US stripping being perfect.
    if cleaned.startswith("+"):
        return cleaned[1:]      # strip just the '+', keep full number with country code

    # No + prefix, not a recognised US number — return as-is
    return cleaned



def bare_national_number(phone: Optional[str]) -> str:
    """Return the national number suitable for direct input into a phone field.

    This is the single source of truth for what value to type.  Always use
    this instead of ``personal.phone`` directly to avoid the leading-0 bug.

    Examples
    --------
    >>> bare_national_number("+1 (415) 555-0192")
    '4155550192'
    >>> bare_national_number("415-555-0192")
    '4155550192'
    >>> bare_national_number("14155550192")
    '4155550192'
    >>> bare_national_number("+44 20 7946 0958")
    '2079460958'
    """
    if not phone:
        return ""
    e164 = normalize_phone_number(phone)
    return strip_country_code(e164) or re.sub(r"[^\d]", "", phone)


# ---------------------------------------------------------------------------
# DOM helpers — country-code dropdown detection and filling
# ---------------------------------------------------------------------------

# Labels / aria-labels / ids that indicate a phone-country-code dropdown
_CODE_DROPDOWN_PATTERNS = re.compile(
    r"country\s*code|dial\s*code|phone\s*code|phone\s*country|"
    r"country_code|intl.*code|code.*phone|flag.*select|phone.*flag|"
    r"phone.*prefix|prefix.*phone|iti__|intl.tel",
    re.IGNORECASE,
)

# Option text / value patterns that represent +1 / United States
_PLUS_ONE_PATTERNS = re.compile(
    r"\(\+1\)|\+1\b|united\s*states?\s*\(\+1\)|canada\s*\(\+1\)|US\s*\(\+1\)|"
    r"\bUS\b.*\+1|\+1.*US|^1$",
    re.IGNORECASE,
)

# Phone input patterns
_PHONE_INPUT_PATTERNS = re.compile(
    r"phone|mobile|tel|cell|contact.?number|phone.?number|mobile.?number",
    re.IGNORECASE,
)


def _clear_and_fill(page: Page, loc, value: str) -> None:
    """Reliably clear a phone input and type *value*.

    Uses three clearing strategies in order so stale JS-set values don't
    linger as a leading '0':
      1. Triple-click to select-all, then type replacement (most reliable).
      2. Ctrl/Cmd+A → Delete → type.
      3. loc.fill() as last resort (may not fire React synthetic events).
    """
    import sys as _sys
    try:
        loc.click(timeout=1500)
        page.wait_for_timeout(100)
    except Exception:
        pass

    # Strategy 1: triple-click selects all existing text, then type replaces it
    try:
        loc.click(click_count=3, timeout=1500)
        page.wait_for_timeout(80)
        page.keyboard.type(value, delay=40)
        page.wait_for_timeout(150)
        # Verify it worked
        try:
            current = (loc.input_value() or "").strip()
            # Accept if the field ends with our value (masking may add prefix)
            if value and (current == value or current.endswith(value)):
                return
        except Exception:
            return
    except Exception:
        pass

    # Strategy 2: Ctrl/Cmd+A → Delete → type
    mod = "Meta" if _sys.platform == "darwin" else "Control"
    try:
        page.keyboard.press(f"{mod}+A")
        page.wait_for_timeout(60)
        page.keyboard.press("Delete")
        page.wait_for_timeout(60)
        page.keyboard.type(value, delay=40)
        page.wait_for_timeout(150)
        return
    except Exception:
        pass

    # Strategy 3: Playwright fill() — fires input/change events but may not
    # clear React controlled-input values on some ATS frameworks
    try:
        loc.fill(value)
    except Exception:
        pass


def fill_phone_with_country_code(
    page: Page,
    phone: str,
    logger=None,
) -> bool:
    """Fill the phone country-code dropdown (+1) and the phone number input.

    Handles the very common pattern on Greenhouse, Lever, Ashby, Workday etc.:

        [🇺🇸 ▾ +1]  [ _______________ ]    ← two adjacent widgets
         (select)       (text input)

    The *bare national number* (e.g. ``4155550192``) is always what gets typed
    into the text input — never ``+14155550192`` — because the country-code
    overlay/dropdown already handles the ``+1`` prefix, and typing it again
    causes masking libraries to insert a spurious leading ``0``.

    Returns ``True`` if at least the phone number input was successfully filled.
    """
    if not phone:
        return False

    # The value to type into the phone text input — always bare national digits
    bare = bare_national_number(phone)
    if not bare:
        bare = re.sub(r"[^\d]", "", phone)

    filled_phone = False
    filled_code = False

    # ── 1. Detect & select +1 in any country-code dropdown ────────────────
    try:
        dropdowns: list[dict] = page.evaluate(r"""() => {
            const out = [];
            const candidates = [...document.querySelectorAll(
                'select, [role="combobox"], [role="listbox"], .iti__flag-container, .intl-tel-input'
            )];
            for (const el of candidates) {
                const id   = (el.id   || '').toLowerCase();
                const name = (el.name || '').toLowerCase();
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const ph   = (el.getAttribute('placeholder') || '').toLowerCase();
                const cls  = (el.className || '').toLowerCase();
                // Try to find associated label text
                let labelText = '';
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) labelText = lbl.innerText.toLowerCase();
                }
                if (!labelText && el.parentElement) {
                    const lbl = el.parentElement.querySelector('label');
                    if (lbl) labelText = lbl.innerText.toLowerCase();
                }
                let selector = '';
                if (el.id) selector = '#' + el.id;
                else if (el.name) selector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                else if (el.className) {
                    // Use first meaningful class for iti__ widgets
                    const cls2 = el.className.split(' ').find(c => c.length > 3);
                    if (cls2) selector = el.tagName.toLowerCase() + '.' + cls2;
                }
                const rect = el.getBoundingClientRect();
                if (!selector || rect.width === 0) continue;
                out.push({ selector, id, name, aria_label: aria,
                           placeholder: ph, label_text: labelText, class: cls });
            }
            return out;
        }""") or []
    except Exception:
        dropdowns = []

    for dd in dropdowns:
        combined = " ".join([
            dd.get("aria_label", ""),
            dd.get("name", ""),
            dd.get("id", ""),
            dd.get("placeholder", ""),
            dd.get("label_text", ""),
            dd.get("class", ""),
        ])
        if not _CODE_DROPDOWN_PATTERNS.search(combined):
            continue

        sel = dd.get("selector", "")
        if not sel:
            continue
        try:
            loc = page.locator(sel).first
            if not loc.is_visible(timeout=1000):
                continue

            tag = loc.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                # Native <select> — fuzzy option match for +1 / United States
                options: list[dict] = loc.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                chosen = None
                # Pass 1: explicit +1 patterns
                for opt in options:
                    if _PLUS_ONE_PATTERNS.search(opt["text"]) or opt["value"] in ("+1", "1", "US"):
                        chosen = opt["value"]
                        break
                # Pass 2: United States by name
                if chosen is None:
                    for opt in options:
                        t = opt["text"].upper()
                        if "UNITED STATES" in t or ("US" == t.strip()) or "USA" == t.strip():
                            chosen = opt["value"]
                            break
                if chosen is not None:
                    page.select_option(sel, value=chosen, timeout=3000)
                    # Wait for any JS to finish reacting (e.g. auto-populating 0)
                    page.wait_for_timeout(300)
                    filled_code = True
                    if logger:
                        logger.info(f"Selected +1 country code in <select> '{sel}'")
            else:
                # ARIA combobox / intl-tel-input button — click and search
                loc.click(timeout=2000)
                page.wait_for_timeout(300)
                page.keyboard.type("+1", delay=50)
                page.wait_for_timeout(400)
                opts = page.locator("[role='option']")
                count = min(opts.count(), 20)
                picked = False
                for i in range(count):
                    try:
                        txt = (opts.nth(i).text_content() or "").strip()
                        if _PLUS_ONE_PATTERNS.search(txt) or "United States" in txt:
                            opts.nth(i).click(timeout=2000)
                            page.wait_for_timeout(300)
                            filled_code = True
                            picked = True
                            break
                    except Exception:
                        continue
                if not picked:
                    page.keyboard.press("Escape")
        except Exception:
            continue

    # ── 2. Fill the phone number input with bare national digits ──────────
    # After selecting the dropdown (step 1), some ATS JS auto-populates a
    # "0" into the phone field.  _clear_and_fill() always clears first.
    try:
        phone_inputs: list[dict] = page.evaluate(r"""() => {
            const inputs = [...document.querySelectorAll(
                'input[type="tel"], input[type="text"], input[type="number"]'
            )];
            const out = [];
            for (const el of inputs) {
                if (el.disabled || el.readOnly) continue;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const id   = (el.id   || '').toLowerCase();
                const name = (el.name || '').toLowerCase();
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const ph   = (el.getAttribute('placeholder') || '').toLowerCase();
                let labelText = '';
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) labelText = lbl.innerText.toLowerCase();
                }
                let selector = '';
                if (el.id) selector = '#' + el.id;
                else if (el.name) selector = 'input[name="' + el.name + '"]';
                if (!selector) continue;
                out.push({
                    selector, id, name, aria_label: aria,
                    placeholder: ph, label_text: labelText,
                    type: el.type,
                    current_value: (el.value || '').trim()
                });
            }
            return out;
        }""") or []
    except Exception:
        phone_inputs = []

    for inp in phone_inputs:
        combined = " ".join([
            inp.get("aria_label", ""),
            inp.get("name", ""),
            inp.get("id", ""),
            inp.get("placeholder", ""),
            inp.get("label_text", ""),
            inp.get("type", ""),
        ])
        is_phone_input = (
            _PHONE_INPUT_PATTERNS.search(combined)
            or inp.get("type") == "tel"
        )
        if not is_phone_input:
            continue

        sel = inp.get("selector", "")
        if not sel:
            continue
        try:
            loc = page.locator(sel).first
            if not loc.is_visible(timeout=1000):
                continue

            # Already has a real phone number? Skip.
            existing = inp.get("current_value", "") or ""
            existing_digits = re.sub(r"[^\d]", "", existing)
            if existing_digits and len(existing_digits) >= 7:
                # Could already be correctly filled — accept
                filled_phone = True
                break

            # Always fill with bare national digits — never with +1 prefix.
            # Use _clear_and_fill to handle any JS-auto-populated "0".
            _clear_and_fill(page, loc, bare)
            filled_phone = True
            if logger:
                logger.info(
                    f"Filled phone input '{sel}' with bare number '{bare}' "
                    f"(original: '{phone}')"
                )
            break
        except Exception:
            continue

    return filled_phone or filled_code
