/**
 * bamboohrStrategy.js
 * Strategy for BambooHr application forms.
 */
class BambooHrStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70;
    }

    async execute(normalizedData, resumeFile = null) {
        // console.log("Executing BambooHrStrategy...");

        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        await super.execute(normalizedData, resumeFile);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('bamboohr.com'),
        BambooHrStrategy
    );
}
