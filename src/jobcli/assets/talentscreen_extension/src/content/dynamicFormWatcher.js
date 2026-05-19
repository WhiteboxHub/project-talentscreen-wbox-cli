/**
 * Dynamic Form Watcher
 * Monitors DOM for dynamically loaded forms, fields, and page changes
 * Handles SPAs, lazy-loaded forms, and AJAX-loaded content
 * @version 1.0.0
 */

const DynamicFormWatcher = {
  observer: null,
  debounceTimer: null,
  trackedFields: new Set(),
  isActive: false,
  config: {
    debounceDelay: 500,
    maxRetries: 3
  },

  /**
   * Initialize watcher
   */
  init() {
    if (this.isActive) {
      console.log('[DynamicFormWatcher] Already initialized');
      return;
    }

    this.observer = new MutationObserver(this.handleMutations.bind(this));

    this.observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'style', 'disabled', 'hidden', 'aria-hidden']
    });

    this.isActive = true;
    console.log('[DynamicFormWatcher] Initialized');
  },

  /**
   * Stop watching
   */
  stop() {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }

    this.isActive = false;
    console.log('[DynamicFormWatcher] Stopped');
  },

  /**
   * Handle DOM mutations (debounced)
   * @param {MutationRecord[]} mutations
   */
  handleMutations(mutations) {
    clearTimeout(this.debounceTimer);

    this.debounceTimer = setTimeout(() => {
      this.processMutations(mutations);
    }, this.config.debounceDelay);
  },

  /**
   * Process mutations after debounce
   * @param {MutationRecord[]} mutations
   */
  async processMutations(mutations) {
    try {
      const changes = {
        newFields: this.detectNewFields(),
        loadedDropdowns: this.detectLoadedDropdowns(),
        visibleFields: this.detectNewlyVisibleFields(),
        pageChanged: this.detectPageChange()
      };

      // Handle new fields
      if (changes.newFields.length > 0) {
        console.log('[DynamicFormWatcher] New fields detected:', changes.newFields.length);
        await this.handleNewFields(changes.newFields);
      }

      // Handle loaded dropdowns
      if (changes.loadedDropdowns.length > 0) {
        console.log('[DynamicFormWatcher] Dropdowns loaded:', changes.loadedDropdowns.length);
        await this.handleLoadedDropdowns(changes.loadedDropdowns);
      }

      // Handle newly visible fields
      if (changes.visibleFields.length > 0) {
        console.log('[DynamicFormWatcher] Fields became visible:', changes.visibleFields.length);
        await this.handleNewFields(changes.visibleFields);
      }

      // Handle page change
      if (changes.pageChanged) {
        console.log('[DynamicFormWatcher] Page change detected');
        await this.handlePageChange();
      }

    } catch (error) {
      console.error('[DynamicFormWatcher] Error processing mutations:', error);
    }
  },

  /**
   * Detect new form fields
   * @returns {HTMLElement[]}
   */
  detectNewFields() {
    const allFields = document.querySelectorAll('input:not([type="hidden"]), select, textarea');
    const newFields = [];

    allFields.forEach(field => {
      const fieldId = this.getFieldId(field);
      if (!this.trackedFields.has(fieldId) && this.isValidField(field)) {
        newFields.push(field);
        this.trackedFields.add(fieldId);
      }
    });

    return newFields;
  },

  /**
   * Detect dropdowns that finished loading options
   * @returns {HTMLSelectElement[]}
   */
  detectLoadedDropdowns() {
    const dropdowns = document.querySelectorAll('select');
    const loaded = [];

    dropdowns.forEach(dropdown => {
      const fieldId = this.getFieldId(dropdown);

      // Check if dropdown now has options (was empty before)
      if (dropdown.options.length > 1 && this.trackedFields.has(fieldId)) {
        const optionText = Array.from(dropdown.options).map(o => o.text).join(',');

        // Check if we've seen these options before
        const storedOptions = dropdown.dataset.watcherOptions;
        if (storedOptions !== optionText) {
          dropdown.dataset.watcherOptions = optionText;
          loaded.push(dropdown);
        }
      }
    });

    return loaded;
  },

  /**
   * Detect fields that became visible
   * @returns {HTMLElement[]}
   */
  detectNewlyVisibleFields() {
    const visible = [];

    this.trackedFields.forEach(fieldId => {
      const field = document.querySelector(`[data-field-id="${fieldId}"]`);
      if (!field) return;

      const wasHidden = field.dataset.watcherHidden === 'true';
      const isVisible = this.isFieldVisible(field);

      if (wasHidden && isVisible) {
        field.dataset.watcherHidden = 'false';
        visible.push(field);
      } else if (!wasHidden && !isVisible) {
        field.dataset.watcherHidden = 'true';
      }
    });

    return visible;
  },

  /**
   * Detect page change (SPA navigation, multi-step forms)
   * @returns {boolean}
   */
  detectPageChange() {
    const currentUrl = window.location.href;
    const previousUrl = this.lastKnownUrl;

    this.lastKnownUrl = currentUrl;

    if (!previousUrl) return false;

    // Check URL change
    if (currentUrl !== previousUrl) {
      return true;
    }

    // Check for multi-step form indicators
    const stepIndicators = document.querySelectorAll('[class*="step"]');
    if (stepIndicators.length > 0) {
      const activeSteps = Array.from(stepIndicators).filter(el =>
        el.classList.contains('active') ||
        el.classList.contains('current') ||
        el.getAttribute('aria-current') === 'step'
      );

      const currentStep = activeSteps.map(el => el.textContent).join(',');
      if (currentStep !== this.lastKnownStep) {
        this.lastKnownStep = currentStep;
        return true;
      }
    }

    return false;
  },

  /**
   * Handle new fields
   * @param {HTMLElement[]} fields
   */
  async handleNewFields(fields) {
    // Notify FormTracker if available
    if (window.FormTracker && typeof window.FormTracker.registerField === 'function') {
      fields.forEach(field => {
        try {
          window.FormTracker.registerField(field);
        } catch (error) {
          console.error('[DynamicFormWatcher] Error registering field:', error);
        }
      });
    }

    // Notify content script via custom event
    document.dispatchEvent(new CustomEvent('dynamicFieldsDetected', {
      detail: {
        fields: fields.map(f => ({
          id: this.getFieldId(f),
          name: f.name || '',
          type: f.type || f.tagName.toLowerCase(),
          visible: this.isFieldVisible(f)
        }))
      }
    }));
  },

  /**
   * Handle loaded dropdowns
   * @param {HTMLSelectElement[]} dropdowns
   */
  async handleLoadedDropdowns(dropdowns) {
    // Retry filling these dropdowns
    if (window.FormTracker && typeof window.FormTracker.retryFields === 'function') {
      const fieldIds = dropdowns.map(d => this.getFieldId(d));
      window.FormTracker.retryFields(fieldIds);
    }

    // Notify via event
    document.dispatchEvent(new CustomEvent('dropdownsLoaded', {
      detail: {
        dropdowns: dropdowns.map(d => ({
          id: this.getFieldId(d),
          name: d.name || '',
          optionCount: d.options.length
        }))
      }
    }));
  },

  /**
   * Handle page change
   */
  async handlePageChange() {
    // Reset tracking for new page
    this.trackedFields.clear();

    // Notify about page change
    document.dispatchEvent(new CustomEvent('pageChanged', {
      detail: {
        url: window.location.href,
        timestamp: Date.now()
      }
    }));

    // Check settings for auto-continue behavior
    const settings = await this.getSettings();
    if (settings.autofillAfterPageTurn === 'automatically') {
      // Trigger autofill on new page
      setTimeout(() => {
        document.dispatchEvent(new CustomEvent('autoContinueAutofill'));
      }, 1000); // Wait 1s for page to stabilize
    }
  },

  /**
   * Get field identifier
   * @param {HTMLElement} field
   * @returns {string}
   */
  getFieldId(field) {
    return field.id ||
           field.name ||
           field.getAttribute('data-field-id') ||
           `field_${Array.from(document.querySelectorAll('input, select, textarea')).indexOf(field)}`;
  },

  /**
   * Check if field is valid for tracking
   * @param {HTMLElement} field
   * @returns {boolean}
   */
  isValidField(field) {
    // Skip hidden inputs
    if (field.type === 'hidden') return false;

    // Skip if not visible
    if (!this.isFieldVisible(field)) return false;

    // Skip if disabled
    if (field.disabled) return false;

    return true;
  },

  /**
   * Check if field is visible
   * @param {HTMLElement} field
   * @returns {boolean}
   */
  isFieldVisible(field) {
    const style = window.getComputedStyle(field);

    return field.offsetParent !== null &&
           style.display !== 'none' &&
           style.visibility !== 'hidden' &&
           style.opacity !== '0' &&
           field.getAttribute('aria-hidden') !== 'true';
  },

  /**
   * Get settings from storage
   * @returns {Promise<Object>}
   */
  async getSettings() {
    if (typeof chrome !== 'undefined' && chrome.storage) {
      return new Promise(resolve => {
        chrome.storage.local.get('userSettings', result => {
          resolve(result.userSettings || {});
        });
      });
    }
    return {};
  },

  /**
   * Get watcher statistics
   * @returns {Object}
   */
  getStats() {
    return {
      isActive: this.isActive,
      trackedFieldsCount: this.trackedFields.size,
      currentUrl: this.lastKnownUrl || window.location.href,
      currentStep: this.lastKnownStep || 'unknown'
    };
  },

  /**
   * Export data for debugging
   * @returns {Object}
   */
  exportData() {
    return {
      stats: this.getStats(),
      trackedFields: Array.from(this.trackedFields),
      config: this.config,
      timestamp: new Date().toISOString()
    };
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.DynamicFormWatcher = DynamicFormWatcher;
}

// Export for Node.js (testing)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DynamicFormWatcher;
}

console.log('[DynamicFormWatcher] Module loaded');
