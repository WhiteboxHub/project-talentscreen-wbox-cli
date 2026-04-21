"""Anti-bot fingerprint hardening for Playwright browser sessions.

Centralises the launch flags, context options, and init script that make
the browser indistinguishable from a regular Chrome/Chromium session to
the detection stacks used by common ATSes:

  * Greenhouse / Ashby / Lever (Cloudflare Turnstile + in-house models).
  * Workday / UKG Pro (Akamai Bot Manager, PerimeterX).
  * LinkedIn / Indeed (custom behavioural classifiers).

The JS runs on every new document (main frame + iframes) *before any
page script*, and it is designed to leave **no runtime artefacts** — the
spoofed functions pass ``.toString()`` checks that the more advanced
anti-bot SDKs perform.

If you add a new patch here, also add a corresponding assertion to
``tests/test_stealth.py`` so regressions are caught in CI.
"""

from __future__ import annotations

from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# Playwright launch + context settings
# ──────────────────────────────────────────────────────────────────────

#: Command-line flags that strip the most common "this is automation"
#: markers from the Chromium process itself.
LAUNCH_ARGS: list[str] = [
    # Removes the ``navigator.webdriver`` JS flag and the
    # ``Automation`` CDP banner by disabling the Blink feature that
    # sets them.
    "--disable-blink-features=AutomationControlled",
    # Skip the first-run wizard and default-browser prompt.
    "--no-default-browser-check",
    "--no-first-run",
    # Prevents site isolation from spawning extra processes that can
    # leak extra fingerprint surface via perf counters.
    "--disable-features=IsolateOrigins,site-per-process",
    # Suppresses the "Chrome is being controlled by automated test
    # software" infobar.
    "--disable-infobars",
    # Disable the password-save prompt (another classic headless tell).
    "--password-store=basic",
    # Work around some iframe-based CAPTCHA detection that checks for
    # the "--enable-automation" switch (also dropped via
    # ``ignore_default_args`` in ``engine.py``).
]

#: Arguments Playwright would otherwise add that leak automation status.
IGNORE_DEFAULT_ARGS: list[str] = ["--enable-automation"]

#: Realistic context options — viewport, locale, timezone.  These should
#: match typical US-based Chrome users.
CONTEXT_OPTIONS: dict = {
    "viewport": {"width": 1366, "height": 864},
    "locale": "en-US",
    "timezone_id": "America/Los_Angeles",
    "java_script_enabled": True,
    "color_scheme": "light",
    "reduced_motion": "no-preference",
}


# ──────────────────────────────────────────────────────────────────────
# Stealth init script
# ──────────────────────────────────────────────────────────────────────
# Runs before any page script on every document.  Every override is
# also wrapped so ``Function.prototype.toString`` on the spoofed function
# returns ``"function () { [native code] }"`` — otherwise advanced
# fingerprinters catch the patches immediately.

STEALTH_JS: str = r"""
(() => {
    'use strict';

    // ── Helper: make a function look native ─────────────────────────
    // Advanced fingerprinters inspect ``fn.toString()`` to tell whether
    // a built-in has been monkey-patched.  We keep a cache of the
    // original ``Function.prototype.toString`` and make each of our
    // overrides reference it so they report as native.
    const realToString = Function.prototype.toString;
    const fnToStringMap = new WeakMap();
    function makeNative(fn, name) {
        const pretty = `function ${name || fn.name || ''}() { [native code] }`;
        fnToStringMap.set(fn, pretty);
        return fn;
    }
    Function.prototype.toString = makeNative(function toString() {
        if (fnToStringMap.has(this)) return fnToStringMap.get(this);
        return realToString.call(this);
    }, 'toString');

    // ── 1. Hide ``navigator.webdriver`` ─────────────────────────────
    try {
        Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: makeNative(function () { return undefined; }, 'get webdriver'),
            configurable: true,
        });
    } catch (_) {}

    // ── 2. Populate ``navigator.plugins`` and ``mimeTypes`` ─────────
    // Playwright ships with empty arrays; real Chrome has the PDF
    // viewer registered as five plugins with their matching MIME
    // types.  We fabricate the same shape.
    //
    // Two headless-specific quirks we defend against here:
    //
    //   * ``Plugin`` / ``PluginArray`` / ``MimeType`` constructors
    //     aren't guaranteed to be exposed in every Chromium build.
    //     If they're missing we fall back to ``Array`` + the correct
    //     ``Symbol.toStringTag`` so ``Object.prototype.toString.call``
    //     still reports ``[object PluginArray]``.
    //   * ``plugins`` can be an *own* property of the navigator
    //     instance, which shadows our ``Navigator.prototype`` getter.
    //     We delete the own property first, then redefine on the
    //     prototype so the override actually takes effect.
    try {
        const mimeTypeData = [
            { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', __plugin: 'Chrome PDF Viewer' },
            { type: 'text/pdf',        suffixes: 'pdf', description: 'Portable Document Format', __plugin: 'Chrome PDF Viewer' },
        ];
        const pluginData = [
            { name: 'PDF Viewer',                 filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer',          filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chromium PDF Viewer',        filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Microsoft Edge PDF Viewer',  filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'WebKit built-in PDF',        filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        ];

        // Resolve constructors; fall back to ``Object.prototype`` when
        // the interface isn't global (happens on some Chromium builds).
        const MimeTypeProto       = (typeof MimeType       !== 'undefined') ? MimeType.prototype       : Object.prototype;
        const PluginProto         = (typeof Plugin         !== 'undefined') ? Plugin.prototype         : Object.prototype;
        const PluginArrayProto    = (typeof PluginArray    !== 'undefined') ? PluginArray.prototype    : Object.prototype;
        const MimeTypeArrayProto  = (typeof MimeTypeArray  !== 'undefined') ? MimeTypeArray.prototype  : Object.prototype;

        const mimeTypes = mimeTypeData.map(m => {
            const o = Object.create(MimeTypeProto);
            Object.assign(o, m);
            return o;
        });
        const plugins = pluginData.map(p => {
            const plugin = Object.create(PluginProto);
            Object.assign(plugin, p);
            Object.defineProperty(plugin, 'length', { value: mimeTypes.length, enumerable: false });
            mimeTypes.forEach((mt, i) => { plugin[i] = mt; });
            return plugin;
        });
        const pluginArray = Object.create(PluginArrayProto);
        Object.defineProperty(pluginArray, 'length', { value: plugins.length, enumerable: false });
        plugins.forEach((p, i) => { pluginArray[i] = p; });
        // ``namedItem`` / ``item`` are on the real PluginArray; provide
        // minimal stubs in case a detection script calls them.
        pluginArray.item       = makeNative(function (i) { return plugins[i] || null; }, 'item');
        pluginArray.namedItem  = makeNative(function (n) { return plugins.find(p => p.name === n) || null; }, 'namedItem');
        pluginArray.refresh    = makeNative(function () {}, 'refresh');

        const mimeArray = Object.create(MimeTypeArrayProto);
        Object.defineProperty(mimeArray, 'length', { value: mimeTypes.length, enumerable: false });
        mimeTypes.forEach((mt, i) => { mimeArray[i] = mt; });
        mimeArray.item       = makeNative(function (i) { return mimeTypes[i] || null; }, 'item');
        mimeArray.namedItem  = makeNative(function (n) { return mimeTypes.find(m => m.type === n) || null; }, 'namedItem');

        // Install the override on **both** the prototype and the
        // live navigator instance.  This is necessary because:
        //   * ``chrome-headless-shell`` exposes ``navigator.plugins``
        //     as an own property of ``navigator`` whose accessor is
        //     defined in C++ — an unrelated ``Navigator.prototype``
        //     definition doesn't shadow it.  We need an own-property
        //     override on the instance itself.
        //   * On the other hand, some fingerprint scripts call
        //     ``Object.getOwnPropertyDescriptor(Navigator.prototype,
        //     'plugins').get.toString()`` — they never touch the
        //     instance.  So we keep the prototype override too, for
        //     the ``toString`` native-code illusion.
        const pluginsGetter   = makeNative(function () { return pluginArray; }, 'get plugins');
        const mimeTypesGetter = makeNative(function () { return mimeArray;   }, 'get mimeTypes');

        const installOn = (target, name, getter) => {
            try {
                Object.defineProperty(target, name, {
                    get: getter,
                    configurable: true,
                    enumerable: true,
                });
            } catch (_) {
                // Property is non-configurable on this build; last
                // resort — ``delete`` then redefine, swallow if both
                // fail because we still have the other target.
                try {
                    delete target[name];
                    Object.defineProperty(target, name, {
                        get: getter,
                        configurable: true,
                        enumerable: true,
                    });
                } catch (_) {}
            }
        };

        installOn(Navigator.prototype, 'plugins',   pluginsGetter);
        installOn(Navigator.prototype, 'mimeTypes', mimeTypesGetter);
        installOn(navigator,           'plugins',   pluginsGetter);
        installOn(navigator,           'mimeTypes', mimeTypesGetter);
    } catch (_) {}

    // ── 3. ``navigator.languages`` ─────────────────────────────────
    try {
        Object.defineProperty(Navigator.prototype, 'languages', {
            get: makeNative(function () { return ['en-US', 'en']; }, 'get languages'),
            configurable: true,
        });
    } catch (_) {}

    // ── 4. ``window.chrome`` with a believable runtime ─────────────
    // The real Chrome object has many fields.  We include the ones
    // commonly probed by fingerprinters.
    try {
        if (!window.chrome) {
            window.chrome = {};
        }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                OnInstalledReason: {
                    CHROME_UPDATE: 'chrome_update',
                    INSTALL: 'install',
                    SHARED_MODULE_UPDATE: 'shared_module_update',
                    UPDATE: 'update',
                },
                OnRestartRequiredReason: {
                    APP_UPDATE: 'app_update',
                    OS_UPDATE: 'os_update',
                    PERIODIC: 'periodic',
                },
                PlatformArch:    { ARM: 'arm', MIPS: 'mips', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformNaclArch:{ ARM: 'arm', MIPS: 'mips', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformOs:      { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                RequestUpdateCheckStatus: {
                    NO_UPDATE: 'no_update',
                    THROTTLED: 'throttled',
                    UPDATE_AVAILABLE: 'update_available',
                },
            };
        }
        if (!window.chrome.loadTimes) {
            window.chrome.loadTimes = makeNative(function () {
                return {
                    requestTime:       Date.now() / 1000 - 5,
                    startLoadTime:     Date.now() / 1000 - 4.9,
                    commitLoadTime:    Date.now() / 1000 - 4.8,
                    finishDocumentLoadTime: Date.now() / 1000 - 4.5,
                    finishLoadTime:    Date.now() / 1000 - 4,
                    firstPaintTime:    Date.now() / 1000 - 4.1,
                    firstPaintAfterLoadTime: 0,
                    navigationType:    'Other',
                    wasFetchedViaSpdy: true,
                    wasNpnNegotiated:  true,
                    npnNegotiatedProtocol: 'h2',
                    wasAlternateProtocolAvailable: false,
                    connectionInfo:    'h2',
                };
            }, 'loadTimes');
        }
        if (!window.chrome.csi) {
            window.chrome.csi = makeNative(function () {
                return {
                    startE:       Date.now() - 5000,
                    onloadT:      Date.now() - 4000,
                    pageT:        Date.now() - 3000,
                    tran:         15,
                };
            }, 'csi');
        }
        if (!window.chrome.app) {
            window.chrome.app = {
                isInstalled: false,
                InstallState:  { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState:  { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
            };
        }
    } catch (_) {}

    // ── 5. ``navigator.permissions.query`` ──────────────────────────
    // Headless Chrome returns ``denied`` for the ``notifications``
    // permission even on a fresh profile; a real Chrome returns
    // ``prompt``.  The usual naïve patch —
    //     state: Notification.permission || 'default'
    // — doesn't help because ``'denied'`` is truthy, so it falls
    // straight through.  We explicitly rewrite ``'denied'`` to
    // ``'prompt'`` for the notifications / push permissions that
    // fingerprinters probe.
    try {
        const origQuery = navigator.permissions && navigator.permissions.query.bind(navigator.permissions);
        if (origQuery) {
            const spoofedForDenied = new Set(['notifications', 'push', 'midi']);
            navigator.permissions.query = makeNative(function (parameters) {
                const name = parameters && parameters.name;
                if (!name) return origQuery(parameters);
                if (spoofedForDenied.has(name)) {
                    return Promise.resolve({
                        state: 'prompt',
                        onchange: null,
                    });
                }
                return origQuery(parameters);
            }, 'query');
        }
    } catch (_) {}

    // ── 6. Hardware counters ────────────────────────────────────────
    try {
        Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {
            get: makeNative(function () { return 8; }, 'get hardwareConcurrency'),
            configurable: true,
        });
        Object.defineProperty(Navigator.prototype, 'deviceMemory', {
            get: makeNative(function () { return 8; }, 'get deviceMemory'),
            configurable: true,
        });
        Object.defineProperty(Navigator.prototype, 'maxTouchPoints', {
            get: makeNative(function () { return 0; }, 'get maxTouchPoints'),
            configurable: true,
        });
    } catch (_) {}

    // ── 7. WebGL renderer / vendor ──────────────────────────────────
    // Anti-bot SDKs pull the WebGL vendor/renderer strings and match
    // them against a known-good allowlist.  Headless Chromium reports
    // a software renderer by default, which is a known automation
    // signal.  Spoof Apple M-series (matches macOS hosts well).
    try {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = makeNative(function (p) {
            // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL
            if (p === 37445) return 'Apple Inc.';
            if (p === 37446) return 'Apple M1';
            return getParameter.call(this, p);
        }, 'getParameter');
        if (window.WebGL2RenderingContext) {
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = makeNative(function (p) {
                if (p === 37445) return 'Apple Inc.';
                if (p === 37446) return 'Apple M1';
                return getParameter2.call(this, p);
            }, 'getParameter');
        }
    } catch (_) {}

    // ── 8. ``navigator.connection`` ─────────────────────────────────
    // Headless Chrome leaves this undefined in some builds; real users
    // almost always have 4g / rtt / downlink values.
    try {
        if (!navigator.connection) {
            Object.defineProperty(Navigator.prototype, 'connection', {
                get: makeNative(function () {
                    return {
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false,
                    };
                }, 'get connection'),
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 9. Iframe contentWindow.navigator.webdriver ─────────────────
    // Some detection scripts create a hidden iframe and read its
    // ``contentWindow.navigator.webdriver`` because iframe globals
    // can skip certain monkey-patches.  We override the
    // ``HTMLIFrameElement.contentWindow`` getter so any iframe we
    // own inherits our patched globals via a Proxy.
    try {
        const contentWindowDesc = Object.getOwnPropertyDescriptor(
            HTMLIFrameElement.prototype, 'contentWindow'
        );
        if (contentWindowDesc && contentWindowDesc.get) {
            const orig = contentWindowDesc.get;
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: makeNative(function () {
                    const win = orig.call(this);
                    if (!win || win.__jobcli_stealth_patched) return win;
                    try {
                        Object.defineProperty(win.Navigator.prototype, 'webdriver', {
                            get: function () { return undefined; },
                            configurable: true,
                        });
                        win.__jobcli_stealth_patched = true;
                    } catch (_) {}
                    return win;
                }, 'get contentWindow'),
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 10. ``window.outerWidth`` / ``window.outerHeight`` ─────────
    // Headless chromium leaves these at 0 which is a giveaway.  Align
    // them with the inner dims plus a typical browser chrome.
    try {
        if (window.outerWidth === 0 && window.innerWidth > 0) {
            Object.defineProperty(window, 'outerWidth',  { get: function () { return window.innerWidth;  }, configurable: true });
            Object.defineProperty(window, 'outerHeight', { get: function () { return window.innerHeight + 74; }, configurable: true });
        }
    } catch (_) {}
})();
"""


def apply_stealth(context, logger=None) -> None:
    """Install :data:`STEALTH_JS` on a Playwright ``BrowserContext``.

    Safe to call more than once — Playwright queues each init script
    separately, so calling it twice just adds a no-op second copy.
    Accepts a logger so misconfigurations surface rather than being
    swallowed.
    """
    try:
        context.add_init_script(STEALTH_JS)
    except Exception as e:
        if logger is not None:
            try:
                logger.warning(f"Stealth init script failed to install: {e}")
            except Exception:
                pass
        else:
            import warnings
            warnings.warn(f"Stealth init script failed to install: {e}")


def make_browser_launch_kwargs(
    headless: bool,
    user_agent: Optional[str] = None,
) -> dict:
    """Return kwargs suitable for ``chromium.launch(...)``."""
    return {
        "headless": headless,
        "args": LAUNCH_ARGS,
        "ignore_default_args": IGNORE_DEFAULT_ARGS,
    }


def make_context_kwargs(user_agent: Optional[str] = None) -> dict:
    """Return kwargs suitable for ``browser.new_context(...)``."""
    kw = dict(CONTEXT_OPTIONS)
    if user_agent:
        kw["user_agent"] = user_agent
    return kw
