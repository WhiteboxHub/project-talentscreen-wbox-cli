/**
 * Mutation Manager
 * Watches for dynamically added form fields and triggers re-autofill
 * @module mutationManager
 */

const MutationManager = {
    observer: null,
    observedFields: new Set(),
    callback: null,
    config: {},
    stopTimeout: null,

    /**
     * Start observing for new form fields
     * @param {Function} onNewFields - Callback when new fields detected
     * @param {Object} options - Configuration options
     */
    start(onNewFields, options = {}) {
        const {
            timeout = 30000, // Stop after 30 seconds
            debounceDelay = 500,
            targetNode = document.body,
            debug = false
        } = options;

        this.config = { debug, debounceDelay };
        this.callback = onNewFields;

        // Create debounced handler
        let debounceTimer = null;
        const debouncedHandler = (mutations) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.handleMutations(mutations);
            }, debounceDelay);
        };

        // Create observer
        this.observer = new MutationObserver(debouncedHandler);

        // Start observing
        this.observer.observe(targetNode, {
            childList: true,
            subtree: true,
            attributes: false
        });

        if (debug) {
            console.log('[MutationManager] Started observing for new fields');
        }

        // Auto-stop after timeout
        this.stopTimeout = setTimeout(() => {
            this.stop();
            if (debug) {
                console.log('[MutationManager] Auto-stopped after timeout');
            }
        }, timeout);
    },

    /**
     * Stop observing
     */
    stop() {
        if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
        }

        if (this.stopTimeout) {
            clearTimeout(this.stopTimeout);
            this.stopTimeout = null;
        }

        if (this.config.debug) {
            console.log('[MutationManager] Stopped observing');
        }
    },

    /**
     * Handle mutations
     * @param {Array} mutations - MutationRecord array
     */
    handleMutations(mutations) {
        const newFields = [];

        for (const mutation of mutations) {
            // Check added nodes
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== Node.ELEMENT_NODE) continue;

                // Find form fields in added node
                const fields = this.findFormFields(node);

                // Filter out already observed fields
                for (const field of fields) {
                    const fieldId = this.getFieldIdentifier(field);
                    if (!this.observedFields.has(fieldId)) {
                        this.observedFields.add(fieldId);
                        newFields.push(field);
                    }
                }
            }
        }

        // Notify callback if new fields found
        if (newFields.length > 0) {
            if (this.config.debug) {
                console.log('[MutationManager] New fields detected:', newFields.length);
            }

            if (this.callback) {
                this.callback(newFields);
            }
        }
    },

    /**
     * Find form fields in an element
     * @param {HTMLElement} element - Element to search
     * @returns {Array<HTMLElement>}
     */
    findFormFields(element) {
        const fields = [];

        // Check if element itself is a field
        if (this.isFormField(element)) {
            fields.push(element);
        }

        // Find fields within element
        const selectors = [
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"])',
            'textarea',
            'select',
            '[role="combobox"]',
            '[role="textbox"]',
            '[contenteditable="true"]'
        ];

        const found = element.querySelectorAll(selectors.join(','));
        fields.push(...Array.from(found));

        return fields;
    },

    /**
     * Check if element is a form field
     * @param {HTMLElement} element - Element to check
     * @returns {boolean}
     */
    isFormField(element) {
        const tagName = element.tagName?.toLowerCase();

        if (tagName === 'input') {
            const type = element.type?.toLowerCase();
            return !['hidden', 'submit', 'button'].includes(type);
        }

        if (tagName === 'textarea' || tagName === 'select') {
            return true;
        }

        const role = element.getAttribute('role');
        if (role === 'combobox' || role === 'textbox') {
            return true;
        }

        if (element.getAttribute('contenteditable') === 'true') {
            return true;
        }

        return false;
    },

    /**
     * Get unique identifier for a field
     * @param {HTMLElement} field - Field element
     * @returns {string}
     */
    getFieldIdentifier(field) {
        return (
            field.id ||
            field.name ||
            field.getAttribute('data-testid') ||
            field.getAttribute('data-automation-id') ||
            this.getXPath(field)
        );
    },

    /**
     * Get XPath for element
     * @param {HTMLElement} element - Element
     * @returns {string}
     */
    getXPath(element) {
        if (element.id) return `//*[@id="${element.id}"]`;

        const parts = [];
        let current = element;

        while (current && current.nodeType === Node.ELEMENT_NODE) {
            let index = 0;
            let sibling = current.previousSibling;

            while (sibling) {
                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === current.tagName) {
                    index++;
                }
                sibling = sibling.previousSibling;
            }

            const tagName = current.tagName.toLowerCase();
            const pathIndex = index > 0 ? `[${index + 1}]` : '';
            parts.unshift(tagName + pathIndex);

            current = current.parentNode;
        }

        return '/' + parts.join('/');
    },

    /**
     * Reset observed fields (for fresh start)
     */
    reset() {
        this.observedFields.clear();
        if (this.config.debug) {
            console.log('[MutationManager] Reset observed fields');
        }
    }
};

// Export
if (typeof window !== 'undefined') {
    window.MutationManager = MutationManager;
}
