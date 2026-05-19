/**
 * adpStrategy.js
 * Strategy for Adp application forms.
 */
class AdpStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70;
    }

    async execute(normalizedData, resumeFile = null) {
        // console.log("Executing AdpStrategy...");
        await super.execute(normalizedData, resumeFile);
    }


    findValueForInput(input, normalizedData) {
        const id = (input.id || "").toLowerCase();
        const name = (input.name || "").toLowerCase();
        const combined = id + " " + name;

        const identity = normalizedData.identity || {};
        const contact = normalizedData.contact || {};

        // ADP specific patterns (often uses prefixes like 'rb_' or specific container IDs)
        if (combined.includes('first_name') || id.includes('firstname')) return { value: identity.first_name, confidence: 95 };
        if (combined.includes('last_name') || id.includes('lastname')) return { value: identity.last_name, confidence: 95 };
        if (combined.includes('email')) return { value: contact.email, confidence: 95 };
        if (combined.includes('phone') || combined.includes('mobile')) return { value: contact.phone, confidence: 95 };
        if (combined.includes('address') && combined.includes('1')) return { value: contact.address, confidence: 95 };
        if (combined.includes('city')) return { value: contact.city, confidence: 95 };
        if (combined.includes('zip') || combined.includes('postal')) return { value: contact.zip_code, confidence: 95 };

        return super.findValueForInput(input, normalizedData);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('adp.com'),
        AdpStrategy
    );
}
