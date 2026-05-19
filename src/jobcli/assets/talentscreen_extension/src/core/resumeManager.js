/**
 * Resume Manager
 * Handles multiple resume storage, selection, and management
 * @version 2.0.0
 */

const ResumeManager = {
  /**
   * Get all stored resumes
   * @returns {Promise<Array>} - Array of resume objects
   */
  async getAll() {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.storage) {
        resolve([]);
        return;
      }

      chrome.storage.local.get(['resumes'], (result) => {
        if (chrome.runtime.lastError) {
          console.error('[ResumeManager] GetAll error:', chrome.runtime.lastError);
          resolve([]);
          return;
        }

        resolve(result.resumes || []);
      });
    });
  },

  /**
   * Add a new resume
   * @param {Object} resumeData - Resume JSON data
   * @param {Object} resumeFile - Resume file data (PDF/DOC)
   * @param {string} name - Optional custom name
   * @returns {Promise<Object>} - Created resume object
   */
  async add(resumeData, resumeFile, name = null) {
    const resumes = await this.getAll();

    // Generate name if not provided
    const resumeName = name || this._generateName(resumeData, resumes.length);

    // Create resume object
    const resume = {
      id: this._generateId(),
      name: resumeName,
      jsonData: resumeData,
      fileData: resumeFile ? resumeFile.data : null,
      fileName: resumeFile ? resumeFile.name : null,
      fileType: resumeFile ? resumeFile.type : null,
      fileSize: resumeFile ? resumeFile.size : null,
      version: 'original', // or 'extension-template'
      isPrimary: resumes.length === 0, // First resume is primary
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    // Add to array
    resumes.push(resume);

    // Save
    await this._saveAll(resumes);

    // If this is the primary resume, update legacy storage
    if (resume.isPrimary) {
      await this._updateLegacyStorage(resume);
    }

    console.log('[ResumeManager] Added resume:', resume.id, resume.name);

    return resume;
  },

  /**
   * Update a resume
   * @param {string} id - Resume ID
   * @param {Object} updates - Fields to update
   * @returns {Promise<boolean>} - Success status
   */
  async update(id, updates) {
    const resumes = await this.getAll();
    const index = resumes.findIndex(r => r.id === id);

    if (index === -1) {
      console.error('[ResumeManager] Resume not found:', id);
      return false;
    }

    // Update fields
    resumes[index] = {
      ...resumes[index],
      ...updates,
      updatedAt: new Date().toISOString()
    };

    // Save
    await this._saveAll(resumes);

    // If this is the primary resume, update legacy storage
    if (resumes[index].isPrimary) {
      await this._updateLegacyStorage(resumes[index]);
    }

    console.log('[ResumeManager] Updated resume:', id);

    return true;
  },

  /**
   * Delete a resume
   * @param {string} id - Resume ID
   * @returns {Promise<boolean>} - Success status
   */
  async delete(id) {
    const resumes = await this.getAll();
    const index = resumes.findIndex(r => r.id === id);

    if (index === -1) {
      console.error('[ResumeManager] Resume not found:', id);
      return false;
    }

    const wasPrimary = resumes[index].isPrimary;

    // Remove from array
    resumes.splice(index, 1);

    // If deleted resume was primary, make first resume primary
    if (wasPrimary && resumes.length > 0) {
      resumes[0].isPrimary = true;
      await this._updateLegacyStorage(resumes[0]);
    }

    // Save
    await this._saveAll(resumes);

    console.log('[ResumeManager] Deleted resume:', id);

    return true;
  },

  /**
   * Get a specific resume by ID
   * @param {string} id - Resume ID
   * @returns {Promise<Object|null>} - Resume object or null
   */
  async getById(id) {
    const resumes = await this.getAll();
    return resumes.find(r => r.id === id) || null;
  },

  /**
   * Get the primary resume
   * @returns {Promise<Object|null>} - Primary resume or null
   */
  async getPrimary() {
    const resumes = await this.getAll();
    return resumes.find(r => r.isPrimary) || resumes[0] || null;
  },

  /**
   * Set a resume as primary
   * @param {string} id - Resume ID
   * @returns {Promise<boolean>} - Success status
   */
  async setPrimary(id) {
    const resumes = await this.getAll();

    // Unset all primary flags
    resumes.forEach(r => r.isPrimary = false);

    // Set new primary
    const index = resumes.findIndex(r => r.id === id);
    if (index === -1) {
      console.error('[ResumeManager] Resume not found:', id);
      return false;
    }

    resumes[index].isPrimary = true;

    // Save
    await this._saveAll(resumes);

    // Update legacy storage
    await this._updateLegacyStorage(resumes[index]);

    console.log('[ResumeManager] Set primary resume:', id);

    return true;
  },

  /**
   * Rename a resume
   * @param {string} id - Resume ID
   * @param {string} newName - New name
   * @returns {Promise<boolean>} - Success status
   */
  async rename(id, newName) {
    return this.update(id, { name: newName });
  },

  /**
   * Change resume version
   * @param {string} id - Resume ID
   * @param {string} version - 'original' or 'extension-template'
   * @returns {Promise<boolean>} - Success status
   */
  async setVersion(id, version) {
    if (!['original', 'extension-template'].includes(version)) {
      console.error('[ResumeManager] Invalid version:', version);
      return false;
    }

    return this.update(id, { version: version });
  },

  /**
   * Export resume as JSON
   * @param {string} id - Resume ID
   * @returns {Promise<string>} - JSON string
   */
  async exportJson(id) {
    const resume = await this.getById(id);
    if (!resume) return null;

    return JSON.stringify(resume.jsonData, null, 2);
  },

  /**
   * Export resume file (PDF/DOC)
   * @param {string} id - Resume ID
   * @returns {Promise<Object>} - File data
   */
  async exportFile(id) {
    const resume = await this.getById(id);
    if (!resume || !resume.fileData) return null;

    return {
      data: resume.fileData,
      name: resume.fileName,
      type: resume.fileType
    };
  },

  /**
   * Migrate legacy storage to multi-resume
   * @returns {Promise<boolean>} - Success status
   */
  async migrateLegacy() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['resumeData', 'resumeFile', 'resumes'], (result) => {
        // Skip if already migrated or no legacy data
        if (result.resumes || (!result.resumeData && !result.resumeFile)) {
          resolve(false);
          return;
        }

        console.log('[ResumeManager] Migrating legacy storage...');

        // Create resume from legacy data
        const resume = {
          id: this._generateId(),
          name: this._generateName(result.resumeData, 0),
          jsonData: result.resumeData,
          fileData: result.resumeFile?.data || null,
          fileName: result.resumeFile?.name || null,
          fileType: result.resumeFile?.type || null,
          fileSize: result.resumeFile?.size || null,
          version: 'original',
          isPrimary: true,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        };

        // Save as new format
        chrome.storage.local.set({ resumes: [resume] }, () => {
          if (chrome.runtime.lastError) {
            console.error('[ResumeManager] Migration error:', chrome.runtime.lastError);
            resolve(false);
            return;
          }

          console.log('[ResumeManager] Migration complete');
          resolve(true);
        });
      });
    });
  },

  // === INTERNAL HELPERS ===

  async _saveAll(resumes) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ resumes: resumes }, () => {
        if (chrome.runtime.lastError) {
          console.error('[ResumeManager] Save error:', chrome.runtime.lastError);
          resolve(false);
          return;
        }
        resolve(true);
      });
    });
  },

  async _updateLegacyStorage(resume) {
    // Keep legacy storage in sync for backward compatibility
    return new Promise((resolve) => {
      const normalized = window.ResumeProcessor ?
        window.ResumeProcessor.normalize(resume.jsonData) : null;

      chrome.storage.local.set({
        resumeData: resume.jsonData,
        normalizedData: normalized,
        resumeFile: {
          data: resume.fileData,
          name: resume.fileName,
          type: resume.fileType,
          size: resume.fileSize
        }
      }, resolve);
    });
  },

  _generateId() {
    return `resume_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  },

  _generateName(resumeData, index) {
    const basics = resumeData?.basics || {};
    const name = basics.name || basics.label || 'Resume';

    if (index === 0) {
      return name;
    }

    return `${name} ${index + 1}`;
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.ResumeManager = ResumeManager;
}

// Export for Node.js (testing)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ResumeManager;
}
