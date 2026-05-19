// ... (previous code above remains the same)

let autoFillState = {
    hasRun: false,
    debouncing: false,

    get submissionAttempted() {
        return sessionStorage.getItem('autofill_submission_attempted') === 'true';
    },
    set submissionAttempted(val) {
        sessionStorage.setItem('autofill_submission_attempted', val ? 'true' : 'false');
    }
};

// Mark any field the USER physically edits so autofill never overwrites their corrections.
document.addEventListener('input', (e) => {
    if (e.isTrusted && e.target.matches('input, textarea, select')) {
        e.target.dataset.afUserLocked = 'true';
    }
}, true);

// Listen for messages from popup (Manual fallback or Edits)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "fill_form") {
        fillForm(request.normalizedData, true, request.resumeFile);
        sendResponse({ status: "done" });
    } else if (request.action === "get_page_context") {
        try {
            const strategy = ATSStrategyRegistry.getStrategy(window.location.href, document);
            if (strategy && typeof strategy.getPageContext === 'function') {
                sendResponse(strategy.getPageContext());
            } else {
                sendResponse({
                    pageTitle: document.title,
                    headerText: document.querySelector('h1')?.innerText || "",
                    url: window.location.href
                });
            }
        } catch (e) { sendResponse({}); }
        return true;
    } else if (request.action === "check_progress") {
        // Check if FormTracker has an active session with progress
        let hasProgress = false;

        if (typeof FormTracker !== 'undefined' && FormTracker.initialized) {
            const session = FormTracker.getCurrentSession();
            hasProgress = session && (session.fields.filled > 0 || session.fields.failed > 0);
        } else {
            // Fallback: check if any fields have been filled
            const filledFields = document.querySelectorAll('input[data-autofilled], textarea[data-autofilled], select[data-autofilled]');
            hasProgress = filledFields.length > 0;
        }

        sendResponse({ hasProgress: hasProgress });
    }
});



// 5. Manual Submission Tracking
document.addEventListener('mousedown', (e) => {
    const btn = e.target.closest('button, input[type="submit"], input[type="button"], a.btn');
    if (!btn) return;
    const txt = (btn.innerText || btn.value || "").toLowerCase();
    const className = (btn.className || "").toLowerCase();
    const href = (btn.getAttribute('href') || "").toLowerCase();

    // Skip LinkedIn or other third-party apply buttons
    if (txt.includes('linkedin') ||
        txt.includes('apply with linkedin') ||
        txt.includes('easy apply') ||
        className.includes('linkedin') ||
        href.includes('linkedin') ||
        txt.includes('indeed') ||
        className.includes('indeed')) {
        console.log('[Content] Ignoring third-party apply button:', txt);
        return;
    }

    if (txt.includes('submit') || txt.includes('finish') || txt.includes('apply')) {
        autoFillState.submissionAttempted = true;
        if (chrome.runtime?.id) {
            chrome.storage.local.set({ lastSubmittedUrl: window.location.href });
            chrome.runtime.sendMessage({ action: 'log_submission', url: window.location.href });
        }
    }
}, true);

function checkSuccessPage() {
    const keywords = ["thank you for applying", "application received", "application submitted", "successfully submitted"];
    const bodyText = document.body.innerText.toLowerCase();
    const isSuccessText = keywords.some(k => bodyText.includes(k));
    const isUrl = window.location.href.toLowerCase().match(/confirmation|thank-you|thank_you/);
    const inputs = document.querySelectorAll('input:not([type="hidden"]):not(footer input)');
    return (isSuccessText || isUrl) && inputs.length <= 5;
}

async function fillForm(data, manual = false, resume = null) {
    let counts = { filled: 0, total: 0 };
    try {
        const strategy = ATSStrategyRegistry.getStrategy(window.location.href, document);
        if (strategy) {
            counts = await strategy.execute(data, resume) || counts;
        }
    } catch (err) { /* silent error for generic strategy */ }

    const meta = extractJobMetadata();
    chrome.runtime.sendMessage({ 
        action: 'log_fill', 
        data: { 
            url: window.location.href, 
            company: meta.company, 
            role: meta.role,
            filled: counts.filled,
            total: counts.total
        } 
    });
}


function showToast(msg, type = 'info') {
    const t = document.createElement('div');
    t.style.cssText = `position:fixed; top:20px; right:20px; z-index:2147483647; background:${type === 'error' ? '#ef4444' : 'rgba(0,0,0,0.8)'}; color:white; padding:10px 20px; border-radius:12px; font-family:sans-serif; font-size:13px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), type === 'error' ? 6000 : 3000);
}

function extractJobMetadata() {
    // Use enhanced JobMetadataExtractor if available
    if (typeof JobMetadataExtractor !== 'undefined') {
        const metadata = JobMetadataExtractor.extract();
        return {
            company: metadata.company.substring(0, 50),
            role: metadata.jobTitle.substring(0, 70),
            location: metadata.location,
            jobType: metadata.jobType,
            salary: metadata.salary,
            // Full metadata available for advanced usage
            full: metadata
        };
    }

    // Fallback to simple extraction
    let company = "", role = "";
    const gC = document.querySelector('.company-name'), gR = document.querySelector('.app-title');
    if (gC) company = gC.innerText.trim(); if (gR) role = gR.innerText.trim();
    const lR = document.querySelector('.posting-header h2'), lC = document.querySelector('.posting-header .company-logo img')?.alt;
    if (lR) role = lR.innerText.trim(); if (lC) company = lC.replace(" logo", "").trim();
    if (!company || !role) {
        const m = document.title.match(/(.+) (at|\||-) (.+)/i);
        if (m) { role = m[1].trim(); company = m[3].trim(); } else role = document.title;
    }
    return { company: company.substring(0, 50) || "Company", role: role.substring(0, 70) || "Job" };
}

function extractJobDescription() {
    const ss = [
        '.job-description', '#job-description', '.description',
        '[class*="jobDescription"]', '[id*="jobDescription"]',
        '.posting-description', '.job-info', 'main', 'article',
        '#main-content', '.main-content'
    ];
    for (const s of ss) {
        const e = document.querySelector(s);
        if (e && e.innerText.trim().length > 300) {
            // Remove scripts, styles and other junk from innerText if possible
            const clone = e.cloneNode(true);
            clone.querySelectorAll('script, style, nav, footer, header').forEach(n => n.remove());
            const text = clone.innerText.trim();
            if (text.length > 300) return text.substring(0, 5000);
        }
    }
    // Fallback to body but try to find the largest text container
    return document.body.innerText.substring(0, 5000);
}

// ============================================
// Phase 4: Smart Autofill Features
// ============================================

// Initialize Dynamic Form Watcher
if (typeof DynamicFormWatcher !== 'undefined') {
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            DynamicFormWatcher.init();
            console.log('[Content] DynamicFormWatcher initialized');
        });
    } else {
        DynamicFormWatcher.init();
        console.log('[Content] DynamicFormWatcher initialized');
    }

    // Listen for dynamic fields detected
    document.addEventListener('dynamicFieldsDetected', (e) => {
        console.log('[Content] New fields detected:', e.detail.fields.length);
        // Could trigger retry autofill for pending fields here
    });

    // Listen for dropdowns loaded
    document.addEventListener('dropdownsLoaded', (e) => {
        console.log('[Content] Dropdowns loaded:', e.detail.dropdowns.length);
        // Could trigger retry for failed dropdown fills
    });

    // Listen for page change
    document.addEventListener('pageChanged', (e) => {
        console.log('[Content] Page changed:', e.detail.url);
        // Reset state for new page
        autoFillState.hasRun = false;
    });

    // Listen for auto-continue autofill (multi-step forms)
    document.addEventListener('autoContinueAutofill', async () => {
        console.log('[Content] Auto-continuing autofill on new page');
        // Get stored resume data and continue filling
        const result = await chrome.storage.local.get(['resumeData', 'normalizedData']);
        if (result.normalizedData) {
            fillForm(result.normalizedData, false, result.resumeFile);
        }
    });
}

// CAPTCHA Detection and Warning
if (typeof CaptchaDetector !== 'undefined') {
    // Check for CAPTCHA on page load
    window.addEventListener('load', () => {
        const captchaStatus = CaptchaDetector.getStatus();

        if (captchaStatus.present && !captchaStatus.solved) {
            console.warn('[Content] CAPTCHA detected:', captchaStatus.type);
            showToast(`⚠️ ${captchaStatus.message}`, 'info');

            // Notify sidepanel about CAPTCHA
            chrome.runtime.sendMessage({
                action: 'captcha_detected',
                type: captchaStatus.type,
                message: captchaStatus.message
            });
        }
    });
}

console.log('[Content] Phase 4 features initialized');

