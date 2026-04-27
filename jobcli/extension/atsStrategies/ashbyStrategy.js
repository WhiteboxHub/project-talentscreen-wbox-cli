/**
 * ashbyStrategy.js
 * Strategy for Ashby application forms.
 */
class AshbyStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; 
    }

    execute(normalizedData, aiEnabled) {
        console.log("Executing AshbyStrategy...");
        
        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        super.execute(normalizedData, aiEnabled);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('ashhq.by') || url.includes('ashbyhq.com'),
        AshbyStrategy
    );
}
