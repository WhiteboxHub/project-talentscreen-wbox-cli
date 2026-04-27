/**
 * successfactorsStrategy.js
 * Strategy for SuccessFactors application forms.
 */
class SuccessFactorsStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; 
    }

    execute(normalizedData, aiEnabled) {
        console.log("Executing SuccessFactorsStrategy...");
        
        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        super.execute(normalizedData, aiEnabled);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('sapsf.com') || url.includes('successfactors.com'),
        SuccessFactorsStrategy
    );
}
