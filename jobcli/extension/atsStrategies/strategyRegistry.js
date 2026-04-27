/**
 * strategyRegistry.js
 * Registry to dynamically select the correct ATS Strategy
 * based on the current URL or DOM markers.
 */
class ATSStrategyRegistry {
    static strategies = [];

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
     * @param {String} url - The current window location href
     * @param {Document} doc - The current document 
     * @returns {GenericStrategy} An instance of the matching strategy (or GenericStrategy fallback)
     */
    static getStrategy(url, doc) {
        for (const { matchCondition, strategyClass } of this.strategies) {
            if (matchCondition(url, doc)) {
                return new strategyClass();
            }
        }
        return new GenericStrategy();
    }
}
