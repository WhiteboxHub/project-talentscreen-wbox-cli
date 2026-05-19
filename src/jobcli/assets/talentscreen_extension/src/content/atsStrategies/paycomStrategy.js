/**
 * paycomStrategy.js
 * Strategy for Paycom application forms.
 */
class PaycomStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70;
    }

    async execute(normalizedData, resumeFile = null) {
        // console.log("Executing PaycomStrategy...");

        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        await super.execute(normalizedData, resumeFile);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('paycom.com'),
        PaycomStrategy
    );
}
