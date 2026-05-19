/**
 * Settings Manager
 * Centralized settings storage and management
 * @version 2.0.0
 */

const SettingsManager = {
  // Default settings
  defaults: {
    // Phase 2: New Settings
    autofillAfterPageTurn: 'manually', // 'automatically' | 'manually'
    defaultPluginView: 'expanded', // 'expanded' | 'minimized'

    // Phase 1: Confirmation preferences
    dontAskAgainAutofill: false,

    // Autofill behavior
    fillEEO: false,
    fillLegal: false,
    fillSensitive: false,
    preserveUserInput: true,
    autoSubmit: false,

    // UI preferences
    debugMode: false,
    showFieldLabels: true,
    highlightFilledFields: true,

    // Performance
    autofillDelay: 100, // ms between field fills
    retryAttempts: 3,
    retryDelay: 1000, // ms between retries

    // Tracking
    enableTracking: true,
    enableSessionHistory: true,
    maxHistoryEntries: 50
  },

  /**
   * Get a single setting
   * @param {string} key - Setting key
   * @returns {Promise<any>} - Setting value
   */
  async get(key) {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.storage) {
        resolve(this.defaults[key]);
        return;
      }

      chrome.storage.local.get(['userSettings'], (result) => {
        if (chrome.runtime.lastError) {
          console.error('[SettingsManager] Get error:', chrome.runtime.lastError);
          resolve(this.defaults[key]);
          return;
        }

        const settings = result.userSettings || {};
        const value = settings[key] !== undefined ? settings[key] : this.defaults[key];
        resolve(value);
      });
    });
  },

  /**
   * Set a single setting
   * @param {string} key - Setting key
   * @param {any} value - Setting value
   * @returns {Promise<boolean>} - Success status
   */
  async set(key, value) {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.storage) {
        resolve(false);
        return;
      }

      chrome.storage.local.get(['userSettings'], (result) => {
        if (chrome.runtime.lastError) {
          console.error('[SettingsManager] Set error:', chrome.runtime.lastError);
          resolve(false);
          return;
        }

        const settings = result.userSettings || {};
        settings[key] = value;

        chrome.storage.local.set({ userSettings: settings }, () => {
          if (chrome.runtime.lastError) {
            console.error('[SettingsManager] Save error:', chrome.runtime.lastError);
            resolve(false);
            return;
          }

          console.log(`[SettingsManager] Set ${key} = ${value}`);
          resolve(true);
        });
      });
    });
  },

  /**
   * Get all settings
   * @returns {Promise<Object>} - All settings
   */
  async getAll() {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.storage) {
        resolve({ ...this.defaults });
        return;
      }

      chrome.storage.local.get(['userSettings'], (result) => {
        if (chrome.runtime.lastError) {
          console.error('[SettingsManager] GetAll error:', chrome.runtime.lastError);
          resolve({ ...this.defaults });
          return;
        }

        const settings = result.userSettings || {};
        const merged = { ...this.defaults, ...settings };
        resolve(merged);
      });
    });
  },

  /**
   * Set multiple settings at once
   * @param {Object} settings - Settings object
   * @returns {Promise<boolean>} - Success status
   */
  async setMultiple(settings) {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.storage) {
        resolve(false);
        return;
      }

      chrome.storage.local.get(['userSettings'], (result) => {
        if (chrome.runtime.lastError) {
          console.error('[SettingsManager] SetMultiple error:', chrome.runtime.lastError);
          resolve(false);
          return;
        }

        const currentSettings = result.userSettings || {};
        const updatedSettings = { ...currentSettings, ...settings };

        chrome.storage.local.set({ userSettings: updatedSettings }, () => {
          if (chrome.runtime.lastError) {
            console.error('[SettingsManager] Save error:', chrome.runtime.lastError);
            resolve(false);
            return;
          }

          console.log('[SettingsManager] Updated multiple settings:', Object.keys(settings));
          resolve(true);
        });
      });
    });
  },

  /**
   * Reset a setting to default
   * @param {string} key - Setting key
   * @returns {Promise<boolean>} - Success status
   */
  async reset(key) {
    return this.set(key, this.defaults[key]);
  },

  /**
   * Reset all settings to defaults
   * @returns {Promise<boolean>} - Success status
   */
  async resetAll() {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.storage) {
        resolve(false);
        return;
      }

      chrome.storage.local.set({ userSettings: { ...this.defaults } }, () => {
        if (chrome.runtime.lastError) {
          console.error('[SettingsManager] ResetAll error:', chrome.runtime.lastError);
          resolve(false);
          return;
        }

        console.log('[SettingsManager] Reset all settings to defaults');
        resolve(true);
      });
    });
  },

  /**
   * Validate setting value
   * @param {string} key - Setting key
   * @param {any} value - Setting value
   * @returns {Object} - Validation result
   */
  validate(key, value) {
    const validators = {
      autofillAfterPageTurn: (v) => ['automatically', 'manually'].includes(v),
      defaultPluginView: (v) => ['expanded', 'minimized'].includes(v),
      dontAskAgainAutofill: (v) => typeof v === 'boolean',
      fillEEO: (v) => typeof v === 'boolean',
      fillLegal: (v) => typeof v === 'boolean',
      fillSensitive: (v) => typeof v === 'boolean',
      preserveUserInput: (v) => typeof v === 'boolean',
      autoSubmit: (v) => typeof v === 'boolean',
      debugMode: (v) => typeof v === 'boolean',
      showFieldLabels: (v) => typeof v === 'boolean',
      highlightFilledFields: (v) => typeof v === 'boolean',
      autofillDelay: (v) => typeof v === 'number' && v >= 0 && v <= 5000,
      retryAttempts: (v) => typeof v === 'number' && v >= 0 && v <= 10,
      retryDelay: (v) => typeof v === 'number' && v >= 0 && v <= 10000,
      enableTracking: (v) => typeof v === 'boolean',
      enableSessionHistory: (v) => typeof v === 'boolean',
      maxHistoryEntries: (v) => typeof v === 'number' && v >= 10 && v <= 1000
    };

    const validator = validators[key];
    if (!validator) {
      return { valid: false, error: `Unknown setting: ${key}` };
    }

    const valid = validator(value);
    if (!valid) {
      return { valid: false, error: `Invalid value for ${key}: ${value}` };
    }

    return { valid: true };
  },

  /**
   * Export settings as JSON
   * @returns {Promise<string>} - JSON string
   */
  async export() {
    const settings = await this.getAll();
    return JSON.stringify(settings, null, 2);
  },

  /**
   * Import settings from JSON
   * @param {string} json - JSON string
   * @returns {Promise<Object>} - Import result
   */
  async import(json) {
    try {
      const settings = JSON.parse(json);
      const errors = [];

      // Validate all settings
      for (const [key, value] of Object.entries(settings)) {
        const validation = this.validate(key, value);
        if (!validation.valid) {
          errors.push(`${key}: ${validation.error}`);
        }
      }

      if (errors.length > 0) {
        return {
          success: false,
          errors: errors
        };
      }

      // Import valid settings
      const success = await this.setMultiple(settings);

      return {
        success: success,
        imported: Object.keys(settings).length,
        errors: []
      };
    } catch (error) {
      return {
        success: false,
        errors: ['Invalid JSON: ' + error.message]
      };
    }
  },

  /**
   * Listen for setting changes
   * @param {Function} callback - Called when settings change
   */
  onChange(callback) {
    if (typeof chrome === 'undefined' || !chrome.storage) {
      return;
    }

    chrome.storage.onChanged.addListener((changes, namespace) => {
      if (namespace === 'local' && changes.userSettings) {
        const oldSettings = changes.userSettings.oldValue || {};
        const newSettings = changes.userSettings.newValue || {};

        // Find what changed
        const changedKeys = Object.keys(newSettings).filter(
          key => newSettings[key] !== oldSettings[key]
        );

        if (changedKeys.length > 0) {
          callback({
            changed: changedKeys,
            oldSettings: oldSettings,
            newSettings: newSettings
          });
        }
      }
    });
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.SettingsManager = SettingsManager;
}

// Export for Node.js (testing)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SettingsManager;
}
