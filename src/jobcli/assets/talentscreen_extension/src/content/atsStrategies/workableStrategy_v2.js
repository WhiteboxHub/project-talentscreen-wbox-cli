/**
 * Workable Strategy v2
 * Production-quality autofill for Workable ATS with React support
 * @version 2.0.0
 */

class WorkableStrategyV2 extends GenericStrategy {
    constructor() {
        super();

        // Configuration
        this.config = {
            confidenceThreshold: 50, // Lower for Workable's inconsistent labels
            maxRetries: 3,
            retryDelay: 150,
            formStabilizationWait: 2000,
            formStabilizationCheckInterval: 200,
            minFieldsThreshold: 5, // Minimum fields to consider form ready
            mutationObserverTimeout: 30000,
            secondPassDelay: 2000, // Wait before second pass
            debug: false // Enable via localStorage.setItem('workable_debug', 'true')
        };

        // State
        this.filledFields = new Set();
        this.attemptedFields = new Set();
        this.passNumber = 0;

        // Check debug mode
        if (typeof localStorage !== 'undefined' && localStorage.getItem('workable_debug') === 'true') {
            this.config.debug = true;
        }
    }

    /**
     * Main execution method
     * @param {Object} normalizedData - Resume data
     * @param {Object} resumeFile - Resume file
     * @returns {Promise<Object>} Results
     */
    async execute(normalizedData, resumeFile = null) {
        const startTime = Date.now();

        if (!normalizedData) {
            console.error('[WorkableV2] No resume data provided');
            return this.createErrorResult('No resume data');
        }

        this.log('=== Starting Workable Autofill ===');

        // Start telemetry session
        if (window.AutofillTelemetry) {
            window.AutofillTelemetry.startSession({
                atsType: 'workable',
                strategy: 'v2'
            });
        }

        try {
            // Step 1: Wait for form stabilization
            this.log('Step 1: Waiting for form stabilization...');
            const formReady = await this.waitForFormStabilization();

            if (!formReady) {
                this.log('Form did not stabilize in time', 'warn');
                return this.createErrorResult('Form not ready');
            }

            // Step 2: First autofill pass
            this.log('Step 2: Starting first autofill pass...');
            const firstPassResult = await this.autofillPass(normalizedData, resumeFile, 1);

            // Step 3: Wait for dynamic fields
            this.log(`Step 3: Waiting ${this.config.secondPassDelay}ms for dynamic fields...`);
            await this.sleep(this.config.secondPassDelay);

            // Step 4: Second autofill pass
            this.log('Step 4: Starting second autofill pass...');
            const secondPassResult = await this.autofillPass(normalizedData, resumeFile, 2);

            // Step 5: Start mutation observer for late-appearing fields
            this.log('Step 5: Starting mutation observer...');
            this.startMutationObserver(normalizedData, resumeFile);

            // Calculate totals
            const totalFilled = firstPassResult.filled + secondPassResult.filled;
            const totalAttempted = firstPassResult.attempted + secondPassResult.attempted;
            const totalFailed = firstPassResult.failed + secondPassResult.failed;

            const result = {
                success: true,
                filled: totalFilled,
                attempted: totalAttempted,
                failed: totalFailed,
                passes: 2,
                duration: Date.now() - startTime
            };

            this.log(`=== Autofill Complete: ${totalFilled}/${totalAttempted} fields ===`);

            // End telemetry
            if (window.AutofillTelemetry) {
                const summary = window.AutofillTelemetry.endSession();
                if (this.config.debug && summary) {
                    window.AutofillTelemetry.logSummary();
                }
            }

            return result;

        } catch (error) {
            this.log('Fatal error: ' + error.message, 'error');

            if (window.AutofillTelemetry) {
                window.AutofillTelemetry.trackError(error);
                window.AutofillTelemetry.endSession();
            }

            return this.createErrorResult(error.message);
        }
    }

    /**
     * Wait for form to stabilize (React rendering complete)
     * @returns {Promise<boolean>}
     */
    async waitForFormStabilization() {
        const startTime = Date.now();
        const timeout = this.config.formStabilizationWait;
        const checkInterval = this.config.formStabilizationCheckInterval;

        let previousFieldCount = 0;
        let stableChecks = 0;
        const requiredStableChecks = 3; // Need 3 consecutive stable checks

        while (Date.now() - startTime < timeout) {
            const fields = this.detectAllFormFields();
            const currentFieldCount = fields.length;

            this.log(`Field count: ${currentFieldCount} (previous: ${previousFieldCount})`);

            // Check if count is stable
            if (currentFieldCount === previousFieldCount && currentFieldCount >= this.config.minFieldsThreshold) {
                stableChecks++;

                if (stableChecks >= requiredStableChecks) {
                    this.log(`Form stabilized with ${currentFieldCount} fields`);
                    return true;
                }
            } else {
                stableChecks = 0;
            }

            previousFieldCount = currentFieldCount;
            await this.sleep(checkInterval);
        }

        // Timeout reached
        const fields = this.detectAllFormFields();
        this.log(`Timeout reached. Found ${fields.length} fields`, 'warn');

        return fields.length >= this.config.minFieldsThreshold;
    }

    /**
     * Detect all form fields
     * @returns {Array<HTMLElement>}
     */
    detectAllFormFields() {
        const selectors = [
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"])',
            'textarea',
            'select',
            '[role="combobox"]',
            '[role="textbox"]',
            '[contenteditable="true"]'
        ];

        const elements = document.querySelectorAll(selectors.join(','));
        return Array.from(elements).filter(el => {
            // Filter out invisible fields
            return el.offsetParent !== null && !el.disabled;
        });
    }

    /**
     * Perform one autofill pass
     * @param {Object} normalizedData - Resume data
     * @param {Object} resumeFile - Resume file
     * @param {number} passNumber - Pass number
     * @returns {Promise<Object>}
     */
    async autofillPass(normalizedData, resumeFile, passNumber) {
        this.passNumber = passNumber;
        this.log(`--- Pass ${passNumber} ---`);

        const passStartTime = Date.now();
        const fields = this.detectAllFormFields();

        this.log(`Detected ${fields.length} fields`);

        if (window.AutofillTelemetry && passNumber === 1) {
            window.AutofillTelemetry.trackFieldsFound(fields.length);
        }

        let filled = 0;
        let attempted = 0;
        let failed = 0;

        for (const field of fields) {
            const fieldId = this.getFieldIdentifier(field);

            // Skip already filled fields
            if (this.filledFields.has(fieldId)) {
                continue;
            }

            // Mark as attempted
            this.attemptedFields.add(fieldId);
            attempted++;

            // Extract features and match value
            const features = this.extractEnhancedFeatures(field);
            const match = this.findBestMatch(features, normalizedData);

            if (!match || !match.value) {
                this.log(`Skipping field (no match): ${features.label}`, 'debug');
                continue;
            }

            if (match.confidence < this.config.confidenceThreshold) {
                this.log(`Skipping field (low confidence ${match.confidence}): ${features.label}`, 'debug');
                continue;
            }

            // Attempt to fill
            const fillStartTime = Date.now();
            const fillResult = await this.fillFieldWithVerification(field, match.value, features);
            const fillDuration = Date.now() - fillStartTime;

            // Track in telemetry
            if (window.AutofillTelemetry) {
                window.AutofillTelemetry.trackFieldAttempt({
                    selector: this.getFieldSelector(field),
                    label: features.label,
                    detectedType: features.fieldType,
                    matchedKey: match.key,
                    confidenceScore: match.confidence,
                    value: match.value,
                    success: fillResult.success,
                    failureReason: fillResult.error,
                    retryCount: fillResult.attempts - 1,
                    fillDuration,
                    sensitive: features.isSensitive
                });
            }

            if (fillResult.success) {
                this.filledFields.add(fieldId);
                filled++;
                this.log(`✓ Filled: ${features.label} = ${match.value}`, 'success');
            } else {
                failed++;
                this.log(`✗ Failed: ${features.label} - ${fillResult.error}`, 'error');
            }

            // Small delay between fields
            await this.sleep(50);
        }

        const passResult = {
            filled,
            attempted,
            failed,
            duration: Date.now() - passStartTime
        };

        // Track pass in telemetry
        if (window.AutofillTelemetry) {
            window.AutofillTelemetry.trackPass({
                passNumber,
                fieldsAttempted: attempted,
                fieldsSuccessful: filled,
                fieldsFailed: failed,
                duration: passResult.duration
            });
        }

        this.log(`Pass ${passNumber} complete: ${filled} filled, ${failed} failed`);

        return passResult;
    }

    /**
     * Fill field with verification and retry
     * @param {HTMLElement} field - Field element
     * @param {string|number} value - Value to fill
     * @param {Object} features - Field features
     * @returns {Promise<Object>}
     */
    async fillFieldWithVerification(field, value, features) {
        // Handle combobox/autocomplete fields
        if (features.isCombobox) {
            return this.fillComboboxField(field, value);
        }

        // Handle regular inputs with React support
        if (window.ReactInputHelper) {
            return await window.ReactInputHelper.fillWithVerification(field, value, {
                maxRetries: this.config.maxRetries,
                retryDelay: this.config.retryDelay,
                verificationDelay: 50
            });
        }

        // Fallback to basic fill
        return this.basicFillWithRetry(field, value);
    }

    /**
     * Fill combobox field
     * @param {HTMLElement} field - Combobox element
     * @param {string} value - Value to select
     * @returns {Promise<Object>}
     */
    async fillComboboxField(field, value) {
        if (window.ComboboxHandler) {
            return await window.ComboboxHandler.fillCombobox(field, value, {
                debug: this.config.debug
            });
        }

        // Fallback
        return this.basicFillWithRetry(field, value);
    }

    /**
     * Basic fill with retry (fallback)
     * @param {HTMLElement} field - Field element
     * @param {string|number} value - Value to fill
     * @returns {Promise<Object>}
     */
    async basicFillWithRetry(field, value) {
        const result = {
            success: false,
            attempts: 0,
            error: null
        };

        for (let i = 0; i < this.config.maxRetries; i++) {
            result.attempts++;

            try {
                field.value = String(value);
                field.dispatchEvent(new Event('input', { bubbles: true }));
                field.dispatchEvent(new Event('change', { bubbles: true }));

                await this.sleep(this.config.retryDelay);

                // Verify
                if (field.value === String(value)) {
                    result.success = true;
                    return result;
                }
            } catch (error) {
                result.error = error.message;
            }
        }

        result.error = result.error || 'Value did not persist';
        return result;
    }

    /**
     * Extract enhanced features from field
     * @param {HTMLElement} field - Field element
     * @returns {Object}
     */
    extractEnhancedFeatures(field) {
        const label = this.extractLabel(field);
        const placeholder = field.placeholder || '';
        const name = field.name || '';
        const id = field.id || '';
        const ariaLabel = field.getAttribute('aria-label') || '';
        const testId = field.getAttribute('data-testid') || '';
        const automationId = field.getAttribute('data-automation-id') || '';
        const autocomplete = field.getAttribute('autocomplete') || '';
        const role = field.getAttribute('role') || '';
        const fieldType = field.type || field.tagName.toLowerCase();

        // Combine all text features
        const combinedText = [
            label,
            ariaLabel,
            placeholder,
            name,
            id,
            testId,
            automationId,
            autocomplete
        ].join(' ').toLowerCase();

        // Detect if combobox
        const isCombobox = (
            role === 'combobox' ||
            field.getAttribute('aria-autocomplete') === 'list' ||
            fieldType === 'combobox'
        );

        return {
            element: field,
            label,
            placeholder,
            name,
            id,
            ariaLabel,
            testId,
            automationId,
            autocomplete,
            role,
            fieldType,
            combinedText,
            isCombobox,
            isSensitive: this.isSensitiveField(combinedText)
        };
    }

    /**
     * Extract label for field
     * @param {HTMLElement} field - Field element
     * @returns {string}
     */
    extractLabel(field) {
        // Try associated label
        if (field.id) {
            const label = document.querySelector(`label[for="${field.id}"]`);
            if (label) return label.textContent.trim();
        }

        // Try parent label
        const parentLabel = field.closest('label');
        if (parentLabel) return parentLabel.textContent.trim();

        // Try aria-label
        const ariaLabel = field.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel.trim();

        // Try preceding label-like element
        let prev = field.previousElementSibling;
        while (prev) {
            if (prev.tagName === 'LABEL' || prev.classList.contains('label')) {
                return prev.textContent.trim();
            }
            if (prev.matches('div, span') && prev.textContent.trim().length < 100) {
                return prev.textContent.trim();
            }
            prev = prev.previousElementSibling;
        }

        return field.placeholder || field.name || 'Unknown';
    }

    /**
     * Find best match for field
     * @param {Object} features - Field features
     * @param {Object} data - Resume data
     * @returns {Object|null}
     */
    findBestMatch(features, data) {
        const text = features.combinedText;

        // Identity fields
        if (text.includes('first') && text.includes('name')) {
            return { value: data.identity?.first_name, confidence: 100, key: 'first_name' };
        }
        if (text.includes('last') && text.includes('name')) {
            return { value: data.identity?.last_name, confidence: 100, key: 'last_name' };
        }
        if (text.includes('full') && text.includes('name') || text === 'name') {
            return { value: data.identity?.full_name, confidence: 95, key: 'full_name' };
        }

        // Contact fields
        if (text.includes('email')) {
            return { value: data.contact?.email, confidence: 100, key: 'email' };
        }
        if (text.includes('phone') || text.includes('mobile') || text.includes('telephone')) {
            return { value: data.contact?.phone, confidence: 100, key: 'phone' };
        }

        // Location fields
        if (text.includes('city') || text.includes('town')) {
            return { value: data.contact?.city || data.location?.city, confidence: 90, key: 'city' };
        }
        if (text.includes('state') || text.includes('region') || text.includes('province')) {
            return { value: data.contact?.state || data.location?.region, confidence: 90, key: 'state' };
        }
        if (text.includes('country')) {
            return { value: data.contact?.country || data.location?.country, confidence: 90, key: 'country' };
        }
        if (text.includes('postal') || text.includes('zip')) {
            return { value: data.contact?.postal_code, confidence: 85, key: 'postal_code' };
        }
        if (text.includes('address') && !text.includes('email')) {
            return { value: data.contact?.address, confidence: 80, key: 'address' };
        }

        // LinkedIn
        if (text.includes('linkedin')) {
            return { value: data.contact?.linkedin, confidence: 95, key: 'linkedin' };
        }

        // Website
        if (text.includes('website') || text.includes('portfolio') || text.includes('url')) {
            return { value: data.contact?.website, confidence: 85, key: 'website' };
        }

        // Professional summary
        if (text.includes('summary') || text.includes('about') || text.includes('bio')) {
            return { value: data.summary?.text, confidence: 70, key: 'summary' };
        }

        // No match
        return null;
    }

    /**
     * Start mutation observer for dynamic fields
     * @param {Object} normalizedData - Resume data
     * @param {Object} resumeFile - Resume file
     */
    startMutationObserver(normalizedData, resumeFile) {
        if (!window.MutationManager) {
            this.log('MutationManager not available', 'warn');
            return;
        }

        window.MutationManager.start(
            (newFields) => {
                this.log(`Mutation observer detected ${newFields.length} new fields`);
                this.handleNewFields(newFields, normalizedData, resumeFile);
            },
            {
                timeout: this.config.mutationObserverTimeout,
                debounceDelay: 500,
                debug: this.config.debug
            }
        );
    }

    /**
     * Handle newly detected fields
     * @param {Array<HTMLElement>} fields - New fields
     * @param {Object} normalizedData - Resume data
     * @param {Object} resumeFile - Resume file
     */
    async handleNewFields(fields, normalizedData, resumeFile) {
        let filled = 0;

        for (const field of fields) {
            const fieldId = this.getFieldIdentifier(field);

            if (this.filledFields.has(fieldId)) {
                continue;
            }

            const features = this.extractEnhancedFeatures(field);
            const match = this.findBestMatch(features, normalizedData);

            if (!match || !match.value || match.confidence < this.config.confidenceThreshold) {
                continue;
            }

            const fillResult = await this.fillFieldWithVerification(field, match.value, features);

            if (fillResult.success) {
                this.filledFields.add(fieldId);
                filled++;
                this.log(`✓ Filled (mutation): ${features.label}`);
            }

            await this.sleep(50);
        }

        this.log(`Mutation handler filled ${filled} fields`);
    }

    /**
     * Get field identifier
     * @param {HTMLElement} field - Field element
     * @returns {string}
     */
    getFieldIdentifier(field) {
        return (
            field.id ||
            field.name ||
            field.getAttribute('data-testid') ||
            field.getAttribute('data-automation-id') ||
            this.getFieldSelector(field)
        );
    }

    /**
     * Get CSS selector for field
     * @param {HTMLElement} field - Field element
     * @returns {string}
     */
    getFieldSelector(field) {
        if (field.id) return `#${field.id}`;
        if (field.name) return `[name="${field.name}"]`;

        const tag = field.tagName.toLowerCase();
        const className = field.className ? `.${field.className.split(' ')[0]}` : '';
        return `${tag}${className}`;
    }

    /**
     * Check if field is sensitive
     * @param {string} text - Combined field text
     * @returns {boolean}
     */
    isSensitiveField(text) {
        const sensitive = ['password', 'ssn', 'social security', 'credit card', 'cvv', 'pin'];
        return sensitive.some(s => text.includes(s));
    }

    /**
     * Create error result
     * @param {string} message - Error message
     * @returns {Object}
     */
    createErrorResult(message) {
        return {
            success: false,
            filled: 0,
            attempted: 0,
            failed: 0,
            error: message
        };
    }

    /**
     * Sleep utility
     * @param {number} ms - Milliseconds
     * @returns {Promise}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Logging utility
     * @param {string} message - Message to log
     * @param {string} level - Log level
     */
    log(message, level = 'info') {
        if (!this.config.debug) return;

        const prefix = '[WorkableV2]';
        const styles = {
            info: 'color: #00D9A5',
            success: 'color: #10b981',
            warn: 'color: #f59e0b',
            error: 'color: #ef4444',
            debug: 'color: #6b7280'
        };

        console.log(`%c${prefix} ${message}`, styles[level] || '');
    }
}

// Register strategy
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('workable.com'),
        WorkableStrategyV2
    );

    console.log('[WorkableV2] Strategy registered');
}
