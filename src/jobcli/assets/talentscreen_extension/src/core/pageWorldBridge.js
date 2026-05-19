/**
 * TalentScreen — page (MAIN) world bridge for Playwright / JobCLI.
 * Proxies window.AutofillExtension to the isolated content-script AutofillAPI via DOM events.
 */
(function () {
    'use strict';

    const BRIDGE_VERSION = '2.0.0-bridge';
    const BRIDGE_TIMEOUT_MS = 30000;
    const CALL_EVENT = '__autofillExtensionCall';
    const RESPONSE_EVENT = '__autofillExtensionResponse';

    const BRIDGED_METHODS = [
        'getPageContext',
        'getFields',
        'dryRun',
        'fill',
        'fillEnhanced',
        'getResult',
        'clearSession',
        'setCustomMappings',
        'getCustomMappings',
        'configure',
        'getConfiguration',
        'injectProfile',
        'getProfile',
        'detectMultiStep',
        'exportReport',
        'retryFailed',
    ];

    function newRequestId() {
        if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
            return crypto.randomUUID();
        }
        return 'bridge-' + Date.now() + '-' + Math.random().toString(36).slice(2);
    }

    /**
     * Dispatch RPC to isolated AutofillAPI and return a Promise with the result.
     * @param {string} method
     * @param {unknown[]} args
     * @returns {Promise<unknown>}
     */
    function callBridge(method, args) {
        return new Promise((resolve, reject) => {
            const id = newRequestId();
            let settled = false;

            const timeoutId = setTimeout(() => {
                if (settled) return;
                settled = true;
                document.removeEventListener(RESPONSE_EVENT, onResponse);
                reject(new Error('AutofillExtension bridge timeout: ' + method));
            }, BRIDGE_TIMEOUT_MS);

            function onResponse(event) {
                const detail = event.detail;
                if (!detail || detail.id !== id) return;
                if (settled) return;
                settled = true;
                clearTimeout(timeoutId);
                document.removeEventListener(RESPONSE_EVENT, onResponse);

                if (detail.error) {
                    const err = new Error(detail.error);
                    if (detail.validationErrors) {
                        err.validationErrors = detail.validationErrors;
                    }
                    reject(err);
                    return;
                }
                resolve(detail.result);
            }

            document.addEventListener(RESPONSE_EVENT, onResponse);
            document.dispatchEvent(
                new CustomEvent(CALL_EVENT, {
                    detail: { id, method, args: args || [] },
                }),
            );
        });
    }

    if (typeof window.AutofillExtension !== 'undefined' && window.AutofillExtension.__bridge === true) {
        return;
    }

    const proxy = {
        __bridge: true,
        version: BRIDGE_VERSION,
    };

    for (const method of BRIDGED_METHODS) {
        proxy[method] = function (...args) {
            return callBridge(method, args);
        };
    }

    window.AutofillExtension = proxy;
    console.log('[AutofillBridge] Page-world API ready at window.AutofillExtension (__bridge=true)');
})();
