"""Verify the anti-bot stealth patches actually land on the page.

Two test strata:

* **Static tests** - cheap: they just lint the ``STEALTH_JS`` string and
  assert every patch we promised in the docs is present.  These always
  run.
* **Runtime tests** - spin up a real headless Chromium via Playwright,
  inject the stealth script, and assert that ``navigator.webdriver``
  and friends are spoofed in the document.  These are skipped when
  Playwright (or its browser binaries) aren't installed, so the suite
  remains green on minimal CI images.

Keep these tests in sync with the patches in ``jobcli/core/stealth.py``.
A failure here means an ATS spam classifier will almost certainly flag
us in production.
"""

from __future__ import annotations

import pytest

from jobcli.core.stealth import (
    CONTEXT_OPTIONS,
    IGNORE_DEFAULT_ARGS,
    LAUNCH_ARGS,
    STEALTH_JS,
    apply_stealth,
)


# ──────────────────────────────────────────────────────────────────────
# Static tests — run on every CI pass
# ──────────────────────────────────────────────────────────────────────

class TestStealthScriptShape:
    """Lightweight assertions on the stealth JS source.

    They don't require a browser and catch accidental deletions of
    critical patches during refactors.
    """

    def test_hides_webdriver(self) -> None:
        assert "webdriver" in STEALTH_JS
        assert "undefined" in STEALTH_JS

    def test_populates_plugins(self) -> None:
        assert "PluginArray" in STEALTH_JS
        assert "PDF Viewer" in STEALTH_JS

    def test_spoofs_languages(self) -> None:
        assert "'en-US'" in STEALTH_JS

    def test_stubs_chrome_runtime(self) -> None:
        assert "OnInstalledReason" in STEALTH_JS
        assert "loadTimes" in STEALTH_JS

    def test_patches_permissions_query(self) -> None:
        assert "permissions" in STEALTH_JS
        assert "notifications" in STEALTH_JS

    def test_sets_hardware_counters(self) -> None:
        assert "hardwareConcurrency" in STEALTH_JS
        assert "deviceMemory" in STEALTH_JS

    def test_spoofs_webgl_vendor(self) -> None:
        assert "37445" in STEALTH_JS  # UNMASKED_VENDOR_WEBGL
        assert "37446" in STEALTH_JS  # UNMASKED_RENDERER_WEBGL
        assert "SwiftShader" not in STEALTH_JS  # we must NOT re-expose it

    def test_patches_iframe_contentwindow(self) -> None:
        assert "HTMLIFrameElement" in STEALTH_JS
        assert "contentWindow" in STEALTH_JS

    def test_function_tostring_is_native(self) -> None:
        assert "[native code]" in STEALTH_JS


class TestLaunchConfig:
    """The launch / context options that travel alongside the JS."""

    def test_launch_args_strip_automation_signals(self) -> None:
        assert "--disable-blink-features=AutomationControlled" in LAUNCH_ARGS
        assert "--no-default-browser-check" in LAUNCH_ARGS

    def test_ignore_enable_automation(self) -> None:
        assert "--enable-automation" in IGNORE_DEFAULT_ARGS

    def test_context_has_realistic_viewport(self) -> None:
        vp = CONTEXT_OPTIONS["viewport"]
        assert vp["width"] >= 1200 and vp["height"] >= 700

    def test_context_is_us_english(self) -> None:
        assert CONTEXT_OPTIONS["locale"] == "en-US"


# ──────────────────────────────────────────────────────────────────────
# Runtime tests — spin up a real browser
# ──────────────────────────────────────────────────────────────────────

_playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright not installed — skipping runtime stealth checks",
)


def _launch_with_stealth():
    """Helper: launch headless Chromium with the production config.

    Returns ``(playwright, browser, context, page)``.  Caller is
    responsible for closing everything via the returned ``cleanup``.
    """
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    try:
        browser = p.chromium.launch(
            headless=True,
            args=LAUNCH_ARGS,
            ignore_default_args=IGNORE_DEFAULT_ARGS,
        )
    except Exception as exc:  # pragma: no cover — defensive
        p.stop()
        pytest.skip(f"Chromium binary unavailable: {exc}")

    context = browser.new_context(**CONTEXT_OPTIONS)
    apply_stealth(context)
    page = context.new_page()
    # Navigate to a real HTML document instead of ``about:blank`` —
    # headless Chromium lazy-initialises parts of ``navigator`` (plugins
    # in particular) only on the first proper document load, so
    # ``about:blank`` can return empty plugin lists even after our
    # init script ran.  A minimal ``data:`` URL forces a real commit.
    page.goto("data:text/html,<!DOCTYPE html><html><body></body></html>")

    def cleanup() -> None:
        try:
            context.close()
            browser.close()
        finally:
            p.stop()

    return page, cleanup


@pytest.fixture(scope="module")
def stealth_page():
    """Shared stealth page for all runtime assertions."""
    page, cleanup = _launch_with_stealth()
    yield page
    cleanup()


class TestRuntimeStealth:
    """Assert the init-script applied correctly inside a real document."""

    def test_webdriver_is_undefined(self, stealth_page) -> None:
        typ = stealth_page.evaluate("() => typeof navigator.webdriver")
        assert typ == "undefined", "navigator.webdriver leaked automation"

    def test_plugins_are_populated(self, stealth_page) -> None:
        length = stealth_page.evaluate("() => navigator.plugins.length")
        assert length >= 3, "plugins list is too short — looks headless"

    def test_languages_are_us_english(self, stealth_page) -> None:
        langs = stealth_page.evaluate("() => navigator.languages")
        assert isinstance(langs, list)
        assert langs[:1] == ["en-US"]

    def test_chrome_object_exists(self, stealth_page) -> None:
        has_chrome = stealth_page.evaluate("() => !!window.chrome")
        assert has_chrome

    def test_chrome_runtime_has_oninstalled(self, stealth_page) -> None:
        ok = stealth_page.evaluate(
            "() => !!(window.chrome && window.chrome.runtime && window.chrome.runtime.OnInstalledReason)"
        )
        assert ok is True

    def test_hardware_counters_plausible(self, stealth_page) -> None:
        hc = stealth_page.evaluate("() => navigator.hardwareConcurrency")
        dm = stealth_page.evaluate("() => navigator.deviceMemory")
        assert hc and hc >= 4, f"hardwareConcurrency={hc} looks headless"
        assert dm and dm >= 4, f"deviceMemory={dm} looks headless"

    def test_webgl_vendor_is_not_swiftshader(self, stealth_page) -> None:
        vendor = stealth_page.evaluate(
            """() => {
                const c = document.createElement('canvas').getContext('webgl');
                return c ? c.getParameter(37445) : null;
            }"""
        )
        if vendor is None:
            pytest.skip("WebGL unavailable in this build")
        assert "SwiftShader" not in vendor
        assert vendor != "Google Inc."

    def test_spoofed_function_looks_native(self, stealth_page) -> None:
        repr_ = stealth_page.evaluate(
            """() => {
                const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
                return d && d.get ? d.get.toString() : '';
            }"""
        )
        assert "[native code]" in repr_, (
            "Spoofed getter exposed its source — fingerprinters will catch this"
        )

    def test_permissions_query_returns_default(self, stealth_page) -> None:
        state = stealth_page.evaluate(
            """async () => (await navigator.permissions.query({name: 'notifications'})).state"""
        )
        # Real Chrome returns 'default' (or 'prompt'/'granted').  Head-
        # less Chrome returns 'denied'.  Anything not in the whitelist
        # means our permissions patch is broken.
        assert state in ("default", "prompt", "granted"), state
