/**
 * workableStrategy.js
 * Strategy for Workable application forms.
 */
class WorkableStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 60; // Lowered slightly to capture more fields
        this.executed = false;
    }

    async execute(normalizedData, resumeFile = null) {
        if (!normalizedData) {
            console.error("WorkableStrategy: No resume data provided.");
            return;
        }

        // console.log("Executing WorkableStrategy (Human-like speed)...");

        // Basic fallback execution. 
        await super.execute(normalizedData, resumeFile);

        // Workable is a heavy SPA. The forms are often loaded dynamically.
        // GenericStrategy handles most things, but we can add specific logic here if needed.
        // For example, Workable sometimes uses specific data-automation-id attributes.

        // console.log("Workable AutoFill cycle complete.");
    }

    /**
     * Override findValueForInput to handle Workable-specific patterns.
     */
    findValueForInput(input, normalizedData) {
        const features = this.extractFeatures(input);

        // Workable specific data attributes
        const automationId = input.getAttribute('data-automation-id') || "";
        const testId = input.getAttribute('data-testid') || "";
        const combined = (features.name_attr + " " + features.id_attr + " " + automationId + " " + testId + " " + features.label_text).toLowerCase();

        const identity = normalizedData.identity || {};
        const contact = normalizedData.contact || {};

        // Phone specific override for Workable
        if (combined.includes("phone") || combined.includes("mobile") || automationId.includes("phone")) {
            return { value: contact.phone, confidence: 100, fieldKey: "contact.phone" };
        }

        // Location/City/Address
        if (combined.includes("city") || combined.includes("location")) {
            return { value: contact.city, confidence: 90, fieldKey: "contact.city" };
        }

        return super.findValueForInput(input, normalizedData);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('workable.com'),
        WorkableStrategy
    );
}
