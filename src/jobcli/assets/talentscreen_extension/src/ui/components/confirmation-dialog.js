/**
 * Reusable Confirmation Dialog Component
 * Used for "Autofill Again" and other confirmations
 */

const ConfirmationDialog = {
  currentDialog: null,

  /**
   * Show confirmation dialog
   * @param {Object} options
   * @param {string} options.title - Dialog title
   * @param {string} options.message - Dialog message
   * @param {string} options.confirmText - Confirm button text (default: "Yes")
   * @param {string} options.cancelText - Cancel button text (default: "Cancel")
   * @param {string} options.dontAskAgainKey - Storage key for "don't ask again" preference
   * @param {boolean} options.showDontAskAgain - Show "don't ask again" checkbox (default: false)
   * @returns {Promise<boolean>} - true if confirmed, false if cancelled
   */
  async show(options) {
    const {
      title = 'Confirm',
      message = 'Are you sure?',
      confirmText = 'Yes',
      cancelText = 'Cancel',
      dontAskAgainKey = null,
      showDontAskAgain = false
    } = options;

    // Check if user has opted out
    if (dontAskAgainKey) {
      const preference = await this._getPreference(dontAskAgainKey);
      if (preference) {
        return true; // Auto-confirm
      }
    }

    return new Promise((resolve) => {
      // Remove existing dialog if any
      this.hide();

      // Create dialog HTML
      const dialog = document.createElement('div');
      dialog.className = 'confirmation-dialog-overlay';
      dialog.innerHTML = `
        <div class="confirmation-dialog">
          <div class="confirmation-header">
            <h3>${this._escapeHtml(title)}</h3>
          </div>
          <div class="confirmation-body">
            <p>${this._escapeHtml(message)}</p>
          </div>
          ${showDontAskAgain && dontAskAgainKey ? `
            <div class="confirmation-checkbox">
              <label>
                <input type="checkbox" id="dontAskAgainCheckbox">
                <span>Don't ask again</span>
              </label>
            </div>
          ` : ''}
          <div class="confirmation-actions">
            <button class="confirmation-btn confirmation-btn-cancel" id="confirmDialogCancel">
              ${this._escapeHtml(cancelText)}
            </button>
            <button class="confirmation-btn confirmation-btn-confirm" id="confirmDialogConfirm">
              ${this._escapeHtml(confirmText)}
            </button>
          </div>
        </div>
      `;

      // Add to document
      document.body.appendChild(dialog);
      this.currentDialog = dialog;

      // Event handlers
      const confirmBtn = dialog.querySelector('#confirmDialogConfirm');
      const cancelBtn = dialog.querySelector('#confirmDialogCancel');
      const dontAskCheckbox = dialog.querySelector('#dontAskAgainCheckbox');

      const handleConfirm = async () => {
        if (dontAskCheckbox && dontAskCheckbox.checked && dontAskAgainKey) {
          await this._setPreference(dontAskAgainKey, true);
        }
        this.hide();
        resolve(true);
      };

      const handleCancel = () => {
        this.hide();
        resolve(false);
      };

      confirmBtn.addEventListener('click', handleConfirm);
      cancelBtn.addEventListener('click', handleCancel);

      // Close on overlay click
      dialog.addEventListener('click', (e) => {
        if (e.target === dialog) {
          handleCancel();
        }
      });

      // Close on Escape key
      const handleEscape = (e) => {
        if (e.key === 'Escape') {
          handleCancel();
          document.removeEventListener('keydown', handleEscape);
        }
      };
      document.addEventListener('keydown', handleEscape);
    });
  },

  /**
   * Hide current dialog
   */
  hide() {
    if (this.currentDialog) {
      this.currentDialog.remove();
      this.currentDialog = null;
    }
  },

  /**
   * Get preference from storage
   */
  async _getPreference(key) {
    return new Promise((resolve) => {
      if (typeof chrome !== 'undefined' && chrome.storage) {
        chrome.storage.local.get(['userPreferences'], (result) => {
          resolve(result.userPreferences?.[key] || false);
        });
      } else {
        resolve(false);
      }
    });
  },

  /**
   * Set preference in storage
   */
  async _setPreference(key, value) {
    return new Promise((resolve) => {
      if (typeof chrome !== 'undefined' && chrome.storage) {
        chrome.storage.local.get(['userPreferences'], (result) => {
          const preferences = result.userPreferences || {};
          preferences[key] = value;
          chrome.storage.local.set({ userPreferences: preferences }, resolve);
        });
      } else {
        resolve();
      }
    });
  },

  /**
   * Escape HTML to prevent XSS
   */
  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.ConfirmationDialog = ConfirmationDialog;
}
