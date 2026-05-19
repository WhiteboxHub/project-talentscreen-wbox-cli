/**
 * workdayStrategy.js
 * Strategy for Workday application forms.
 */
class WorkdayStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; // Keep standard threshold for workday
    }

    async execute(normalizedData, resumeFile = null) {

        this.executed = true;
        this.lastExecutedUrl = window.location.href;

        await super.execute(normalizedData, resumeFile);

        // Handle Workday-specific custom country dropdowns that GenericStrategy might miss
        this._fillWorkdayCountry(normalizedData);
        // Handle Workday's pervasive custom "pseudo-selects"
        this._handleWorkdayPseudoSelects(normalizedData);
    }

    _fillWorkdayCountry(normalizedData) {
        const country = normalizedData?.contact?.country || "";
        if (!country) return;

        const usVariations = ['us', 'usa', 'united states', 'united states of america'];
        const isUS = usVariations.includes(country.toLowerCase().replace(/[^\w\s]/g, '').trim());

        // Workday often uses buttons with data-automation-id="countryDropdown" 
        // or a div with data-automation-id="addressSection_country"
        const countryTriggers = document.querySelectorAll('[data-automation-id*="country"], [aria-label*="country" i]');

        countryTriggers.forEach(trigger => {
            if (trigger.tagName === 'BUTTON' || trigger.tagName === 'DIV' || trigger.getAttribute('role') === 'button') {
                const text = (trigger.innerText || "").toLowerCase();
                if (isUS && (text.includes('united states') || text.includes('usa'))) return;

                const input = trigger.querySelector('input') || (trigger.tagName === 'INPUT' ? trigger : null);
                if (input) {
                    this.setInputValue(input, isUS ? "United States of America" : country);
                }
            }
        });
    }

    /**
     * Workday uses <div> or <button> elements that act as "Select" triggers.
     * These often have data-automation-id="selectWidget" or similar.
     */
    _handleWorkdayPseudoSelects(normalizedData) {
        const triggers = document.querySelectorAll('[data-automation-id*="selectWidget"], [data-automation-id*="promptIcon"], [role="combobox"]');
        
        triggers.forEach(trigger => {
            const container = trigger.closest('[data-automation-id*="formField"]');
            if (!container) return;

            const label = container.querySelector('label')?.innerText || "";
            if (!label) return;

            // Reuse generic value finder by mocking an input
            const mockInput = {
                getAttribute: (attr) => attr === 'data-automation-id' ? container.getAttribute('data-automation-id') : null,
                tagName: 'INPUT',
                id: '',
                name: '',
                closest: () => container
            };

            const match = this.findValueForInput(mockInput, normalizedData);
            if (match && match.value) {
                // To actually "select" in Workday, we usually need to click the trigger
                // which opens a listbox, then click the item.
                // However, Workday also has a hidden input or state. 
                // For a safer "submission-ready" approach, we'll try to set the nested input if visible.
                const input = trigger.querySelector('input') || container.querySelector('input');
                if (input && !input.value) {
                    this.setInputValue(input, match.value);
                }
            }
        });
    }

    handleInitialEntry() {
        // console.log("WorkdayStrategy: Looking for Apply button on Workday job page...");

        // On Workday job listing pages, the Apply button is usually near the job title
        // It might be an icon button with no text, so we need to be more permissive

        // First, try to find buttons with obvious apply-related attributes or text
        const likelyApplyButtons = Array.from(document.querySelectorAll(
            'button, [role="button"], a[role="button"]'
        )).filter(btn => {
            if (btn.disabled || btn.offsetParent === null) return false;

            const text = (btn.innerText || btn.textContent || "").toLowerCase().trim();
            const ariaLabel = (btn.getAttribute('aria-label') || "").toLowerCase();
            const dataId = (btn.getAttribute('data-automation-id') || "").toLowerCase();
            const title = (btn.getAttribute('title') || "").toLowerCase();
            const className = (btn.className || "").toLowerCase();
            const href = (btn.getAttribute('href') || "").toLowerCase();

            // Check all possible places text could be
            const allText = text + ' ' + ariaLabel + ' ' + dataId + ' ' + title + ' ' + className + ' ' + href;

            // EXCLUSION: Never click LinkedIn or other third-party apply buttons
            if (allText.includes('linkedin') ||
                allText.includes('easy apply') ||
                allText.includes('indeed') ||
                btn.querySelector('img[alt*="linkedin" i]') ||
                btn.querySelector('svg[aria-label*="linkedin" i]')) {
                console.log('[WorkdayStrategy] Skipping third-party button:', text);
                return false;
            }

            return allText.includes('apply');
        });

        // console.log("WorkdayStrategy: Found", likelyApplyButtons.length, "buttons with 'apply' in text/attributes");

        if (likelyApplyButtons.length > 0) {
            // Log details about each
            likelyApplyButtons.forEach((btn, idx) => {
                const text = (btn.innerText || btn.textContent || "").substring(0, 40);
                const ariaLabel = btn.getAttribute('aria-label') || "N/A";
                // console.log(`  [${idx}] text="${text}" aria-label="${ariaLabel}"`);
            });

            // Click the first obvious apply button
            const btn = likelyApplyButtons[0];
            // console.log("WorkdayStrategy: ✓ Clicking Apply button");
            btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => {
                btn.click();
            }, 300);
            return true;
        }

        // Fallback: if no explicit "apply" button, look for the most prominent button
        // (highest z-index, latest in DOM) that might be the apply button
        // console.log("WorkdayStrategy: No explicit 'apply' button found, scanning all buttons...");

        const allButtons = Array.from(document.querySelectorAll('button, [role="button"], a[role="button"]'));
        const visibleButtons = allButtons.filter(b => b.offsetParent !== null && !b.disabled);

        // console.log("WorkdayStrategy: Found", visibleButtons.length, "visible buttons total");

        // Check if any button looks like a primary CTA (usually styled differently)
        let ctaButton = null;
        for (const btn of visibleButtons) {
            const style = window.getComputedStyle(btn);
            const bgColor = style.backgroundColor;
            const btnText = (btn.innerText || btn.textContent || "").toLowerCase().trim();
            const className = (btn.className || "").toLowerCase();
            const href = (btn.getAttribute('href') || "").toLowerCase();

            // Skip tiny buttons (likely icons or minor controls)
            const rect = btn.getBoundingClientRect();
            if (rect.width < 30 || rect.height < 20) continue;

            // Skip buttons with explicit exclusion keywords
            if (btnText.includes('close') || btnText.includes('cancel') || btnText.includes('back')) continue;

            // EXCLUSION: Skip LinkedIn and third-party buttons
            if (btnText.includes('linkedin') ||
                btnText.includes('easy apply') ||
                btnText.includes('indeed') ||
                className.includes('linkedin') ||
                href.includes('linkedin') ||
                btn.querySelector('img[alt*="linkedin" i]') ||
                btn.querySelector('svg[aria-label*="linkedin" i]')) {
                console.log('[WorkdayStrategy] Skipping third-party CTA button:', btnText);
                continue;
            }

            // Look for the button nearest to the job content area (usually top of page or job header)
            // Workday typically shows the Apply button in the job header
            if (!ctaButton) {
                ctaButton = btn;
            }
        }

        if (ctaButton) {
            const text = (ctaButton.innerText || ctaButton.textContent || "").substring(0, 40);
            // console.log("WorkdayStrategy: Clicking prominent button: \"" + text + "\"");
            ctaButton.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => {
                ctaButton.click();
            }, 300);
            return true;
        }

        // console.log("WorkdayStrategy: Could not find apply button, falling back to generic handler");
        return super.handleInitialEntry();
    }


    findValueForInput(input, normalizedData) {
        let match = this.findWorkdaySpecificMatch(input, normalizedData);
        if (match && match.value) return match;
        return super.findValueForInput(input, normalizedData);
    }

    findWorkdaySpecificMatch(input, data) {
        const dataAutomationId = (input.getAttribute('data-automation-id') || "").toLowerCase();

        if (!dataAutomationId) {
            // Check label text for specific Sutter Health questions if automation ID is missing
            const label = input.closest('div')?.querySelector('label')?.innerText.toLowerCase() || "";
            if (label.includes('sutter health') && label.includes('past')) return { value: 'No', confidence: 95 };
            if (label.includes('how did you hear')) return { value: 'Job Search Site', confidence: 95 };
            return null;
        }

        const identity = data?.identity || {};
        const contact = data?.contact || {};
        const employment = data?.employment?.history?.[0] || {};
        const education = data?.education?.[0] || {};

        // Common Workday data-automation-ids
        // Common Workday data-automation-ids
        if (dataAutomationId.includes('first') && dataAutomationId.includes('name')) return { value: identity.first_name, confidence: 95 };
        if (dataAutomationId.includes('last') && dataAutomationId.includes('name')) return { value: identity.last_name, confidence: 95 };
        if (dataAutomationId.includes('email')) return { value: contact.email, confidence: 95 };
        if (dataAutomationId.includes('phone')) return { value: contact.phone, confidence: 95 };
        if (dataAutomationId.includes('address-line1') || dataAutomationId.includes('addressline1')) return { value: contact.address, confidence: 95 };
        if (dataAutomationId.includes('address-city') || dataAutomationId.includes('city')) return { value: contact.city, confidence: 95 };
        if (dataAutomationId.includes('address-postal-code') || dataAutomationId.includes('postal')) return { value: contact.zip_code, confidence: 95 };

        // Dates
        if (dataAutomationId.includes('date') && (dataAutomationId.includes('start') || dataAutomationId.includes('from'))) return { value: employment.startDate || education.startDate, confidence: 90 };
        if (dataAutomationId.includes('date') && (dataAutomationId.includes('end') || dataAutomationId.includes('to'))) return { value: employment.endDate || education.endDate, confidence: 90 };

        // Employment Data
        if (dataAutomationId.includes('jobtitle') || dataAutomationId.includes('title')) return { value: employment.position || " ", confidence: 95, fieldKey: 'employment.current_role' };
        if (dataAutomationId.includes('company')) return { value: employment.company || employment.name || " ", confidence: 95, fieldKey: 'employment.current_company' };
        if (dataAutomationId.includes('roledescription') || dataAutomationId.includes('description')) return { value: employment.summary || " ", confidence: 95, fieldKey: 'employment.work_description' };

        // Education Data
        if (dataAutomationId.includes('school') || dataAutomationId.includes('institution')) return { value: education.institution || " ", confidence: 95, fieldKey: 'education_flat.institution' };
        if (dataAutomationId.includes('degree')) return { value: education.degree || " ", confidence: 95, fieldKey: 'education_flat.degree' };
        if (dataAutomationId.includes('fieldofstudy') || dataAutomationId.includes('major')) return { value: education.major || " ", confidence: 95, fieldKey: 'education_flat.major' };

        // Demographics
        if (dataAutomationId.includes('gender')) return { value: identity.gender, confidence: 95, fieldKey: 'identity.gender' };
        if (dataAutomationId.includes('ethnicity') || dataAutomationId.includes('race')) return { value: identity.ethnicity, confidence: 95, fieldKey: 'identity.ethnicity' };
        if (dataAutomationId.includes('hispanic')) return { value: identity.hispanic_latino, confidence: 95, fieldKey: 'identity.hispanic_latino' };
        if (dataAutomationId.includes('veteran')) return { value: identity.veteran_status, confidence: 95, fieldKey: 'identity.veteran_status' };
        if (dataAutomationId.includes('disability')) return { value: identity.disability_status, confidence: 95, fieldKey: 'identity.disability_status' };

        // Specific mappings
        if (dataAutomationId.includes('sourceprompt')) return { value: 'LinkedIn', confidence: 95 };
        if (dataAutomationId.includes('previousemployee')) return { value: 'No', confidence: 95 };
        if (dataAutomationId.includes('legalright') || dataAutomationId.includes('workauth')) return { value: 'Yes', confidence: 95, fieldKey: 'identity.authorized_to_work' };
        if (dataAutomationId.includes('requiresponsorship') || dataAutomationId.includes('sponsorship')) return { value: 'No', confidence: 95, fieldKey: 'identity.sponsorship_required' };
        if (dataAutomationId.includes('relocation')) return { value: identity.relocation_open || 'No', confidence: 90, fieldKey: 'identity.relocation_open' };
        if (dataAutomationId.includes('noticeperiod')) return { value: identity.notice_period || 'Immediate', confidence: 90, fieldKey: 'identity.notice_period' };
        if (dataAutomationId.includes('salary') || dataAutomationId.includes('expectation')) return { value: identity.expected_salary || 'Competitive', confidence: 85, fieldKey: 'identity.expected_salary' };

        return null;
    }

    // Workday specific radio handling: labels are often far from inputs or use specific aria classes
    handleRadioCheckbox(input, data) {
        const dataAutomationId = (input.getAttribute('data-automation-id') || "").toLowerCase();

        // Check if this input is part of a radio group with a specific value
        const match = this.findWorkdaySpecificMatch(input, data);
        if (match && match.value) {
            const val = String(match.value).toLowerCase();
            const parent = input.closest('[data-automation-id*="formField"]') || input.parentElement;
            // Scan for a label that contains our target value
            const labels = Array.from(parent?.querySelectorAll('label') || []);
            const targetLabel = labels.find(l => {
                const text = l.innerText.toLowerCase().trim();
                return text === val || text.includes(val);
            });

            if (targetLabel) {
                // If this specific input's associated label matches our target value, check it
                const inputLabel = this.getLabelText(input).toLowerCase();
                if (inputLabel.includes(val) || val.includes(inputLabel)) {
                    input.checked = true;
                    this.setInputValue(input, null, 'green');
                    return;
                }
            }
        }

        super.handleRadioCheckbox(input, data);
    }
}

// Register with Strategy Registry if available
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('workday.com') || url.includes('myworkdayjobs.com'),
        WorkdayStrategy
    );
}
