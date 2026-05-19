/**
 * Resume Selector Modal
 * Allows user to select, manage, and preview resumes
 */

const ResumeSelectorModal = {
  currentModal: null,
  selectedResumeId: null,
  applyWithoutResume: false,
  onSelectCallback: null,

  /**
   * Show resume selector modal
   * @param {Function} onSelect - Callback when resume selected
   */
  async show(onSelect) {
    this.onSelectCallback = onSelect;
    this.hide(); // Remove existing modal

    // Load resumes
    const resumes = await ResumeManager.getAll();
    const primary = await ResumeManager.getPrimary();
    this.selectedResumeId = primary?.id || null;

    // Create modal HTML
    const modal = document.createElement('div');
    modal.className = 'resume-selector-overlay';
    modal.innerHTML = `
      <div class="resume-selector-modal">
        <div class="resume-selector-header">
          <h2>View & Select Your Resume</h2>
          <button class="resume-selector-close-btn" id="resumeSelectorCloseBtn" aria-label="Close">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="resume-selector-body">
          <!-- Resume List -->
          <div class="resume-list-container">
            <h3>Your Resumes</h3>
            <div id="resumeListContent" class="resume-list">
              ${this._renderResumeList(resumes)}
            </div>

            <button class="btn-add-resume" id="addResumeBtn">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="16"></line>
                <line x1="8" y1="12" x2="16" y2="12"></line>
              </svg>
              Add New Resume
            </button>

            <label class="apply-without-resume">
              <input type="checkbox" id="applyWithoutResumeCheckbox">
              <span>Apply without resume</span>
            </label>
          </div>

          <!-- Resume Preview -->
          <div class="resume-preview-container">
            <h3>Preview</h3>
            <div id="resumePreview" class="resume-preview">
              ${this._renderPreview(primary)}
            </div>

            <!-- Version Selector -->
            <div class="version-selector" id="versionSelectorContainer" ${!this.selectedResumeId ? 'style="display:none;"' : ''}>
              <label for="versionSelector">Version:</label>
              <select id="versionSelector">
                <option value="original">Original Version</option>
                <option value="extension-template">Extension Template</option>
              </select>
            </div>
          </div>
        </div>

        <div class="resume-selector-actions">
          <button class="btn-secondary" id="downloadResumeBtn" ${!this.selectedResumeId ? 'disabled' : ''}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            Download Resume
          </button>
          <button class="btn-primary" id="continueBtn">Continue</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    this.currentModal = modal;

    // Event listeners
    this._attachEventListeners(modal, resumes);
  },

  /**
   * Render resume list
   */
  _renderResumeList(resumes) {
    if (resumes.length === 0) {
      return '<p class="empty-state">No resumes uploaded yet</p>';
    }

    return resumes.map(resume => `
      <div class="resume-item ${resume.isPrimary ? 'primary' : ''} ${resume.id === this.selectedResumeId ? 'selected' : ''}" data-id="${resume.id}">
        <div class="resume-item-content">
          <div class="resume-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
          </div>
          <div class="resume-info">
            <div class="resume-name-edit">
              <input type="text" class="resume-name-input" value="${this._escapeHtml(resume.name)}" data-id="${resume.id}">
            </div>
            <div class="resume-meta">
              ${resume.fileName || 'No file'} • ${this._formatSize(resume.fileSize)} • ${this._formatDate(resume.createdAt)}
            </div>
          </div>
        </div>
        <div class="resume-item-actions">
          ${resume.isPrimary ? '<span class="primary-badge">Primary</span>' : `<button class="btn-icon btn-set-primary" data-id="${resume.id}" title="Set as primary">⭐</button>`}
          <button class="btn-icon btn-delete-resume" data-id="${resume.id}" title="Delete">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path>
            </svg>
          </button>
        </div>
      </div>
    `).join('');
  },

  /**
   * Render preview
   */
  _renderPreview(resume) {
    if (!resume) {
      return '<p class="empty-state">No resume selected</p>';
    }

    const basics = resume.jsonData?.basics || {};
    const work = resume.jsonData?.work || [];
    const education = resume.jsonData?.education || [];
    const skills = resume.jsonData?.skills || [];

    return `
      <div class="preview-section">
        <h4>${basics.name || 'Name not provided'}</h4>
        <p class="preview-contact">
          ${basics.email || ''} ${basics.email && basics.phone ? '•' : ''} ${basics.phone || ''}
        </p>
        ${basics.summary ? `<p class="preview-summary">${basics.summary}</p>` : ''}
      </div>

      ${work.length > 0 ? `
        <div class="preview-section">
          <h5>Work Experience</h5>
          <ul>
            ${work.slice(0, 3).map(job => `<li>${job.position || 'Position'} at ${job.name || 'Company'}</li>`).join('')}
            ${work.length > 3 ? `<li>+ ${work.length - 3} more...</li>` : ''}
          </ul>
        </div>
      ` : ''}

      ${education.length > 0 ? `
        <div class="preview-section">
          <h5>Education</h5>
          <ul>
            ${education.slice(0, 2).map(edu => `<li>${edu.studyType || 'Degree'} in ${edu.area || 'Field'}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      ${skills.length > 0 ? `
        <div class="preview-section">
          <h5>Skills</h5>
          <p class="preview-skills">${skills.flatMap(s => s.keywords || []).slice(0, 10).join(', ')}</p>
        </div>
      ` : ''}
    `;
  },

  /**
   * Attach event listeners
   */
  _attachEventListeners(modal, resumes) {
    const closeBtn = modal.querySelector('#resumeSelectorCloseBtn');
    const continueBtn = modal.querySelector('#continueBtn');
    const downloadBtn = modal.querySelector('#downloadResumeBtn');
    const addResumeBtn = modal.querySelector('#addResumeBtn');
    const applyWithoutCheckbox = modal.querySelector('#applyWithoutResumeCheckbox');
    const versionSelector = modal.querySelector('#versionSelector');
    const overlay = modal.querySelector('.resume-selector-overlay');

    // Close handlers
    const handleClose = () => this.hide();
    closeBtn.addEventListener('click', handleClose);

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) handleClose();
    });

    // Escape key
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        handleClose();
        document.removeEventListener('keydown', handleEscape);
      }
    };
    document.addEventListener('keydown', handleEscape);

    // Resume item click - select
    modal.querySelectorAll('.resume-item').forEach(item => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.resume-item-actions')) return;
        if (e.target.classList.contains('resume-name-input')) return;

        const id = item.dataset.id;
        this._selectResume(id, modal, resumes);
      });
    });

    // Resume name edit
    modal.querySelectorAll('.resume-name-input').forEach(input => {
      input.addEventListener('blur', async () => {
        const id = input.dataset.id;
        const newName = input.value.trim();
        if (newName) {
          await ResumeManager.rename(id, newName);
        }
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.target.blur();
        }
      });
    });

    // Set primary button
    modal.querySelectorAll('.btn-set-primary').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        await ResumeManager.setPrimary(id);
        await this._refreshList(modal, resumes);
      });
    });

    // Delete button
    modal.querySelectorAll('.btn-delete-resume').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;

        if (!confirm('Delete this resume? This cannot be undone.')) {
          return;
        }

        await ResumeManager.delete(id);
        const updatedResumes = await ResumeManager.getAll();
        await this._refreshList(modal, updatedResumes);
      });
    });

    // Apply without resume
    applyWithoutCheckbox.addEventListener('change', (e) => {
      this.applyWithoutResume = e.target.checked;
      const versionContainer = modal.querySelector('#versionSelectorContainer');
      if (versionContainer) {
        versionContainer.style.display = e.target.checked ? 'none' : 'flex';
      }
    });

    // Version selector
    if (versionSelector) {
      versionSelector.addEventListener('change', async (e) => {
        if (this.selectedResumeId) {
          await ResumeManager.setVersion(this.selectedResumeId, e.target.value);
        }
      });
    }

    // Download button
    downloadBtn.addEventListener('click', async () => {
      if (!this.selectedResumeId) return;

      const fileData = await ResumeManager.exportFile(this.selectedResumeId);
      if (!fileData) return;

      // Create download link
      const a = document.createElement('a');
      a.href = fileData.data;
      a.download = fileData.name;
      a.click();
    });

    // Add resume button
    addResumeBtn.addEventListener('click', () => {
      // Trigger file input in sidepanel
      this.hide();
      if (this.onSelectCallback) {
        this.onSelectCallback({ action: 'add_new' });
      }
    });

    // Continue button
    continueBtn.addEventListener('click', async () => {
      if (this.applyWithoutResume) {
        if (this.onSelectCallback) {
          this.onSelectCallback({ applyWithoutResume: true });
        }
      } else if (this.selectedResumeId) {
        const resume = await ResumeManager.getById(this.selectedResumeId);
        if (this.onSelectCallback) {
          this.onSelectCallback({ resume: resume });
        }
      }
      this.hide();
    });
  },

  /**
   * Select a resume
   */
  async _selectResume(id, modal, resumes) {
    this.selectedResumeId = id;

    // Update UI
    modal.querySelectorAll('.resume-item').forEach(item => {
      item.classList.toggle('selected', item.dataset.id === id);
    });

    // Update preview
    const resume = resumes.find(r => r.id === id);
    const previewEl = modal.querySelector('#resumePreview');
    if (previewEl && resume) {
      previewEl.innerHTML = this._renderPreview(resume);
    }

    // Update version selector
    const versionSelector = modal.querySelector('#versionSelector');
    if (versionSelector && resume) {
      versionSelector.value = resume.version || 'original';
    }

    // Enable download button
    const downloadBtn = modal.querySelector('#downloadResumeBtn');
    if (downloadBtn) {
      downloadBtn.disabled = false;
    }
  },

  /**
   * Refresh resume list
   */
  async _refreshList(modal, resumes) {
    const updatedResumes = await ResumeManager.getAll();
    const listEl = modal.querySelector('#resumeListContent');
    if (listEl) {
      listEl.innerHTML = this._renderResumeList(updatedResumes);
      this._attachEventListeners(modal, updatedResumes);
    }
  },

  /**
   * Hide modal
   */
  hide() {
    if (this.currentModal) {
      this.currentModal.remove();
      this.currentModal = null;
    }
  },

  /**
   * Helpers
   */
  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  _formatSize(bytes) {
    if (!bytes) return '—';
    const kb = bytes / 1024;
    return kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(1)} MB`;
  },

  _formatDate(isoString) {
    if (!isoString) return '—';
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return '—';
    }
  }
};

// Export for use in other scripts
if (typeof window !== 'undefined') {
  window.ResumeSelectorModal = ResumeSelectorModal;
}
