/**
 * teamtailorStrategy.js
 * Strategy for Teamtailor application forms.
 */
class TeamtailorStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; 
    }

    async execute(normalizedData, resumeFile = null) {
        // console.log("Executing TeamtailorStrategy...");
        
        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        await super.execute(normalizedData, resumeFile);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('teamtailor.com'),
        TeamtailorStrategy
    );
}
