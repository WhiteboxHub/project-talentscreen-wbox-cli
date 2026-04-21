#!/usr/bin/env python3
"""Diagnostic: verify the stealth config against real bot-detection pages.

Run this **before** submitting a real application on a flaky ATS to
confirm your browser fingerprint still looks human.  It launches
Chromium with the exact same flags / init script the production engine
uses, loads a set of well-known detection pages, and prints a pass/fail
report for each signal.

Usage:

    python scripts/stealth_check.py                # headed (default)
    python scripts/stealth_check.py --headless     # invisible
    python scripts/stealth_check.py --url URL ...  # add custom page

Exit code is ``0`` when every local check passes, ``1`` otherwise —
easy to wire into CI smoke tests.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from jobcli.core.stealth import (
    LAUNCH_ARGS,
    IGNORE_DEFAULT_ARGS,
    CONTEXT_OPTIONS,
    apply_stealth,
)


# ──────────────────────────────────────────────────────────────────────
# Checks
# ──────────────────────────────────────────────────────────────────────
# Each entry is (name, js-expression, expectation callable).
# The expression is evaluated on an ``about:blank`` page *after* the
# stealth script has been injected, so we isolate the init-script from
# anything a public detection page might do.

LOCAL_CHECKS: list[tuple[str, str, callable]] = [
    (
        "navigator.webdriver is undefined",
        "() => typeof navigator.webdriver",
        lambda v: v == "undefined",
    ),
    (
        "navigator.plugins is populated",
        "() => navigator.plugins.length",
        lambda v: isinstance(v, int) and v >= 3,
    ),
    (
        "navigator.languages looks US-English",
        "() => navigator.languages",
        lambda v: isinstance(v, list) and v[:1] == ["en-US"],
    ),
    (
        "window.chrome exists",
        "() => typeof window.chrome",
        lambda v: v == "object",
    ),
    (
        "window.chrome.runtime has OnInstalledReason",
        "() => !!(window.chrome && window.chrome.runtime && window.chrome.runtime.OnInstalledReason)",
        lambda v: v is True,
    ),
    (
        "navigator.hardwareConcurrency is plausible",
        "() => navigator.hardwareConcurrency",
        lambda v: isinstance(v, int) and v >= 4,
    ),
    (
        "navigator.deviceMemory is plausible",
        "() => navigator.deviceMemory",
        lambda v: isinstance(v, (int, float)) and v >= 4,
    ),
    (
        "WebGL vendor is not SwiftShader",
        """() => {
            const c = document.createElement('canvas').getContext('webgl');
            if (!c) return 'no-webgl';
            return c.getParameter(37445);
        }""",
        lambda v: isinstance(v, str) and "SwiftShader" not in v and "Google" not in v,
    ),
    (
        "Function.prototype.toString on spoofed getter looks native",
        """() => {
            const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
            return d && d.get ? d.get.toString() : '';
        }""",
        lambda v: isinstance(v, str) and "[native code]" in v,
    ),
    (
        "navigator.permissions.query('notifications') returns 'default'",
        """async () => {
            const r = await navigator.permissions.query({name: 'notifications'});
            return r.state;
        }""",
        lambda v: v in ("default", "prompt", "granted"),
    ),
]


# ──────────────────────────────────────────────────────────────────────
# Remote smoke tests (optional, require network)
# ──────────────────────────────────────────────────────────────────────
# Light-weight: we just visit the page, wait a moment, and scrape the
# result table when we can.  These are informational — we do not let
# them fail CI because the pages themselves change.

REMOTE_PAGES: list[tuple[str, str]] = [
    ("sannysoft (generic fingerprint)", "https://bot.sannysoft.com/"),
    ("areyouheadless", "https://arh.antoinevastel.com/bots/areyouheadless"),
]


def run(url_overrides: list[str], headless: bool, skip_remote: bool) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌  Playwright is not installed.  `pip install playwright` first.")
        return 2

    print("═" * 68)
    print(" jobcli stealth-check")
    print("═" * 68)

    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=LAUNCH_ARGS,
            ignore_default_args=IGNORE_DEFAULT_ARGS,
        )
        context = browser.new_context(**CONTEXT_OPTIONS)
        apply_stealth(context)
        page = context.new_page()
        # ``data:`` URL forces a real document commit.  headless
        # Chromium leaves parts of ``navigator`` uninitialised on
        # ``about:blank``, which makes some stealth patches look
        # broken when they are actually fine.
        page.goto("data:text/html,<!DOCTYPE html><html><body></body></html>")

        print("\nLocal fingerprint checks")
        print("─" * 68)
        for name, expr, check in LOCAL_CHECKS:
            try:
                value = page.evaluate(expr)
                ok = bool(check(value))
            except Exception as e:
                value = f"<error: {e}>"
                ok = False
            mark = "PASS" if ok else "FAIL"
            print(f" [{mark}] {name:<55}  →  {_pretty(value)}")
            if not ok:
                failures += 1

        if not skip_remote:
            print("\nRemote detection pages (informational)")
            print("─" * 68)
            for title, url in REMOTE_PAGES + [("custom", u) for u in url_overrides]:
                if not url:
                    continue
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    # Give each page a second to do its client-side work.
                    page.wait_for_timeout(2_500)
                    excerpt = page.evaluate(
                        """() => (document.body ? document.body.innerText : '').slice(0, 400)"""
                    )
                    print(f"\n • {title}  {url}")
                    for line in excerpt.splitlines()[:20]:
                        line = line.strip()
                        if line:
                            print(f"     {line}")
                except Exception as e:
                    print(f"\n • {title}  {url}")
                    print(f"     ⚠  could not load: {e}")

        context.close()
        browser.close()

    print("\n" + "═" * 68)
    if failures == 0:
        print(" ✓ All local checks passed.")
    else:
        print(f" ✗ {failures} local check(s) failed — see output above.")
    print("═" * 68)
    return 0 if failures == 0 else 1


def _pretty(v) -> str:
    try:
        return json.dumps(v, default=str)[:80]
    except Exception:
        return str(v)[:80]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--headless", action="store_true", help="Run invisible")
    ap.add_argument("--skip-remote", action="store_true", help="Skip public pages")
    ap.add_argument("--url", action="append", default=[], help="Extra URLs to probe")
    args = ap.parse_args()
    return run(args.url, args.headless, args.skip_remote)


if __name__ == "__main__":
    sys.exit(main())
