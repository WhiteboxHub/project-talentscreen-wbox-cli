/**
 * TalentScreen - Public Autofill API
 * Exposes clean API for CLI/Playwright integration
 * @version 2.0.0
 */

(function() {
    'use strict';

    const AutofillAPI = {
        version: '2.0.0',
        schemaVersion: '1.0',

        // Internal state
        _currentProfile: null,
        _currentSession: null,
        _lastResult: null,
        _settings: {
            dryRun: false,
            confidenceThreshold: 0.6, // balanced
            fillEEO: false, // require explicit opt-in
            fillLegal: false, // require explicit opt-in
            fillSensitive: false,
            autoSubmit: false,
            pauseOnLowConfidence: true,
            pauseOnMissingData: true,
            pauseOnCAPTCHA: true,
            preserveUserValues: true // don't overwrite user-entered values
        },
        _customMappings: {},
        _filledFields: new Set(), // for idempotency

        /**
         * Get current page context
         */
        getPageContext() {
            return {
                url: window.location.href,
                title: document.title,
                atsType: this._detectATSType(),
                company: this._extractCompany(),
                jobTitle: this._extractJobTitle(),
                formSections: this._detectFormSections(),
                hasMultipleSteps: this._detectMultiStep(),
                hasCAPTCHA: this._detectCAPTCHA(),
                timestamp: new Date().toISOString()
            };
        },

        /**
         * Get all detected form fields
         */
        getFields() {
            const fields = [];
            const formElements = document.querySelectorAll('input, select, textarea');

            formElements.forEach((elem, index) => {
                if (elem.type === 'hidden' || elem.type === 'submit' || elem.type === 'button') {
                    return;
                }

                const field = {
                    id: this._generateFieldId(elem),
                    index: index,
                    label: this._extractLabel(elem),
                    type: elem.type || elem.tagName.toLowerCase(),
                    name: elem.name || '',
                    required: elem.required || elem.hasAttribute('required'),
                    value: elem.value || '',
                    placeholder: elem.placeholder || '',
                    options: this._getSelectOptions(elem),
                    confidence: 0,
                    matchedPath: null,
                    category: this._categorizeField(elem),
                    isSensitive: this._isSensitiveField(elem),
                    isEEO: this._isEEOField(elem),
                    isLegal: this._isLegalField(elem),
                    selector: this._getSelector(elem),
                    visible: this._isVisible(elem),
                    disabled: elem.disabled,
                    readonly: elem.readOnly
                };

                fields.push(field);
            });

            return fields;
        },

        /**
         * Dry run - show what would be filled without actually filling
         */
        async dryRun(profile, options = {}) {
            this._currentProfile = this._validateAndNormalize(profile);
            this._applyOptions(options);

            const fields = this.getFields();
            const results = {
                mode: 'dry_run',
                context: this.getPageContext(),
                fields: {
                    total: fields.length,
                    willFill: [],
                    willSkip: [],
                    needsReview: [],
                    blocked: []
                },
                warnings: [],
                errors: []
            };

            for (const field of fields) {
                const match = await this._findMatchForField(field, this._currentProfile);

                if (!match.value) {
                    results.fields.willSkip.push({
                        field: field.label,
                        reason: 'no_data_available',
                        category: field.category
                    });
                } else if (this._shouldBlockField(field, match)) {
                    results.fields.blocked.push({
                        field: field.label,
                        reason: this._getBlockReason(field),
                        category: field.category
                    });
                } else if (match.confidence < this._settings.confidenceThreshold) {
                    results.fields.needsReview.push({
                        field: field.label,
                        value: match.value,
                        confidence: match.confidence,
                        reason: 'low_confidence',
                        category: field.category
                    });
                } else {
                    results.fields.willFill.push({
                        field: field.label,
                        value: this._sanitizeValue(match.value, field.isSensitive),
                        confidence: match.confidence,
                        source: match.source,
                        category: field.category
                    });
                }
            }

            // Add warnings
            if (results.fields.blocked.length > 0) {
                results.warnings.push(`${results.fields.blocked.length} fields blocked by settings (EEO/Legal/Sensitive)`);
            }
            if (results.fields.needsReview.length > 0) {
                results.warnings.push(`${results.fields.needsReview.length} fields need manual review (low confidence)`);
            }
            if (results.fields.willSkip.length > 0) {
                results.warnings.push(`${results.fields.willSkip.length} fields will be skipped (no data)`);
            }

            this._lastResult = results;
            return results;
        },

        /**
         * Fill form with profile data
         */
        async fill(profile, options = {}) {
            if (options.dryRun) {
                return this.dryRun(profile, options);
            }

            this._currentProfile = this._validateAndNormalize(profile);
            this._applyOptions(options);

            // Start tracking session
            if (window.TrackingIntegration) {
                window.TrackingIntegration.init(this.getPageContext().atsType, null);
            }

            const fields = this.getFields();
            const results = {
                mode: 'fill',
                context: this.getPageContext(),
                fields: {
                    total: fields.length,
                    filled: [],
                    skipped: [],
                    failed: [],
                    needsReview: []
                },
                warnings: [],
                errors: [],
                timestamp: new Date().toISOString()
            };

            for (const field of fields) {
                const element = this._findElement(field.selector);
                if (!element) {
                    results.fields.failed.push({
                        field: field.label,
                        reason: 'element_not_found',
                        category: field.category
                    });
                    continue;
                }

                // Check idempotency - skip if already filled
                if (this._filledFields.has(field.id)) {
                    results.fields.skipped.push({
                        field: field.label,
                        reason: 'already_filled',
                        category: field.category
                    });
                    continue;
                }

                const match = await this._findMatchForField(field, this._currentProfile);

                // Track field
                if (window.TrackingIntegration) {
                    window.TrackingIntegration.trackField(element, field.label, field.type, {
                        confidence: match.confidence
                    });
                }

                if (!match.value) {
                    results.fields.skipped.push({
                        field: field.label,
                        reason: 'no_data',
                        category: field.category
                    });
                    if (window.TrackingIntegration) {
                        window.TrackingIntegration.trackSkipped(element, 'no_data');
                    }
                    continue;
                }

                if (this._shouldBlockField(field, match)) {
                    results.fields.skipped.push({
                        field: field.label,
                        reason: this._getBlockReason(field),
                        category: field.category
                    });
                    if (window.TrackingIntegration) {
                        window.TrackingIntegration.trackSkipped(element, this._getBlockReason(field));
                    }
                    continue;
                }

                if (match.confidence < this._settings.confidenceThreshold) {
                    results.fields.needsReview.push({
                        field: field.label,
                        value: this._sanitizeValue(match.value, field.isSensitive),
                        confidence: match.confidence,
                        reason: 'low_confidence',
                        category: field.category
                    });
                    if (window.TrackingIntegration) {
                        window.TrackingIntegration.trackNeedsReview(element, 'low_confidence');
                    }

                    if (this._settings.pauseOnLowConfidence) {
                        results.warnings.push(`Paused at field "${field.label}" due to low confidence`);
                        break;
                    }
                    continue;
                }

                // Fill the field
                try {
                    await this._fillField(element, match.value, field.type);

                    results.fields.filled.push({
                        field: field.label,
                        value: this._sanitizeValue(match.value, field.isSensitive),
                        confidence: match.confidence,
                        source: match.source,
                        category: field.category
                    });

                    // Mark as filled for idempotency
                    this._filledFields.add(field.id);

                    if (window.TrackingIntegration) {
                        window.TrackingIntegration.trackFilled(element, match.value, match.source);
                    }

                } catch (error) {
                    results.fields.failed.push({
                        field: field.label,
                        reason: error.message,
                        category: field.category
                    });
                    results.errors.push(`Failed to fill "${field.label}": ${error.message}`);

                    if (window.TrackingIntegration) {
                        window.TrackingIntegration.trackFailed(element, error.message);
                    }
                }
            }

            // Calculate completion
            results.completion = {
                percentage: Math.round((results.fields.filled.length / results.fields.total) * 100),
                filled: results.fields.filled.length,
                total: results.fields.total
            };

            this._lastResult = results;

            // End tracking session
            if (window.TrackingIntegration) {
                const status = results.errors.length > 0 ? 'partial' : 'completed';
                window.TrackingIntegration.endSession(status);
            }

            return results;
        },

        /**
         * Get last fill result
         */
        getResult() {
            return this._lastResult;
        },

        /**
         * Clear current session and state
         */
        clearSession() {
            this._currentProfile = null;
            this._currentSession = null;
            this._lastResult = null;
            this._filledFields.clear();

            if (window.TrackingIntegration && window.TrackingIntegration.initialized) {
                window.TrackingIntegration.endSession('cleared');
            }

            return { success: true, message: 'Session cleared' };
        },

        /**
         * Set custom field mappings
         */
        setCustomMappings(mappings) {
            this._customMappings = { ...this._customMappings, ...mappings };
            return { success: true, count: Object.keys(this._customMappings).length };
        },

        /**
         * Get custom mappings
         */
        getCustomMappings() {
            return { ...this._customMappings };
        },

        /**
         * Configure settings
         */
        configure(settings) {
            this._settings = { ...this._settings, ...settings };
            return { success: true, settings: { ...this._settings } };
        },

        /**
         * Get current configuration
         */
        getConfiguration() {
            return { ...this._settings };
        },

        /**
         * Inject profile data directly (bypasses sidepanel upload)
         */
        injectProfile(profile) {
            try {
                const validated = this._validateAndNormalize(profile);
                this._currentProfile = validated;

                // Also save to chrome.storage for sidepanel access
                if (typeof chrome !== 'undefined' && chrome.storage) {
                    const normalized = window.ResumeProcessor.normalize(validated);
                    chrome.storage.local.set({
                        resumeData: validated,
                        normalizedData: normalized
                    });
                }

                return {
                    success: true,
                    message: 'Profile injected successfully',
                    schemaVersion: validated.schema_version || 'unknown'
                };
            } catch (error) {
                return {
                    success: false,
                    error: error.message,
                    validationErrors: error.validationErrors || []
                };
            }
        },

        /**
         * Get current profile
         */
        getProfile() {
            return this._currentProfile ? { ...this._currentProfile } : null;
        },

        /**
         * Detect multi-step form and get navigation
         */
        detectMultiStep() {
            const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
            const nextButtons = buttons.filter(btn => {
                const text = (btn.textContent || btn.value || '').toLowerCase();
                return text.includes('next') || text.includes('continue') || text.includes('proceed');
            });

            const prevButtons = buttons.filter(btn => {
                const text = (btn.textContent || btn.value || '').toLowerCase();
                return text.includes('previous') || text.includes('back');
            });

            return {
                isMultiStep: nextButtons.length > 0,
                currentStep: this._detectCurrentStep(),
                totalSteps: this._detectTotalSteps(),
                navigation: {
                    next: nextButtons.length > 0 ? this._getSelector(nextButtons[0]) : null,
                    previous: prevButtons.length > 0 ? this._getSelector(prevButtons[0]) : null,
                    submit: this._findSubmitButton()
                }
            };
        },

        /**
         * Export run report for CLI
         */
        exportReport() {
            const context = this.getPageContext();
            const result = this._lastResult;

            return {
                version: this.version,
                timestamp: new Date().toISOString(),
                application: {
                    company: context.company,
                    jobTitle: context.jobTitle,
                    url: context.url,
                    atsType: context.atsType
                },
                results: result ? {
                    mode: result.mode,
                    fieldsTotal: result.fields.total,
                    fieldsFilled: result.fields.filled?.length || 0,
                    fieldsSkipped: result.fields.skipped?.length || 0,
                    fieldsFailed: result.fields.failed?.length || 0,
                    fieldsNeedingReview: result.fields.needsReview?.length || 0,
                    completion: result.completion,
                    warnings: result.warnings,
                    errors: result.errors
                } : null,
                tracking: window.FormTracker ? window.FormTracker.exportSessionData() : null
            };
        },

        /**
         * Phase 5: Retry failed fields
         * @returns {Promise<Object>} Retry results
         */
        async retryFailed() {
            if (!window.FormTracker) {
                return {
                    success: false,
                    error: 'FormTracker not available'
                };
            }

            const failedFields = window.FormTracker.getFailures();
            if (failedFields.length === 0) {
                return {
                    success: true,
                    message: 'No failed fields to retry',
                    total: 0,
                    succeeded: 0,
                    failed: 0,
                    fields: []
                };
            }

            const results = {
                success: true,
                total: failedFields.length,
                succeeded: 0,
                failed: 0,
                fields: []
            };

            for (const field of failedFields) {
                try {
                    const element = document.querySelector(field.selector);
                    if (!element) {
                        results.fields.push({
                            ...field,
                            status: 'failed',
                            error: 'Element not found'
                        });
                        results.failed++;
                        continue;
                    }

                    // Retry filling
                    await this._fillField(element, field.value, field.type);

                    results.fields.push({
                        ...field,
                        status: 'success'
                    });
                    results.succeeded++;

                    // Update tracker
                    window.FormTracker.markFilled(element, field.value, 'retry');

                } catch (error) {
                    results.fields.push({
                        ...field,
                        status: 'failed',
                        error: error.message
                    });
                    results.failed++;
                }
            }

            return results;
        },

        /**
         * Phase 5: Get performance metrics
         * @returns {Object} Performance data
         */
        getPerformanceMetrics() {
            const result = this._lastResult;
            if (!result) {
                return {
                    available: false,
                    message: 'No autofill session available'
                };
            }

            const session = window.FormTracker ? window.FormTracker.getCurrentSession() : null;

            return {
                available: true,
                autofill: {
                    totalFields: result.fields.total || 0,
                    filled: result.fields.filled?.length || 0,
                    skipped: result.fields.skipped?.length || 0,
                    failed: result.fields.failed?.length || 0,
                    successRate: result.fields.total > 0
                        ? Math.round((result.fields.filled?.length || 0) / result.fields.total * 100)
                        : 0,
                    completionPercentage: result.completion?.percentage || 0
                },
                timing: session ? {
                    startedAt: session.startedAt,
                    endedAt: session.endedAt,
                    duration: session.endedAt && session.startedAt
                        ? new Date(session.endedAt) - new Date(session.startedAt)
                        : null
                } : null,
                errors: {
                    count: result.errors?.length || 0,
                    messages: result.errors || []
                },
                warnings: {
                    count: result.warnings?.length || 0,
                    messages: result.warnings || []
                }
            };
        },

        /**
         * Phase 5: Get field statistics
         * @returns {Object} Field statistics
         */
        getFieldStatistics() {
            const fields = this.getFields();

            const stats = {
                total: fields.length,
                byType: {},
                byCategory: {},
                byStatus: {
                    visible: 0,
                    hidden: 0,
                    disabled: 0,
                    readonly: 0,
                    required: 0
                },
                sensitive: {
                    eeo: 0,
                    legal: 0,
                    sensitive: 0
                }
            };

            fields.forEach(field => {
                // Count by type
                stats.byType[field.type] = (stats.byType[field.type] || 0) + 1;

                // Count by category
                stats.byCategory[field.category] = (stats.byCategory[field.category] || 0) + 1;

                // Count by status
                if (field.visible) stats.byStatus.visible++;
                if (!field.visible) stats.byStatus.hidden++;
                if (field.disabled) stats.byStatus.disabled++;
                if (field.readonly) stats.byStatus.readonly++;
                if (field.required) stats.byStatus.required++;

                // Count sensitive fields
                if (field.isEEO) stats.sensitive.eeo++;
                if (field.isLegal) stats.sensitive.legal++;
                if (field.isSensitive) stats.sensitive.sensitive++;
            });

            return stats;
        },

        /**
         * Phase 5: Enhanced fill with options
         * @param {Object} profile - Resume data
         * @param {Object} options - Enhanced options
         * @returns {Promise<Object>} Fill results
         */
        async fillEnhanced(profile, options = {}) {
            // Merge with enhanced options
            const enhancedOptions = {
                ...options,
                resumeFile: options.resumeFile || null,
                overwriteExisting: options.overwriteExisting || false,
                autoContinueOnNextPage: options.autoContinueOnNextPage || false,
                pauseOnCaptcha: options.pauseOnCaptcha !== false,
                performanceMode: options.performanceMode || 'balanced' // 'fast' | 'balanced' | 'careful'
            };

            // Set performance-based delay
            const delayMap = {
                fast: 50,
                balanced: 100,
                careful: 200
            };
            this._settings.delay = delayMap[enhancedOptions.performanceMode] || 100;

            // Override user value preservation if specified
            if (enhancedOptions.overwriteExisting) {
                this._settings.preserveUserValues = false;
            }

            // Check for CAPTCHA if enabled
            if (enhancedOptions.pauseOnCaptcha && window.CaptchaDetector) {
                const captchaStatus = window.CaptchaDetector.getStatus();
                if (captchaStatus.present && !captchaStatus.solved) {
                    return {
                        success: false,
                        error: 'CAPTCHA detected and not solved',
                        captcha: captchaStatus,
                        message: 'Please complete the CAPTCHA before continuing'
                    };
                }
            }

            // Store resume file if provided
            if (enhancedOptions.resumeFile && typeof chrome !== 'undefined' && chrome.storage) {
                await chrome.storage.local.set({ resumeFile: enhancedOptions.resumeFile });
            }

            // Execute standard fill
            const result = await this.fill(profile, enhancedOptions);

            // Set up auto-continue if enabled
            if (enhancedOptions.autoContinueOnNextPage && window.DynamicFormWatcher) {
                document.addEventListener('pageChanged', async () => {
                    console.log('[AutofillAPI] Auto-continuing on next page...');
                    setTimeout(() => {
                        this.fill(profile, enhancedOptions);
                    }, 1000);
                }, { once: true });
            }

            return result;
        },

        // === INTERNAL HELPERS ===

        _validateAndNormalize(profile) {
            if (!profile) {
                throw new Error('Profile data is required');
            }

            // Check schema version
            if (!profile.schema_version) {
                profile.schema_version = this.schemaVersion;
            }

            // Validate basics
            if (!profile.basics) {
                throw new Error('Profile must contain "basics" section');
            }

            const errors = [];

            // Required fields
            if (!profile.basics.name && !profile.basics.label) {
                errors.push('Missing required field: basics.name or basics.label');
            }
            if (!profile.basics.email) {
                errors.push('Missing required field: basics.email');
            }

            // Validate email format
            if (profile.basics.email && !this._isValidEmail(profile.basics.email)) {
                errors.push('Invalid email format: ' + profile.basics.email);
            }

            // Validate URLs
            if (profile.basics.url && !this._isValidURL(profile.basics.url)) {
                errors.push('Invalid URL format: ' + profile.basics.url);
            }

            // Validate dates in work experience
            if (profile.work && Array.isArray(profile.work)) {
                profile.work.forEach((job, idx) => {
                    if (job.startDate && !this._isValidDate(job.startDate)) {
                        errors.push(`Invalid date format in work[${idx}].startDate: ${job.startDate}`);
                    }
                    if (job.endDate && !this._isValidDate(job.endDate)) {
                        errors.push(`Invalid date format in work[${idx}].endDate: ${job.endDate}`);
                    }
                });
            }

            // Validate dates in education
            if (profile.education && Array.isArray(profile.education)) {
                profile.education.forEach((edu, idx) => {
                    if (edu.startDate && !this._isValidDate(edu.startDate)) {
                        errors.push(`Invalid date format in education[${idx}].startDate: ${edu.startDate}`);
                    }
                    if (edu.endDate && !this._isValidDate(edu.endDate)) {
                        errors.push(`Invalid date format in education[${idx}].endDate: ${edu.endDate}`);
                    }
                });
            }

            if (errors.length > 0) {
                const error = new Error('Profile validation failed');
                error.validationErrors = errors;
                throw error;
            }

            // Normalize using ResumeProcessor if available
            if (window.ResumeProcessor) {
                return profile;
            }

            return profile;
        },

        _isValidEmail(email) {
            return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
        },

        _isValidURL(url) {
            try {
                new URL(url);
                return true;
            } catch {
                return false;
            }
        },

        _isValidDate(dateStr) {
            // Accept YYYY-MM-DD, YYYY-MM, or YYYY formats
            if (/^\d{4}(-\d{2}(-\d{2})?)?$/.test(dateStr)) {
                const date = new Date(dateStr);
                return !isNaN(date.getTime());
            }
            return false;
        },

        _applyOptions(options) {
            if (options.confidenceThreshold !== undefined) {
                this._settings.confidenceThreshold = options.confidenceThreshold;
            }
            if (options.fillEEO !== undefined) {
                this._settings.fillEEO = options.fillEEO;
            }
            if (options.fillLegal !== undefined) {
                this._settings.fillLegal = options.fillLegal;
            }
            if (options.fillSensitive !== undefined) {
                this._settings.fillSensitive = options.fillSensitive;
            }
            if (options.autoSubmit !== undefined) {
                this._settings.autoSubmit = options.autoSubmit;
            }
            if (options.customMappings) {
                this.setCustomMappings(options.customMappings);
            }
        },

        async _findMatchForField(field, profile) {
            // Check custom mappings first
            if (this._customMappings[field.label]) {
                const path = this._customMappings[field.label];
                const value = this._getValueByPath(profile, path);
                if (value) {
                    return {
                        value: value,
                        confidence: 1.0,
                        source: `custom_mapping:${path}`
                    };
                }
            }

            // Use ResumeProcessor if available
            if (window.ResumeProcessor) {
                const normalized = window.ResumeProcessor.normalize(profile);
                const match = this._matchFieldToNormalizedData(field, normalized);
                if (match.value) {
                    return match;
                }
            }

            // Fallback to basic matching
            return this._basicFieldMatch(field, profile);
        },

        _matchFieldToNormalizedData(field, normalized) {
            const label = field.label.toLowerCase();

            // Identity fields
            if (label.includes('first') && label.includes('name')) {
                return { value: normalized.identity?.first_name, confidence: 1.0, source: 'identity.first_name' };
            }
            if (label.includes('last') && label.includes('name')) {
                return { value: normalized.identity?.last_name, confidence: 1.0, source: 'identity.last_name' };
            }
            if (label.includes('full') && label.includes('name')) {
                return { value: normalized.identity?.full_name, confidence: 1.0, source: 'identity.full_name' };
            }

            // Contact fields
            if (label.includes('email')) {
                return { value: normalized.contact?.email, confidence: 1.0, source: 'contact.email' };
            }
            if (label.includes('phone')) {
                return { value: normalized.contact?.phone, confidence: 1.0, source: 'contact.phone' };
            }

            // Location fields
            if (label.includes('city')) {
                return { value: normalized.location?.city, confidence: 0.9, source: 'location.city' };
            }
            if (label.includes('state') || label.includes('region')) {
                return { value: normalized.location?.region, confidence: 0.9, source: 'location.region' };
            }

            // LinkedIn
            if (label.includes('linkedin')) {
                return { value: normalized.contact?.linkedin, confidence: 0.9, source: 'contact.linkedin' };
            }

            return { value: null, confidence: 0, source: null };
        },

        _basicFieldMatch(field, profile) {
            const label = field.label.toLowerCase();

            if (label.includes('email') && profile.basics?.email) {
                return { value: profile.basics.email, confidence: 1.0, source: 'basics.email' };
            }
            if (label.includes('phone') && profile.basics?.phone) {
                return { value: profile.basics.phone, confidence: 1.0, source: 'basics.phone' };
            }
            if (label.includes('name') && profile.basics?.name) {
                return { value: profile.basics.name, confidence: 0.8, source: 'basics.name' };
            }

            return { value: null, confidence: 0, source: null };
        },

        _shouldBlockField(field, match) {
            if (field.isEEO && !this._settings.fillEEO) return true;
            if (field.isLegal && !this._settings.fillLegal) return true;
            if (field.isSensitive && !this._settings.fillSensitive) return true;
            return false;
        },

        _getBlockReason(field) {
            if (field.isEEO) return 'eeo_disabled';
            if (field.isLegal) return 'legal_disabled';
            if (field.isSensitive) return 'sensitive_disabled';
            return 'blocked';
        },

        async _fillField(element, value, type) {
            // User Value Preservation: Check if field has existing value
            const hasExistingValue = await this._checkUserValue(element, type);

            if (hasExistingValue) {
                const preservePreference = this._settings.preserveUserValues !== false;

                if (preservePreference) {
                    // Mark as user-filled and skip
                    element.dataset.userFilled = 'true';
                    console.log('[AutofillAPI] Preserving user value in field:', element.name || element.id);

                    // Track as preserved
                    if (window.TrackingIntegration) {
                        window.TrackingIntegration.trackSkipped(element, 'user_value_preserved');
                    }

                    // Throw to mark as skipped in results
                    throw new Error('User value preserved');
                }
            }

            // Proceed with filling
            if (type === 'select' || type === 'select-one') {
                element.value = value;
                element.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (type === 'checkbox') {
                element.checked = !!value;
                element.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (type === 'radio') {
                element.checked = true;
                element.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                element.value = value;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }

            await new Promise(resolve => setTimeout(resolve, 100));
        },

        /**
         * Check if field has user-entered value
         * @param {HTMLElement} element
         * @param {string} type
         * @returns {Promise<boolean>}
         */
        async _checkUserValue(element, type) {
            // Skip if explicitly marked to overwrite
            if (element.dataset.allowOverwrite === 'true') {
                return false;
            }

            // Check based on field type
            if (type === 'checkbox' || type === 'radio') {
                // For boolean fields, consider "checked" as having value
                return element.checked === true;
            } else if (type === 'select' || type === 'select-one') {
                // For selects, check if non-default option selected
                const value = element.value;
                const firstOption = element.options[0]?.value || '';
                return value && value !== firstOption && value !== '';
            } else {
                // For text inputs, check if non-empty
                const value = element.value?.trim() || '';
                const placeholder = element.placeholder?.trim() || '';
                return value.length > 0 && value !== placeholder;
            }
        },

        _categorizeField(element) {
            const label = this._extractLabel(element).toLowerCase();

            if (this._isEEOField(element)) return 'eeo';
            if (this._isLegalField(element)) return 'legal';
            if (label.includes('experience') || label.includes('work')) return 'work';
            if (label.includes('education') || label.includes('degree')) return 'education';
            if (label.includes('skill')) return 'skills';
            if (label.includes('name') || label.includes('email') || label.includes('phone')) return 'personal';

            return 'other';
        },

        _isEEOField(element) {
            const label = this._extractLabel(element).toLowerCase();
            const eeoKeywords = ['race', 'ethnicity', 'gender', 'veteran', 'disability', 'lgbtq', 'pronoun'];
            return eeoKeywords.some(kw => label.includes(kw));
        },

        _isLegalField(element) {
            const label = this._extractLabel(element).toLowerCase();
            const legalKeywords = ['authorization', 'work permit', 'visa', 'sponsorship', 'eligible to work', 'legally authorized'];
            return legalKeywords.some(kw => label.includes(kw));
        },

        _isSensitiveField(element) {
            const label = this._extractLabel(element).toLowerCase();
            const sensitiveKeywords = ['ssn', 'social security', 'password', 'credit card', 'bank', 'salary'];
            return sensitiveKeywords.some(kw => label.includes(kw));
        },

        _sanitizeValue(value, isSensitive) {
            if (isSensitive && value) {
                return '***REDACTED***';
            }
            return value;
        },

        _getValueByPath(obj, path) {
            return path.split('.').reduce((acc, part) => acc && acc[part], obj);
        },

        _detectATSType() {
            const url = window.location.href;
            if (url.includes('greenhouse.io')) return 'greenhouse';
            if (url.includes('lever.co')) return 'lever';
            if (url.includes('workday')) return 'workday';
            if (url.includes('smartrecruiters')) return 'smartrecruiters';
            if (url.includes('icims')) return 'icims';
            if (url.includes('taleo')) return 'taleo';
            return 'unknown';
        },

        _extractCompany() {
            const selectors = ['[data-company]', '.company-name', 'h1'];
            for (const sel of selectors) {
                const elem = document.querySelector(sel);
                if (elem) return elem.textContent.trim();
            }
            return '';
        },

        _extractJobTitle() {
            const selectors = ['[data-job-title]', '.job-title', 'h2'];
            for (const sel of selectors) {
                const elem = document.querySelector(sel);
                if (elem) return elem.textContent.trim();
            }
            return '';
        },

        _detectFormSections() {
            const sections = [];
            document.querySelectorAll('fieldset, [role="group"], .form-section').forEach((elem, idx) => {
                const legend = elem.querySelector('legend') || elem.querySelector('h3') || elem.querySelector('h4');
                sections.push({
                    index: idx,
                    title: legend ? legend.textContent.trim() : `Section ${idx + 1}`,
                    fieldCount: elem.querySelectorAll('input, select, textarea').length
                });
            });
            return sections;
        },

        _detectMultiStep() {
            const buttons = document.querySelectorAll('button, input[type="button"]');
            return Array.from(buttons).some(btn => {
                const text = (btn.textContent || btn.value || '').toLowerCase();
                return text.includes('next') || text.includes('continue');
            });
        },

        _detectCAPTCHA() {
            return !!(
                document.querySelector('.g-recaptcha') ||
                document.querySelector('[data-sitekey]') ||
                document.querySelector('iframe[src*="recaptcha"]') ||
                document.querySelector('iframe[src*="hcaptcha"]')
            );
        },

        _detectCurrentStep() {
            const indicator = document.querySelector('[data-step], .step-indicator, .progress-step');
            if (indicator) {
                const match = indicator.textContent.match(/(\d+)/);
                return match ? parseInt(match[1]) : 1;
            }
            return 1;
        },

        _detectTotalSteps() {
            const indicator = document.querySelector('[data-total-steps], .step-indicator');
            if (indicator) {
                const match = indicator.textContent.match(/of\s+(\d+)|\/\s*(\d+)/);
                return match ? parseInt(match[1] || match[2]) : null;
            }
            return null;
        },

        _findSubmitButton() {
            const submit = document.querySelector('input[type="submit"], button[type="submit"]');
            return submit ? this._getSelector(submit) : null;
        },

        _generateFieldId(element) {
            if (element.id) return `id:${element.id}`;
            if (element.name) return `name:${element.name}`;
            return `xpath:${this._getXPath(element)}`;
        },

        _extractLabel(element) {
            if (element.id) {
                const label = document.querySelector(`label[for="${element.id}"]`);
                if (label) return label.textContent.trim();
            }

            const parentLabel = element.closest('label');
            if (parentLabel) return parentLabel.textContent.trim();

            if (element.getAttribute('aria-label')) {
                return element.getAttribute('aria-label').trim();
            }

            if (element.placeholder) {
                return element.placeholder.trim();
            }

            return element.name || element.id || 'unknown';
        },

        _getSelectOptions(element) {
            if (element.tagName === 'SELECT') {
                return Array.from(element.options).map(opt => ({
                    value: opt.value,
                    text: opt.textContent.trim()
                }));
            }
            return null;
        },

        _getSelector(element) {
            if (element.id) return `#${element.id}`;
            if (element.name) return `[name="${element.name}"]`;
            return element.tagName.toLowerCase();
        },

        _getXPath(element) {
            if (element.id) return `//*[@id="${element.id}"]`;
            const parts = [];
            while (element && element.nodeType === Node.ELEMENT_NODE) {
                let index = 0;
                let sibling = element.previousSibling;
                while (sibling) {
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === element.tagName) {
                        index++;
                    }
                    sibling = sibling.previousSibling;
                }
                const tagName = element.tagName.toLowerCase();
                const pathIndex = index > 0 ? `[${index + 1}]` : '';
                parts.unshift(tagName + pathIndex);
                element = element.parentNode;
            }
            return parts.length ? '/' + parts.join('/') : '';
        },

        _isVisible(element) {
            return !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
        },

        _findElement(selector) {
            try {
                return document.querySelector(selector);
            } catch {
                return null;
            }
        }
    };

    // Expose API in isolated content-script world (sidepanel / internal use)
    window.AutofillExtension = AutofillAPI;

    console.log('[AutofillAPI] Public API exposed at window.AutofillExtension (isolated world)');

    // RPC bridge: MAIN-world pageWorldBridge.js calls into isolated AutofillAPI
    const CALL_EVENT = '__autofillExtensionCall';
    const RESPONSE_EVENT = '__autofillExtensionResponse';

    document.addEventListener(CALL_EVENT, async (event) => {
        const detail = event.detail || {};
        const { id, method, args } = detail;
        if (!id || !method) return;

        const respond = (payload) => {
            document.dispatchEvent(
                new CustomEvent(RESPONSE_EVENT, {
                    detail: { id, ...payload },
                }),
            );
        };

        try {
            const fn = AutofillAPI[method];
            if (typeof fn !== 'function') {
                respond({ error: 'Unknown AutofillExtension method: ' + method });
                return;
            }

            let result = fn.apply(AutofillAPI, args || []);
            if (result && typeof result.then === 'function') {
                result = await result;
            }
            respond({ result });
        } catch (error) {
            respond({
                error: error && error.message ? error.message : String(error),
                validationErrors: error && error.validationErrors ? error.validationErrors : undefined,
            });
        }
    });

})();
