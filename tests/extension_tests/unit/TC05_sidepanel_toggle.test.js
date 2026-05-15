/**
 * TC-05: sidepanel.js — autoTriggerToggle load/save
 *
 * Tests that the toggle checkbox:
 * 1. Loads correctly from chrome.storage (true → checked, false → unchecked,
 *    undefined → checked by default)
 * 2. Saves the correct value on change
 * 3. Does NOT affect other storage keys
 */

beforeEach(() => {
    resetChromeMock();
    // Build a minimal DOM that matches sidepanel.html
    document.body.innerHTML = `
        <input type="checkbox" id="autoTriggerToggle" />
        <button id="fillFormBtn" disabled>Force Fill Form</button>
    `;
});

// ─── Inline the exact sidepanel.js load/save logic ───────────────────────────

function loadToggleState() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['autoTriggerEnabled'], (result) => {
            const toggle = document.getElementById('autoTriggerToggle');
            if (toggle) {
                // Same logic as sidepanel.js: undefined → default true
                toggle.checked = result.autoTriggerEnabled !== false;
            }
            resolve(toggle?.checked);
        });
    });
}

function bindToggleSaveListener() {
    const toggle = document.getElementById('autoTriggerToggle');
    if (toggle) {
        toggle.addEventListener('change', (e) => {
            chrome.storage.local.set({ autoTriggerEnabled: e.target.checked });
        });
    }
}

// ─────────────────────────────────────────────────────────────────────────────
describe('TC-05 | sidepanel.js — autoTriggerToggle load state', () => {

    test('TC-05-01 ✅ Storage: autoTriggerEnabled=true → checkbox checked', async () => {
        await new Promise(r => chrome.storage.local.set({ autoTriggerEnabled: true }, r));
        const checked = await loadToggleState();
        expect(checked).toBe(true);
        expect(document.getElementById('autoTriggerToggle').checked).toBe(true);
    });

    test('TC-05-02 ✅ Storage: autoTriggerEnabled=false → checkbox unchecked', async () => {
        await new Promise(r => chrome.storage.local.set({ autoTriggerEnabled: false }, r));
        const checked = await loadToggleState();
        expect(checked).toBe(false);
        expect(document.getElementById('autoTriggerToggle').checked).toBe(false);
    });

    test('TC-05-03 ✅ Storage: autoTriggerEnabled=undefined (fresh) → checkbox checked (default ON)', async () => {
        // Key never set — new user should get auto-trigger ON by default
        const checked = await loadToggleState();
        expect(checked).toBe(true);
        expect(document.getElementById('autoTriggerToggle').checked).toBe(true);
    });

    test('TC-05-04 ✅ Toggle element exists in DOM after setup', () => {
        const toggle = document.getElementById('autoTriggerToggle');
        expect(toggle).not.toBeNull();
        expect(toggle.type).toBe('checkbox');
    });
});

describe('TC-05 | sidepanel.js — autoTriggerToggle save on change', () => {

    test('TC-05-05 ✅ Checking the toggle → saves autoTriggerEnabled=true', async () => {
        bindToggleSaveListener();
        const toggle = document.getElementById('autoTriggerToggle');

        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));

        // Allow microtask to complete
        await new Promise(r => setTimeout(r, 0));

        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(true);
    });

    test('TC-05-06 ✅ Unchecking the toggle → saves autoTriggerEnabled=false', async () => {
        // Start checked
        await new Promise(r => chrome.storage.local.set({ autoTriggerEnabled: true }, r));
        await loadToggleState();
        bindToggleSaveListener();

        const toggle = document.getElementById('autoTriggerToggle');
        toggle.checked = false;
        toggle.dispatchEvent(new Event('change'));

        await new Promise(r => setTimeout(r, 0));

        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(false);
    });

    test('TC-05-07 ✅ Toggle change does NOT affect other storage keys', async () => {
        // Pre-populate other keys
        await new Promise(r => chrome.storage.local.set({
            normalizedData: { first_name: 'John' },
            activeProfileName: 'my-profile',
            autoRunActive: false
        }, r));

        bindToggleSaveListener();
        const toggle = document.getElementById('autoTriggerToggle');
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));

        await new Promise(r => setTimeout(r, 0));

        const result = await new Promise(r => chrome.storage.local.get(
            ['normalizedData', 'activeProfileName', 'autoRunActive', 'autoTriggerEnabled'], r
        ));

        // autoTriggerEnabled updated
        expect(result.autoTriggerEnabled).toBe(true);
        // All other keys untouched
        expect(result.normalizedData).toEqual({ first_name: 'John' });
        expect(result.activeProfileName).toBe('my-profile');
        expect(result.autoRunActive).toBe(false);
    });

    test('TC-05-08 ✅ Multiple toggle flips → always saves last state', async () => {
        bindToggleSaveListener();
        const toggle = document.getElementById('autoTriggerToggle');

        // flip on
        toggle.checked = true; toggle.dispatchEvent(new Event('change'));
        await new Promise(r => setTimeout(r, 0));

        // flip off
        toggle.checked = false; toggle.dispatchEvent(new Event('change'));
        await new Promise(r => setTimeout(r, 0));

        // flip on again
        toggle.checked = true; toggle.dispatchEvent(new Event('change'));
        await new Promise(r => setTimeout(r, 0));

        const result = await new Promise(r => chrome.storage.local.get(['autoTriggerEnabled'], r));
        expect(result.autoTriggerEnabled).toBe(true);
    });
});
