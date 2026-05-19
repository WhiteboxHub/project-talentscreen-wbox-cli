/**
 * Autofill Telemetry
 * Tracks detailed metrics and diagnostics for autofill operations
 * @module autofillTelemetry
 */

const AutofillTelemetry = {
    currentSession: null,
    sessionHistory: [],

    /**
     * Start a new autofill session
     * @param {Object} metadata - Session metadata
     * @returns {string} Session ID
     */
    startSession(metadata = {}) {
        const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

        this.currentSession = {
            id: sessionId,
            startTime: Date.now(),
            endTime: null,
            duration: null,
            metadata: {
                url: window.location.href,
                atsType: metadata.atsType || 'unknown',
                userAgent: navigator.userAgent,
                ...metadata
            },
            metrics: {
                totalFieldsFound: 0,
                attemptedFields: 0,
                filledSuccessfully: 0,
                failedFields: 0,
                skippedFields: 0,
                totalRetries: 0,
                passCount: 0
            },
            fields: [],
            passes: [],
            errors: []
        };

        return sessionId;
    },

    /**
     * Track a field attempt
     * @param {Object} fieldData - Field data
     */
    trackFieldAttempt(fieldData) {
        if (!this.currentSession) {
            console.warn('[Telemetry] No active session');
            return;
        }

        const field = {
            timestamp: Date.now(),
            selector: fieldData.selector || null,
            label: fieldData.label || null,
            detectedType: fieldData.detectedType || null,
            matchedKey: fieldData.matchedKey || null,
            confidenceScore: fieldData.confidenceScore || 0,
            value: fieldData.sensitive ? '[REDACTED]' : fieldData.value,
            success: fieldData.success || false,
            failureReason: fieldData.failureReason || null,
            retryCount: fieldData.retryCount || 0,
            fillDuration: fieldData.fillDuration || null,
            metadata: fieldData.metadata || {}
        };

        this.currentSession.fields.push(field);

        // Update metrics
        const metrics = this.currentSession.metrics;
        metrics.attemptedFields++;

        if (field.success) {
            metrics.filledSuccessfully++;
        } else if (fieldData.skipped) {
            metrics.skippedFields++;
        } else {
            metrics.failedFields++;
        }

        metrics.totalRetries += field.retryCount;
    },

    /**
     * Track total fields found
     * @param {number} count - Number of fields
     */
    trackFieldsFound(count) {
        if (!this.currentSession) return;
        this.currentSession.metrics.totalFieldsFound = count;
    },

    /**
     * Track an autofill pass (for multi-pass strategies)
     * @param {Object} passData - Pass data
     */
    trackPass(passData) {
        if (!this.currentSession) return;

        const pass = {
            passNumber: passData.passNumber || this.currentSession.metrics.passCount + 1,
            timestamp: Date.now(),
            fieldsAttempted: passData.fieldsAttempted || 0,
            fieldsSuccessful: passData.fieldsSuccessful || 0,
            fieldsFailed: passData.fieldsFailed || 0,
            duration: passData.duration || null
        };

        this.currentSession.passes.push(pass);
        this.currentSession.metrics.passCount++;
    },

    /**
     * Track an error
     * @param {Error|string} error - Error object or message
     * @param {Object} context - Additional context
     */
    trackError(error, context = {}) {
        if (!this.currentSession) return;

        this.currentSession.errors.push({
            timestamp: Date.now(),
            message: error.message || String(error),
            stack: error.stack || null,
            context
        });
    },

    /**
     * End current session
     * @returns {Object} Session summary
     */
    endSession() {
        if (!this.currentSession) {
            console.warn('[Telemetry] No active session to end');
            return null;
        }

        this.currentSession.endTime = Date.now();
        this.currentSession.duration = this.currentSession.endTime - this.currentSession.startTime;

        // Calculate success rate
        const metrics = this.currentSession.metrics;
        metrics.successRate = metrics.attemptedFields > 0
            ? Math.round((metrics.filledSuccessfully / metrics.attemptedFields) * 100)
            : 0;

        // Calculate average retries
        metrics.avgRetries = metrics.attemptedFields > 0
            ? (metrics.totalRetries / metrics.attemptedFields).toFixed(2)
            : 0;

        // Save to history
        this.sessionHistory.push({ ...this.currentSession });

        // Keep only last 10 sessions
        if (this.sessionHistory.length > 10) {
            this.sessionHistory = this.sessionHistory.slice(-10);
        }

        const summary = this.getSessionSummary();

        // Clear current session
        this.currentSession = null;

        return summary;
    },

    /**
     * Get current session summary
     * @returns {Object} Summary object
     */
    getSessionSummary() {
        if (!this.currentSession) return null;

        return {
            id: this.currentSession.id,
            duration: this.currentSession.duration || (Date.now() - this.currentSession.startTime),
            metrics: { ...this.currentSession.metrics },
            atsType: this.currentSession.metadata.atsType,
            url: this.currentSession.metadata.url,
            passCount: this.currentSession.metrics.passCount,
            errorCount: this.currentSession.errors.length
        };
    },

    /**
     * Get detailed session report
     * @returns {Object} Detailed report
     */
    getDetailedReport() {
        if (!this.currentSession) return null;

        return {
            ...this.currentSession,
            fields: this.currentSession.fields.map(f => ({
                label: f.label,
                type: f.detectedType,
                matched: f.matchedKey,
                confidence: f.confidenceScore,
                success: f.success,
                retries: f.retryCount,
                error: f.failureReason
            }))
        };
    },

    /**
     * Export telemetry data
     * @returns {Object} Exportable data
     */
    exportData() {
        return {
            currentSession: this.currentSession,
            sessionHistory: this.sessionHistory,
            exportedAt: new Date().toISOString()
        };
    },

    /**
     * Get field-by-field breakdown
     * @returns {Array} Field details
     */
    getFieldBreakdown() {
        if (!this.currentSession) return [];

        return this.currentSession.fields.map(field => ({
            label: field.label || 'Unknown',
            selector: field.selector,
            type: field.detectedType || 'text',
            matched: field.matchedKey || 'none',
            confidence: field.confidenceScore,
            status: field.success ? 'SUCCESS' : (field.failureReason ? 'FAILED' : 'SKIPPED'),
            retries: field.retryCount,
            reason: field.failureReason,
            duration: field.fillDuration ? `${field.fillDuration}ms` : 'N/A'
        }));
    },

    /**
     * Get performance metrics
     * @returns {Object} Performance data
     */
    getPerformanceMetrics() {
        if (!this.currentSession) return null;

        const metrics = this.currentSession.metrics;
        const duration = this.currentSession.duration || (Date.now() - this.currentSession.startTime);

        return {
            totalDuration: `${duration}ms`,
            averageFieldTime: metrics.attemptedFields > 0
                ? `${Math.round(duration / metrics.attemptedFields)}ms`
                : 'N/A',
            successRate: `${metrics.successRate || 0}%`,
            fieldsPerSecond: metrics.attemptedFields > 0
                ? (metrics.attemptedFields / (duration / 1000)).toFixed(2)
                : 0,
            retryRate: `${metrics.avgRetries || 0}`,
            errorRate: this.currentSession.errors.length > 0
                ? `${Math.round((this.currentSession.errors.length / metrics.attemptedFields) * 100)}%`
                : '0%'
        };
    },

    /**
     * Log summary to console (debug mode)
     */
    logSummary() {
        if (!this.currentSession) {
            console.log('[Telemetry] No active session');
            return;
        }

        const summary = this.getSessionSummary();
        const metrics = summary.metrics;

        console.group(`[Telemetry] Session ${summary.id}`);
        console.log('Duration:', `${summary.duration}ms`);
        console.log('ATS Type:', summary.atsType);
        console.log('URL:', summary.url);
        console.log('---');
        console.log('Total Fields Found:', metrics.totalFieldsFound);
        console.log('Attempted:', metrics.attemptedFields);
        console.log('✓ Filled:', metrics.filledSuccessfully);
        console.log('✗ Failed:', metrics.failedFields);
        console.log('⊗ Skipped:', metrics.skippedFields);
        console.log('↻ Total Retries:', metrics.totalRetries);
        console.log('Success Rate:', `${metrics.successRate}%`);
        console.log('Passes:', summary.passCount);
        console.log('Errors:', summary.errorCount);
        console.groupEnd();
    },

    /**
     * Reset telemetry
     */
    reset() {
        this.currentSession = null;
        this.sessionHistory = [];
        console.log('[Telemetry] Reset complete');
    }
};

// Export
if (typeof window !== 'undefined') {
    window.AutofillTelemetry = AutofillTelemetry;
}
