/**
 * Combobox Handler
 * Handles React Select, custom dropdowns, autocomplete fields, and comboboxes
 * @module comboboxHandler
 */

const ComboboxHandler = {
    /**
     * Fill a combobox/autocomplete field
     * @param {HTMLElement} element - Combobox element
     * @param {string} value - Value to select
     * @param {Object} options - Configuration options
     * @returns {Promise<Object>} Result object
     */
    async fillCombobox(element, value, options = {}) {
        const {
            searchDelay = 300,
            dropdownWaitTime = 500,
            maxWaitForOptions = 3000,
            debug = false
        } = options;

        if (debug) {
            console.log('[ComboboxHandler] Attempting to fill:', { element, value });
        }

        const result = {
            success: false,
            method: null,
            error: null
        };

        try {
            // Try different strategies
            const strategies = [
                () => this.fillReactSelect(element, value, options),
                () => this.fillAriaCombobox(element, value, options),
                () => this.fillCustomDropdown(element, value, options),
                () => this.fillAutocompleteInput(element, value, options)
            ];

            for (const strategy of strategies) {
                const strategyResult = await strategy();
                if (strategyResult.success) {
                    return strategyResult;
                }
            }

            result.error = 'All fill strategies failed';
            return result;

        } catch (error) {
            result.error = error.message;
            if (debug) {
                console.error('[ComboboxHandler] Error:', error);
            }
            return result;
        }
    },

    /**
     * Fill React Select component
     * @param {HTMLElement} element - React Select input
     * @param {string} value - Value to select
     * @param {Object} options - Options
     * @returns {Promise<Object>}
     */
    async fillReactSelect(element, value, options) {
        const { debug = false } = options;
        const result = { success: false, method: 'react-select', error: null };

        try {
            // Find the React Select container
            const container = element.closest('[class*="select"]') || element.closest('[class*="Select"]');

            if (!container) {
                result.error = 'React Select container not found';
                return result;
            }

            // Focus the input
            element.focus();
            await this.sleep(100);

            // Type the value
            await this.typeValue(element, value);
            await this.sleep(300);

            // Wait for options to appear
            const optionsList = await this.waitForElement(
                '[class*="menu"] [class*="option"], [role="option"], [class*="dropdown"] [class*="item"]',
                2000,
                container
            );

            if (!optionsList) {
                // Try pressing Enter as fallback
                this.pressEnter(element);
                await this.sleep(200);

                if (debug) {
                    console.log('[ComboboxHandler] React Select: Options not found, pressed Enter');
                }

                result.success = true;
                return result;
            }

            // Find and click matching option
            const matchingOption = this.findMatchingOption(optionsList, value);

            if (matchingOption) {
                matchingOption.click();
                result.success = true;
                if (debug) {
                    console.log('[ComboboxHandler] React Select: Clicked matching option');
                }
            } else {
                // Fallback to Enter key
                this.pressEnter(element);
                result.success = true;
                if (debug) {
                    console.log('[ComboboxHandler] React Select: No exact match, pressed Enter');
                }
            }

            return result;

        } catch (error) {
            result.error = error.message;
            return result;
        }
    },

    /**
     * Fill ARIA combobox
     * @param {HTMLElement} element - Combobox element
     * @param {string} value - Value to select
     * @param {Object} options - Options
     * @returns {Promise<Object>}
     */
    async fillAriaCombobox(element, value, options) {
        const { debug = false } = options;
        const result = { success: false, method: 'aria-combobox', error: null };

        try {
            const role = element.getAttribute('role');
            const ariaAutocomplete = element.getAttribute('aria-autocomplete');

            if (role !== 'combobox' && ariaAutocomplete !== 'list') {
                result.error = 'Not an ARIA combobox';
                return result;
            }

            // Focus and type
            element.focus();
            await this.sleep(100);

            await this.typeValue(element, value);
            await this.sleep(300);

            // Find listbox
            const listboxId = element.getAttribute('aria-controls') || element.getAttribute('aria-owns');
            let listbox;

            if (listboxId) {
                listbox = document.getElementById(listboxId);
            } else {
                // Try to find listbox nearby
                listbox = document.querySelector('[role="listbox"]');
            }

            if (!listbox) {
                // Fallback to Enter
                this.pressEnter(element);
                result.success = true;
                return result;
            }

            // Find and click matching option
            const options = listbox.querySelectorAll('[role="option"]');
            const matchingOption = this.findMatchingOption(Array.from(options), value);

            if (matchingOption) {
                matchingOption.click();
                result.success = true;
            } else {
                this.pressEnter(element);
                result.success = true;
            }

            return result;

        } catch (error) {
            result.error = error.message;
            return result;
        }
    },

    /**
     * Fill custom dropdown
     * @param {HTMLElement} element - Input element
     * @param {string} value - Value to select
     * @param {Object} options - Options
     * @returns {Promise<Object>}
     */
    async fillCustomDropdown(element, value, options) {
        const result = { success: false, method: 'custom-dropdown', error: null };

        try {
            // Focus and type
            element.focus();
            await this.sleep(100);

            await this.typeValue(element, value);
            await this.sleep(400);

            // Look for dropdown in various common structures
            const dropdownSelectors = [
                '.dropdown-menu',
                '.dropdown',
                '[class*="dropdown"]',
                '[class*="menu"]',
                'ul[role="listbox"]',
                '.autocomplete-results',
                '[class*="results"]'
            ];

            let dropdown = null;
            for (const selector of dropdownSelectors) {
                dropdown = await this.waitForElement(selector, 1000);
                if (dropdown) break;
            }

            if (!dropdown) {
                // Try Enter key
                this.pressEnter(element);
                result.success = true;
                return result;
            }

            // Find options
            const optionSelectors = [
                '[role="option"]',
                'li',
                '.item',
                '[class*="option"]',
                '[class*="item"]'
            ];

            let optionsList = [];
            for (const selector of optionSelectors) {
                const found = dropdown.querySelectorAll(selector);
                if (found.length > 0) {
                    optionsList = Array.from(found);
                    break;
                }
            }

            const matchingOption = this.findMatchingOption(optionsList, value);

            if (matchingOption) {
                matchingOption.click();
                result.success = true;
            } else {
                this.pressEnter(element);
                result.success = true;
            }

            return result;

        } catch (error) {
            result.error = error.message;
            return result;
        }
    },

    /**
     * Fill autocomplete input (simple type and enter)
     * @param {HTMLElement} element - Input element
     * @param {string} value - Value to type
     * @param {Object} options - Options
     * @returns {Promise<Object>}
     */
    async fillAutocompleteInput(element, value, options) {
        const result = { success: false, method: 'autocomplete', error: null };

        try {
            element.focus();
            await this.sleep(100);

            await this.typeValue(element, value);
            await this.sleep(200);

            // Press Enter to confirm
            this.pressEnter(element);

            result.success = true;
            return result;

        } catch (error) {
            result.error = error.message;
            return result;
        }
    },

    /**
     * Type value character by character (more realistic)
     * @param {HTMLElement} element - Input element
     * @param {string} value - Value to type
     */
    async typeValue(element, value) {
        const stringValue = String(value);

        // Use React helper if available
        if (window.ReactInputHelper) {
            return window.ReactInputHelper.fillReactInput(element, stringValue);
        }

        // Fallback: type character by character
        element.value = '';
        for (let i = 0; i < stringValue.length; i++) {
            element.value += stringValue[i];
            element.dispatchEvent(new Event('input', { bubbles: true }));
            await this.sleep(20);
        }

        element.dispatchEvent(new Event('change', { bubbles: true }));
    },

    /**
     * Press Enter key on element
     * @param {HTMLElement} element - Element to press Enter on
     */
    pressEnter(element) {
        const enterEvent = new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true
        });

        element.dispatchEvent(enterEvent);
    },

    /**
     * Find matching option from list
     * @param {Array|NodeList} options - List of option elements
     * @param {string} value - Value to match
     * @returns {HTMLElement|null}
     */
    findMatchingOption(options, value) {
        if (!options || options.length === 0) return null;

        const normalizedValue = String(value).toLowerCase().trim();

        // Try exact match first
        for (const option of options) {
            const optionText = (option.textContent || '').toLowerCase().trim();
            if (optionText === normalizedValue) {
                return option;
            }
        }

        // Try partial match
        for (const option of options) {
            const optionText = (option.textContent || '').toLowerCase().trim();
            if (optionText.includes(normalizedValue) || normalizedValue.includes(optionText)) {
                return option;
            }
        }

        // Return first option as fallback
        return options[0] || null;
    },

    /**
     * Wait for element to appear
     * @param {string} selector - CSS selector
     * @param {number} timeout - Max wait time in ms
     * @param {HTMLElement} context - Context to search within
     * @returns {Promise<HTMLElement|null>}
     */
    async waitForElement(selector, timeout = 2000, context = document) {
        const startTime = Date.now();

        while (Date.now() - startTime < timeout) {
            const element = context.querySelector(selector);
            if (element && element.offsetParent !== null) {
                return element;
            }
            await this.sleep(100);
        }

        return null;
    },

    /**
     * Sleep utility
     * @param {number} ms - Milliseconds
     * @returns {Promise}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
};

// Export
if (typeof window !== 'undefined') {
    window.ComboboxHandler = ComboboxHandler;
}
