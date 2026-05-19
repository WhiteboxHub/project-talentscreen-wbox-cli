/**
 * TalentScreen Settings Page
 * Full browser window settings interface
 */

document.addEventListener('DOMContentLoaded', () => {
    if (typeof chrome === 'undefined' || !chrome.storage) {
        console.error('[Settings] Chrome API not available');
        return;
    }

    // Navigation
    const navTabs = document.querySelectorAll('.nav-tab');
    const sections = document.querySelectorAll('.settings-section');

    // Forms
    const personalForm = document.getElementById('personalForm');
    const workForm = document.getElementById('workForm');
    const educationForm = document.getElementById('educationForm');
    const skillsForm = document.getElementById('skillsForm');
    const customForm = document.getElementById('customForm');

    // Buttons
    const closeBtn = document.getElementById('closeBtn');
    const addWorkBtn = document.getElementById('addWorkBtn');
    const addEducationBtn = document.getElementById('addEducationBtn');
    const deleteProfileBtn = document.getElementById('deleteProfileBtn');
    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    const resetPersonalBtn = document.getElementById('resetPersonalBtn');
    const savePreferencesBtn = document.getElementById('savePreferencesBtn');
    const resetPreferencesBtn = document.getElementById('resetPreferencesBtn');

    // File inputs
    const jsonInput = document.getElementById('jsonInput');
    const pdfInput = document.getElementById('pdfInput');

    // Containers
    const workEntriesContainer = document.getElementById('workEntries');
    const educationEntriesContainer = document.getElementById('educationEntries');

    // State
    let currentResumeData = null;
    let currentResumeFile = null;
    let originalData = null;

    // Initialize
    async function init() {
        // Load preferences
        await loadPreferences();

        chrome.storage.local.get(['resumeData', 'resumeFile'], (result) => {
            if (chrome.runtime.lastError) {
                console.error('[Settings] Storage error:', chrome.runtime.lastError);
                showToast('Failed to load data', 'error');
                return;
            }

            currentResumeData = result.resumeData || null;
            currentResumeFile = result.resumeFile || null;
            originalData = JSON.parse(JSON.stringify(currentResumeData));

            if (currentResumeData) {
                populateAllForms();
            }

            updateFileDisplays();

            // Handle deep link (hash)
            const hash = window.location.hash.substring(1);
            if (hash) {
                showSection(hash);
            }
        });
    }

    // Navigation
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const sectionId = tab.dataset.section;
            showSection(sectionId);
        });
    });

    function showSection(sectionId) {
        navTabs.forEach(tab => {
            if (tab.dataset.section === sectionId) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });

        sections.forEach(section => {
            if (section.id === sectionId + 'Section') {
                section.classList.add('active');
            } else {
                section.classList.remove('active');
            }
        });
    }

    // Close button
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            window.close();
        });
    }

    // === PERSONAL INFO FORM ===

    function populatePersonalForm() {
        if (!currentResumeData) return;

        const basics = currentResumeData.basics || {};
        const location = basics.location || {};
        const profiles = basics.profiles || [];
        const linkedin = profiles.find(p => p.network === 'LinkedIN' || p.network === 'LinkedIn');
        const github = profiles.find(p => p.network === 'GitHub' || p.network === 'Github');

        document.getElementById('fullName').value = basics.name || '';
        document.getElementById('email').value = basics.email || '';
        document.getElementById('phone').value = basics.phone || '';
        document.getElementById('city').value = location.city || '';
        document.getElementById('region').value = location.region || '';
        document.getElementById('country').value = location.country || '';
        document.getElementById('postalCode').value = location.postalCode || '';
        document.getElementById('linkedin').value = linkedin?.url || '';
        document.getElementById('github').value = github?.url || '';
        document.getElementById('summary').value = basics.summary || '';
    }

    if (personalForm) {
        personalForm.addEventListener('submit', (e) => {
            e.preventDefault();

            if (!currentResumeData) currentResumeData = {};
            if (!currentResumeData.basics) currentResumeData.basics = {};
            if (!currentResumeData.basics.location) currentResumeData.basics.location = {};
            if (!currentResumeData.basics.profiles) currentResumeData.basics.profiles = [];

            currentResumeData.basics.name = document.getElementById('fullName').value;
            currentResumeData.basics.email = document.getElementById('email').value;
            currentResumeData.basics.phone = document.getElementById('phone').value;
            currentResumeData.basics.location.city = document.getElementById('city').value;
            currentResumeData.basics.location.region = document.getElementById('region').value;
            currentResumeData.basics.location.country = document.getElementById('country').value;
            currentResumeData.basics.location.postalCode = document.getElementById('postalCode').value;
            currentResumeData.basics.summary = document.getElementById('summary').value;

            // Update LinkedIn
            const linkedinUrl = document.getElementById('linkedin').value;
            const linkedinProfile = currentResumeData.basics.profiles.find(p => p.network === 'LinkedIN' || p.network === 'LinkedIn');
            if (linkedinProfile) {
                linkedinProfile.url = linkedinUrl;
            } else if (linkedinUrl) {
                currentResumeData.basics.profiles.push({ network: 'LinkedIN', url: linkedinUrl });
            }

            // Update GitHub
            const githubUrl = document.getElementById('github').value;
            const githubProfile = currentResumeData.basics.profiles.find(p => p.network === 'GitHub' || p.network === 'Github');
            if (githubProfile) {
                githubProfile.url = githubUrl;
            } else if (githubUrl) {
                currentResumeData.basics.profiles.push({ network: 'GitHub', url: githubUrl });
            }

            saveResumeData('Personal information saved successfully!');
        });
    }

    if (resetPersonalBtn) {
        resetPersonalBtn.addEventListener('click', () => {
            populatePersonalForm();
            showToast('Changes reset', 'info');
        });
    }

    // === WORK EXPERIENCE FORM ===

    function populateWorkForm() {
        if (!currentResumeData) return;

        const work = currentResumeData.work || [];
        workEntriesContainer.innerHTML = '';

        work.forEach((job, index) => {
            addWorkEntry(job, index);
        });

        if (work.length === 0) {
            addWorkEntry({}, 0);
        }
    }

    function addWorkEntry(job = {}, index) {
        const entryDiv = document.createElement('div');
        entryDiv.className = 'entry-card';
        entryDiv.innerHTML = `
            <div class="entry-header">
                <h4>Position ${index + 1}</h4>
                <button type="button" class="btn-remove" data-index="${index}">Remove</button>
            </div>
            <div class="form-grid">
                <div class="form-group full-width">
                    <label>Company Name</label>
                    <input type="text" class="work-company" value="${job.name || ''}" placeholder="Acme Corporation">
                </div>
                <div class="form-group full-width">
                    <label>Job Title</label>
                    <input type="text" class="work-position" value="${job.position || ''}" placeholder="Senior Software Engineer">
                </div>
                <div class="form-group">
                    <label>Start Date</label>
                    <input type="text" class="work-start" value="${job.startDate || ''}" placeholder="2020-01-15">
                </div>
                <div class="form-group">
                    <label>End Date</label>
                    <input type="text" class="work-end" value="${job.endDate || ''}" placeholder="2023-12-31 or leave blank if current">
                </div>
                <div class="form-group full-width">
                    <label>Description/Summary</label>
                    <textarea class="work-summary" rows="4" placeholder="Describe your role and achievements...">${job.summary || ''}</textarea>
                </div>
            </div>
        `;
        workEntriesContainer.appendChild(entryDiv);

        const removeBtn = entryDiv.querySelector('.btn-remove');
        removeBtn.addEventListener('click', () => {
            entryDiv.remove();
        });
    }

    if (addWorkBtn) {
        addWorkBtn.addEventListener('click', () => {
            const currentCount = workEntriesContainer.querySelectorAll('.entry-card').length;
            addWorkEntry({}, currentCount);
        });
    }

    if (workForm) {
        workForm.addEventListener('submit', (e) => {
            e.preventDefault();

            const workEntries = Array.from(workEntriesContainer.querySelectorAll('.entry-card'));
            currentResumeData.work = workEntries.map(entry => {
                return {
                    name: entry.querySelector('.work-company').value,
                    position: entry.querySelector('.work-position').value,
                    startDate: entry.querySelector('.work-start').value,
                    endDate: entry.querySelector('.work-end').value,
                    summary: entry.querySelector('.work-summary').value
                };
            }).filter(job => job.name || job.position);

            saveResumeData('Work experience saved successfully!');
        });
    }

    // === EDUCATION FORM ===

    function populateEducationForm() {
        if (!currentResumeData) return;

        const education = currentResumeData.education || [];
        educationEntriesContainer.innerHTML = '';

        education.forEach((edu, index) => {
            addEducationEntry(edu, index);
        });

        if (education.length === 0) {
            addEducationEntry({}, 0);
        }
    }

    function addEducationEntry(edu = {}, index) {
        const entryDiv = document.createElement('div');
        entryDiv.className = 'entry-card';
        entryDiv.innerHTML = `
            <div class="entry-header">
                <h4>Education ${index + 1}</h4>
                <button type="button" class="btn-remove" data-index="${index}">Remove</button>
            </div>
            <div class="form-grid">
                <div class="form-group full-width">
                    <label>Institution</label>
                    <input type="text" class="edu-institution" value="${edu.institution || ''}" placeholder="University of California">
                </div>
                <div class="form-group">
                    <label>Degree</label>
                    <input type="text" class="edu-degree" value="${edu.studyType || ''}" placeholder="Bachelor's, Master's, PhD">
                </div>
                <div class="form-group">
                    <label>Field of Study</label>
                    <input type="text" class="edu-area" value="${edu.area || ''}" placeholder="Computer Science">
                </div>
                <div class="form-group">
                    <label>Start Date</label>
                    <input type="text" class="edu-start" value="${edu.startDate || ''}" placeholder="2016-09-01">
                </div>
                <div class="form-group">
                    <label>End Date</label>
                    <input type="text" class="edu-end" value="${edu.endDate || ''}" placeholder="2020-05-15">
                </div>
                <div class="form-group full-width">
                    <label>GPA (optional)</label>
                    <input type="text" class="edu-gpa" value="${edu.score || ''}" placeholder="3.8">
                </div>
            </div>
        `;
        educationEntriesContainer.appendChild(entryDiv);

        const removeBtn = entryDiv.querySelector('.btn-remove');
        removeBtn.addEventListener('click', () => {
            entryDiv.remove();
        });
    }

    if (addEducationBtn) {
        addEducationBtn.addEventListener('click', () => {
            const currentCount = educationEntriesContainer.querySelectorAll('.entry-card').length;
            addEducationEntry({}, currentCount);
        });
    }

    if (educationForm) {
        educationForm.addEventListener('submit', (e) => {
            e.preventDefault();

            const eduEntries = Array.from(educationEntriesContainer.querySelectorAll('.entry-card'));
            currentResumeData.education = eduEntries.map(entry => {
                return {
                    institution: entry.querySelector('.edu-institution').value,
                    studyType: entry.querySelector('.edu-degree').value,
                    area: entry.querySelector('.edu-area').value,
                    startDate: entry.querySelector('.edu-start').value,
                    endDate: entry.querySelector('.edu-end').value,
                    score: entry.querySelector('.edu-gpa').value
                };
            }).filter(edu => edu.institution || edu.studyType);

            saveResumeData('Education saved successfully!');
        });
    }

    // === SKILLS FORM ===

    function populateSkillsForm() {
        if (!currentResumeData) return;

        const skills = currentResumeData.skills || [];
        const allKeywords = skills.flatMap(s => s.keywords || []);
        document.getElementById('skillsText').value = allKeywords.join(', ');
    }

    if (skillsForm) {
        skillsForm.addEventListener('submit', (e) => {
            e.preventDefault();

            const skillsText = document.getElementById('skillsText').value;
            const keywords = skillsText.split(',').map(s => s.trim()).filter(s => s);

            currentResumeData.skills = [{
                name: 'Skills',
                keywords: keywords
            }];

            saveResumeData('Skills saved successfully!');
        });
    }

    // === CUSTOM FIELDS FORM ===

    function populateCustomForm() {
        if (!currentResumeData) return;

        const custom = currentResumeData.custom_fields || {};
        const eeo = custom.eeo || {};
        const legal = custom.legal || {};
        const technical = custom.technical_screening || {};
        const logistics = custom.application_logistics || {};
        const screening = logistics.screening_answers || {};

        // EEO
        document.getElementById('gender').value = eeo.gender || 'male';
        document.getElementById('ethnicity').value = eeo.ethnicity || 'asian';
        document.getElementById('veteranStatus').value = eeo.veteran_status || 'no';
        document.getElementById('disabilityStatus').value = eeo.disability_status || 'no';

        // Legal/Work Authorization
        document.getElementById('workAuthUs').checked = legal.work_auth_us !== undefined ? legal.work_auth_us : true;
        document.getElementById('sponsorshipNow').checked = legal.sponsorship_required_now || false;
        document.getElementById('sponsorshipFuture').checked = legal.sponsorship_required_future || false;
        document.getElementById('noticePeriod').value = legal.notice_period_days || 14;
        document.getElementById('visaStatus').value = legal.visa_status || 'citizen';
        document.getElementById('securityClearance').value = legal.security_clearance || 'no';

        // Technical Screening
        document.getElementById('yearsLlm').value = technical.years_llm || 3;
        document.getElementById('yearsMlDeploy').value = technical.years_ml_deployment || 5;
        document.getElementById('yearsPython').value = technical.years_python || 15;
        document.getElementById('yearsK8s').value = technical.years_kubernetes || 5;
        document.getElementById('highestEducation').value = technical.highest_education || 'masters';
        document.getElementById('experienceRag').checked = technical.experience_rag !== undefined ? technical.experience_rag : true;
        document.getElementById('experienceAgenticAi').checked = technical.experience_agentic_ai !== undefined ? technical.experience_agentic_ai : true;

        // Application Logistics
        document.getElementById('willingRelocate').value = logistics.willing_to_relocate || 'yes';
        document.getElementById('willingTravel').value = logistics.willing_to_travel || 'yes';
        document.getElementById('whyInterested').value = screening.why_interested || 'Driven by the challenge of architecting production-grade agentic workflows and scaling LLM infrastructure within enterprise environments.';
        document.getElementById('whyGoodFit').value = screening.why_good_fit || 'Proven experience leading AI architecture at Lucid Motors and Yahoo, focusing on end-to-end MLOps and highly available distributed systems.';
    }

    if (customForm) {
        customForm.addEventListener('submit', (e) => {
            e.preventDefault();

            if (!currentResumeData.custom_fields) currentResumeData.custom_fields = {};
            if (!currentResumeData.custom_fields.eeo) currentResumeData.custom_fields.eeo = {};
            if (!currentResumeData.custom_fields.legal) currentResumeData.custom_fields.legal = {};
            if (!currentResumeData.custom_fields.technical_screening) currentResumeData.custom_fields.technical_screening = {};
            if (!currentResumeData.custom_fields.application_logistics) currentResumeData.custom_fields.application_logistics = {};
            if (!currentResumeData.custom_fields.application_logistics.screening_answers) currentResumeData.custom_fields.application_logistics.screening_answers = {};

            // EEO
            currentResumeData.custom_fields.eeo.gender = document.getElementById('gender').value;
            currentResumeData.custom_fields.eeo.ethnicity = document.getElementById('ethnicity').value;
            currentResumeData.custom_fields.eeo.veteran_status = document.getElementById('veteranStatus').value;
            currentResumeData.custom_fields.eeo.disability_status = document.getElementById('disabilityStatus').value;

            // Legal/Work Authorization
            currentResumeData.custom_fields.legal.work_auth_us = document.getElementById('workAuthUs').checked;
            currentResumeData.custom_fields.legal.sponsorship_required_now = document.getElementById('sponsorshipNow').checked;
            currentResumeData.custom_fields.legal.sponsorship_required_future = document.getElementById('sponsorshipFuture').checked;
            currentResumeData.custom_fields.legal.notice_period_days = parseInt(document.getElementById('noticePeriod').value) || 14;
            currentResumeData.custom_fields.legal.visa_status = document.getElementById('visaStatus').value;
            currentResumeData.custom_fields.legal.security_clearance = document.getElementById('securityClearance').value;

            // Technical Screening
            currentResumeData.custom_fields.technical_screening.years_llm = parseInt(document.getElementById('yearsLlm').value) || 3;
            currentResumeData.custom_fields.technical_screening.years_ml_deployment = parseInt(document.getElementById('yearsMlDeploy').value) || 5;
            currentResumeData.custom_fields.technical_screening.years_python = parseInt(document.getElementById('yearsPython').value) || 15;
            currentResumeData.custom_fields.technical_screening.years_kubernetes = parseInt(document.getElementById('yearsK8s').value) || 5;
            currentResumeData.custom_fields.technical_screening.highest_education = document.getElementById('highestEducation').value;
            currentResumeData.custom_fields.technical_screening.experience_rag = document.getElementById('experienceRag').checked;
            currentResumeData.custom_fields.technical_screening.experience_agentic_ai = document.getElementById('experienceAgenticAi').checked;

            // Application Logistics
            currentResumeData.custom_fields.application_logistics.willing_to_relocate = document.getElementById('willingRelocate').value;
            currentResumeData.custom_fields.application_logistics.willing_to_travel = document.getElementById('willingTravel').value;
            currentResumeData.custom_fields.application_logistics.screening_answers.why_interested = document.getElementById('whyInterested').value;
            currentResumeData.custom_fields.application_logistics.screening_answers.why_good_fit = document.getElementById('whyGoodFit').value;

            saveResumeData('Custom fields saved successfully!');
        });
    }

    // === FILE UPLOADS ===

    function updateFileDisplays() {
        // JSON file
        const jsonFileInfo = document.getElementById('jsonFileInfo');
        if (currentResumeData && jsonFileInfo) {
            const fileName = currentResumeData.basics?.name || 'Resume Data';
            jsonFileInfo.innerHTML = `<span class="file-status uploaded">✓ ${fileName} (JSON loaded)</span>`;
        }

        // PDF file
        const pdfFileInfo = document.getElementById('pdfFileInfo');
        if (currentResumeFile && pdfFileInfo) {
            const sizeKB = (currentResumeFile.size / 1024).toFixed(1);
            pdfFileInfo.innerHTML = `<span class="file-status uploaded">✓ ${currentResumeFile.name} (${sizeKB} KB)</span>`;
        }
    }

    if (jsonInput) {
        jsonInput.addEventListener('change', (event) => {
            handleJsonUpload(event.target.files[0]);
        });
    }

    function handleJsonUpload(file) {
        if (!file) return;

        const jsonStatus = document.getElementById('jsonStatus');
        const reader = new FileReader();

        reader.onload = (e) => {
            try {
                const rawText = e.target.result;
                const text = rawText.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');
                const json = JSON.parse(text);

                const validation = validateJsonData(json);
                if (validation.valid) {
                    currentResumeData = json;
                    saveResumeData('JSON file uploaded successfully!');
                    populateAllForms();
                    updateFileDisplays();

                    if (jsonStatus) {
                        jsonStatus.textContent = `✓ ${file.name} uploaded successfully`;
                        jsonStatus.className = 'upload-status success';
                    }
                } else {
                    if (jsonStatus) {
                        jsonStatus.textContent = `✗ ${validation.message}`;
                        jsonStatus.className = 'upload-status error';
                    }
                    showToast('Invalid JSON: ' + validation.message, 'error');
                }
            } catch (error) {
                if (jsonStatus) {
                    jsonStatus.textContent = `✗ Invalid JSON: ${error.message}`;
                    jsonStatus.className = 'upload-status error';
                }
                showToast('Failed to parse JSON', 'error');
            }
        };

        reader.onerror = () => {
            const jsonStatus = document.getElementById('jsonStatus');
            if (jsonStatus) {
                jsonStatus.textContent = '✗ Failed to read file';
                jsonStatus.className = 'upload-status error';
            }
            showToast('Failed to read file', 'error');
        };

        reader.readAsText(file);
    }

    if (pdfInput) {
        pdfInput.addEventListener('change', (event) => {
            handlePdfUpload(event.target.files[0]);
        });
    }

    function handlePdfUpload(file) {
        if (!file) return;

        const pdfStatus = document.getElementById('pdfStatus');
        const validation = validatePdfFile(file);

        if (!validation.valid) {
            if (pdfStatus) {
                pdfStatus.textContent = `✗ ${validation.message}`;
                pdfStatus.className = 'upload-status error';
            }
            showToast(validation.message, 'error');
            return;
        }

        const MAX_SIZE = 10 * 1024 * 1024;
        if (file.size > MAX_SIZE) {
            if (pdfStatus) {
                pdfStatus.textContent = '✗ File too large (max 10MB)';
                pdfStatus.className = 'upload-status error';
            }
            showToast('File too large', 'error');
            return;
        }

        const reader = new FileReader();

        reader.onload = (e) => {
            const resumeFileData = {
                data: e.target.result,
                name: file.name,
                type: file.type,
                size: file.size
            };

            chrome.storage.local.set({ resumeFile: resumeFileData }, () => {
                if (chrome.runtime.lastError) {
                    if (pdfStatus) {
                        pdfStatus.textContent = '✗ Failed to save file';
                        pdfStatus.className = 'upload-status error';
                    }
                    showToast('Failed to save PDF', 'error');
                    return;
                }

                currentResumeFile = resumeFileData;
                updateFileDisplays();

                if (pdfStatus) {
                    pdfStatus.textContent = `✓ ${file.name} uploaded successfully`;
                    pdfStatus.className = 'upload-status success';
                }
                showToast('Resume file uploaded successfully!', 'success');
            });
        };

        reader.onerror = () => {
            if (pdfStatus) {
                pdfStatus.textContent = '✗ Failed to read file';
                pdfStatus.className = 'upload-status error';
            }
            showToast('Failed to read file', 'error');
        };

        reader.readAsDataURL(file);
    }

    // === TRACKING SECTION ===

    const debugModeToggle = document.getElementById('debugModeToggle');
    if (debugModeToggle) {
        chrome.storage.local.get(['formTrackerDebugMode'], (result) => {
            debugModeToggle.checked = result.formTrackerDebugMode || false;
        });

        debugModeToggle.addEventListener('change', () => {
            const enabled = debugModeToggle.checked;
            chrome.storage.local.set({ formTrackerDebugMode: enabled });
            showToast(`Debug mode ${enabled ? 'enabled' : 'disabled'}`, 'success');
        });
    }

    // === PREFERENCES SECTION ===

    if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to clear all application history?')) {
                chrome.storage.local.set({ applicationHistory: [] }, () => {
                    if (chrome.runtime.lastError) {
                        showToast('Failed to clear history', 'error');
                        return;
                    }
                    showToast('Application history cleared', 'success');
                });
            }
        });
    }

    if (deleteProfileBtn) {
        deleteProfileBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to delete ALL resume data? This action cannot be undone.')) {
                chrome.storage.local.set({
                    resumeData: null,
                    normalizedData: null,
                    resumeFile: null
                }, () => {
                    if (chrome.runtime.lastError) {
                        showToast('Failed to delete data', 'error');
                        return;
                    }

                    currentResumeData = null;
                    currentResumeFile = null;
                    showToast('All resume data deleted', 'success');

                    setTimeout(() => {
                        window.close();
                    }, 1500);
                });
            }
        });
    }

    // === HELPER FUNCTIONS ===

    function populateAllForms() {
        populatePersonalForm();
        populateWorkForm();
        populateEducationForm();
        populateSkillsForm();
        populateCustomForm();
    }

    function saveResumeData(successMessage = 'Data saved successfully!') {
        try {
            const normalized = ResumeProcessor.normalize(currentResumeData);

            chrome.storage.local.set({
                resumeData: currentResumeData,
                normalizedData: normalized
            }, () => {
                if (chrome.runtime.lastError) {
                    showToast('Failed to save: ' + chrome.runtime.lastError.message, 'error');
                    return;
                }

                showToast(successMessage, 'success');
            });
        } catch (error) {
            showToast('Failed to save: ' + error.message, 'error');
        }
    }

    function validateJsonData(data) {
        if (!data) return { valid: false, message: 'No data provided' };
        try {
            const norm = ResumeProcessor.normalize(data);
            const missing = [];

            if (!norm.identity?.first_name && !norm.identity?.full_name) missing.push("Name");
            if (!norm.contact?.email) missing.push("Email");

            if (missing.length > 0) {
                return { valid: false, message: `Missing required fields: ${missing.join(', ')}` };
            }
            return { valid: true };
        } catch (error) {
            return { valid: false, message: 'Invalid resume format: ' + error.message };
        }
    }

    function validatePdfFile(file) {
        if (!file) return { valid: false, message: 'No file selected' };
        const name = (file.name || '').toLowerCase();
        if (name.endsWith('.pdf') || name.endsWith('.doc') || name.endsWith('.docx')) {
            return { valid: true };
        }
        return { valid: false, message: 'Invalid format. Must be PDF, DOC, or DOCX' };
    }

    function showToast(message, type = 'info') {
        const toast = document.getElementById('statusToast');
        if (!toast) return;

        toast.textContent = message;
        toast.className = `status-toast ${type} show`;

        setTimeout(() => {
            toast.classList.remove('show');
        }, type === 'error' ? 5000 : 3000);
    }

    // Initialize
    init();
});

    // === PREFERENCES MANAGEMENT ===

    // Load preferences from SettingsManager
    async function loadPreferences() {
        try {
            const settings = await SettingsManager.getAll();

            // Autofill Behavior
            const autofillAfterPageTurn = document.getElementById('autofillAfterPageTurn');
            if (autofillAfterPageTurn) {
                autofillAfterPageTurn.value = settings.autofillAfterPageTurn || 'manually';
            }

            const preserveUserInput = document.getElementById('preserveUserInput');
            if (preserveUserInput) {
                preserveUserInput.checked = settings.preserveUserInput !== false;
            }

            const fillEEO = document.getElementById('fillEEO');
            if (fillEEO) {
                fillEEO.checked = settings.fillEEO || false;
            }

            const fillLegal = document.getElementById('fillLegal');
            if (fillLegal) {
                fillLegal.checked = settings.fillLegal || false;
            }

            // UI Settings
            const defaultPluginView = document.getElementById('defaultPluginView');
            if (defaultPluginView) {
                defaultPluginView.value = settings.defaultPluginView || 'expanded';
            }

            const highlightFilledFields = document.getElementById('highlightFilledFields');
            if (highlightFilledFields) {
                highlightFilledFields.checked = settings.highlightFilledFields !== false;
            }

            // Performance Settings
            const autofillDelay = document.getElementById('autofillDelay');
            if (autofillDelay) {
                autofillDelay.value = settings.autofillDelay || 100;
            }

            const retryAttempts = document.getElementById('retryAttempts');
            if (retryAttempts) {
                retryAttempts.value = settings.retryAttempts || 3;
            }

            console.log('[Settings] Preferences loaded:', settings);
        } catch (error) {
            console.error('[Settings] Error loading preferences:', error);
            showToast('Failed to load preferences', 'error');
        }
    }

    // Save preferences
    if (savePreferencesBtn) {
        savePreferencesBtn.addEventListener('click', async () => {
            try {
                const preferences = {
                    autofillAfterPageTurn: document.getElementById('autofillAfterPageTurn')?.value || 'manually',
                    preserveUserInput: document.getElementById('preserveUserInput')?.checked !== false,
                    fillEEO: document.getElementById('fillEEO')?.checked || false,
                    fillLegal: document.getElementById('fillLegal')?.checked || false,
                    defaultPluginView: document.getElementById('defaultPluginView')?.value || 'expanded',
                    highlightFilledFields: document.getElementById('highlightFilledFields')?.checked !== false,
                    autofillDelay: parseInt(document.getElementById('autofillDelay')?.value || 100),
                    retryAttempts: parseInt(document.getElementById('retryAttempts')?.value || 3)
                };

                // Validate
                for (const [key, value] of Object.entries(preferences)) {
                    const validation = SettingsManager.validate(key, value);
                    if (!validation.valid) {
                        showToast(`Invalid ${key}: ${validation.error}`, 'error');
                        return;
                    }
                }

                // Save
                const success = await SettingsManager.setMultiple(preferences);

                if (success) {
                    showToast('Preferences saved successfully!', 'success');
                } else {
                    showToast('Failed to save preferences', 'error');
                }
            } catch (error) {
                console.error('[Settings] Error saving preferences:', error);
                showToast('Failed to save preferences: ' + error.message, 'error');
            }
        });
    }

    // Reset preferences to defaults
    if (resetPreferencesBtn) {
        resetPreferencesBtn.addEventListener('click', async () => {
            if (!confirm('Reset all preferences to default values?')) {
                return;
            }

            try {
                const success = await SettingsManager.resetAll();

                if (success) {
                    await loadPreferences(); // Reload form
                    showToast('Preferences reset to defaults', 'success');
                } else {
                    showToast('Failed to reset preferences', 'error');
                }
            } catch (error) {
                console.error('[Settings] Error resetting preferences:', error);
                showToast('Failed to reset preferences: ' + error.message, 'error');
            }
        });
    }
