/**
 * ResumeProcessor - Central module for normalizing JSON Resume data
 * Supports standard JSON Resume schema + custom_fields extension
 *
 * @version 2.0.0
 * @description TalentScreen - Whitebox Learning Autofill Extension
 */

class ResumeProcessor {
    static isPlainObject(value) {
        return !!value && typeof value === 'object' && !Array.isArray(value);
    }

    static asArray(value) {
        if (Array.isArray(value)) return value;
        if (value === undefined || value === null || value === '') return [];
        return [value];
    }

    static firstNonEmpty(...values) {
        for (const value of values) {
            if (value === undefined || value === null) continue;
            if (typeof value === 'string' && value.trim()) return value.trim();
            if (Array.isArray(value) && value.length > 0) return value;
            if (this.isPlainObject(value) && Object.keys(value).length > 0) return value;
            if (typeof value === 'number' || typeof value === 'boolean') return value;
        }
        return "";
    }

    static findValueByAliases(obj, aliases = []) {
        if (!this.isPlainObject(obj)) return "";
        const normalizedAliases = aliases.map(alias => this.normalizeText(alias));
        for (const [key, value] of Object.entries(obj)) {
            const normalizedKey = this.normalizeText(key);
            if (normalizedAliases.some(alias => normalizedKey === alias || normalizedKey.includes(alias))) {
                return value;
            }
        }
        return "";
    }

    static findSection(source, aliases = []) {
        if (!this.isPlainObject(source)) return null;
        const direct = this.findValueByAliases(source, aliases);
        if (direct) return direct;

        for (const value of Object.values(source)) {
            if (!this.isPlainObject(value)) continue;
            const nested = this.findValueByAliases(value, aliases);
            if (nested) return nested;
        }

        return null;
    }

    static joinTextParts(parts = []) {
        return parts
            .filter(part => typeof part === 'string' && part.trim())
            .map(part => part.trim())
            .join(', ');
    }

    static normalizeProfiles(rawProfiles, source) {
        const profiles = [];
        const pushProfile = (network, url) => {
            if (!url) return;
            profiles.push({
                network: network || "profile",
                url: typeof url === 'string' ? url.trim() : url
            });
        };

        this.asArray(rawProfiles).forEach(profile => {
            if (typeof profile === 'string') {
                pushProfile("profile", profile);
                return;
            }

            if (!this.isPlainObject(profile)) return;
            pushProfile(
                this.firstNonEmpty(profile.network, profile.platform, profile.type, profile.label, profile.name),
                this.firstNonEmpty(profile.url, profile.link, profile.href, profile.username)
            );
        });

        if (this.isPlainObject(source)) {
            pushProfile("linkedin", this.firstNonEmpty(source.linkedin, source.linkedinUrl, source.linkedIn));
            pushProfile("github", this.firstNonEmpty(source.github, source.githubUrl));
            pushProfile("portfolio", this.firstNonEmpty(source.portfolio, source.website, source.url));
        }

        return profiles.filter(profile => profile.url);
    }

    static normalizeSkills(rawSkills) {
        if (!rawSkills) return [];

        const addKeywords = (bucket, values) => {
            this.asArray(values).forEach(value => {
                if (typeof value === 'string' && value.trim()) {
                    bucket.push(value.trim());
                }
            });
        };

        const skills = [];
        this.asArray(rawSkills).forEach(entry => {
            if (typeof entry === 'string') {
                skills.push({ name: "General", keywords: [entry.trim()] });
                return;
            }

            if (!this.isPlainObject(entry)) return;

            const name = this.firstNonEmpty(entry.name, entry.category, entry.group, entry.type, "General");
            const keywords = [];
            addKeywords(keywords, entry.keywords);
            addKeywords(keywords, entry.skills);
            addKeywords(keywords, entry.items);
            addKeywords(keywords, entry.technologies);
            addKeywords(keywords, entry.tools);

            const fallbackValue = this.firstNonEmpty(entry.name, entry.skill);
            if (keywords.length === 0 && typeof fallbackValue === 'string') {
                keywords.push(fallbackValue);
            }

            skills.push({ name, keywords });
        });

        return skills.filter(skill => skill.keywords && skill.keywords.length > 0);
    }

    static normalizeWorkEntries(rawWork) {
        return this.asArray(rawWork)
            .filter(entry => this.isPlainObject(entry))
            .map(job => ({
                ...job,
                name: this.firstNonEmpty(job.name, job.company, job.companyName, job.employer, job.organization),
                position: this.firstNonEmpty(job.position, job.title, job.role, job.jobTitle, job.designation),
                startDate: this.firstNonEmpty(job.startDate, job.start_date, job.from, job.dateStart),
                endDate: this.firstNonEmpty(job.endDate, job.end_date, job.to, job.dateEnd, job.finishDate),
                summary: this.firstNonEmpty(job.summary, job.description, job.responsibilities, job.highlights),
                location: this.firstNonEmpty(job.location, job.city, job.region)
            }))
            .filter(job => job.name || job.position || job.summary);
    }

    static normalizeEducationEntries(rawEducation) {
        return this.asArray(rawEducation)
            .filter(entry => this.isPlainObject(entry))
            .map(edu => ({
                ...edu,
                institution: this.firstNonEmpty(edu.institution, edu.school, edu.university, edu.college, edu.organization),
                studyType: this.firstNonEmpty(edu.studyType, edu.degree, edu.degreeName, edu.qualification, edu.Discipline),
                area: this.firstNonEmpty(edu.area, edu.major, edu.fieldOfStudy, edu.specialization, edu.department),
                startDate: this.firstNonEmpty(edu.startDate, edu.start_date, edu.from, edu.dateStart),
                endDate: this.firstNonEmpty(edu.endDate, edu.end_date, edu.to, edu.dateEnd, edu.graduationDate)
            }))
            .filter(edu => edu.institution || edu.studyType || edu.area);
    }

    static buildCanonicalResume(resumeData) {
        if (!this.isPlainObject(resumeData)) return {};

        const rawBasics = this.findSection(resumeData, [
            "basics", "basic", "personal", "personal info", "personal information",
            "profile", "contact", "candidate", "header"
        ]) || {};

        const workSection = this.findSection(resumeData, [
            "work", "experience", "work experience", "employment", "employment history",
            "professional experience", "positions", "career history"
        ]);

        const educationSection = this.findSection(resumeData, [
            "education", "education history", "academics", "academic", "studies", "qualifications"
        ]);

        const skillsSection = this.findSection(resumeData, [
            "skills", "skill set", "skillset", "technologies", "technical skills",
            "core competencies", "expertise"
        ]);

        const basicsSource = this.isPlainObject(rawBasics) ? rawBasics : {};
        const firstName = this.firstNonEmpty(
            basicsSource.firstName,
            basicsSource.first_name,
            resumeData.firstName,
            resumeData.first_name
        );
        const middleName = this.firstNonEmpty(
            basicsSource.middleName,
            basicsSource.middle_name,
            resumeData.middleName,
            resumeData.middle_name
        );
        const lastName = this.firstNonEmpty(
            basicsSource.lastName,
            basicsSource.last_name,
            resumeData.lastName,
            resumeData.last_name
        );

        const fullName = this.firstNonEmpty(
            basicsSource.name,
            basicsSource.fullName,
            basicsSource.full_name,
            resumeData.name,
            resumeData.fullName,
            this.joinTextParts([firstName, middleName, lastName]).replace(/,\s*/g, ' ')
        );

        const rawLocation = this.findSection(basicsSource, ["location", "address"]) ||
            this.findSection(resumeData, ["location", "address"]) || {};

        const location = this.isPlainObject(rawLocation) ? {
            address: this.firstNonEmpty(rawLocation.address, rawLocation.street, rawLocation.line1),
            city: this.firstNonEmpty(rawLocation.city, rawLocation.town),
            region: this.firstNonEmpty(rawLocation.region, rawLocation.state, rawLocation.province),
            postalCode: this.firstNonEmpty(rawLocation.postalCode, rawLocation.zip, rawLocation.zipCode, rawLocation.postcode),
            countryCode: this.firstNonEmpty(rawLocation.countryCode, rawLocation.country, rawLocation.nation)
        } : {};

        const basics = {
            ...basicsSource,
            name: fullName,
            email: this.firstNonEmpty(basicsSource.email, resumeData.email),
            phone: this.firstNonEmpty(basicsSource.phone, basicsSource.phoneNumber, resumeData.phone, resumeData.phoneNumber),
            url: this.firstNonEmpty(basicsSource.url, basicsSource.website, basicsSource.portfolio, resumeData.url, resumeData.website),
            label: this.firstNonEmpty(basicsSource.label, basicsSource.headline, basicsSource.title, resumeData.label, resumeData.headline),
            summary: this.firstNonEmpty(
                basicsSource.summary,
                basicsSource.objective,
                basicsSource.profileSummary,
                basicsSource.bio,
                resumeData.summary,
                resumeData.objective,
                resumeData.profileSummary
            ),
            gender: this.firstNonEmpty(basicsSource.gender, resumeData.gender),
            pronouns: this.firstNonEmpty(basicsSource.pronouns, resumeData.pronouns),
            veteranStatus: this.firstNonEmpty(basicsSource.veteranStatus, basicsSource.veteran_status, resumeData.veteranStatus),
            disabilityStatus: this.firstNonEmpty(basicsSource.disabilityStatus, basicsSource.disability_status, resumeData.disabilityStatus),
            ethnicity: this.firstNonEmpty(basicsSource.ethnicity, basicsSource.race, resumeData.ethnicity),
            hispanicLatino: this.firstNonEmpty(basicsSource.hispanicLatino, basicsSource.hispanic_latino, resumeData.hispanicLatino),
            profiles: this.normalizeProfiles(
                this.firstNonEmpty(basicsSource.profiles, basicsSource.links, basicsSource.social, basicsSource.websites, resumeData.profiles),
                basicsSource
            ),
            location,
            workAuthorization: this.isPlainObject(basicsSource.workAuthorization) ? basicsSource.workAuthorization : (this.isPlainObject(resumeData.workAuthorization) ? resumeData.workAuthorization : {}),
            availability: this.isPlainObject(basicsSource.availability) ? basicsSource.availability : (this.isPlainObject(resumeData.availability) ? resumeData.availability : {}),
            custom: this.isPlainObject(basicsSource.custom) ? basicsSource.custom : {},
            experience: this.isPlainObject(basicsSource.experience) ? basicsSource.experience : {}
        };

        return {
            ...resumeData,
            basics,
            work: this.normalizeWorkEntries(workSection || resumeData.work),
            education: this.normalizeEducationEntries(educationSection || resumeData.education),
            skills: this.normalizeSkills(skillsSection || resumeData.skills)
        };
    }

    static normalizeText(text) {
        if (!text || typeof text !== 'string') return '';

        let normalized = text.toLowerCase()
            .replace(/[^\w\s]|_/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();

        const abbreviations = {
            "ml": "machine learning",
            "ai": "artificial intelligence",
            "js": "javascript",
            "ts": "typescript",
            "fe": "frontend",
            "be": "backend",
            "fs": "fullstack",
            "ux": "user experience",
            "ui": "user interface",
            "aws": "amazon web services",
            "gcp": "google cloud platform",
            "db": "database",
            "sdlc": "software development life cycle",
            "qa": "quality assurance"
        };

        return normalized.split(' ').map(word => abbreviations[word] || word).join(' ');
    }

    /**
     * Normalizes a JSON Resume into a structured internal index with custom_fields support
     * @param {Object} resumeData - Raw resume JSON
     * @returns {Object} Normalized resume data structure
     * @throws {Error} If resume data is invalid
     */
    static normalize(resumeData) {
        try {
            if (!resumeData) {
                throw new Error("Resume data is required");
            }

            const canonicalResume = this.buildCanonicalResume(resumeData);

            const basics = canonicalResume.basics || {};
            const work = canonicalResume.work || [];
            const skills = canonicalResume.skills || [];
            const location = basics.location || {};
            const profiles = basics.profiles || [];

            // Extract custom_fields (TalentScreen extension) with defaults
            const customFields = canonicalResume.custom_fields || {};

            // Default EEO values
            const eeo = {
                gender: "male",
                ethnicity: "asian",
                veteran_status: "no",
                disability_status: "no",
                lgbtq: "decline",
                pronouns: "",
                ...customFields.eeo
            };

            // Default legal/authorization values
            const legal = {
                work_auth_us: true,
                sponsorship_required_now: false,
                sponsorship_required_future: false,
                security_clearance: "no",
                visa_status: "citizen",
                work_authorization_expiration: "n/a",
                notice_period_days: 14,
                ...customFields.legal
            };

            // Default technical screening values
            const technical = {
                years_llm: 3,
                years_ml_deployment: 5,
                years_python: 15,
                years_kubernetes: 5,
                experience_rag: true,
                experience_agentic_ai: true,
                highest_education: "masters",
                ...customFields.technical_screening
            };

            // Default application logistics
            const logistics = {
                resume_pdf_url: "",
                willing_to_relocate: "yes",
                willing_to_travel: "yes",
                screening_answers: {
                    why_interested: "Driven by the challenge of architecting production-grade agentic workflows and scaling LLM infrastructure within enterprise environments.",
                    why_good_fit: "Proven experience leading AI architecture at Lucid Motors and Yahoo, focusing on end-to-end MLOps and highly available distributed systems.",
                    ...(customFields.application_logistics?.screening_answers || {})
                },
                ...customFields.application_logistics
            };

            // 1. Identity
            const fullName = (basics.name || "").trim();
            const nameParts = fullName.split(/\s+/);
            let firstName = "", middleName = "", lastName = "";

            if (nameParts.length === 1) {
                firstName = nameParts[0];
            } else if (nameParts.length === 2) {
                firstName = nameParts[0];
                lastName = nameParts[1];
            } else if (nameParts.length > 2) {
                firstName = nameParts[0];
                lastName = nameParts[nameParts.length - 1];
                middleName = nameParts.slice(1, nameParts.length - 1).join(" ");
            }

            const findByPattern = (obj, patterns) => {
                if (!obj) return "";
                const keys = Object.keys(obj);
                const foundKey = keys.find(k => patterns.some(p => k.toLowerCase().includes(p.toLowerCase())));
                return foundKey ? obj[foundKey] : "";
            };

            const preferredName = "";

            const identity = {
                first_name: firstName,
                middle_name: middleName,
                last_name: lastName,
                preferred_name: preferredName,
                full_name: fullName,
                gender: eeo.gender || basics.gender || "",
                pronouns: eeo.pronouns || basics.pronouns || (basics.custom && basics.custom.pronouns) || "",
                veteran_status: eeo.veteran_status || basics.veteranStatus || "",
                disability_status: eeo.disability_status || basics.disabilityStatus || "",
                ethnicity: eeo.ethnicity || basics.ethnicity || basics.race || (basics.demographics && (basics.demographics.ethnicity || basics.demographics.race)) || "",
                sponsorship_required: legal.sponsorship_required_now || legal.sponsorship_required_future || (basics.workAuthorization && basics.workAuthorization.requiresSponsorshipNowOrFuture) ||
                    findByPattern(basics.workAuthorization, ["sponsorship"]) || "",
                hispanic_latino: eeo.hispanic_latino || basics.hispanicLatino || (basics.demographics && basics.demographics.hispanicOrLatino) || "",
                authorized_to_work: legal.work_auth_us !== undefined ? (legal.work_auth_us ? "Yes" : "No") : "",
                security_clearance_eligible: legal.security_clearance || "",
                lgbtq: eeo.lgbtq || "",
                relocation_open: logistics.willing_to_relocate || "",
                notice_period: legal.notice_period_days ? `${legal.notice_period_days} days` : ""
            };

            const availabilityVal = (basics.availability && basics.availability.soonestStartDate) ||
                findByPattern(basics.availability, ["soonest", "start date", "available"]);

            const availability = {
                start_date: availabilityVal
            };

            // 2. Contact & Links
            const getProfile = (network) => {
                const p = profiles.find(pf => this.normalizeText(pf.network).includes(network));
                return p ? p.url : "";
            };

            const contact = {
                email: basics.email || "",
                phone: basics.phone ? basics.phone.replace(/[^\d+]/g, "") : "",
                linkedin: getProfile('linkedin'),
                github: getProfile('github'),
                portfolio: basics.url || "",
                address: location.address || "",
                city: location.city || "",
                state: location.region || "",
                zip_code: location.postalCode || "",
                country: location.countryCode || "",
                location: (location.city && location.region) ? `${location.city}, ${location.region}` : (location.address || location.city || "")
            };

            // 3. Employment & Reverse Maps
            const workEntries = work.map(job => {
                const start = job.startDate ? new Date(job.startDate) : null;
                const end = job.endDate ? new Date(job.endDate) : new Date();
                let durationMonths = 0;

                if (start && !isNaN(start.getTime()) && !isNaN(end.getTime())) {
                    const diffTime = Math.abs(end - start);
                    durationMonths = Math.ceil(diffTime / (1000 * 60 * 60 * 24 * 30.44));
                }

                return {
                    ...job,
                    durationMonths,
                    normCompany: this.normalizeText(job.name),
                    normTitle: this.normalizeText(job.position)
                };
            });

            let totalMonths = 0;
            const companyToDuration = {};
            const titleToDuration = {};
            const rolesByYear = {};

            workEntries.forEach(job => {
                totalMonths += job.durationMonths;
                companyToDuration[job.normCompany] = (companyToDuration[job.normCompany] || 0) + job.durationMonths;
                titleToDuration[job.normTitle] = (titleToDuration[job.normTitle] || 0) + job.durationMonths;

                if (job.startDate) {
                    const startYear = new Date(job.startDate).getFullYear();
                    const endYear = job.endDate ? new Date(job.endDate).getFullYear() : new Date().getFullYear();
                    for (let y = startYear; y <= endYear; y++) {
                        if (!rolesByYear[y]) rolesByYear[y] = [];
                        if (!rolesByYear[y].includes(job.position)) {
                            rolesByYear[y].push(job.position);
                        }
                    }
                }
            });

            const employment = {
                current_role: workEntries[0]?.position || basics.label || "",
                current_company: workEntries[0]?.name || "",
                years_total: Math.round(totalMonths / 12),
                roles_by_year: rolesByYear,
                history: workEntries
            };

            // 4. Skills & Reverse Maps
            const normalizedSkillSet = new Set();
            const skillFrequency = {};
            const skillToYears = {};
            const skillCategories = {};

            skills.forEach(skillCategory => {
                const catName = this.normalizeText(skillCategory.name);
                skillCategories[catName] = [];

                const keywords = skillCategory.keywords || [skillCategory.name];

                keywords.forEach(keyword => {
                    const normKeyword = this.normalizeText(keyword);
                    normalizedSkillSet.add(normKeyword);
                    skillCategories[catName].push(normKeyword);

                    skillFrequency[normKeyword] = (skillFrequency[normKeyword] || 0) + 1;
                    skillToYears[normKeyword] = employment.years_total;
                });
            });

            const skillsData = {
                normalized_skill_set: Array.from(normalizedSkillSet),
                skill_frequency: skillFrequency,
                skill_categories: skillCategories,
                skills_string: Array.from(normalizedSkillSet).join(", ")
            };

            // Summaries
            const summaryLong = basics.summary || "";
            let summaryShort = "";
            if (summaryLong) {
                const firstSentence = summaryLong.split(/[.!?]/)[0];
                summaryShort = firstSentence ? firstSentence.trim() + "." : summaryLong;
            }

            const professionalStatement = logistics.screening_answers?.why_good_fit ||
                findByPattern(basics, ["describe your relevant experiences", "industrial projects", "professional statement"]) ||
                findByPattern(basics.experience, ["describe your relevant experiences", "industrial projects", "highlight"]);

            const motivation = logistics.screening_answers?.why_interested ||
                findByPattern(basics.experience, ["multiple roles", "motivation for each", "order them", "apply to multiple"]) || "";

            const onsiteSunnyvale = findByPattern(basics.custom, ["sunnyvale", "on-site", "work on-site"]);
            const aiToolExperience = findByPattern(basics.custom, ["claude", "cursor", "experience"]) ||
                findByPattern(basics.experience, ["claude", "cursor", "experience"]);

            // Output Index
            return {
                identity: identity,
                contact: contact,
                employment: employment,
                availability: availability,
                skills: skillsData,
                summary: {
                    short: summaryShort,
                    long: summaryLong,
                    professional_statement: professionalStatement,
                    motivation: motivation,
                    onsite_sunnyvale: onsiteSunnyvale,
                    ai_tool_experience: aiToolExperience
                },
                education: (canonicalResume.education || []).map(edu => ({
                    ...edu,
                    degree: edu.studyType || edu.Discipline || "",
                    normInstitution: this.normalizeText(edu.institution),
                    normDegree: this.normalizeText(edu.studyType || edu.Discipline || ""),
                    normMajor: this.normalizeText(edu.area || "")
                })),
                education_flat: canonicalResume.education && canonicalResume.education[0] ? {
                    institution: canonicalResume.education[0].institution || "",
                    degree: canonicalResume.education[0].studyType || canonicalResume.education[0].Discipline || "",
                    major: canonicalResume.education[0].area || "",
                    start_date: canonicalResume.education[0].startDate || "",
                    end_date: canonicalResume.education[0].endDate || ""
                } : {},
                reverse_maps: {
                    skill_to_years: skillToYears,
                    company_to_duration: companyToDuration,
                    title_to_duration: titleToDuration
                },
                custom_fields: {
                    eeo: eeo,
                    legal: legal,
                    technical_screening: technical,
                    application_logistics: logistics
                },
                technical_screening: technical,
                application_logistics: logistics
            };
        } catch (error) {
            console.error("[ResumeProcessor] Normalization error:", error);
            throw new Error(`Failed to normalize resume: ${error.message}`);
        }
    }

    static pruneForAi(normalizedData) {
        if (!normalizedData) return {};
        const pruned = JSON.parse(JSON.stringify(normalizedData));
        if (pruned.reverse_maps) delete pruned.reverse_maps;
        if (pruned.skills && pruned.skills.skill_frequency) delete pruned.skills.skill_frequency;
        if (pruned.skills && pruned.skills.skill_categories) delete pruned.skills.skill_categories;
        if (pruned.employment && pruned.employment.roles_by_year) delete pruned.employment.roles_by_year;
        if (pruned.employment && pruned.employment.history) {
            pruned.employment.history = pruned.employment.history.map(job => ({
                company: job.name || job.company,
                title: job.position || job.title,
                startDate: job.startDate,
                endDate: job.endDate || "Present",
                description: job.summary || job.description
            }));
        }
        if (pruned.education) {
            pruned.education = pruned.education.map(edu => ({
                institution: edu.institution,
                degree: edu.studyType || edu.degree,
                area: edu.area || edu.major,
                startDate: edu.startDate,
                endDate: edu.endDate
            }));
        }
        return pruned;
    }
}

// Export for use in extension
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResumeProcessor;
} else {
    const globalScope = typeof window !== 'undefined' ? window : self;
    globalScope.ResumeProcessor = ResumeProcessor;
}
