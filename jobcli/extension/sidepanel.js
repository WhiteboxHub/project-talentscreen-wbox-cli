document.addEventListener('DOMContentLoaded', () => {
    const resumeInput = document.getElementById('resumeInput');
    const fillFormBtn = document.getElementById('fillFormBtn');
    const viewResumeBtn = document.getElementById('viewResumeBtn');
    const statusDiv = document.getElementById('status');
    const resumePreview = document.getElementById('resumePreview');
    const resumeContent = document.getElementById('resumeContent');
    const profileSelect = document.getElementById('profileSelect');
    const deleteProfileBtn = document.getElementById('deleteProfileBtn');

    // Summary Panel Elements
    const summaryPanelContainer = document.getElementById('summaryPanelContainer');
    const summaryTableBody = document.getElementById('summaryTableBody');
    const applyEditsBtn = document.getElementById('applyEditsBtn');

    // Custom Answers Elements
    const atsSelector = document.getElementById('atsSelector');
    const customAnswersInput = document.getElementById('customAnswersInput');
    const saveCustomAnswersBtn = document.getElementById('saveCustomAnswersBtn');

    // Keep track of the current tab ID logic executes on 
    let activeTabId = null;
    let customAtsAnswers = {
        Generic: {},
        Greenhouse: {},
        Lever: {},
        Workday: {},
        SuccessFactors: {},
        Adp: {},
        Ashby: {},
        SmartRecruiters: {},
        Icims: {},
        Jobvite: {},
        Taleo: {},
        Workable: {},
        BambooHr: {},
        Paycom: {},
        Paychex: {},
        Ultipro: {},
        Linkedin: {},
        Indeed: {},
        Recruitee: {},
        Teamtailor: {},
        Personio: {},
        OracleCloud: {},
        ApplyToJob: {},
        Brassring: {},
        Rippling: {}
    };

    let savedProfiles = {};
    let activeProfileName = null;

    // First load to initialize the extension. 
    // Data is strictly managed through the single source of truth in local storage.
    chrome.storage.local.get(['resumeData', 'aiEnabled', 'customAtsAnswers', 'savedProfiles', 'activeProfileName', 'normalizedData', 'resumeFile'], (result) => {

        // --- 1. Settings Bootstrapping ---
        if (result.aiEnabled) {
            document.getElementById('aiToggle').checked = true;
        }
        if (result.customAtsAnswers) {
            customAtsAnswers = { ...customAtsAnswers, ...result.customAtsAnswers };
        }
        updateCustomAnswersTextarea();

        // --- 2. Profile Bootstrapping ---
        if (result.savedProfiles) {
            savedProfiles = result.savedProfiles;
        }

        // Migrate a legacy install (single profile) to the new multi-profile structure.
        if (!result.savedProfiles && result.resumeData) {
            const legacyName = "resume (legacy)";
            savedProfiles[legacyName] = {
                resumeData: result.resumeData,
                normalizedData: result.normalizedData,
                resumeFile: result.resumeFile
            };
            activeProfileName = legacyName;

            // Re-save immediately
            chrome.storage.local.set({
                savedProfiles: savedProfiles,
                activeProfileName: activeProfileName
            });
        }
        else if (result.activeProfileName) {
            activeProfileName = result.activeProfileName;
        }

        renderProfileDropdown();
    });

    // Handle ATS Selector Change
    atsSelector.addEventListener('change', () => {
        updateCustomAnswersTextarea();
    });

    // Handle Custom Answers Save
    saveCustomAnswersBtn.addEventListener('click', () => {
        const selectedAts = atsSelector.value;
        const inputText = customAnswersInput.value.trim();

        try {
            if (inputText) {
                const parsedJson = JSON.parse(inputText);
                customAtsAnswers[selectedAts] = parsedJson;
            } else {
                customAtsAnswers[selectedAts] = {};
            }

            chrome.storage.local.set({ customAtsAnswers: customAtsAnswers }, () => {
                showStatus('Custom Answers Saved!', 'success');
            });
        } catch (error) {
            showStatus('Invalid JSON format.', 'error');
            console.error('JSON Parse Error:', error);
        }
    });

    function updateCustomAnswersTextarea() {
        const selectedAts = atsSelector.value;
        const data = customAtsAnswers[selectedAts] || {};
        if (Object.keys(data).length === 0) {
            customAnswersInput.value = '';
        } else {
            customAnswersInput.value = JSON.stringify(data, null, 2);
        }
    }

    // Handle AI Toggle
    document.getElementById('aiToggle').addEventListener('change', (e) => {
        chrome.storage.local.set({ aiEnabled: e.target.checked });
    });

    // Render Profile Dropdown and Swap Storage State
    function renderProfileDropdown() {
        const profileNames = Object.keys(savedProfiles);

        profileSelect.innerHTML = ''; // Clear dropdown

        if (profileNames.length === 0) {
            const option = document.createElement('option');
            option.value = "";
            option.textContent = "No Profiles Found - Please Upload";
            profileSelect.appendChild(option);

            deleteProfileBtn.disabled = true;
            fillFormBtn.disabled = true;
            viewResumeBtn.disabled = true;

            const resumeFileName = document.getElementById('resumeFileName');
            if (resumeFileName) resumeFileName.textContent = "Upload PDF/DOCX";

            return;
        }

        profileNames.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            if (name === activeProfileName) {
                option.selected = true;
            }
            profileSelect.appendChild(option);
        });

        deleteProfileBtn.disabled = false;

        // Force the root storage sync to match the actively selected profile
        syncActiveProfileToRoot();
    }

    // Handles the heavy-lifting of keeping the root keys exactly matching the chosen profile's data. 
    // This allows content.js completely agnostic access without knowing about profiles.
    function syncActiveProfileToRoot() {
        if (!activeProfileName || !savedProfiles[activeProfileName]) return;

        const profileData = savedProfiles[activeProfileName];

        chrome.storage.local.set({
            activeProfileName: activeProfileName,
            resumeData: profileData.resumeData,
            normalizedData: profileData.normalizedData,
            resumeFile: profileData.resumeFile
        }, () => {
            enableButtons();
            showStatus(`Profile "${activeProfileName}" Active`, 'success');
            updatePreview(profileData.resumeData);

            const resumeFileName = document.getElementById('resumeFileName');
            if (resumeFileName) {
                resumeFileName.textContent = profileData.resumeFile ? `📎 ${profileData.resumeFile.name}` : "Upload PDF/DOCX";
            }
        });
    }

    // Handle Dropdown Change
    profileSelect.addEventListener('change', (e) => {
        activeProfileName = e.target.value;
        syncActiveProfileToRoot();
    });

    // Handle Profile Deletion
    deleteProfileBtn.addEventListener('click', () => {
        if (activeProfileName && savedProfiles[activeProfileName]) {
            delete savedProfiles[activeProfileName];

            // Pick a new active profile gracefully
            const remainingProfiles = Object.keys(savedProfiles);
            if (remainingProfiles.length > 0) {
                activeProfileName = remainingProfiles[0];
            } else {
                activeProfileName = null;
                // If completely empty, thoroughly flush root keys
                chrome.storage.local.remove(['resumeData', 'normalizedData', 'resumeFile']);
                updatePreview({});
            }

            chrome.storage.local.set({ savedProfiles: savedProfiles }, () => {
                renderProfileDropdown();
            });
        }
    });

    // Handle File Upload (JSON Resume Creation/Overwrite)
    resumeInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            // "frontend.json" -> "frontend"
            const newProfileName = file.name.replace(/\.[^/.]+$/, "");

            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const json = JSON.parse(e.target.result);
                    const normalizedData = ResumeProcessor.normalize(json);

                    // Determine if we need to retain an existing DOCX/PDF
                    let retainedFile = null;
                    if (savedProfiles[newProfileName] && savedProfiles[newProfileName].resumeFile) {
                        retainedFile = savedProfiles[newProfileName].resumeFile;
                    }

                    // Save to the index
                    savedProfiles[newProfileName] = {
                        resumeData: json,
                        normalizedData: normalizedData,
                        resumeFile: retainedFile
                    };

                    activeProfileName = newProfileName;

                    chrome.storage.local.set({ savedProfiles: savedProfiles }, () => {
                        renderProfileDropdown(); // Re-renders dropdown and forcibly syncs data to root
                    });

                } catch (error) {
                    showStatus('Error parsing JSON file.', 'error');
                    console.error(error);
                }
            };
            reader.readAsText(file);
        }
    });

    // Handle Resume File Upload (PDF/DOCX)
    const resumeFileInput = document.getElementById('resumeFileInput');

    if (resumeFileInput) {
        resumeFileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                if (!activeProfileName || !savedProfiles[activeProfileName]) {
                    showStatus('Upload a JSON resume first to create a profile!', 'error');
                    return;
                }

                const reader = new FileReader();
                reader.onload = (e) => {
                    const resumeFileData = {
                        data: e.target.result, // base64 data
                        name: file.name,
                        type: file.type,
                        size: file.size
                    };

                    // Append the file specifically to the Active Profile instead of loosely globally.
                    savedProfiles[activeProfileName].resumeFile = resumeFileData;

                    chrome.storage.local.set({ savedProfiles: savedProfiles }, () => {
                        syncActiveProfileToRoot();
                    });
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Handle manual form fill (Fallback)
    fillFormBtn.addEventListener('click', () => {
        chrome.storage.local.get(['resumeData', 'aiEnabled'], (result) => {
            if (result.resumeData) {
                chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                    const normalizedData = ResumeProcessor.normalize(result.resumeData);
                    activeTabId = tabs[0].id; // Save tab ID for reporting
                    chrome.tabs.sendMessage(activeTabId, {
                        action: "fill_form",
                        data: result.resumeData,
                        normalizedData: normalizedData,
                        aiEnabled: result.aiEnabled || false,
                        manual: true
                    }, (response) => {
                        if (chrome.runtime.lastError) {
                            showStatus('Could not force fill. Try refreshing.', 'error');
                        } else {
                            showStatus('Form filling initiated!', 'success');
                        }
                    });
                });
            } else {
                showStatus('No resume data found.', 'error');
            }
        });
    });

    // Listen for fill reports from the content scripts
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === 'fill_report') {
            activeTabId = sender.tab.id;
            renderSummaryTable(request.report);
            sendResponse({ status: 'ok' });
        }
    });

    // Handle "Apply Edits" from the Side Panel
    applyEditsBtn.addEventListener('click', () => {
        const editedData = [];
        const rows = summaryTableBody.querySelectorAll('tr');

        rows.forEach(row => {
            const fieldId = row.dataset.fieldid;
            const input = row.querySelector('.edit-input');
            if (fieldId && input && input.value !== undefined) {
                editedData.push({ id: fieldId, value: input.value });
            }
        });

        if (activeTabId && editedData.length > 0) {
            chrome.tabs.sendMessage(activeTabId, {
                action: 'apply_edits',
                edits: editedData
            }, (response) => {
                showStatus('Edits applied successfully!', 'success');
            });
        }
    });

    function renderSummaryTable(reportData) {
        summaryTableBody.innerHTML = ''; // Clear previous

        if (!reportData || reportData.length === 0) {
            summaryPanelContainer.classList.add('hidden');
            return;
        }

        reportData.forEach(item => {
            const tr = document.createElement('tr');
            tr.dataset.fieldid = item.id;

            // Field Label cell
            const tdLabel = document.createElement('td');
            tdLabel.textContent = item.label.substring(0, 20) + (item.label.length > 20 ? '...' : '');
            tdLabel.title = item.label;

            // Edit Value cell
            const tdValue = document.createElement('td');
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'edit-input';
            input.value = item.value || '';
            tdValue.appendChild(input);

            // Status Indicator cell
            const tdStatus = document.createElement('td');
            let statusBadge = '';

            if (item.status === 'filled') {
                statusBadge = `<span class="badge badge-green">${item.confidence}%</span>`;
            } else if (item.status === 'low_confidence') {
                statusBadge = `<span class="badge badge-yellow">${item.confidence}%</span>`;
            } else if (item.status === 'unmatched_required') {
                statusBadge = `<span class="badge badge-red">Missed</span>`;
            }

            tdStatus.innerHTML = statusBadge;

            tr.appendChild(tdLabel);
            tr.appendChild(tdValue);
            tr.appendChild(tdStatus);
            summaryTableBody.appendChild(tr);
        });

        summaryPanelContainer.classList.remove('hidden');
    }

    // Toggle Preview
    viewResumeBtn.addEventListener('click', () => {
        resumePreview.classList.toggle('hidden');
        viewResumeBtn.textContent = resumePreview.classList.contains('hidden')
            ? 'View Stored Data'
            : 'Hide Data';
    });

    function showStatus(msg, type) {
        statusDiv.textContent = msg;
        statusDiv.className = `status-message status-${type}`;
        statusDiv.classList.remove('hidden');
        setTimeout(() => {
            statusDiv.classList.add('hidden');
        }, 3000);
    }

    function enableButtons() {
        fillFormBtn.disabled = false;
        viewResumeBtn.disabled = false;
    }

    function updatePreview(data) {
        const normalized = ResumeProcessor.normalize(data);
        resumeContent.textContent = JSON.stringify({
            _normalized: normalized,
            _raw: data
        }, null, 2);
    }
});
