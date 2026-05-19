/**
 * jobviteStrategy.js
 * Strategy for Jobvite application forms.
 */
class JobviteStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; 
    }

    async execute(normalizedData, resumeFile = null) {
        // console.log("Executing JobviteStrategy...");
        
        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        await super.execute(normalizedData, resumeFile);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('jobvite.com'),
        JobviteStrategy
    );
}
