/**
 * genericStrategy.js
 * Default strategy for applying resume data to standard job application forms.
 */
class GenericStrategy {
    constructor() {
        this.CONFIDENCE_THRESHOLD = 70;
        this._hasUploadedResume = false;

        // Field Mapping Dictionary
        this.FIELD_MAPPING = {
            "identity.first_name": ["first_name", "first name", "fname", "given name"],
            "identity.middle_name": ["middle_name", "middle name", "m.i.", "middle initial"],
            "identity.last_name": ["last_name", "last name", "lname", "surname", "family name"],
            "identity.full_name": ["name", "fullname", "full_name", "applicant name"],
            "identity.pronouns": ["pronouns", "preferred pronouns", "gender pronouns"],
            "contact.email": ["email", "e-mail", "mail", "email address"],
            "contact.phone": ["phone", "tel", "mobile", "cell", "contact", "phone number"],
            "contact.linkedin": ["linkedin", "linkedin url", "linkedin profile"],
            "contact.github": ["github", "github profile", "github url"],
            "contact.portfolio": ["website", "url", "portfolio", "link", "personal website"],
            "contact.address": ["address", "street", "address line 1"],
            "contact.city": ["city", "town", "location"],
            "contact.zip_code": ["zip", "postal", "code", "zip code"],
            "contact.state": ["state", "province", "region"],
            "contact.country": ["country", "country format", "country/region", "location country"],
            "contact.location": ["current location", "location", "lives in", "city, state"],
            "summary.short": ["summary", "about", "bio", "description"],
            "summary.professional_statement": ["describe your relevant experiences", "professional statement", "highlight your industrial projects", "research record", "relevant experiences", "industrial projects", "3-4 sentences", "highlight your projects", "highlight your industrial projects and research record"],
            "summary.motivation": ["multiple roles", "motivation for each", "order them", "apply to multiple roles", "explain your motivation"],
            "employment.current_role": ["job title", "current role", "current title", "position title", "role", "position"],
            "employment.current_company": ["company", "employer", "current company", "organization", "company name"],
            "employment.years_total": ["total years of experience", "total years experience", "number of years", "years of relevant experience"],
            "employment.work_description": ["responsibilities", "work description", "job description", "summary", "description", "work highlights"],
            "employment.start_date": ["work start", "employment start", "job start", "start date"],
            "employment.end_date": ["work end", "employment end", "job end", "end date"],
            // Dropdown specific / Additional fields
            "education_flat.degree": ["degree", "level of education", "educational attainment"],
            "education_flat.institution": ["school", "university", "college", "institution"],
            "education_flat.major": ["major", "field of study", "specialization", "discipline"],
            "education_flat.start_date": ["education start", "edu start", "graduation date", "education start date"],
            "education_flat.end_date": ["education end", "edu end", "graduation date", "education end date"],
            "identity.gender": ["gender", "sex", "gender identity", "what is your gender", "sexual identity"],
            "identity.ethnicity": ["ethnicity", "race", "ethnic", "racial", "race/ethnicity", "self-identification", "what is your race"],
            "identity.hispanic_latino": ["hispanic", "latino", "hispanic or latino"],
            "identity.veteran_status": ["veteran", "military", "protected veteran", "veteran status", "i am not a veteran"],
            "identity.disability_status": ["disability", "handicap", "voluntary self-identification", "physical or mental impairment"],
            "identity.sexual_orientation": ["sexual orientation", "orientation", "sexual identity"],
            "identity.transgender_status": ["transgender", "transgender status"],
            "identity.sponsorship_required": ["sponsorship", "sponsor", "visa", "need sponsorship", "require sponsorship for employment visa status", "require employment visa sponsorship", "now or will you in the future require"],
            "identity.authorized_to_work": ["authorized to work", "legally authorized", "work authorization", "authorized to work in the united states", "eligible to work", "legal right to work"],
            "identity.relocation_open": ["open to relocation", "willing to relocate", "relocate", "open to relocate"],
            "availability.start_date": ["start date", "availability", "soonest start", "available to start", "soonest", "soonest you can start"],
            "summary.source": ["how did you hear", "how did you find out", "source", "how_did_you_hear"],
            "summary.onsite_sunnyvale": ["sunnyvale", "on-site", "work on-site", "sunnyvale office", "sunnyvale, ca office"],
            "summary.ai_tool_experience": ["claude", "cursor", "ai tool", "claude code"],
            "identity.security_clearance_eligible": ["obtain and maintain", "government clearance", "security clearance", "u.s. government clearance", "requires u.s citizenship"],
            "contact.linkedin_manual": ["urls[linkedin]", "linkedin_url"],
            "contact.github_manual": ["urls[github]", "github_url"],
            "contact.portfolio_manual": ["urls[portfolio]", "portfolio_url"]
        };
    }

    normalizeYesNoDecline(valueStr) {
        if (!valueStr) return '';
        const val = String(valueStr).toLowerCase().trim();

        if (val === 'no' || val === 'false' || val === 'n' || val.startsWith('no,') ||
            val.includes('not a protected') || val.includes('do not have') || val.includes("don't have") ||
            val.includes('no, i am not') || val.includes('not hispanic') ||
            val === 'not_a_veteran' || val === 'no_disability') {
            return 'no';
        }

        if (val === 'yes' || val === 'true' || val === 'y' || val.startsWith('yes,') ||
            val.includes('i am a protected veteran') || val.includes('have a disability') ||
            val.includes('hispanic or latino') || val.includes('yes, i am')) {
            return 'yes';
        }

        if (val.includes('decline') || val.includes('prefer not') || val.includes('choose not') || val.includes('wish not')) {
            return 'decline';
        }

        return val;
    }

    getUSVariations() {
        return ['us', 'usa', 'united states', 'united states of america', 'united states (usa)', 'us (usa)', 'u.s.a.', 'u.s.'];
    }

    getStateVariations(state) {
        const states = {
            'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
            'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
            'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
            'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
            'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
            'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
            'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
            'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
            'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
            'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY'
        };
        const s = String(state).toLowerCase().trim();
        return [s, states[s], Object.keys(states).find(key => states[key].toLowerCase() === s)].filter(Boolean);
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    getNestedValue(obj, path) {
        if (!obj || !path) return null;
        return path.split('.').reduce((acc, part) => acc && acc[part], obj);
    }

    handleFileUpload(resumeFile) {
        if (!resumeFile || !resumeFile.data) return;

        // NEW: Persistence check across strategy instances/re-injections using sessionStorage
        const sessionKey = `af_uploaded_${window.location.hostname}`;
        if (sessionStorage.getItem(sessionKey)) {
            // 
            return;
        }

        const fileInputs = document.querySelectorAll('input[type="file"]');
        for (const input of fileInputs) {
            // Skip if the input already has a file or has our marker attribute
            if ((input.files && input.files.length > 0) || input.dataset.afUploaded === 'true') continue;

            const features = this.extractFeatures(input);
            const labelTxt = features.label_text.toLowerCase();
            const containerTxt = input.closest('div, fieldset')?.innerText?.toLowerCase() || "";
            const parentContainerTxt = input.parentElement?.parentElement?.innerText?.toLowerCase() || "";
            const combinedTxt = labelTxt + " " + containerTxt + " " + parentContainerTxt + " " + (input.name || "").toLowerCase() + " " + (input.id || "").toLowerCase();

            // Match resume keywords but EXCLUDE fields clearly marked for cover letters
            const resumeKeywords = ["resume", "cv", "curriculum", "attach", "upload", "file", "document", "application"];
            const isResumeField = resumeKeywords.some(kw => combinedTxt.includes(kw));
            const isCoverLetterField = combinedTxt.includes("cover");

            if (isResumeField && !isCoverLetterField) {


                try {
                    // Convert base64 Data URL to Blob
                    const byteString = atob(resumeFile.data.split(',')[1]);
                    const mimeString = resumeFile.data.split(',')[0].split(':')[1].split(';')[0];
                    const ab = new ArrayBuffer(byteString.length);
                    const ia = new Uint8Array(ab);
                    for (let i = 0; i < byteString.length; i++) {
                        ia[i] = byteString.charCodeAt(i);
                    }
                    const blob = new Blob([ab], { type: mimeString });
                    const file = new File([blob], resumeFile.name, { type: mimeString });

                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    input.files = dataTransfer.files;

                    ['change', 'input', 'blur'].forEach(ev => {
                        input.dispatchEvent(new Event(ev, { bubbles: true }));
                    });

                    // Set both the DOM attribute and the sessionStorage flag
                    input.dataset.afUploaded = 'true';
                    sessionStorage.setItem(sessionKey, 'true');
                    this._hasUploadedResume = true;
                    break;
                } catch (e) {
                    console.error("AutoFill: Error attaching file", e);
                }
            }
        }
    }
    getPageContext() {
        const title = document.title || "";
        const h1 = document.querySelector('h1')?.innerText || "";

        // Attempt to find company name from common meta tags or structural elements
        const metaCompany = document.querySelector('meta[property="og:site_name"]')?.content ||
            document.querySelector('meta[name="author"]')?.content ||
            document.querySelector('.company-name, .brand-name, #logo img')?.alt || "";

        return {
            pageTitle: title,
            headerText: h1,
            companyName: metaCompany,
            url: window.location.href
        };
    }

    handleInitialEntry() {
        const entryPatterns = [
            'apply', 'apply now', 'apply for this job', 'apply manually',
            'fill manually', 'enter manually', 'start application', 'start'
        ];

        const selectors = [
            'button:not([style*="display: none"])',
            'a.btn',
            'a[role="button"]',
            '[role="button"]',
            '[data-automation-id*="apply" i]',
            '[data-automation-id*="Apply"]',
            '[data-automation-id*="manual" i]',
            'input[type="submit"]'
        ];

        const buttons = Array.from(document.querySelectorAll(selectors.join(', ')));

        // Deduplicate buttons (in case they match multiple selectors)
        const uniqueButtons = Array.from(new Set(buttons));

        // Filter out hidden and disabled buttons, and sort by visibility
        const visibleButtons = uniqueButtons.filter(b => {
            return b.offsetParent !== null && !b.disabled;
        }).sort((a, b) => {
            // Prioritize buttons with higher z-index
            const getZIndex = (el) => parseInt(window.getComputedStyle(el).zIndex || 0, 10);
            return getZIndex(b) - getZIndex(a);
        });

        // 

        // Find the best candidate for an entry button
        const entryBtn = visibleButtons.find(b => {
            const text = (b.innerText || b.value || b.getAttribute('aria-label') || b.textContent || "").toLowerCase().trim();
            const automationId = (b.getAttribute('data-automation-id') || "").toLowerCase();
            const className = (b.className || "").toLowerCase();
            const href = (b.getAttribute('href') || "").toLowerCase();

            // EXCLUSION: Never click LinkedIn apply buttons
            if (text.includes('linkedin') ||
                text.includes('apply with linkedin') ||
                text.includes('easy apply') ||
                className.includes('linkedin') ||
                href.includes('linkedin') ||
                b.querySelector('img[alt*="linkedin" i]') ||
                b.querySelector('svg[aria-label*="linkedin" i]')) {
                console.log('[GenericStrategy] Skipping LinkedIn button:', text);
                return false;
            }

            // EXCLUSION: Skip other third-party apply buttons
            if (text.includes('indeed') ||
                text.includes('apply with indeed') ||
                className.includes('indeed')) {
                console.log('[GenericStrategy] Skipping Indeed button:', text);
                return false;
            }

            // Priority 1: Clear "Apply Manually" indicators (to skip popups)
            if (text.includes('apply manually') || text.includes('fill manually') || text.includes('enter manually')) {
                //
                return true;
            }
            if (automationId === 'applymanually' || automationId.includes('manual')) {
                //
                return true;
            }

            // Priority 2: Exact match for standard "Apply" buttons
            if (entryPatterns.some(p => text === p)) {
                // 
                return true;
            }

            // Priority 3: Partial match
            const matches = entryPatterns.some(p => text.includes(p));
            if (matches) {
                // 
            }
            return matches;
        });

        if (entryBtn) {
            // );
            // Ensure button is in view before clicking
            // entryBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => {
                // 
                entryBtn.click();
            }, 200);
            return true;
        }

        // 
        return false;
    }

    async execute(normalizedData, resumeFile = null) {
        // 
        // 
        // 
        // 
        // 
        // 
        // 
        // 

        // --- Handle Initial Entry (Popups or Apply buttons) ---
        const entryClicked = this.handleInitialEntry();
        if (entryClicked) {
            // Give the DOM a moment to react if we clicked a popup
            await this.sleep(1000);
        }

        // --- Handle Resume Attachment ---
        if (resumeFile) {
            this.handleFileUpload(resumeFile);
        }

        // --- Handle Dynamic Entry Addition ---
        const handleAddButtons = () => {
            const sections = [
                {
                    data: normalizedData.employment?.history || [],
                    selectors: ['.work-entry', '.experience-entry', 'fieldset[id*="work"]', 'div[id*="work-experience"]'],
                    btnPatterns: ['Add Experience', 'Add Work', 'Add Another', 'Add Job']
                },
                {
                    data: normalizedData.education || [],
                    selectors: ['.education-entry', 'fieldset[id*="edu"]', 'div[id*="education"]'],
                    btnPatterns: ['Add Education', 'Add School', 'Add Another']
                }
            ];

            sections.forEach(section => {
                if (section.data.length <= 1) return;

                // Count existing containers
                let containerCount = 0;
                for (const sel of section.selectors) {
                    const found = document.querySelectorAll(sel).length;
                    if (found > containerCount) containerCount = found;
                }

                if (containerCount > 0 && containerCount < section.data.length) {
                    // Try to find the "Add" button
                    const buttons = Array.from(document.querySelectorAll('button, a, span.btn, .add-btn'));
                    const addBtn = buttons.find(b => {
                        const text = b.innerText || "";
                        return section.btnPatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
                    });

                    if (addBtn) {
                        // 
                        addBtn.click();
                        // We click only once per execute cycle. 
                        // The MutationObserver in content.js will trigger execute() again if the DOM changes.
                    }
                }
            });
        };

        handleAddButtons();

        const inputs = document.querySelectorAll('input, textarea, select');
        let fillCount = 0;
        let totalInteractable = 0;
        let educationGroupTracker = new Map();
        let employmentGroupTracker = new Map();

        for (const input of inputs) {
            // Allow hidden fields if they have a name or id (likely state holders for custom dropdowns)
            if (input.type === 'hidden' && !input.id && !input.name && !input.getAttribute('data-automation-id')) continue;
            if (input.disabled || input.readOnly) continue;
            
            // Skip Select2-hidden selects
            if (
                input.tagName === 'SELECT' &&
                (input.classList.contains('select2-hidden-accessible') ||
                    input.getAttribute('aria-hidden') === 'true' && input.style.display === 'none')
            ) continue;

            totalInteractable++;

            // Skip fields the user has manually edited
            if (input.dataset.afUserLocked === 'true') continue;

            // Handle Radio/Checkbox
            if (input.type === 'radio' || input.type === 'checkbox') {
                this.handleRadioCheckbox(input, normalizedData);
                if (input.checked) fillCount++;
                continue;
            }

            // Skip inputs that are already filled (unless forced)
            if (input.value && input.value.trim() !== '') {
                fillCount++;
                continue;
            }

            let match = this.findValueForInput(input, normalizedData);

            if (match && match.fieldKey === 'identity.middle_name' && !match.value) {
                continue;
            }

            // --- Multi-Entry Grouping Logic (Education & Employment) ---
            if (match && match.fieldKey) {
                const isEdu = match.fieldKey.startsWith('education_flat');
                const isEmp = match.fieldKey.startsWith('employment.');

                if (isEdu || isEmp) {
                    const sourceData = isEdu ? normalizedData.education : (normalizedData.employment?.history || []);

                    if (sourceData && sourceData.length > 0) {
                        const features = this.extractFeatures(input);
                        const context = (features.label_text + " " + features.nearby_text + " " + (input.name || "")).toLowerCase();
                        let bestIdx = -1;

                        // 1. Context Match
                        let highestScore = 0;
                        sourceData.forEach((item, index) => {
                            let score = 0;
                            const normVal = isEdu ? (item.normDegree + " " + item.normMajor) : (item.normCompany + " " + item.normTitle);
                            if (normVal && context.includes(normVal.toLowerCase())) score += 50;
                            if (item.startDate && context.includes(item.startDate.split('-')[0])) score += 20;

                            if (score > highestScore) {
                                highestScore = score;
                                bestIdx = index;
                            }
                        });

                        // 2. Name-based Index
                        if (bestIdx === -1) {
                            const indexMatch = (input.name || "").match(/\d+/);
                            if (indexMatch) {
                                const foundIdx = parseInt(indexMatch[0]);
                                if (foundIdx < sourceData.length) bestIdx = foundIdx;
                            }
                        }

                        // 3. Proximity Fallback
                        if (bestIdx === -1) {
                            const tracker = isEdu ? educationGroupTracker : employmentGroupTracker;
                            const selector = isEdu ? '.education-entry, fieldset, .school-entry, [data-automation-id*="education"]' : '.work-entry, .experience-entry, fieldset, .employment-entry, .job-entry, [data-automation-id*="workExperience"]';
                            const container = input.closest(`${selector}, div[id*="edu"], div[id*="work"], div[id*="employment"], section[id*="experience"]`);

                            const containers = Array.from(document.querySelectorAll(selector));
                            let groupId = container ? containers.indexOf(container) : "global";
                            if (groupId === -1) groupId = "misc-" + (isEdu ? "edu" : "emp");

                            if (!tracker.has(groupId)) {
                                tracker.set(groupId, tracker.size % sourceData.length);
                            }
                            bestIdx = tracker.get(groupId);
                        }

                        if (bestIdx !== -1) {
                            const subKey = match.fieldKey.split('.')[1];
                            if (isEdu) {
                                const eduKeyMap = { 'major': 'area', 'start_date': 'startDate', 'end_date': 'endDate' };
                                const targetKey = eduKeyMap[subKey] || subKey;
                                match.value = sourceData[bestIdx][targetKey] || sourceData[bestIdx][subKey] || sourceData[bestIdx].degree || sourceData[bestIdx].major || "";
                            } else {
                                const empKeyMap = { 'current_role': 'position', 'current_company': 'name', 'work_description': 'summary', 'start_date': 'startDate', 'end_date': 'endDate' };
                                const targetKey = empKeyMap[subKey] || subKey;
                                match.value = sourceData[bestIdx][targetKey] || sourceData[bestIdx][subKey] || sourceData[bestIdx].company || sourceData[bestIdx].title || "";
                            }
                            match.confidence = 95;
                        }
                    }
                }

                if (match && match.value) {
                    if (match.confidence >= this.CONFIDENCE_THRESHOLD) {
                        this.setInputValue(input, match.value, 'green');
                        fillCount++;
                    }
                } else {
                    if (input.required || input.getAttribute('aria-required') === 'true') {
                        this.highlightUnmatchedRequired(input);
                    }
                }

                if (match && match.confidence >= this.CONFIDENCE_THRESHOLD) {
                    await this.sleep(Math.floor(Math.random() * 200) + 100);
                }
            }
        }

        // Report progress to side panel
        if (typeof chrome !== 'undefined' && chrome.runtime?.id) {
            chrome.runtime.sendMessage({ action: 'update_progress', filled: fillCount, total: totalInteractable });
        }

        return { filled: fillCount, total: totalInteractable };
    }

    findCustomAnswer(input, hostname, customAtsAnswers) {
        if (!customAtsAnswers) return null;

        const features = this.extractFeatures(input);
        const combinedText = `${features.name_attr} ${features.id_attr} ${features.label_text} ${features.aria_label}`.toLowerCase();

        // Determine which ATS key we are currently under
        let atsKey = "Global";
        if (hostname.includes("greenhouse.io")) atsKey = "Greenhouse";
        else if (hostname.includes("lever.co")) atsKey = "Lever";
        else if (hostname.includes("workday.com") || hostname.includes("myworkdayjobs.com")) atsKey = "Workday";

        // Check platform specific answers first, then fallback to Global
        const answerSets = [customAtsAnswers[atsKey], customAtsAnswers["Global"]];

        for (const answers of answerSets) {
            if (answers && typeof answers === 'object') {
                // Iterate through keys defined by user
                for (const [questionKeyword, customValue] of Object.entries(answers)) {
                    if (combinedText.includes(questionKeyword.toLowerCase())) {
                        return { value: customValue, confidence: 100 };
                    }
                }
            }
        }
        return null;
    }

    extractFeatures(input) {
        // Normalizes camelCase, snake_case, param-case to spaces so \b word boundaries work flawlessly
        const normalizeIdName = str => (str || "").replace(/[-_]/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();

        return {
            name_attr: normalizeIdName(input.name),
            id_attr: normalizeIdName(input.id),
            placeholder: (input.placeholder || "").toLowerCase(),
            aria_label: (input.getAttribute('aria-label') || "").toLowerCase(),
            label_text: (this.getLabelText(input) || "").toLowerCase(),
            nearby_text: (this.getNearbyText(input) || "").toLowerCase(),
            input_type: (input.type || "text").toLowerCase(),
            normalized_combined: (typeof ResumeProcessor !== 'undefined') ?
                ResumeProcessor.normalizeText(
                    `${normalizeIdName(input.name)} ${normalizeIdName(input.id)} ${this.getLabelText(input)} ${input.getAttribute('aria-label') || ""}`
                ) : ""
        };
    }

    calculateConfidence(features, keywords, fieldKey) {
        let keywordScore = 0;
        const keywordWeights = {
            name_attr: 40,
            id_attr: 40,
            aria_label: 35,
            label_text: 60, // Increased from 35 to favor explicit questions
            placeholder: 25
        };

        let matchedPrimaryFeature = false;
        const escapeRegExp = string => string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

        keywords.forEach(keyword => {
            const kw = keyword.toLowerCase();
            // Demands a strict word boundary. Fixes catastrophic bugs where searching for the "state" field internally matched the phrase "United States" in Veteran surveys.
            const wordBoundaryRegex = new RegExp('(?:^|\\b)' + escapeRegExp(kw) + '(?:\\b|$)', 'i');

            for (const [featureName, weight] of Object.entries(keywordWeights)) {
                const featureValue = features[featureName];
                if (featureValue && wordBoundaryRegex.test(featureValue)) {
                    keywordScore += weight;
                    matchedPrimaryFeature = true;
                    // Boost if it's the only thing in the attribute (ignoring asterisks)
                    if (featureValue === kw || featureValue.replace(/[*:\s]/g, '') === kw) {
                        keywordScore += weight * 0.5;
                    }
                }
            }
        });
        keywordScore = Math.min(keywordScore, 70);

        // Negative weight: if this is a Full Name attempt but field has "middle", penalize heavily
        if (fieldKey === "identity.full_name") {
            const combinedTxt = `${features.name_attr} ${features.id_attr} ${features.label_text}`.toLowerCase();
            if (combinedTxt.includes("middle")) {
                keywordScore -= 50;
            }
        }

        // Prevent Full Name, First Name, Last Name from matching referral/reference fields
        if (fieldKey === "identity.full_name" || fieldKey === "identity.first_name" || fieldKey === "identity.last_name") {
            const combinedTxt = `${features.name_attr} ${features.id_attr} ${features.label_text}`.toLowerCase();
            if (combinedTxt.includes("refer") || combinedTxt.includes("manager") || combinedTxt.includes("spouse") || combinedTxt.includes("partner")) {
                keywordScore -= 100;
            }
        }

        let contextScore = 0;
        keywords.forEach(keyword => {
            if (features.nearby_text && features.nearby_text.includes(keyword.toLowerCase())) {
                contextScore += 5;
            }
        });
        contextScore = Math.min(contextScore, 15);

        let typeScore = 0;
        const isEmailField = fieldKey === 'email';
        const isPhoneField = fieldKey === 'phone';
        const isUrlField = fieldKey.includes('url') || fieldKey.includes('linkedin') || fieldKey.includes('github') || fieldKey === 'website';

        if (isEmailField && features.input_type === 'email') typeScore = 15;
        else if (isPhoneField && features.input_type === 'tel') typeScore = 15;
        else if (isUrlField && features.input_type === 'url') typeScore = 15;
        else typeScore = 5;

        let confidence = keywordScore + contextScore + typeScore;

        if (!matchedPrimaryFeature) {
            confidence = Math.min(confidence, 30);
        }

        return Math.min(Math.round(confidence), 100);
    }

    findValueForInput(input, normalizedData) {
        const features = this.extractFeatures(input);

        // Debug logging for every field being checked
        const fieldName = input.name || input.id || '(unnamed)';
        const fieldLabel = this.getLabelText(input) || '(no label)';
        // 

        // --- 1. Attempt Domain-Specific Dynamic Reverse Lookups ---
        // Guard: skip this if the label matches a professional statement question.
        // (The label may contain "experiences" which would falsely trigger the years lookup.)
        const PROFESSIONAL_STATEMENT_PHRASES = [
            "describe your relevant experiences",
            "industrial projects",
            "research record",
            "3-4 sentences",
            "highlight your",
            "professional statement"
        ];
        const isProfessionalStatementField = PROFESSIONAL_STATEMENT_PHRASES.some(phrase =>
            features.label_text.includes(phrase) ||
            features.nearby_text.includes(phrase) ||
            features.aria_label.includes(phrase)
        );

        const MOTIVATION_PHRASES = [
            "multiple roles",
            "motivation for each",
            "order them",
            "apply to multiple roles",
            "explain your motivation"
        ];
        const isMotivationField = MOTIVATION_PHRASES.some(phrase =>
            features.label_text.includes(phrase) ||
            features.nearby_text.includes(phrase) ||
            features.aria_label.includes(phrase)
        );

        if (!isProfessionalStatementField && (features.normalized_combined.includes("year") || features.normalized_combined.includes("experience"))) {
            if (normalizedData.reverse_maps) {
                // Check skills first
                for (const [skill, years] of Object.entries(normalizedData.reverse_maps.skill_to_years)) {
                    if (features.normalized_combined.includes(skill)) {
                        return { value: years.toString(), confidence: 95 };
                    }
                }
                // Check titles/companies
                for (const [company, months] of Object.entries(normalizedData.reverse_maps.company_to_duration)) {
                    if (features.normalized_combined.includes(company)) {
                        return { value: Math.round(months / 12).toString(), confidence: 90 };
                    }
                }
                for (const [title, months] of Object.entries(normalizedData.reverse_maps.title_to_duration)) {
                    if (features.normalized_combined.includes(title)) {
                        return { value: Math.round(months / 12).toString(), confidence: 90 };
                    }
                }
            }
        }

        // Fast-path: if this is clearly a professional statement field, return it directly
        if (isProfessionalStatementField && normalizedData.summary?.professional_statement) {
            // : "${normalizedData.summary.professional_statement.substring(0, 50)}..."`);
            return {
                value: normalizedData.summary.professional_statement,
                confidence: 100,
                fieldKey: 'summary.professional_statement'
            };
        }

        // Fast-path: if this is clearly a motivation/multiple-roles field, return it directly
        if (isMotivationField && normalizedData.summary?.motivation) {
            // : "${normalizedData.summary.motivation.substring(0, 50)}..."`);
            return {
                value: normalizedData.summary.motivation,
                confidence: 100,
                fieldKey: 'summary.motivation'
            };
        }

        // --- 2. Standard Heuristic Matching ---
        let bestMatch = { value: null, confidence: 0 };

        for (const [fieldKey, keywords] of Object.entries(this.FIELD_MAPPING)) {
            const confidence = this.calculateConfidence(features, keywords, fieldKey);

            if (confidence > bestMatch.confidence) {
                const value = this.getNestedValue(normalizedData, fieldKey);

                if (value !== undefined && value !== null) {
                    bestMatch = { value, confidence, fieldKey };
                    //  = "${String(value).substring(0, 40)}..."`);
                }
            }
        }

        if (bestMatch.confidence > 0) {
            // `);
            return bestMatch;
        } else {
            // --- Custom Hardcoded Fallbacks for High-Confidence Questions ---
            if (features.normalized_combined.includes("government clearance") ||
                (features.normalized_combined.includes("obtain") && features.normalized_combined.includes("maintain") && features.normalized_combined.includes("clearance"))) {
                // : "Yes"`);
                return { value: "Yes", confidence: 95, fieldKey: "identity.security_clearance_eligible" };
            }

            // Fallback for Authorized to Work (Default: Yes)
            if (features.normalized_combined.includes("authorized") && features.normalized_combined.includes("work")) {
                // : "Yes"`);
                return { value: "Yes", confidence: 90, fieldKey: "identity.authorized_to_work" };
            }

            // Fallback for Sponsorship (Default: No)
            if (features.normalized_combined.includes("sponsorship") || features.normalized_combined.includes("visa")) {
                // : "No"`);
                return { value: "No", confidence: 90, fieldKey: "identity.sponsorship_required" };
            }

            // Fallback for Relocation (Default: Yes)
            if (features.normalized_combined.includes("relocation") || features.normalized_combined.includes("relocate")) {
                // : "Yes"`);
                return { value: "Yes", confidence: 85, fieldKey: "identity.relocation_open" };
            }

            // 
            return null;
        }
    }

    /**
     * Handle Radio and Checkbox inputs
     */
    handleRadioCheckbox(input, normalizedData) {
        const match = this.findValueForInput(input, normalizedData);
        if (!match || (!match.value && match.value !== "")) return;

        const rawVal = String(match.value).toLowerCase();
        const val = this.normalizeYesNoDecline(rawVal);
        const labelText = (this.getLabelText(input) || "").toLowerCase();

        if (input.type === 'radio') {
            // Avoid matching 'no' to any label that just contains 'no' (like 'unknown')
            const isExactNoMatch = (val === 'no' && (labelText === 'no' || labelText === 'n' || labelText.includes('not a protected veteran') || labelText.includes('not hispanic') || labelText.includes('no, i am not') || labelText.includes("no, i don't") || labelText.includes("do not have a disability")));
            const isExactYesMatch = (val === 'yes' && (labelText === 'yes' || labelText === 'y' || labelText.includes('yes,') || labelText.includes('i am a protected veteran') || labelText.includes('hispanic or latino')));

            const isPositiveMatch =
                isExactNoMatch || isExactYesMatch ||
                (val === 'male' && labelText === 'male') ||
                (val === 'female' && labelText === 'female') ||
                (val === 'non-binary' && labelText.includes('non-binary')) ||
                (val === 'decline' && (labelText.includes('decline') || labelText.includes('choose not') || labelText.includes('wish not') || labelText.includes('prefer not'))) ||
                (val.includes('he/him') && labelText.includes('he/him')) ||
                (val.includes('she/her') && labelText.includes('she/her')) ||
                (val !== 'no' && val !== 'yes' && val !== 'decline' && val.length > 2 && labelText.includes(val)); // only use broad includes if it's not a short affirmative/negative

            if (isPositiveMatch) {
                input.checked = true;
                this.setInputValue(input, null, 'green'); // Visual feedback
            }
        } else if (input.type === 'checkbox') {
            if (val === 'yes' || val === 'true' || val === '1') {
                input.checked = true;
                this.setInputValue(input, null, 'green');
            }
        }
    }

    getLabelText(input) {
        if (!input) return '';
        if (input.parentElement && input.parentElement.tagName === 'LABEL') {
            return input.parentElement.innerText;
        }
        if (input.id) {
            const label = document.querySelector(`label[for="${input.id}"]`);
            if (label) return label.innerText;
        }
        const labeledBy = input.getAttribute('aria-labelledby');
        if (labeledBy) {
            const labelElement = document.getElementById(labeledBy);
            if (labelElement) return labelElement.innerText;
        }
        return '';
    }

    getNearbyText(input) {
        if (!input) return '';
        let container = input.parentElement;
        let iterations = 0;
        while (container && iterations < 2) {
            const text = container.innerText || "";
            if (text.length > 0 && text.length < 200) {
                return text;
            }
            container = container.parentElement;
            iterations++;
        }
        return '';
    }

    setInputValue(input, value, highlightType = 'green') {
        if (!input || (!value && highlightType !== 'red')) return;

        if (value) {
            if (input.tagName === 'SELECT') {
                this.setSelectValue(input, value);
            } else {
                // Use the native setter to bypass React's value interception
                const proto = input.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;

                if (nativeSetter) {
                    nativeSetter.call(input, value);
                } else {
                    input.value = value;
                }

                // Also update the value tracker if it exists (React 15/16+)
                const tracker = input._valueTracker;
                if (tracker) {
                    tracker.setValue('');
                }
            }

            // Dispatch events to satisfy modern frameworks
            ['input', 'change', 'blur'].forEach(eventType => {
                input.dispatchEvent(new Event(eventType, { bubbles: true, composed: true }));
            });
        }

        const originalBg = input.style.backgroundColor;
        const originalBorder = input.style.border;

        if (highlightType === 'green') {
            input.style.backgroundColor = "#dcfce7"; // green-100
            input.style.border = "2px solid #22c55e"; // green-500
        } else if (highlightType === 'red') {
            input.style.backgroundColor = "#fee2e2"; // red-100
            input.style.border = "2px solid #ef4444"; // red-500
        }

        // Revert green highlighting after 3 seconds
        if (highlightType === 'green') {
            setTimeout(() => {
                input.style.backgroundColor = originalBg;
                input.style.border = originalBorder;
            }, 3000);
        }
    }

    /**
     * Set value for a SELECT element using fuzzy matching on options
     */
    setSelectValue(select, value) {
        if (!select || !value) return;

        const normalize = (s) => String(s).toLowerCase().replace(/[^\w\s]/g, '').trim();
        let val = normalize(value);
        const usVariations = this.getUSVariations();
        const isUSValue = usVariations.includes(val);

        // Map complex values like "i am not a protected veteran" to "no"
        const mappedVal = this.normalizeYesNoDecline(value);

        let bestOptionIndex = -1;
        let highestConfidence = 0;

        for (let i = 0; i < select.options.length; i++) {
            const option = select.options[i];
            const optText = normalize(option.text);
            const optVal = normalize(option.value);

            // 1. Exact match
            if (optVal === val || optText === val) {
                bestOptionIndex = i;
                highestConfidence = 100;
                break;
            }

            // 2. State Variation Match
            const stateVariations = this.getStateVariations(value);
            if (stateVariations.length > 1) {
                if (stateVariations.some(v => normalize(v) === optVal || normalize(v) === optText)) {
                    if (99 > highestConfidence) { bestOptionIndex = i; highestConfidence = 99; }
                }
            }

            // 3. Logic Equivalence (Yes/No/Decline)
            if (mappedVal === 'no' && (optText.includes("not a protected veteran") || optText.includes("do not have a disability") || optText.includes("not hispanic") || optText === 'no' || optText === 'n')) {
                if (98 > highestConfidence) { bestOptionIndex = i; highestConfidence = 98; }
            }
            if (mappedVal === 'yes' && (optText === 'yes' || optText === 'y' || optText === 'true' || optText.includes("i am a protected veteran") || optText.includes("hispanic or latino"))) {
                if (98 > highestConfidence) { bestOptionIndex = i; highestConfidence = 98; }
            }
            if (mappedVal === 'decline' && (optText.includes('decline') || optText.includes('choose not') || optText.includes('prefer not'))) {
                if (98 > highestConfidence) { bestOptionIndex = i; highestConfidence = 98; }
            }

            // 3. US Variation Equivalence
            if (isUSValue && (usVariations.includes(optVal) || usVariations.includes(optText))) {
                if (95 > highestConfidence) { bestOptionIndex = i; highestConfidence = 95; }
            }

            // 4. Dialing Code Matching (+1 etc)
            if (isUSValue && (optText.includes('+1') || optVal.includes('+1'))) {
                if (92 > highestConfidence) { bestOptionIndex = i; highestConfidence = 92; }
            }

            // 5. Starts with / Includes
            if (optText.startsWith(val) || val.startsWith(optText)) {
                if (90 > highestConfidence) { bestOptionIndex = i; highestConfidence = 90; }
            } else if (optText.includes(val) || val.includes(optText)) {
                if (70 > highestConfidence) { bestOptionIndex = i; highestConfidence = 70; }
            }
        }

        if (bestOptionIndex !== -1) {
            select.selectedIndex = bestOptionIndex;
            ['input', 'change', 'blur'].forEach(ev => {
                select.dispatchEvent(new Event(ev, { bubbles: true, composed: true }));
            });
        } else {
            select.value = value;
            ['input', 'change', 'blur'].forEach(ev => {
                select.dispatchEvent(new Event(ev, { bubbles: true, composed: true }));
            });
        }
    }

    highlightUnmatchedRequired(input) {
        this.setInputValue(input, null, 'red');
    }
}


// Global exposure
if (typeof window !== 'undefined') {
    window.GenericStrategy = GenericStrategy;
}

