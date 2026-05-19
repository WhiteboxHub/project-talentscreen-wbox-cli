/**
 * smartrecruitersStrategy.js
 * Strategy for SmartRecruiters application forms (React SPA)
 * Enhanced with form stabilization, React input support, and mutation observer
 */
class SmartRecruitersStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 50; // Lower for SmartRecruiters' varied field labels

        this.config = {
            confidenceThreshold: 50,
            maxRetries: 3,
            retryDelay: 150,
            formStabilizationWait: 3000,
            formStabilizationCheckInterval: 300,
            minFieldsThreshold: 3,
            mutationObserverTimeout: 30000,
            secondPassDelay: 2000,
            debug: this.isDebugMode()
        };

        this.filledFields = new Set();
    }

    isDebugMode() {
        try {
            return localStorage.getItem('smartrecruiters_debug') === 'true';
        } catch (e) {
            return false;
        }
    }

    log(...args) {
        if (this.config.debug) {
            console.log('[SmartRecruiters]', ...args);
        }
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Wait for SPA form to stabilize
     */
    async waitForFormStabilization() {
        this.log('Waiting for form stabilization...');

        const startTime = Date.now();
        let lastFieldCount = 0;
        let stableCount = 0;
        const requiredStableChecks = 3;

        while (Date.now() - startTime < this.config.formStabilizationWait) {
            const fields = this.detectFields();
            const currentCount = fields.length;

            this.log(`Field count: ${currentCount} (last: ${lastFieldCount})`);

            if (currentCount === lastFieldCount && currentCount >= this.config.minFieldsThreshold) {
                stableCount++;
                if (stableCount >= requiredStableChecks) {
                    this.log(`Form stabilized with ${currentCount} fields`);
                    return true;
                }
            } else {
                stableCount = 0;
            }

            lastFieldCount = currentCount;
            await this.sleep(this.config.formStabilizationCheckInterval);
        }

        this.log(`Form stabilization timeout. Found ${lastFieldCount} fields`);
        return lastFieldCount >= this.config.minFieldsThreshold;
    }

    /**
     * Detect all form fields
     */
    detectFields() {
        const selectors = [
            'input[type="text"]:not([type="hidden"])',
            'input[type="email"]',
            'input[type="tel"]',
            'input[type="url"]',
            'input[type="number"]',
            'input[type="date"]',
            'input:not([type])',
            'textarea',
            'select',
            'input[type="radio"]',
            'input[type="checkbox"]',
            '[role="combobox"]',
            '[role="textbox"]',
            '[contenteditable="true"]'
        ];

        const fields = Array.from(document.querySelectorAll(selectors.join(',')))
            .filter(field => {
                // Skip hidden fields
                if (field.type === 'hidden') return false;
                if (field.offsetParent === null && field.type !== 'radio' && field.type !== 'checkbox') return false;

                // Skip already filled fields (unless radio/checkbox)
                if (field.type !== 'radio' && field.type !== 'checkbox') {
                    if (field.value && field.value.trim() !== '') return false;
                }

                return true;
            });

        return fields;
    }

    /**
     * Extract enhanced features from field
     */
    extractFeatures(field) {
        const features = [];

        // Get label text
        const labelElement = field.labels?.[0] ||
            document.querySelector(`label[for="${field.id}"]`) ||
            field.closest('label') ||
            field.closest('.form-group, .field-group, [class*="field"], [class*="input"]')?.querySelector('label');

        if (labelElement) {
            features.push(labelElement.textContent.trim());
        }

        // Get all attributes
        ['aria-label', 'placeholder', 'name', 'id', 'data-testid', 'data-test', 'autocomplete', 'title'].forEach(attr => {
            const value = field.getAttribute(attr);
            if (value) features.push(value);
        });

        // Get surrounding text (question labels)
        const parent = field.closest('[class*="question"], [class*="field"], .form-group');
        if (parent) {
            const text = parent.textContent;
            if (text && text.length < 500) {
                features.push(text);
            }
        }

        return features.join(' ').toLowerCase().replace(/\s+/g, ' ').trim();
    }

    /**
     * Find best match for field
     */
    findBestMatch(field, data) {
        const text = this.extractFeatures(field);
        const fieldType = field.type?.toLowerCase() || 'text';

        this.log(`Matching field: "${text.substring(0, 100)}..." (type: ${fieldType})`);

        // First name
        if ((text.includes('first') && text.includes('name')) || text.includes('firstname') || text.includes('given name')) {
            return { value: data.identity?.first_name, confidence: 100, key: 'first_name' };
        }

        // Last name
        if ((text.includes('last') && text.includes('name')) || text.includes('lastname') || text.includes('surname') || text.includes('family name')) {
            return { value: data.identity?.last_name, confidence: 100, key: 'last_name' };
        }

        // Full name
        if (text.includes('full name') || (text.includes('name') && !text.includes('first') && !text.includes('last') && !text.includes('company'))) {
            const fullName = `${data.identity?.first_name || ''} ${data.identity?.last_name || ''}`.trim();
            if (fullName) {
                return { value: fullName, confidence: 90, key: 'full_name' };
            }
        }

        // Email
        if (text.includes('email') || text.includes('e-mail') || fieldType === 'email') {
            return { value: data.contact?.email, confidence: 100, key: 'email' };
        }

        // Phone
        if (text.includes('phone') || text.includes('mobile') || text.includes('telephone') || fieldType === 'tel') {
            return { value: data.contact?.phone, confidence: 100, key: 'phone' };
        }

        // LinkedIn
        if (text.includes('linkedin') && (text.includes('url') || text.includes('profile') || text.includes('link'))) {
            return { value: data.contact?.linkedin, confidence: 95, key: 'linkedin' };
        }

        // Website/Portfolio
        if ((text.includes('website') || text.includes('portfolio') || text.includes('personal site')) && !text.includes('company')) {
            return { value: data.contact?.website, confidence: 90, key: 'website' };
        }

        // City
        if ((text.includes('city') || text.includes('town')) && !text.includes('state')) {
            return { value: data.contact?.city, confidence: 90, key: 'city' };
        }

        // State
        if (text.includes('state') || text.includes('province') || text.includes('region')) {
            return { value: data.contact?.state, confidence: 90, key: 'state' };
        }

        // Zip/Postal Code
        if (text.includes('zip') || text.includes('postal')) {
            return { value: data.contact?.zip, confidence: 90, key: 'zip' };
        }

        // Country
        if (text.includes('country')) {
            return { value: data.contact?.country, confidence: 90, key: 'country' };
        }

        // Address
        if (text.includes('address') && !text.includes('email')) {
            return { value: data.contact?.address, confidence: 85, key: 'address' };
        }

        // Work authorization (radio/checkbox) - use custom_fields
        if ((text.includes('authorized') || text.includes('authorization')) && (text.includes('work') || text.includes('employment'))) {
            if (fieldType === 'radio' || fieldType === 'checkbox') {
                const workAuth = data.custom_fields?.legal?.work_auth_us !== undefined
                    ? data.custom_fields.legal.work_auth_us
                    : true;
                // Look for "Yes" option
                if (text.includes('yes') || field.value === '1' || field.value.toLowerCase() === 'yes') {
                    return { value: workAuth, confidence: 95, key: 'work_auth_yes' };
                }
            }
        }

        // Sponsorship (radio/checkbox) - use custom_fields
        if (text.includes('sponsor') && (text.includes('visa') || text.includes('employment') || text.includes('require'))) {
            if (fieldType === 'radio' || fieldType === 'checkbox') {
                const needsSponsorship = data.custom_fields?.legal?.sponsorship_required_now ||
                    data.custom_fields?.legal?.sponsorship_required_future ||
                    false;
                // Look for "No" option (typically don't require sponsorship)
                if (text.includes('no') || field.value === '0' || field.value.toLowerCase() === 'no') {
                    return { value: !needsSponsorship, confidence: 95, key: 'sponsorship_no' };
                }
                // Look for "Yes" option
                if (text.includes('yes') || field.value === '1' || field.value.toLowerCase() === 'yes') {
                    return { value: needsSponsorship, confidence: 95, key: 'sponsorship_yes' };
                }
            }
        }

        // Cover letter / message - use custom screening answers
        if (text.includes('cover letter') || text.includes('message to') || text.includes('why are you') || text.includes('why interested')) {
            const answer = data.custom_fields?.application_logistics?.screening_answers?.why_interested ||
                data.summary?.text ||
                "";
            return { value: answer, confidence: 70, key: 'cover_letter' };
        }

        // Why good fit / qualifications
        if (text.includes('good fit') || text.includes('qualified') || text.includes('qualifications') || text.includes('why you')) {
            const answer = data.custom_fields?.application_logistics?.screening_answers?.why_good_fit ||
                data.summary?.professional_statement ||
                "";
            return { value: answer, confidence: 70, key: 'why_good_fit' };
        }

        // Relocation - use custom_fields
        if (text.includes('relocate') || text.includes('relocation')) {
            if (fieldType === 'radio' || fieldType === 'checkbox') {
                const willingToRelocate = data.custom_fields?.application_logistics?.willing_to_relocate === 'yes';
                // Look for "Yes" option
                if (text.includes('yes') || field.value === '1' || field.value.toLowerCase() === 'yes') {
                    return { value: willingToRelocate, confidence: 80, key: 'relocate_yes' };
                }
                // Look for "No" option
                if (text.includes('no') || field.value === '0' || field.value.toLowerCase() === 'no') {
                    return { value: !willingToRelocate, confidence: 80, key: 'relocate_no' };
                }
            }
        }

        // Veteran status - use custom_fields (for diversity questions)
        if ((text.includes('veteran') || text.includes('protected veteran')) && (fieldType === 'select' || fieldType === 'radio')) {
            const veteranStatus = data.custom_fields?.eeo?.veteran_status || 'no';
            if (veteranStatus === 'no' && text.includes('not a protected veteran')) {
                return { value: true, confidence: 90, key: 'veteran_no' };
            }
            if (veteranStatus === 'yes' && text.includes('protected veteran')) {
                return { value: true, confidence: 90, key: 'veteran_yes' };
            }
            return { value: veteranStatus, confidence: 85, key: 'veteran_status' };
        }

        // Disability status - use custom_fields
        if (text.includes('disability') && (fieldType === 'select' || fieldType === 'radio')) {
            const disabilityStatus = data.custom_fields?.eeo?.disability_status || 'no';
            if (disabilityStatus === 'no' && (text.includes('do not have') || text.includes('not have'))) {
                return { value: true, confidence: 90, key: 'disability_no' };
            }
            if (disabilityStatus === 'yes' && text.includes('have a disability')) {
                return { value: true, confidence: 90, key: 'disability_yes' };
            }
            if (text.includes('not want to answer') || text.includes('prefer not')) {
                return { value: true, confidence: 85, key: 'disability_decline' };
            }
            return { value: disabilityStatus, confidence: 80, key: 'disability_status' };
        }

        // Gender - use custom_fields
        if (text.includes('gender') && (fieldType === 'select' || fieldType === 'radio')) {
            const gender = data.custom_fields?.eeo?.gender || 'male';
            if (text.includes('prefer not')) {
                return { value: true, confidence: 90, key: 'gender_decline' };
            }
            if (gender === 'male' && text.includes('male')) {
                return { value: true, confidence: 95, key: 'gender_male' };
            }
            if (gender === 'female' && text.includes('female')) {
                return { value: true, confidence: 95, key: 'gender_female' };
            }
            return { value: gender, confidence: 85, key: 'gender' };
        }

        // Race/Ethnicity - use custom_fields
        if ((text.includes('race') || text.includes('ethnicity')) && (fieldType === 'select' || fieldType === 'radio')) {
            const ethnicity = data.custom_fields?.eeo?.ethnicity || 'asian';
            if (text.includes('prefer not')) {
                return { value: true, confidence: 90, key: 'ethnicity_decline' };
            }
            if (ethnicity === 'asian' && text.includes('asian')) {
                return { value: true, confidence: 95, key: 'ethnicity_asian' };
            }
            return { value: ethnicity, confidence: 80, key: 'ethnicity' };
        }

        return { value: null, confidence: 0, key: null };
    }

    /**
     * Fill a single field with React support and verification
     */
    async fillField(field, value, data) {
        const fieldId = this.getFieldIdentifier(field);

        if (this.filledFields.has(fieldId)) {
            this.log(`Skipping already filled field: ${fieldId}`);
            return { success: true, skipped: true };
        }

        const text = this.extractFeatures(field);
        const match = this.findBestMatch(field, data);

        if (!match.value || match.confidence < this.config.confidenceThreshold) {
            this.log(`No match for field: "${text.substring(0, 50)}..." (confidence: ${match.confidence})`);
            return { success: false, skipped: true, reason: 'Low confidence' };
        }

        this.log(`Filling field: "${text.substring(0, 50)}..." with: ${match.key}`);

        try {
            const fieldType = field.type?.toLowerCase();

            // Handle radio buttons
            if (fieldType === 'radio') {
                if (match.value === true) {
                    field.click();
                    field.checked = true;
                    field.dispatchEvent(new Event('change', { bubbles: true }));
                    this.filledFields.add(fieldId);
                    return { success: true, method: 'radio' };
                }
                return { success: false, skipped: true };
            }

            // Handle checkboxes
            if (fieldType === 'checkbox') {
                if (match.value === true) {
                    field.click();
                    field.checked = true;
                    field.dispatchEvent(new Event('change', { bubbles: true }));
                    this.filledFields.add(fieldId);
                    return { success: true, method: 'checkbox' };
                }
                return { success: false, skipped: true };
            }

            // Handle select dropdowns
            if (field.tagName === 'SELECT') {
                const stringValue = String(match.value);
                const option = Array.from(field.options).find(opt =>
                    opt.text.toLowerCase().includes(stringValue.toLowerCase()) ||
                    opt.value.toLowerCase().includes(stringValue.toLowerCase())
                );

                if (option) {
                    field.value = option.value;
                    field.dispatchEvent(new Event('change', { bubbles: true }));
                    this.filledFields.add(fieldId);
                    return { success: true, method: 'select' };
                }
                return { success: false, reason: 'Option not found' };
            }

            // Handle combobox (if ComboboxHandler available)
            if (field.getAttribute('role') === 'combobox' && typeof ComboboxHandler !== 'undefined') {
                const result = await ComboboxHandler.fillCombobox(field, match.value, {
                    debug: this.config.debug
                });
                if (result.success) {
                    this.filledFields.add(fieldId);
                }
                return result;
            }

            // Handle regular text inputs with React support
            if (typeof ReactInputHelper !== 'undefined') {
                const result = await ReactInputHelper.fillWithVerification(field, match.value, {
                    maxRetries: this.config.maxRetries,
                    retryDelay: this.config.retryDelay
                });

                if (result.success) {
                    this.filledFields.add(fieldId);
                }
                return result;
            } else {
                // Fallback without React helper
                field.value = match.value;
                field.dispatchEvent(new Event('input', { bubbles: true }));
                field.dispatchEvent(new Event('change', { bubbles: true }));
                field.dispatchEvent(new Event('blur', { bubbles: true }));
                this.filledFields.add(fieldId);
                return { success: true, method: 'fallback' };
            }

        } catch (error) {
            this.log('Error filling field:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Perform autofill pass
     */
    async autofillPass(data, resumeFile, passNumber) {
        this.log(`Starting autofill pass ${passNumber}...`);

        const fields = this.detectFields();
        this.log(`Found ${fields.length} fields to process`);

        let filled = 0;
        let failed = 0;
        let skipped = 0;

        for (const field of fields) {
            const result = await this.fillField(field, null, data);

            if (result.success && !result.skipped) {
                filled++;
            } else if (result.skipped) {
                skipped++;
            } else {
                failed++;
            }

            // Small delay between fields
            await this.sleep(50);
        }

        this.log(`Pass ${passNumber} complete: ${filled} filled, ${failed} failed, ${skipped} skipped`);

        return { filled, failed, skipped, total: fields.length };
    }

    /**
     * Start mutation observer for dynamically added fields
     */
    startMutationObserver(data, resumeFile) {
        if (typeof MutationManager === 'undefined') {
            this.log('MutationManager not available');
            return;
        }

        this.log('Starting mutation observer...');

        MutationManager.start(
            async (newFields) => {
                this.log(`Mutation observer detected ${newFields.length} new fields`);

                for (const field of newFields) {
                    await this.fillField(field, null, data);
                    await this.sleep(50);
                }
            },
            {
                timeout: this.config.mutationObserverTimeout,
                debounceDelay: 500,
                debug: this.config.debug
            }
        );
    }

    getFieldIdentifier(field) {
        return field.id || field.name || field.getAttribute('data-testid') || field.outerHTML.substring(0, 100);
    }

    async execute(normalizedData, resumeFile = null) {
        this.log('Starting SmartRecruiters strategy...');
        this.filledFields.clear();

        try {
            // Wait for form to stabilize
            const formReady = await this.waitForFormStabilization();
            if (!formReady) {
                this.log('Form did not stabilize, proceeding anyway...');
            }

            // First pass
            const firstPass = await this.autofillPass(normalizedData, resumeFile, 1);

            // Wait for potential dynamic fields
            await this.sleep(this.config.secondPassDelay);

            // Second pass
            const secondPass = await this.autofillPass(normalizedData, resumeFile, 2);

            // Start mutation observer
            this.startMutationObserver(normalizedData, resumeFile);

            const totalFilled = firstPass.filled + secondPass.filled;
            const totalAttempted = firstPass.total + secondPass.total - secondPass.skipped;

            this.log(`Strategy complete: ${totalFilled}/${totalAttempted} fields filled`);

            return {
                filled: totalFilled,
                attempted: totalAttempted,
                success: totalFilled > 0
            };

        } catch (error) {
            console.error('[SmartRecruiters] Strategy error:', error);
            throw error;
        }
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('smartrecruiters.com'),
        SmartRecruitersStrategy
    );
}
