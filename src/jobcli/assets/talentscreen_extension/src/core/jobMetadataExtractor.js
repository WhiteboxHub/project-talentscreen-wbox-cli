/**
 * Job Metadata Extractor
 * Extracts company, job title, location, and other metadata from job posting pages
 * @version 1.0.0
 */

const JobMetadataExtractor = {
  /**
   * Extract all available metadata from current page
   * @returns {Object} Job metadata
   */
  extract() {
    return {
      company: this.extractCompany(),
      jobTitle: this.extractJobTitle(),
      location: this.extractLocation(),
      salary: this.extractSalary(),
      jobType: this.extractJobType(),
      postedDate: this.extractPostedDate(),
      applicationCount: this.extractApplicationCount(),
      description: this.extractDescription(),
      requirements: this.extractRequirements(),
      benefits: this.extractBenefits(),
      url: window.location.href,
      atsType: this.detectATS(),
      timestamp: new Date().toISOString()
    };
  },

  /**
   * Extract company name
   * @returns {string}
   */
  extractCompany() {
    // Try ATS-specific selectors first
    const atsSelectors = {
      greenhouse: '.company-name, [data-company-name]',
      lever: '.posting-company h2, .company-name',
      workday: '.company-logo img[alt], [data-automation-id="company"]',
      smartrecruiters: '.company-header h1, .company-name',
      linkedin: '.topcard__org-name-link, .jobs-unified-top-card__company-name'
    };

    const atsType = this.detectATS();
    if (atsSelectors[atsType]) {
      const element = document.querySelector(atsSelectors[atsType]);
      if (element) {
        return this._cleanText(element.textContent || element.alt);
      }
    }

    // Generic selectors
    const genericSelectors = [
      '[data-company]',
      '.company-name',
      '.employer-name',
      '.company',
      'meta[property="og:site_name"]',
      'meta[name="company"]',
      '.topcard__org-name',
      'h1.company',
      '[itemProp="hiringOrganization"]'
    ];

    for (const selector of genericSelectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = element.getAttribute('content') || element.textContent || element.alt;
        if (text && text.trim().length > 0) {
          return this._cleanText(text);
        }
      }
    }

    // Try extracting from title
    const titleMatch = document.title.match(/at\s+([^-|]+)/i);
    if (titleMatch) {
      return this._cleanText(titleMatch[1]);
    }

    return 'Unknown Company';
  },

  /**
   * Extract job title
   * @returns {string}
   */
  extractJobTitle() {
    // ATS-specific selectors
    const atsSelectors = {
      greenhouse: '.app-title, [data-job-title]',
      lever: '.posting-headline h2, .job-title',
      workday: '[data-automation-id="jobPostingHeader"]',
      smartrecruiters: '.job-title h1',
      linkedin: '.topcard__title, .jobs-unified-top-card__job-title'
    };

    const atsType = this.detectATS();
    if (atsSelectors[atsType]) {
      const element = document.querySelector(atsSelectors[atsType]);
      if (element) {
        return this._cleanText(element.textContent);
      }
    }

    // Generic selectors
    const genericSelectors = [
      '[data-job-title]',
      '.job-title',
      '.posting-headline',
      'h1.title',
      'h1[itemprop="title"]',
      'meta[property="og:title"]',
      'meta[name="title"]',
      'h1',
      'h2.job-title'
    ];

    for (const selector of genericSelectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = element.getAttribute('content') || element.textContent;
        if (text && text.trim().length > 0 && text.length < 150) {
          return this._cleanText(text);
        }
      }
    }

    // Extract from page title
    const titleMatch = document.title.match(/^([^-|]+)/);
    if (titleMatch) {
      return this._cleanText(titleMatch[1]);
    }

    return 'Unknown Position';
  },

  /**
   * Extract location
   * @returns {string|null}
   */
  extractLocation() {
    const selectors = [
      '[data-location]',
      '.location',
      '.job-location',
      '[itemprop="jobLocation"]',
      '[data-automation-id="location"]',
      '.posting-categories .location',
      'meta[name="location"]'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = element.getAttribute('content') || element.textContent;
        if (text && text.trim().length > 0) {
          return this._cleanText(text);
        }
      }
    }

    // Try to find in text patterns
    const bodyText = document.body.textContent;
    const locationPattern = /Location:\s*([^\n]+)/i;
    const match = bodyText.match(locationPattern);
    if (match) {
      return this._cleanText(match[1]);
    }

    return null;
  },

  /**
   * Extract salary range
   * @returns {string|null}
   */
  extractSalary() {
    const selectors = [
      '.salary',
      '.compensation',
      '[data-salary]',
      '[itemprop="baseSalary"]',
      '.salary-range'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = element.getAttribute('content') || element.textContent;
        if (text && text.trim().length > 0) {
          return this._cleanText(text);
        }
      }
    }

    // Try to find salary patterns in text
    const bodyText = document.body.textContent;
    const salaryPatterns = [
      /\$[\d,]+\s*-\s*\$[\d,]+/,
      /Salary:\s*([^\n]+)/i,
      /Compensation:\s*([^\n]+)/i
    ];

    for (const pattern of salaryPatterns) {
      const match = bodyText.match(pattern);
      if (match) {
        return this._cleanText(match[0]);
      }
    }

    return null;
  },

  /**
   * Extract job type (full-time, part-time, etc.)
   * @returns {string|null}
   */
  extractJobType() {
    const selectors = [
      '.employment-type',
      '[data-job-type]',
      '[itemprop="employmentType"]',
      '.job-type'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = element.getAttribute('content') || element.textContent;
        if (text && text.trim().length > 0) {
          return this._cleanText(text);
        }
      }
    }

    // Try to find in text
    const bodyText = document.body.textContent.toLowerCase();
    const types = ['full-time', 'full time', 'part-time', 'part time', 'contract', 'temporary', 'internship', 'freelance'];

    for (const type of types) {
      if (bodyText.includes(type)) {
        return type.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join('-');
      }
    }

    return null;
  },

  /**
   * Extract posted date
   * @returns {string|null}
   */
  extractPostedDate() {
    const selectors = [
      '[data-posted-date]',
      '.posted-date',
      '[itemprop="datePosted"]',
      'time[datetime]',
      '[data-automation-id="postedOn"]'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const datetime = element.getAttribute('datetime') ||
                        element.getAttribute('content') ||
                        element.textContent;
        if (datetime && datetime.trim().length > 0) {
          return this._cleanText(datetime);
        }
      }
    }

    // Try to find in text patterns
    const bodyText = document.body.textContent;
    const datePatterns = [
      /Posted:\s*([^\n]+)/i,
      /Posted on:\s*([^\n]+)/i,
      /(\d{1,2}\s+(?:days?|weeks?|months?)\s+ago)/i
    ];

    for (const pattern of datePatterns) {
      const match = bodyText.match(pattern);
      if (match) {
        return this._cleanText(match[1]);
      }
    }

    return null;
  },

  /**
   * Extract application count (if available)
   * @returns {number|null}
   */
  extractApplicationCount() {
    const selectors = [
      '[data-applicant-count]',
      '.applicant-count',
      '.application-count'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = element.getAttribute('content') || element.textContent;
        const match = text.match(/(\d+)/);
        if (match) {
          return parseInt(match[1], 10);
        }
      }
    }

    // Try to find in text
    const bodyText = document.body.textContent;
    const countPattern = /(\d+)\s+applicants?/i;
    const match = bodyText.match(countPattern);
    if (match) {
      return parseInt(match[1], 10);
    }

    return null;
  },

  /**
   * Extract job description
   * @returns {string}
   */
  extractDescription() {
    const selectors = [
      '.job-description',
      '#job-description',
      '[data-job-description]',
      '[itemprop="description"]',
      '.description',
      '.posting-description',
      '[class*="jobDescription"]',
      '[id*="jobDescription"]'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const clone = element.cloneNode(true);
        // Remove unwanted elements
        clone.querySelectorAll('script, style, nav, footer, header').forEach(el => el.remove());
        const text = clone.textContent.trim();
        if (text.length > 100) {
          return text.substring(0, 2000); // Limit to 2000 chars
        }
      }
    }

    return '';
  },

  /**
   * Extract job requirements/qualifications
   * @returns {string[]}
   */
  extractRequirements() {
    const requirements = [];

    // Look for requirements section
    const sectionHeaders = Array.from(document.querySelectorAll('h2, h3, h4, strong, b'));
    const reqHeader = sectionHeaders.find(h => {
      const text = h.textContent.toLowerCase();
      return text.includes('requirement') ||
             text.includes('qualification') ||
             text.includes('must have') ||
             text.includes('skills');
    });

    if (reqHeader) {
      let current = reqHeader.nextElementSibling;
      let count = 0;

      while (current && count < 5) {
        if (current.tagName === 'UL' || current.tagName === 'OL') {
          const items = current.querySelectorAll('li');
          items.forEach(li => {
            const text = this._cleanText(li.textContent);
            if (text.length > 10 && text.length < 200) {
              requirements.push(text);
            }
          });
          break;
        }

        if (current.tagName === 'P') {
          const text = this._cleanText(current.textContent);
          if (text.length > 10 && text.length < 200) {
            requirements.push(text);
          }
        }

        current = current.nextElementSibling;
        count++;
      }
    }

    return requirements;
  },

  /**
   * Extract benefits
   * @returns {string[]}
   */
  extractBenefits() {
    const benefits = [];

    const sectionHeaders = Array.from(document.querySelectorAll('h2, h3, h4, strong, b'));
    const benefitHeader = sectionHeaders.find(h => {
      const text = h.textContent.toLowerCase();
      return text.includes('benefit') ||
             text.includes('perk') ||
             text.includes('we offer');
    });

    if (benefitHeader) {
      let current = benefitHeader.nextElementSibling;
      let count = 0;

      while (current && count < 5) {
        if (current.tagName === 'UL' || current.tagName === 'OL') {
          const items = current.querySelectorAll('li');
          items.forEach(li => {
            const text = this._cleanText(li.textContent);
            if (text.length > 5 && text.length < 150) {
              benefits.push(text);
            }
          });
          break;
        }

        if (current.tagName === 'P') {
          const text = this._cleanText(current.textContent);
          if (text.length > 5 && text.length < 150) {
            benefits.push(text);
          }
        }

        current = current.nextElementSibling;
        count++;
      }
    }

    return benefits;
  },

  /**
   * Detect ATS type from URL
   * @returns {string}
   */
  detectATS() {
    const url = window.location.href.toLowerCase();

    if (url.includes('greenhouse.io')) return 'greenhouse';
    if (url.includes('lever.co')) return 'lever';
    if (url.includes('myworkdayjobs.com') || url.includes('workday')) return 'workday';
    if (url.includes('smartrecruiters.com')) return 'smartrecruiters';
    if (url.includes('linkedin.com')) return 'linkedin';
    if (url.includes('icims.com')) return 'icims';
    if (url.includes('taleo.net')) return 'taleo';
    if (url.includes('successfactors')) return 'successfactors';
    if (url.includes('workable.com')) return 'workable';
    if (url.includes('bamboohr.com')) return 'bamboohr';
    if (url.includes('ashbyhq.com')) return 'ashby';
    if (url.includes('indeed.com')) return 'indeed';

    return 'unknown';
  },

  /**
   * Get company logo URL
   * @returns {string|null}
   */
  getCompanyLogo() {
    const selectors = [
      '.company-logo img',
      '[data-company-logo]',
      'img[alt*="logo" i]',
      '.logo img',
      'meta[property="og:image"]'
    ];

    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const src = element.getAttribute('content') || element.src;
        if (src && src.startsWith('http')) {
          return src;
        }
      }
    }

    return null;
  },

  /**
   * Export metadata as JSON
   * @returns {string}
   */
  exportJSON() {
    return JSON.stringify(this.extract(), null, 2);
  },

  /**
   * Clean and normalize text
   * @param {string} text
   * @returns {string}
   */
  _cleanText(text) {
    if (!text) return '';

    return text
      .replace(/\s+/g, ' ')  // Multiple spaces to single
      .replace(/\n+/g, ' ')  // Newlines to space
      .trim()
      .substring(0, 500);    // Max 500 chars
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.JobMetadataExtractor = JobMetadataExtractor;
}

// Export for Node.js (testing)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = JobMetadataExtractor;
}

console.log('[JobMetadataExtractor] Module loaded');
