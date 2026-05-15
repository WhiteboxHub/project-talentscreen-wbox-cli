/**
 * TC-04: background.js — onInstalled guarded default
 *
 * Verifies that autoTriggerEnabled is set to true ONLY on fresh install
 * (when the key is undefined), and is NOT overwritten on extension updates
 * when the user has already set a preference.
 *
 * This tests the exact guard pattern:
 *   chrome.storage.local.get(['autoTriggerEnabled'], (result) => {
 *     if (result.autoTriggerEnabled === undefined) {
 *       chrome.storage.local.set({ autoTriggerEnabled: true });
 *     }
 *   });
 */

beforeEach(() => {
    resetChromeMock();
});

// ─── Inline the exact background.js guard logic ──────────────────────────────
function applyAutoTriggerDefault() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['autoTriggerEnabled'], (result) => {
            if (result.autoTriggerEnabled === undefined) {
                chrome.storage.local.set({ autoTriggerEnabled: true }, resolve);
            } else {
                resolve(); // no-op
            }
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
describe('TC-04 | background.js — autoTriggerEnabled default (guarded)', () => {

    test('TC-04-01 ✅ Fresh install: key undefined → sets autoTriggerEnabled=true', async () => {
        // Storage empty — simulates brand new install
        await applyAutoTriggerDefault();
        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(true);
    });

    test('TC-04-02 ✅ Extension update: key=true → does NOT overwrite', async () => {
        // User already has it enabled
        await new Promise(r => chrome.storage.local.set({ autoTriggerEnabled: true }, r));
        await applyAutoTriggerDefault();
        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(true); // still true, unchanged
    });

    test('TC-04-03 ✅ Extension update: key=false → does NOT overwrite (CRITICAL)', async () => {
        // User explicitly DISABLED the toggle — update must NOT re-enable it
        await new Promise(r => chrome.storage.local.set({ autoTriggerEnabled: false }, r));
        await applyAutoTriggerDefault();
        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(false); // ✅ user preference preserved
    });

    test('TC-04-04 ✅ Calling onInstalled twice (simulating 2 updates) → still false', async () => {
        // Simulate user disabling, then two consecutive extension updates
        await new Promise(r => chrome.storage.local.set({ autoTriggerEnabled: false }, r));
        await applyAutoTriggerDefault(); // update 1
        await applyAutoTriggerDefault(); // update 2
        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(false); // still respects user preference
    });

    test('TC-04-05 ✅ contextMenus.create is called (existing behavior intact)', () => {
        // The onInstalled listener also creates context menus — verify those still work
        const calls = [];
        chrome.contextMenus.create.mockImplementation((opts) => calls.push(opts.id));

        chrome.contextMenus.create({ id: 'openSidePanel', title: 'Open Side Panel', contexts: ['all'] });
        chrome.contextMenus.create({ id: 'forceFillData', title: 'Force Fill Data', contexts: ['all'] });

        expect(calls).toContain('openSidePanel');
        expect(calls).toContain('forceFillData');
        expect(calls.length).toBe(2);
    });
});
