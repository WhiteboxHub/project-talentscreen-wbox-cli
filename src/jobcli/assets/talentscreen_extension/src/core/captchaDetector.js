/**
 * CAPTCHA Detector
 * Detects reCAPTCHA v2/v3, hCaptcha, and Cloudflare Turnstile
 * @version 1.0.0
 */

const CaptchaDetector = {
  /**
   * Detect if page has any CAPTCHA
   * @returns {Object} Detection result
   */
  detect() {
    const recaptcha = this.hasRecaptcha();
    const hcaptcha = this.hasHcaptcha();
    const turnstile = this.hasTurnstile();

    const hasCaptcha = recaptcha || hcaptcha || turnstile;

    return {
      hasCaptcha,
      type: this.getType(),
      element: this.getElement(),
      details: {
        recaptcha,
        hcaptcha,
        turnstile
      }
    };
  },

  /**
   * Check for Google reCAPTCHA (v2 or v3)
   * @returns {boolean}
   */
  hasRecaptcha() {
    return !!(
      document.querySelector('.g-recaptcha') ||
      document.querySelector('[data-sitekey]') ||
      document.querySelector('iframe[src*="recaptcha"]') ||
      document.querySelector('iframe[src*="google.com/recaptcha"]') ||
      window.grecaptcha ||
      document.getElementById('g-recaptcha-response')
    );
  },

  /**
   * Check for hCaptcha
   * @returns {boolean}
   */
  hasHcaptcha() {
    return !!(
      document.querySelector('.h-captcha') ||
      document.querySelector('[data-hcaptcha-sitekey]') ||
      document.querySelector('iframe[src*="hcaptcha"]') ||
      window.hcaptcha ||
      document.getElementById('h-captcha-response')
    );
  },

  /**
   * Check for Cloudflare Turnstile
   * @returns {boolean}
   */
  hasTurnstile() {
    return !!(
      document.querySelector('[data-cf-turnstile]') ||
      document.querySelector('[data-turnstile-sitekey]') ||
      document.querySelector('iframe[src*="turnstile"]') ||
      document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
      window.turnstile
    );
  },

  /**
   * Get CAPTCHA type
   * @returns {string|null} 'recaptcha', 'hcaptcha', 'turnstile', or null
   */
  getType() {
    if (this.hasRecaptcha()) return 'recaptcha';
    if (this.hasHcaptcha()) return 'hcaptcha';
    if (this.hasTurnstile()) return 'turnstile';
    return null;
  },

  /**
   * Get CAPTCHA element
   * @returns {HTMLElement|null}
   */
  getElement() {
    // Try reCAPTCHA
    let element = document.querySelector('.g-recaptcha') ||
                  document.querySelector('[data-sitekey]') ||
                  document.querySelector('iframe[src*="recaptcha"]');

    if (element) return element;

    // Try hCaptcha
    element = document.querySelector('.h-captcha') ||
              document.querySelector('[data-hcaptcha-sitekey]') ||
              document.querySelector('iframe[src*="hcaptcha"]');

    if (element) return element;

    // Try Turnstile
    element = document.querySelector('[data-cf-turnstile]') ||
              document.querySelector('[data-turnstile-sitekey]') ||
              document.querySelector('iframe[src*="turnstile"]');

    return element || null;
  },

  /**
   * Get nearby form fields (within parent container)
   * @returns {Array<HTMLElement>}
   */
  getNearbyFields() {
    const captchaElement = this.getElement();
    if (!captchaElement) return [];

    // Find parent form or container
    const container = captchaElement.closest('form') ||
                     captchaElement.closest('.form-group') ||
                     captchaElement.closest('[class*="form"]') ||
                     captchaElement.parentElement;

    if (!container) return [];

    // Get all input fields in container
    const fields = container.querySelectorAll('input, select, textarea');
    return Array.from(fields);
  },

  /**
   * Check if CAPTCHA is solved
   * @returns {boolean}
   */
  isSolved() {
    const type = this.getType();

    if (type === 'recaptcha') {
      const response = document.getElementById('g-recaptcha-response');
      return response && response.value.length > 0;
    }

    if (type === 'hcaptcha') {
      const response = document.getElementById('h-captcha-response');
      return response && response.value.length > 0;
    }

    if (type === 'turnstile') {
      // Turnstile injects a hidden input with name="cf-turnstile-response"
      const response = document.querySelector('input[name="cf-turnstile-response"]');
      return response && response.value.length > 0;
    }

    return false;
  },

  /**
   * Get CAPTCHA status message
   * @returns {Object} Status with message and severity
   */
  getStatus() {
    const detection = this.detect();

    if (!detection.hasCaptcha) {
      return {
        present: false,
        message: 'No CAPTCHA detected',
        severity: 'info'
      };
    }

    const solved = this.isSolved();
    const typeName = this.getTypeDisplayName(detection.type);

    return {
      present: true,
      type: detection.type,
      solved,
      message: solved
        ? `${typeName} completed`
        : `${typeName} detected - please complete it manually`,
      severity: solved ? 'success' : 'warning'
    };
  },

  /**
   * Get display name for CAPTCHA type
   * @param {string} type
   * @returns {string}
   */
  getTypeDisplayName(type) {
    const names = {
      recaptcha: 'reCAPTCHA',
      hcaptcha: 'hCaptcha',
      turnstile: 'Cloudflare Turnstile'
    };
    return names[type] || 'CAPTCHA';
  },

  /**
   * Wait for CAPTCHA to be solved
   * @param {number} timeout - Max wait time in ms (default: 60000 = 1 minute)
   * @returns {Promise<boolean>} True if solved, false if timeout
   */
  async waitForSolution(timeout = 60000) {
    const startTime = Date.now();

    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        if (this.isSolved()) {
          clearInterval(checkInterval);
          resolve(true);
        } else if (Date.now() - startTime > timeout) {
          clearInterval(checkInterval);
          resolve(false);
        }
      }, 500); // Check every 500ms
    });
  },

  /**
   * Export detection result for logging/tracking
   * @returns {Object}
   */
  exportResult() {
    const detection = this.detect();
    const status = this.getStatus();

    return {
      timestamp: new Date().toISOString(),
      url: window.location.href,
      detection,
      status,
      nearbyFieldsCount: this.getNearbyFields().length
    };
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.CaptchaDetector = CaptchaDetector;
}

// Export for Node.js (testing)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = CaptchaDetector;
}

console.log('[CaptchaDetector] Module loaded');
