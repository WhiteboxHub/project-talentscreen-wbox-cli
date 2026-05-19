/**
 * strategyRegistry.js
 * Registry to dynamically select the correct ATS Strategy
 * based on the current URL or DOM markers.
 */
class ATSStrategyRegistry {
    static strategies = [];
    static _cache = null; // cached instance for the current page
    static _cachedUrl = null; // URL the cached instance was created for

    /**
     * Registers a strategy class with a matching condition.
     * @param {Function} matchCondition - A function `(url, document) => boolean`
     * @param {Class} strategyClass - The strategy class to instantiate
     */
    static register(matchCondition, strategyClass) {
        this.strategies.push({ matchCondition, strategyClass });
    }

    /**
     * Returns the appropriate strategy for the current page.
     * Caches the instance per URL so `executed` guards persist across
     * repeated MutationObserver callbacks.
     * @param {String} url - The current window location href
     * @param {Document} doc - The current document 
     * @returns {GenericStrategy} An instance of the matching strategy (or GenericStrategy fallback)
     */
    static getStrategy(url, doc) {
        // Find the matched strategy class for the current URL/DOM
        let matchedClass = null;
        for (const { matchCondition, strategyClass } of this.strategies) {
            if (matchCondition(url, doc)) {
                matchedClass = strategyClass;
                break;
            }
        }
        if (!matchedClass) matchedClass = GenericStrategy;

        // If we already have a cached instance of the EXACT same class type, 
        // return it! This ensures internal states (like `this._hasUploadedResume`) 
        // survive single-page-application URL changes (e.g. /job -> /job/apply).
        if (this._cache && this._cache instanceof matchedClass) {
            this._cachedUrl = url;
            return this._cache;
        }

        // Otherwise, instantiate the new class type
        this._cache = new matchedClass();
        this._cachedUrl = url;
        return this._cache;
    }

    /** Call this when navigating to a new page to reset the cache. */
    static clearCache() {
        this._cache = null;
        this._cachedUrl = null;
    }
}

// Global exposure
if (typeof window !== 'undefined') {
    window.ATSStrategyRegistry = ATSStrategyRegistry;
}
