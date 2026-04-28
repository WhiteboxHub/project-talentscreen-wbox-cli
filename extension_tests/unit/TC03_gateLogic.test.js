/**
 * TC-03: shouldBypassGate — gate bypass condition logic
 *
 * Tests that the bypass gate correctly computes:
 *   shouldBypassGate = !!autoTriggerEnabled && isJobPage()
 *
 * And that the resulting gate condition:
 *   if (!sidePanelOpen && !force && !shouldBypassGate) { return; }
 * behaves correctly across all combinations.
 */

// ─── Inline helper (mirrors content.js logic exactly) ────────────────────────
function computeBypassGate(autoTriggerEnabled, isJobPageResult) {
    return !!autoTriggerEnabled && isJobPageResult;
}

function shouldBlock(sidePanelOpen, force, bypassGate) {
    return !sidePanelOpen && !force && !bypassGate;
}

// ─────────────────────────────────────────────────────────────────────────────
// TC-03a: shouldBypassGate computation
// ─────────────────────────────────────────────────────────────────────────────
describe('TC-03a | shouldBypassGate — bypass condition computation', () => {

    test('TC-03a-01 ✅ autoTriggerEnabled=true, isJobPage=true → bypass=true', () => {
        expect(computeBypassGate(true, true)).toBe(true);
    });

    test('TC-03a-02 ❌ autoTriggerEnabled=false, isJobPage=true → bypass=false', () => {
        expect(computeBypassGate(false, true)).toBe(false);
    });

    test('TC-03a-03 ❌ autoTriggerEnabled=true, isJobPage=false → bypass=false', () => {
        expect(computeBypassGate(true, false)).toBe(false);
    });

    test('TC-03a-04 ❌ autoTriggerEnabled=undefined, isJobPage=true → bypass=false', () => {
        expect(computeBypassGate(undefined, true)).toBe(false);
    });

    test('TC-03a-05 ❌ autoTriggerEnabled=null, isJobPage=true → bypass=false', () => {
        expect(computeBypassGate(null, true)).toBe(false);
    });

    test('TC-03a-06 ❌ autoTriggerEnabled=false, isJobPage=false → bypass=false', () => {
        expect(computeBypassGate(false, false)).toBe(false);
    });

    test('TC-03a-07 ✅ autoTriggerEnabled=true (truthy), isJobPage=true → bypass=true', () => {
        // Chrome storage returns true as boolean
        expect(computeBypassGate(true, true)).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// TC-03b: Gate logic — should the function block execution?
//
// Gate: if (!sidePanelOpen && !force && !bypassGate) → BLOCK
// ─────────────────────────────────────────────────────────────────────────────
describe('TC-03b | Gate logic — all path combinations', () => {

    // ─── Existing paths (unchanged behavior) ───
    test('TC-03b-01 ✅ sidePanelOpen=true, force=false, bypass=false → ALLOW (panel open)', () => {
        expect(shouldBlock(true, false, false)).toBe(false);
    });

    test('TC-03b-02 ✅ sidePanelOpen=false, force=true, bypass=false → ALLOW (forced)', () => {
        expect(shouldBlock(false, true, false)).toBe(false);
    });

    test('TC-03b-03 ✅ sidePanelOpen=true, force=true, bypass=false → ALLOW (both)', () => {
        expect(shouldBlock(true, true, false)).toBe(false);
    });

    // ─── New auto-trigger path ───
    test('TC-03b-04 ✅ sidePanelOpen=false, force=false, bypass=true → ALLOW (auto-trigger)', () => {
        // This is the KEY new behaviour — extension works without side panel
        expect(shouldBlock(false, false, true)).toBe(false);
    });

    test('TC-03b-05 ✅ sidePanelOpen=true, force=false, bypass=true → ALLOW (both panel+trigger)', () => {
        expect(shouldBlock(true, false, true)).toBe(false);
    });

    test('TC-03b-06 ✅ sidePanelOpen=false, force=true, bypass=true → ALLOW (all three)', () => {
        expect(shouldBlock(false, true, true)).toBe(false);
    });

    // ─── Block case ───
    test('TC-03b-07 ❌ sidePanelOpen=false, force=false, bypass=false → BLOCK', () => {
        // No panel, no force, no auto-trigger → should block (old behavior preserved)
        expect(shouldBlock(false, false, false)).toBe(true);
    });

    // ─── Real-world scenario: friend opens job page ───
    test('TC-03b-08 ✅ SCENARIO: Friend opens Greenhouse URL, auto-trigger ON → fills without side panel', () => {
        const autoTriggerEnabled = true;
        const isJobPageResult = true; // greenhouse.io URL
        const sidePanelOpen = false;  // friend never opened side panel
        const force = false;

        const bypass = computeBypassGate(autoTriggerEnabled, isJobPageResult);
        const blocked = shouldBlock(sidePanelOpen, force, bypass);

        expect(bypass).toBe(true);
        expect(blocked).toBe(false); // ✅ should fill
    });

    test('TC-03b-09 ❌ SCENARIO: Friend opens Google homepage, auto-trigger ON → does NOT fill', () => {
        const autoTriggerEnabled = true;
        const isJobPageResult = false; // google.com
        const sidePanelOpen = false;
        const force = false;

        const bypass = computeBypassGate(autoTriggerEnabled, isJobPageResult);
        const blocked = shouldBlock(sidePanelOpen, force, bypass);

        expect(bypass).toBe(false);
        expect(blocked).toBe(true); // ❌ should NOT fill on non-job pages
    });

    test('TC-03b-10 ❌ SCENARIO: User disabled toggle, opens Lever URL → does NOT fill', () => {
        const autoTriggerEnabled = false;
        const isJobPageResult = true; // lever.co
        const sidePanelOpen = false;
        const force = false;

        const bypass = computeBypassGate(autoTriggerEnabled, isJobPageResult);
        const blocked = shouldBlock(sidePanelOpen, force, bypass);

        expect(bypass).toBe(false);
        expect(blocked).toBe(true); // ❌ user turned off the toggle → should respect preference
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// TC-03c: Fill condition — should fillForm be called?
//
// Original: (autoRunActive || force) && normalizedData
// New:      (autoRunActive || force || shouldBypassGate) && normalizedData
// ─────────────────────────────────────────────────────────────────────────────
describe('TC-03c | Fill condition — when should fillForm execute?', () => {

    function shouldFill(autoRunActive, force, bypassGate, hasData) {
        return (autoRunActive || force || bypassGate) && hasData;
    }

    test('TC-03c-01 ✅ queue active + has data → fill', () => {
        expect(shouldFill(true, false, false, true)).toBe(true);
    });

    test('TC-03c-02 ✅ force=true + has data → fill', () => {
        expect(shouldFill(false, true, false, true)).toBe(true);
    });

    test('TC-03c-03 ✅ bypass=true + has data → fill (NEW)', () => {
        expect(shouldFill(false, false, true, true)).toBe(true);
    });

    test('TC-03c-04 ❌ bypass=true but NO normalizedData → do NOT fill', () => {
        // No profile uploaded yet — extension should not crash, just skip
        expect(shouldFill(false, false, true, false)).toBe(false);
    });

    test('TC-03c-05 ❌ all false → do NOT fill', () => {
        expect(shouldFill(false, false, false, true)).toBe(false);
    });

    test('TC-03c-06 ❌ bypass=true, queue=true, force=true, but no data → do NOT fill', () => {
        expect(shouldFill(true, true, true, false)).toBe(false);
    });
});
