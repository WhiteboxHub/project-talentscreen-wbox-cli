// content.js — JobCLI Extension
// Injects a simple floating "Autofill" button and fills forms using
// resume data passed from the CLI engine via a shared DOM attribute.

(function () {
    'use strict';

    // ══════════════════════════════════════════════════════════════
    // 1. Read CLI context from DOM (shared between page & extension)
    // ══════════════════════════════════════════════════════════════
    function getCliContext() {
        const raw = document.documentElement.getAttribute('data-jobcli-context');
        if (!raw) return null;
        try { return JSON.parse(raw); } catch (e) { return null; }
    }

    // ══════════════════════════════════════════════════════════════
    // 2. Inject floating "Autofill" button (top-right corner)
    // ══════════════════════════════════════════════════════════════
    function injectAutofillButton() {
        if (document.getElementById('jobcli-autofill-btn')) return;

        const btn = document.createElement('button');
        btn.id = 'jobcli-autofill-btn';
        btn.textContent = '⚡ Autofill';
        btn.style.cssText = `
            position: fixed;
            top: 14px;
            right: 14px;
            z-index: 2147483647;
            padding: 10px 22px;
            font-size: 15px;
            font-weight: 700;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #fff;
            background: linear-gradient(135deg, #f0abfc, #c084fc, #a855f7);
            border: none;
            border-radius: 10px;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(192, 132, 252, 0.45);
            transition: all 0.2s ease;
        `;

        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'scale(1.06)';
            btn.style.boxShadow = '0 6px 20px rgba(192, 132, 252, 0.6)';
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'scale(1)';
            btn.style.boxShadow = '0 4px 14px rgba(192, 132, 252, 0.45)';
        });

        btn.addEventListener('click', async () => {
            const ctx = getCliContext();
            if (ctx && ctx.resume) {
                btn.textContent = '⏳ Filling...';
                btn.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
                const count = await doFill(ctx.resume);
                setTimeout(() => {
                    btn.textContent = `✅ Filled ${count}`;
                    btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
                    // Write result for Playwright to read
                    document.documentElement.setAttribute(
                        'data-jobcli-fill-result',
                        JSON.stringify({ status: 'success', filled: count })
                    );
                    setTimeout(() => {
                        btn.textContent = '⚡ Autofill';
                        btn.style.background = 'linear-gradient(135deg, #f0abfc, #c084fc, #a855f7)';
                    }, 3000);
                }, 800);
            } else {
                btn.textContent = '❌ No data';
                btn.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
                document.documentElement.setAttribute(
                    'data-jobcli-fill-result',
                    JSON.stringify({ status: 'error', error: 'no_context' })
                );
                setTimeout(() => {
                    btn.textContent = '⚡ Autofill';
                    btn.style.background = 'linear-gradient(135deg, #f0abfc, #c084fc, #a855f7)';
                }, 2000);
            }
        });

        document.body.appendChild(btn);
    }

    // ══════════════════════════════════════════════════════════════
    // 3. Core fill logic — maps resume fields to form inputs
    // ══════════════════════════════════════════════════════════════

    async function setInputValue(el, value) {
        if (!el || !value) return false;

        // For select elements, find the matching option
        if (el.tagName === 'SELECT') {
            const options = Array.from(el.options);
            const match = options.find(o =>
                o.value.toLowerCase() === String(value).toLowerCase() ||
                o.textContent.trim().toLowerCase() === String(value).toLowerCase()
            );
            if (match) {
                el.value = match.value;
                el.setAttribute('value', match.value);
                ['input', 'change', 'blur'].forEach(evt =>
                    el.dispatchEvent(new Event(evt, { bubbles: true }))
                );
                flashGreen(el);
                return true;
            }
            return false;
        }

        // For regular inputs — simulate human-like typing events
        el.focus();
        el.value = '';
        el.dispatchEvent(new Event('focus', { bubbles: true }));

        // Type character by character for realism with randomized delay
        for (const char of String(value)) {
            el.value += char;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            // Add a randomized delay (20ms to 70ms) to simulate human typing
            await new Promise(r => setTimeout(r, Math.random() * 50 + 20));
        }
        el.setAttribute('value', el.value);
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        flashGreen(el);
        return true;
    }

    function flashGreen(el) {
        const orig = el.style.cssText;
        el.style.backgroundColor = '#dcfce7';
        el.style.border = '2px solid #22c55e';
        setTimeout(() => {
            el.style.backgroundColor = '';
            el.style.border = '';
        }, 2500);
    }

    // Field mapping: maps common field identifiers to resume data paths
    async function doFill(resume) {
        const personal = resume.personal || {};
        const workAuth = resume.work_authorization || {};
        const demographics = resume.demographics || {};
        const experience = (resume.experience || [])[0] || {};
        const education = (resume.education || [])[0] || {};

        // Build a flat lookup of label/id/name → value
        const fieldMap = {
            // Personal
            'name': [personal.first_name, personal.last_name].filter(Boolean).join(' '),
            'full name': [personal.first_name, personal.last_name].filter(Boolean).join(' '),
            'fullname': [personal.first_name, personal.last_name].filter(Boolean).join(' '),
            'first_name': personal.first_name,
            'first name': personal.first_name,
            'given-name': personal.first_name,
            'given_name': personal.first_name,
            'firstname': personal.first_name,
            'last_name': personal.last_name,
            'last name': personal.last_name,
            'family-name': personal.last_name,
            'family_name': personal.last_name,
            'lastname': personal.last_name,
            'email': personal.email,
            'e-mail': personal.email,
            'email address': personal.email,
            'phone': personal.phone,
            'phone number': personal.phone,
            'tel': personal.phone,
            'mobile': personal.phone,
            'linkedin': personal.linkedin,
            'linkedin profile': personal.linkedin,
            'github': personal.github,
            'github profile': personal.github,
            'portfolio': personal.portfolio || personal.website,
            'website': personal.website || personal.portfolio,
            'address': personal.address,
            'city': personal.city,
            'state': personal.state,
            'zip': personal.zip_code,
            'zip_code': personal.zip_code,
            'zip code': personal.zip_code,
            'postal': personal.zip_code,
            'country': personal.country,
            'location': [personal.city, personal.state].filter(Boolean).join(', '),

            // Work auth
            'authorized': workAuth.authorized_to_work ? 'Yes' : 'No',
            'work authorization': workAuth.authorized_to_work ? 'Yes' : 'No',
            'legally authorized': workAuth.authorized_to_work ? 'Yes' : 'No',
            'work_auth': workAuth.authorized_to_work ? 'Yes' : 'No',
            'sponsorship': workAuth.require_sponsorship ? 'Yes' : 'No',
            'visa': workAuth.require_sponsorship ? 'Yes' : 'No',

            // Demographics (optional)
            'gender': demographics.gender,
            'race': demographics.race,
            'ethnicity': demographics.race,
            'veteran': demographics.veteran_status,
            'veteran_status': demographics.veteran_status,
            'disability': demographics.disability_status,

            // Experience
            'company': experience.company,
            'employer': experience.company,
            'most recent employer': experience.company,
            'job_title': experience.title,
            'job title': experience.title,
            'title': experience.title,
        };

        // Scan all visible form fields on the page
        const inputs = document.querySelectorAll('input, select, textarea');
        let filled = 0;

        for (const el of inputs) {
            if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button' || el.type === 'file') continue;
            if (el.value && el.value.trim()) continue; // Already has a value

            // Try to match by: id, name, autocomplete, associated label text
            const candidates = [
                el.id,
                el.name,
                el.getAttribute('autocomplete'),
                el.getAttribute('aria-label'),
                el.getAttribute('placeholder'),
            ];

            // Find associated label
            const label = el.closest('.form-group, .field, .form-field, div')?.querySelector('label');
            if (label) candidates.push(label.textContent.trim().replace(/\s*\*\s*$/, ''));

            // Also try label[for]
            if (el.id) {
                const forLabel = document.querySelector(`label[for="${el.id}"]`);
                if (forLabel) candidates.push(forLabel.textContent.trim().replace(/\s*\*\s*$/, ''));
            }

            let wasFilled = false;
            for (const candidate of candidates) {
                if (!candidate) continue;
                const key = candidate.toLowerCase().trim();

                // Direct match
                if (fieldMap[key]) {
                    if (await setInputValue(el, fieldMap[key])) {
                        filled++;
                        wasFilled = true;
                        break;
                    }
                }

                // Partial match (label contains key)
                for (const [mapKey, mapVal] of Object.entries(fieldMap)) {
                    if (!mapVal) continue;
                    if (key.includes(mapKey) || mapKey.includes(key)) {
                        if (await setInputValue(el, mapVal)) {
                            filled++;
                            wasFilled = true;
                            break;
                        }
                    }
                }
                if (wasFilled) break;
            }
        }

        console.log(`AutoFill: Filled ${filled} fields.`);
        return filled;
    }

    // ══════════════════════════════════════════════════════════════
    // 4. Page load — inject button + auto-fill if CLI context exists
    // ══════════════════════════════════════════════════════════════
    window.addEventListener('load', () => {
        injectAutofillButton();

        const ctx = getCliContext();
        if (ctx && ctx.resume) {
            // Pre-populate chrome.storage for the extension's other features
            chrome.storage.local.set({
                normalizedData: ctx.resume,
                resumeData: ctx.resume
            });
            console.log("AutoFill: CLI context detected, ready to fill.");
        }
    });

    // ══════════════════════════════════════════════════════════════
    // 5. CLI event bridge — Playwright triggers fill via DOM mutation
    // ══════════════════════════════════════════════════════════════
    const fillObserver = new MutationObserver((mutations) => {
        for (const m of mutations) {
            if (m.attributeName === 'data-jobcli-fill-trigger') {
                // Re-inject button in case DOM was replaced (SPA navigation)
                injectAutofillButton();

                const ctx = getCliContext();
                if (ctx && ctx.resume) {
                    doFill(ctx.resume).then(count => {
                        // Signal completion back via DOM attribute
                        document.documentElement.setAttribute(
                            'data-jobcli-fill-result',
                            JSON.stringify({ status: 'success', filled: count })
                        );

                        // Update button visual
                        const btn = document.getElementById('jobcli-autofill-btn');
                        if (btn) {
                            btn.textContent = `✅ Filled ${count} fields`;
                            btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
                            setTimeout(() => {
                                btn.textContent = '⚡ Autofill';
                                btn.style.background = 'linear-gradient(135deg, #f0abfc, #c084fc, #a855f7)';
                            }, 3000);
                        }
                    });
                }
            }
        }
    });
    fillObserver.observe(document.documentElement, { attributes: true });

    // ══════════════════════════════════════════════════════════════
    // 6. SPA navigation detection — re-inject button on route changes
    // ══════════════════════════════════════════════════════════════
    // Multi-page wizards (Oracle HCM, Workday) use pushState/replaceState
    // to navigate between steps without a full page reload.
    const originalPushState = history.pushState;
    history.pushState = function (...args) {
        originalPushState.apply(this, args);
        setTimeout(injectAutofillButton, 500);
    };
    const originalReplaceState = history.replaceState;
    history.replaceState = function (...args) {
        originalReplaceState.apply(this, args);
        setTimeout(injectAutofillButton, 500);
    };
    window.addEventListener('popstate', () => setTimeout(injectAutofillButton, 500));

    // Also watch for large DOM mutations (React/Angular re-renders)
    const domObserver = new MutationObserver((mutations) => {
        let formFieldsAdded = false;
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.tagName === 'INPUT' || node.tagName === 'SELECT' ||
                        node.tagName === 'TEXTAREA' || node.querySelector?.('input, select, textarea')) {
                        formFieldsAdded = true;
                    }
                }
            }
        }
        if (formFieldsAdded) {
            injectAutofillButton();
        }
    });
    if (document.body) {
        domObserver.observe(document.body, { childList: true, subtree: true });
    }

})();
