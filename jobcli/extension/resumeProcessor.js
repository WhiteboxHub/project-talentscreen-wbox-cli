/**
 * Utility to process and normalize JSON Resume data into a flat, searchable index.
 */
class ResumeProcessor {
    /**
     * Text Normalization Utility
     * - Lowercases text
     * - Removes punctuation (replaces with space)
     * - Standardizes whitespace
     * - Expands abbreviations
     */
    static normalizeText(text) {
        if (!text || typeof text !== 'string') return '';

        let normalized = text.toLowerCase()
            .replace(/[^\w\s]|_/g, ' ') // Strip punctuation
            .replace(/\s+/g, ' ')       // Standardize whitespace
            .trim();

        // Abbreviation expansion dictionary
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

        // Split, expand, and rejoin
        return normalized.split(' ').map(word => abbreviations[word] || word).join(' ');
    }

    /**
     * Normalizes a JSON Resume into a structured internal index.
     */
    static normalize(resumeData) {
        if (!resumeData) return {};

        const basics = resumeData.basics || {};
        const work = resumeData.work || [];
        const skills = resumeData.skills || [];
        const location = basics.location || {};
        const profiles = basics.profiles || [];

        // 1. Identity
        const fullName = basics.name || "";
        const nameParts = fullName.split(' ');
        let firstName = "", middleName = "", lastName = "";

        if (nameParts.length > 0) {
            firstName = nameParts[0];
            lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";
            middleName = nameParts.length > 2 ? nameParts.slice(1, nameParts.length - 1).join(" ") : "";
        }

        const identity = {
            first_name: firstName,
            middle_name: middleName,
            last_name: lastName,
            full_name: fullName
        };

        // 2. Contact & Links
        const getProfile = (network) => {
            const p = profiles.find(pf => this.normalizeText(pf.network).includes(network));
            return p ? p.url : "";
        };

        const contact = {
            email: basics.email || "",
            phone: basics.phone ? basics.phone.replace(/[^\d+]/g, "") : "", // Keep only digits and +
            linkedin: getProfile('linkedin'),
            github: getProfile('github'),
            portfolio: basics.url || "",

            // Location included in contact for convenience
            address: location.address || "",
            city: location.city || "",
            state: location.region || "",
            zip_code: location.postalCode || "",
            country: location.countryCode || ""
        };

        // 3. Employment & Reverse Maps
        const currentWork = work[0] || {};
        let totalMonths = 0;

        const companyToDuration = {};
        const titleToDuration = {};
        const rolesByYear = {};

        work.forEach(job => {
            const start = new Date(job.startDate);
            const end = job.endDate ? new Date(job.endDate) : new Date();

            if (!isNaN(start.getTime()) && !isNaN(end.getTime())) {
                const diffTime = Math.abs(end - start);
                const diffMonths = Math.ceil(diffTime / (1000 * 60 * 60 * 24 * 30.44));
                totalMonths += diffMonths;

                const normCompany = this.normalizeText(job.name);
                const normTitle = this.normalizeText(job.position);

                // Track durations
                companyToDuration[normCompany] = (companyToDuration[normCompany] || 0) + diffMonths;
                titleToDuration[normTitle] = (titleToDuration[normTitle] || 0) + diffMonths;

                // Track roles by year
                const startYear = start.getFullYear();
                const endYear = end.getFullYear();
                for (let y = startYear; y <= endYear; y++) {
                    if (!rolesByYear[y]) rolesByYear[y] = [];
                    if (!rolesByYear[y].includes(job.position)) {
                        rolesByYear[y].push(job.position);
                    }
                }
            }
        });

        const employment = {
            current_role: currentWork.position || basics.label || "",
            current_company: currentWork.name || "",
            years_total: Math.round(totalMonths / 12),
            roles_by_year: rolesByYear
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

                // Estimate skill frequency/years based on overall employment
                // In a perfect system, skills would map to specific jobs. 
                // We'll approximate by assigning total experience to core skills for now.
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

        // Output Index
        return {
            identity: identity,
            contact: contact,
            employment: employment,
            skills: skillsData,
            summary: {
                short: summaryShort,
                long: summaryLong
            },
            education: resumeData.education || [],
            reverse_maps: {
                skill_to_years: skillToYears,
                company_to_duration: companyToDuration,
                title_to_duration: titleToDuration
            }
        };
    }
}

// Export for use in extension (depending on environment)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResumeProcessor;
} else {
    window.ResumeProcessor = ResumeProcessor;
}
