/**
 * leverStrategy.js
 * Strategy for Lever application forms.
 */
class LeverStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 65; // Slightly lower threshold for Lever
    }

    async execute(normalizedData, resumeFile = null) {
        await super.execute(normalizedData, resumeFile);
    }

    findValueForInput(input, normalizedData) {
        let match = this.findLeverSpecificMatch(input, normalizedData);
        if (match && match.value) return match;
        return super.findValueForInput(input, normalizedData);
    }

    findLeverSpecificMatch(input, data) {
        const features = this.extractFeatures(input);
        const nameAttr = (input.name || "").toLowerCase();
        const labelTxt = features.label_text.toLowerCase();
        const placeholder = features.placeholder.toLowerCase();

        const identity = data?.identity || {};
        const contact = data?.contact || {};
        const employment = data?.employment || {};

        // 1. Basic Identity & Contact
        if (nameAttr === 'name' || labelTxt === 'full name') return { value: identity.full_name, confidence: 95 };
        if (nameAttr === 'email' || labelTxt === 'email') return { value: contact.email, confidence: 95 };
        if (nameAttr === 'phone' || labelTxt === 'phone') return { value: contact.phone, confidence: 95 };
        if (nameAttr === 'org' || labelTxt === 'current company') return { value: employment.current_company, confidence: 90 };

        // 2. Location
        if (nameAttr === 'location' || labelTxt.includes('current location') || placeholder.includes('city')) {
            const loc = contact.city && contact.state ? `${contact.city}, ${contact.state}` : (contact.city || contact.address || "");
            return { value: loc, confidence: 90, fieldKey: 'contact.city' };
        }

        // 3. URLs (LinkedIn, GitHub, Portfolio)
        // Lever uses names like: urls[LinkedIn], urls[GitHub], urls[Portfolio]
        if (nameAttr.includes('url') || labelTxt.includes('linkedin') || labelTxt.includes('github') || labelTxt.includes('portfolio') || labelTxt.includes('website')) {
            if (nameAttr.includes('linkedin') || labelTxt.includes('linkedin'))
                return { value: contact.linkedin, confidence: 95, fieldKey: 'contact.linkedin' };
            if (nameAttr.includes('github') || labelTxt.includes('github'))
                return { value: contact.github, confidence: 95, fieldKey: 'contact.github' };
            if (nameAttr.includes('portfolio') || labelTxt.includes('portfolio') || labelTxt.includes('website'))
                return { value: contact.portfolio, confidence: 95, fieldKey: 'contact.portfolio' };
        }

        // 4. Demographics (Gender, Race)
        // These are often radio buttons or selects. 
        if (labelTxt.includes("gender") || nameAttr.includes("gender")) {
            return { value: identity.gender, confidence: 90, fieldKey: "identity.gender" };
        }
        if (labelTxt.includes("race") || labelTxt.includes("ethnicity") || nameAttr.includes("race") || nameAttr.includes("ethnicity")) {
            return { value: identity.ethnicity, confidence: 90, fieldKey: "identity.ethnicity" };
        }

        return null;
    }
}

// Register with Strategy Registry if available
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url) => url.includes('lever.co'),
        LeverStrategy
    );
}
