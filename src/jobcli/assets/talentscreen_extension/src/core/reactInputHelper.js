/**
 * React Input Helper
 * Utilities for filling React-controlled inputs that properly trigger state updates
 * @module reactInputHelper
 */

const ReactInputHelper = {
    /**
     * Fill a React-controlled input field
     * Uses native setters and proper event dispatching to ensure React state updates
     * @param {HTMLElement} element - Input element to fill
     * @param {string|number} value - Value to set
     * @returns {boolean} Success status
     */
    fillReactInput(element, value) {
        if (!element || value === undefined || value === null) {
            return false;
        }

        try {
            const tagName = element.tagName.toLowerCase();
            const inputType = element.type?.toLowerCase();

            // Convert value to string
            const stringValue = String(value);

            // Use native setter to bypass React's value control
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,
                'value'
            )?.set;

            const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype,
                'value'
            )?.set;

            // Set value using native setter
            if (tagName === 'input' && nativeInputValueSetter) {
                nativeInputValueSetter.call(element, stringValue);
            } else if (tagName === 'textarea' && nativeTextAreaValueSetter) {
                nativeTextAreaValueSetter.call(element, stringValue);
            } else if (tagName === 'select') {
                element.value = stringValue;
            } else {
                element.value = stringValue;
            }

            // Dispatch events in proper order
            this.dispatchReactEvents(element);

            return true;
        } catch (error) {
            console.error('[ReactInputHelper] Fill error:', error);
            return false;
        }
    },

    /**
     * Dispatch events that React listens to
     * @param {HTMLElement} element - Element to dispatch events on
     */
    dispatchReactEvents(element) {
        const events = [
            new Event('input', { bubbles: true, cancelable: true }),
            new Event('change', { bubbles: true, cancelable: true }),
            new Event('blur', { bubbles: true, cancelable: true })
        ];

        events.forEach(event => {
            try {
                element.dispatchEvent(event);
            } catch (e) {
                console.warn('[ReactInputHelper] Event dispatch failed:', e);
            }
        });
    },

    /**
     * Fill and verify a React input with retry logic
     * @param {HTMLElement} element - Input element
     * @param {string|number} value - Value to set
     * @param {Object} options - Configuration options
     * @returns {Promise<Object>} Result with success status and attempts
     */
    async fillWithVerification(element, value, options = {}) {
        const {
            maxRetries = 3,
            retryDelay = 100,
            verificationDelay = 50
        } = options;

        const result = {
            success: false,
            attempts: 0,
            finalValue: null,
            error: null
        };

        for (let attempt = 0; attempt < maxRetries; attempt++) {
            result.attempts++;

            // Fill the input
            const filled = this.fillReactInput(element, value);

            if (!filled) {
                result.error = 'Fill operation failed';
                await this.sleep(retryDelay);
                continue;
            }

            // Wait for React to process
            await this.sleep(verificationDelay);

            // Verify the value persisted
            const currentValue = this.getElementValue(element);
            result.finalValue = currentValue;

            if (this.valuesMatch(currentValue, value)) {
                result.success = true;
                return result;
            }

            // Retry if value didn't persist
            if (attempt < maxRetries - 1) {
                await this.sleep(retryDelay);
            }
        }

        result.error = result.error || 'Value did not persist after retries';
        return result;
    },

    /**
     * Get current value from an element
     * @param {HTMLElement} element - Element to get value from
     * @returns {string} Current value
     */
    getElementValue(element) {
        const tagName = element.tagName.toLowerCase();

        if (tagName === 'select') {
            return element.value || '';
        } else if (element.type === 'checkbox') {
            return element.checked ? 'true' : 'false';
        } else if (element.type === 'radio') {
            return element.checked ? element.value : '';
        } else if (element.getAttribute('contenteditable') === 'true') {
            return element.textContent || '';
        } else {
            return element.value || '';
        }
    },

    /**
     * Check if two values match (with normalization)
     * @param {string} current - Current value
     * @param {string|number} expected - Expected value
     * @returns {boolean} Whether values match
     */
    valuesMatch(current, expected) {
        const normalizedCurrent = String(current || '').trim().toLowerCase();
        const normalizedExpected = String(expected || '').trim().toLowerCase();
        return normalizedCurrent === normalizedExpected;
    },

    /**
     * Sleep utility
     * @param {number} ms - Milliseconds to sleep
     * @returns {Promise}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
};

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.ReactInputHelper = ReactInputHelper;
}
