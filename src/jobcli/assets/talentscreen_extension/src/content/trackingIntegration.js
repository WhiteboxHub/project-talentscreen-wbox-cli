/**
 * TalentScreen - Form Tracking Integration
 * Connects FormTracker with content script autofill logic
 * @version 2.0.0
 */

(function() {
    'use strict';

    // Integration wrapper for FormTracker
    const TrackingIntegration = {
        initialized: false,
        currentStrategy: null,

        /**
         * Initialize tracking for a new autofill session
         */
        init(atsType, strategy) {
            if (!window.FormTracker) {
                console.warn('[TrackingIntegration] FormTracker not available');
                return;
            }

            const jobUrl = window.location.href;
            const company = this.extractCompanyName() || '';

            FormTracker.startSession(atsType, jobUrl, company);
            this.currentStrategy = strategy;
            this.initialized = true;

            console.log('[TrackingIntegration] Session started', { atsType, company });
        },

        /**
         * Extract company name from page
         */
        extractCompanyName() {
            // Try common selectors for company name
            const selectors = [
                '[data-company-name]',
                '.company-name',
                '.employer-name',
                'h1',
                '.job-company'
            ];

            for (const selector of selectors) {
                const elem = document.querySelector(selector);
                if (elem && elem.textContent) {
                    return elem.textContent.trim();
                }
            }

            // Try to extract from title
            const titleMatch = document.title.match(/(.+?)\s*[-|–]\s*/);
            if (titleMatch) {
                return titleMatch[1].trim();
            }

            return '';
        },

        /**
         * Track field detection
         */
        trackField(element, label, type, options = {}) {
            if (!this.initialized || !window.FormTracker) return;

            const fieldId = this.generateFieldId(element);
            const fieldData = {
                label: label || this.extractLabel(element),
                type: type || element.type || 'text',
                required: element.required || element.hasAttribute('required'),
                selector: this.getSelector(element),
                confidence: options.confidence || 1.0,
                name: element.name,
                id: element.id
            };

            FormTracker.registerField(fieldId, fieldData);
            return fieldId;
        },

        /**
         * Track successful fill
         */
        trackFilled(element, value, valueSource) {
            if (!this.initialized || !window.FormTracker) return;

            const fieldId = this.generateFieldId(element);
            FormTracker.markFilled(fieldId, value, valueSource);
        },

        /**
         * Track skipped field
         */
        trackSkipped(element, reason = 'no_data') {
            if (!this.initialized || !window.FormTracker) return;

            const fieldId = this.generateFieldId(element);
            FormTracker.markSkipped(fieldId, reason);
        },

        /**
         * Track failed field
         */
        trackFailed(element, error) {
            if (!this.initialized || !window.FormTracker) return;

            const fieldId = this.generateFieldId(element);
            FormTracker.markFailed(fieldId, error);
        },

        /**
         * Track field needing review
         */
        trackNeedsReview(element, reason) {
            if (!this.initialized || !window.FormTracker) return;

            const fieldId = this.generateFieldId(element);
            FormTracker.markNeedsReview(fieldId, reason);
        },

        /**
         * Scan for new fields (for multi-step forms)
         */
        scanNewFields() {
            if (!this.initialized || !window.FormTracker) return;

            FormTracker.scanForNewFields(() => {
                const fields = this.detectAllFields();
                return fields.map(f => ({
                    id: this.generateFieldId(f.element),
                    label: f.label,
                    type: f.type,
                    required: f.required
                }));
            });
        },

        /**
         * Detect all form fields on page
         */
        detectAllFields() {
            const fields = [];
            const formElements = document.querySelectorAll('input, select, textarea');

            formElements.forEach(elem => {
                if (elem.type === 'hidden' || elem.type === 'submit' || elem.type === 'button') {
                    return;
                }

                fields.push({
                    element: elem,
                    label: this.extractLabel(elem),
                    type: elem.type || elem.tagName.toLowerCase(),
                    required: elem.required || elem.hasAttribute('required')
                });
            });

            return fields;
        },

        /**
         * Process retries
         */
        async processRetries(fillCallback) {
            if (!this.initialized || !window.FormTracker) return;

            await FormTracker.processRetries(async (fieldId, state) => {
                try {
                    const element = this.findElementById(fieldId);
                    if (!element) return false;

                    return await fillCallback(element, state);
                } catch (error) {
                    console.error('[TrackingIntegration] Retry error:', error);
                    return false;
                }
            });
        },

        /**
         * Mark submission detected
         */
        trackSubmission() {
            if (!this.initialized || !window.FormTracker) return;

            FormTracker.markSubmissionDetected();
        },

        /**
         * End tracking session
         */
        endSession(status = 'completed') {
            if (!this.initialized || !window.FormTracker) return;

            FormTracker.endSession(status);
            this.initialized = false;
            this.currentStrategy = null;
        },

        /**
         * Generate consistent field ID
         */
        generateFieldId(element) {
            if (element.id) return `id:${element.id}`;
            if (element.name) return `name:${element.name}`;

            const label = this.extractLabel(element);
            if (label) return `label:${label.toLowerCase().replace(/\s+/g, '-')}`;

            return `xpath:${this.getXPath(element)}`;
        },

        /**
         * Extract label for field
         */
        extractLabel(element) {
            // Try associated label
            if (element.id) {
                const label = document.querySelector(`label[for="${element.id}"]`);
                if (label) return label.textContent.trim();
            }

            // Try parent label
            const parentLabel = element.closest('label');
            if (parentLabel) return parentLabel.textContent.trim();

            // Try aria-label
            if (element.getAttribute('aria-label')) {
                return element.getAttribute('aria-label').trim();
            }

            // Try placeholder
            if (element.placeholder) {
                return element.placeholder.trim();
            }

            // Try data attributes
            const dataLabel = element.getAttribute('data-label') || element.getAttribute('data-field-name');
            if (dataLabel) return dataLabel.trim();

            // Try name or id
            return element.name || element.id || 'unknown';
        },

        /**
         * Get CSS selector for element
         */
        getSelector(element) {
            if (element.id) return `#${element.id}`;
            if (element.name) return `[name="${element.name}"]`;
            return element.tagName.toLowerCase();
        },

        /**
         * Get XPath for element
         */
        getXPath(element) {
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

        /**
         * Find element by field ID
         */
        findElementById(fieldId) {
            const [type, value] = fieldId.split(':', 2);

            if (type === 'id') {
                return document.getElementById(value);
            } else if (type === 'name') {
                return document.querySelector(`[name="${value}"]`);
            } else if (type === 'label') {
                const label = value.replace(/-/g, ' ');
                const allFields = this.detectAllFields();
                const found = allFields.find(f =>
                    f.label.toLowerCase().includes(label) ||
                    label.includes(f.label.toLowerCase())
                );
                return found ? found.element : null;
            } else if (type === 'xpath') {
                const result = document.evaluate(value, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return result.singleNodeValue;
            }

            return null;
        }
    };

    // Make available globally
    window.TrackingIntegration = TrackingIntegration;

    // Listen for messages from sidepanel
    if (typeof chrome !== 'undefined' && chrome.runtime) {
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            if (request.action === 'get_tracking_data') {
                if (window.FormTracker) {
                    const data = FormTracker.exportSessionData();
                    sendResponse(data);
                } else {
                    sendResponse(null);
                }
                return true;
            }

            if (request.action === 'retry_failed_fields') {
                if (window.FormTracker && TrackingIntegration.initialized) {
                    TrackingIntegration.processRetries(async (element, state) => {
                        // This would need to call the actual fill logic
                        // For now, just return false to indicate retry not implemented
                        return false;
                    }).then(() => {
                        sendResponse({ success: true });
                    });
                    return true;
                } else {
                    sendResponse({ success: false, error: 'Not initialized' });
                }
                return true;
            }

            if (request.action === 'set_debug_mode') {
                if (window.FormTracker) {
                    FormTracker.setDebugMode(request.enabled);
                    sendResponse({ success: true });
                } else {
                    sendResponse({ success: false });
                }
                return true;
            }

            if (request.action === 'export_tracking_data') {
                if (window.FormTracker) {
                    const data = FormTracker.exportSessionData();
                    sendResponse(data);
                } else {
                    sendResponse(null);
                }
                return true;
            }
        });
    }

    console.log('[TrackingIntegration] Integration layer loaded');
})();
