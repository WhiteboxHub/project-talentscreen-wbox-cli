/**
 * TalentScreen - Form Tracking System
 * Tracks field detection, fill status, retries, and session data
 * @version 2.0.0
 */

const FormTracker = (() => {
    // Configuration
    const CONFIG = {
        MAX_RETRIES: 3,
        RETRY_DELAY: 1000, // ms
        DEBUG_MODE: false,
        SENSITIVE_KEYWORDS: ['ssn', 'social security', 'password', 'credit card', 'bank account'],
        CONFIDENCE_THRESHOLD: 0.6
    };

    // Current session state
    let currentSession = null;
    let sessionHistory = [];
    let fieldStates = new Map(); // fieldId -> state object
    let retryQueue = [];
    let debugLogs = [];

    /**
     * Field States:
     * - detected: field found on page
     * - filled: successfully filled
     * - skipped: intentionally skipped (no data available)
     * - failed: fill attempt failed
     * - needs_review: requires manual input (CAPTCHA, unknown, sensitive, low confidence)
     * - retrying: currently being retried
     */

    /**
     * Initialize a new session
     */
    function startSession(atsType, jobUrl, company = '') {
        currentSession = {
            id: generateSessionId(),
            atsType: atsType || 'unknown',
            jobUrl: jobUrl || window.location.href,
            company: company,
            startTime: new Date().toISOString(),
            endTime: null,
            status: 'in_progress', // in_progress, completed, failed, partial
            fields: {
                total: 0,
                filled: 0,
                skipped: 0,
                failed: 0,
                needs_review: 0
            },
            retries: {
                total: 0,
                successful: 0,
                failed: 0
            },
            submissionDetected: false,
            pauseReason: null
        };

        fieldStates.clear();
        retryQueue = [];

        log('Session started', { sessionId: currentSession.id, atsType, jobUrl });
        notifySidepanel({ action: 'session_started', session: currentSession });

        return currentSession.id;
    }

    /**
     * Register a field as detected
     */
    function registerField(fieldId, fieldData) {
        if (!currentSession) {
            console.warn('[FormTracker] No active session. Call startSession() first.');
            return;
        }

        const state = {
            id: fieldId,
            label: fieldData.label || fieldData.name || fieldData.id || 'unknown',
            type: fieldData.type || 'text',
            required: fieldData.required || false,
            selector: fieldData.selector || '',
            status: 'detected',
            value: null,
            valueSource: null,
            timestamp: null,
            retryCount: 0,
            retryReasons: [],
            confidence: fieldData.confidence || 1.0,
            isSensitive: detectSensitiveField(fieldData.label),
            error: null
        };

        fieldStates.set(fieldId, state);
        currentSession.fields.total++;

        log('Field registered', { fieldId, label: state.label, type: state.type, required: state.required });
        updateProgress();
    }

    /**
     * Mark field as filled
     */
    function markFilled(fieldId, value, valueSource) {
        const state = fieldStates.get(fieldId);
        if (!state) {
            console.warn(`[FormTracker] Field ${fieldId} not registered`);
            return;
        }

        const previousStatus = state.status;
        state.status = 'filled';
        state.value = sanitizeValue(value, state.isSensitive);
        state.valueSource = valueSource;
        state.timestamp = new Date().toISOString();

        if (previousStatus !== 'filled') {
            currentSession.fields.filled++;
            if (previousStatus === 'failed') currentSession.fields.failed--;
            if (previousStatus === 'skipped') currentSession.fields.skipped--;
            if (previousStatus === 'needs_review') currentSession.fields.needs_review--;
        }

        log('Field filled', { fieldId, label: state.label, valueSource });
        updateProgress();
    }

    /**
     * Mark field as skipped
     */
    function markSkipped(fieldId, reason = 'no_data') {
        const state = fieldStates.get(fieldId);
        if (!state) {
            console.warn(`[FormTracker] Field ${fieldId} not registered`);
            return;
        }

        const previousStatus = state.status;
        state.status = 'skipped';
        state.error = reason;
        state.timestamp = new Date().toISOString();

        if (previousStatus !== 'skipped') {
            currentSession.fields.skipped++;
            if (previousStatus === 'failed') currentSession.fields.failed--;
            if (previousStatus === 'needs_review') currentSession.fields.needs_review--;
        }

        log('Field skipped', { fieldId, label: state.label, reason });
        updateProgress();
    }

    /**
     * Mark field as failed
     */
    function markFailed(fieldId, error) {
        const state = fieldStates.get(fieldId);
        if (!state) {
            console.warn(`[FormTracker] Field ${fieldId} not registered`);
            return;
        }

        const previousStatus = state.status;
        state.status = 'failed';
        state.error = error;
        state.timestamp = new Date().toISOString();

        if (previousStatus !== 'failed') {
            currentSession.fields.failed++;
            if (previousStatus === 'skipped') currentSession.fields.skipped--;
            if (previousStatus === 'needs_review') currentSession.fields.needs_review--;
        }

        // Add to retry queue if under retry limit
        if (state.retryCount < CONFIG.MAX_RETRIES) {
            queueRetry(fieldId, error);
        }

        log('Field failed', { fieldId, label: state.label, error, retryCount: state.retryCount });
        updateProgress();
    }

    /**
     * Mark field as needing review
     */
    function markNeedsReview(fieldId, reason) {
        const state = fieldStates.get(fieldId);
        if (!state) {
            console.warn(`[FormTracker] Field ${fieldId} not registered`);
            return;
        }

        const previousStatus = state.status;
        state.status = 'needs_review';
        state.error = reason;
        state.timestamp = new Date().toISOString();

        if (previousStatus !== 'needs_review') {
            currentSession.fields.needs_review++;
            if (previousStatus === 'failed') currentSession.fields.failed--;
            if (previousStatus === 'skipped') currentSession.fields.skipped--;
        }

        // Pause session if needed
        if (shouldPauseForReview(reason)) {
            pauseSession(reason);
        }

        log('Field needs review', { fieldId, label: state.label, reason });
        updateProgress();
        notifySidepanel({ action: 'needs_review', fieldId, label: state.label, reason });
    }

    /**
     * Queue field for retry
     */
    function queueRetry(fieldId, reason) {
        const state = fieldStates.get(fieldId);
        if (!state) return;

        state.retryReasons.push(reason);
        currentSession.retries.total++;

        retryQueue.push({
            fieldId,
            reason,
            queuedAt: Date.now()
        });

        log('Field queued for retry', { fieldId, label: state.label, retryCount: state.retryCount + 1, reason });
    }

    /**
     * Process retry queue
     */
    async function processRetries(fillCallback) {
        if (retryQueue.length === 0) return;

        log(`Processing ${retryQueue.length} retries`);

        for (const retry of retryQueue) {
            const state = fieldStates.get(retry.fieldId);
            if (!state || state.status === 'filled') continue;

            state.status = 'retrying';
            state.retryCount++;

            log('Retrying field', { fieldId: retry.fieldId, label: state.label, attempt: state.retryCount });

            await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY));

            try {
                const success = await fillCallback(retry.fieldId, state);

                if (success) {
                    currentSession.retries.successful++;
                    log('Retry successful', { fieldId: retry.fieldId, label: state.label });
                } else {
                    currentSession.retries.failed++;
                    markFailed(retry.fieldId, 'Retry failed');
                }
            } catch (error) {
                currentSession.retries.failed++;
                markFailed(retry.fieldId, `Retry error: ${error.message}`);
            }
        }

        retryQueue = [];
        updateProgress();
    }

    /**
     * Pause session for manual intervention
     */
    function pauseSession(reason) {
        if (!currentSession) return;

        currentSession.pauseReason = reason;
        log('Session paused', { reason });
        notifySidepanel({ action: 'session_paused', reason });
    }

    /**
     * Resume paused session
     */
    function resumeSession() {
        if (!currentSession) return;

        currentSession.pauseReason = null;
        log('Session resumed');
        notifySidepanel({ action: 'session_resumed' });
    }

    /**
     * End session
     */
    function endSession(status = 'completed') {
        if (!currentSession) return;

        currentSession.endTime = new Date().toISOString();
        currentSession.status = status;

        // Calculate completion percentage
        const total = currentSession.fields.total;
        const filled = currentSession.fields.filled;
        currentSession.completionPercentage = total > 0 ? Math.round((filled / total) * 100) : 0;

        // Save to history
        sessionHistory.push({ ...currentSession });
        saveHistory();

        log('Session ended', {
            sessionId: currentSession.id,
            status,
            completionPercentage: currentSession.completionPercentage
        });

        notifySidepanel({ action: 'session_ended', session: currentSession });

        const completedSession = currentSession;
        currentSession = null;
        fieldStates.clear();

        return completedSession;
    }

    /**
     * Mark submission detected
     */
    function markSubmissionDetected() {
        if (!currentSession) return;

        currentSession.submissionDetected = true;
        log('Submission detected');
        notifySidepanel({ action: 'submission_detected' });
    }

    /**
     * Detect if field is sensitive
     */
    function detectSensitiveField(label) {
        if (!label) return false;
        const lowerLabel = label.toLowerCase();
        return CONFIG.SENSITIVE_KEYWORDS.some(keyword => lowerLabel.includes(keyword));
    }

    /**
     * Should pause for review
     */
    function shouldPauseForReview(reason) {
        const pauseReasons = ['captcha', 'unknown_question', 'sensitive_field', 'low_confidence'];
        return pauseReasons.includes(reason);
    }

    /**
     * Sanitize value for logging (mask sensitive data)
     */
    function sanitizeValue(value, isSensitive) {
        if (isSensitive && value) {
            return '***REDACTED***';
        }
        return value;
    }

    /**
     * Update progress and notify sidepanel
     */
    function updateProgress() {
        if (!currentSession) return;

        notifySidepanel({
            action: 'update_progress',
            filled: currentSession.fields.filled,
            total: currentSession.fields.total,
            skipped: currentSession.fields.skipped,
            failed: currentSession.fields.failed,
            needs_review: currentSession.fields.needs_review
        });
    }

    /**
     * Get current session
     */
    function getCurrentSession() {
        return currentSession ? { ...currentSession } : null;
    }

    /**
     * Get field states
     */
    function getFieldStates() {
        return Array.from(fieldStates.values());
    }

    /**
     * Get failures
     */
    function getFailures() {
        return getFieldStates().filter(field => field.status === 'failed');
    }

    /**
     * Get fields needing review
     */
    function getNeedsReview() {
        return getFieldStates().filter(field => field.status === 'needs_review');
    }

    /**
     * Get session history
     */
    function getHistory() {
        return [...sessionHistory];
    }

    /**
     * Get recent history (last N sessions)
     */
    function getRecentHistory(limit = 10) {
        return sessionHistory.slice(-limit).reverse();
    }

    /**
     * Save history to storage
     */
    function saveHistory() {
        try {
            if (typeof chrome !== 'undefined' && chrome.storage) {
                chrome.storage.local.set({ formTrackerHistory: sessionHistory }, () => {
                    if (chrome.runtime.lastError) {
                        console.error('[FormTracker] Failed to save history:', chrome.runtime.lastError);
                    }
                });
            }
        } catch (error) {
            console.error('[FormTracker] Save history error:', error);
        }
    }

    /**
     * Load history from storage
     */
    function loadHistory() {
        return new Promise((resolve) => {
            if (typeof chrome === 'undefined' || !chrome.storage) {
                resolve([]);
                return;
            }

            chrome.storage.local.get(['formTrackerHistory'], (result) => {
                if (chrome.runtime.lastError) {
                    console.error('[FormTracker] Failed to load history:', chrome.runtime.lastError);
                    resolve([]);
                    return;
                }
                sessionHistory = result.formTrackerHistory || [];
                resolve(sessionHistory);
            });
        });
    }

    /**
     * Clear history
     */
    function clearHistory() {
        sessionHistory = [];
        saveHistory();
        log('History cleared');
    }

    /**
     * Enable/disable debug mode
     */
    function setDebugMode(enabled) {
        CONFIG.DEBUG_MODE = enabled;
        log(`Debug mode ${enabled ? 'enabled' : 'disabled'}`);
    }

    /**
     * Get debug logs
     */
    function getDebugLogs() {
        return [...debugLogs];
    }

    /**
     * Clear debug logs
     */
    function clearDebugLogs() {
        debugLogs = [];
    }

    /**
     * Log with timestamp
     */
    function log(message, data = {}) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            message,
            data,
            sessionId: currentSession?.id || null
        };

        debugLogs.push(logEntry);

        // Keep only last 1000 logs
        if (debugLogs.length > 1000) {
            debugLogs = debugLogs.slice(-1000);
        }

        if (CONFIG.DEBUG_MODE) {
            console.log(`[FormTracker] ${message}`, data);
        }
    }

    /**
     * Notify sidepanel
     */
    function notifySidepanel(message) {
        try {
            if (typeof chrome !== 'undefined' && chrome.runtime) {
                chrome.runtime.sendMessage(message, (response) => {
                    if (chrome.runtime.lastError) {
                        // Sidepanel may not be open, ignore error
                    }
                });
            }
        } catch (error) {
            // Ignore errors when sidepanel is not available
        }
    }

    /**
     * Generate unique session ID
     */
    function generateSessionId() {
        return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Export session data for external tools (Playwright/CLI)
     */
    function exportSessionData() {
        return {
            currentSession: getCurrentSession(),
            fieldStates: getFieldStates(),
            failures: getFailures(),
            needsReview: getNeedsReview(),
            history: getRecentHistory(5),
            debugLogs: CONFIG.DEBUG_MODE ? getDebugLogs() : []
        };
    }

    /**
     * Handle dynamic field detection (for multi-step forms)
     */
    function scanForNewFields(callback) {
        // This should be called periodically or on DOM mutations
        const existingIds = new Set(fieldStates.keys());

        // Call the provided callback to detect fields
        const detectedFields = callback();

        detectedFields.forEach(field => {
            if (!existingIds.has(field.id)) {
                registerField(field.id, field);
            }
        });

        log('Scanned for new fields', { newFields: detectedFields.length - existingIds.size });
    }

    // Initialize
    loadHistory();

    // Public API
    return {
        // Session management
        startSession,
        endSession,
        pauseSession,
        resumeSession,
        getCurrentSession,
        markSubmissionDetected,

        // Field tracking
        registerField,
        markFilled,
        markSkipped,
        markFailed,
        markNeedsReview,
        scanForNewFields,

        // Retry management
        processRetries,
        getRetryQueue: () => [...retryQueue],

        // Data retrieval
        getFieldStates,
        getFailures,
        getNeedsReview,
        getHistory,
        getRecentHistory,
        clearHistory,

        // Debug
        setDebugMode,
        getDebugLogs,
        clearDebugLogs,

        // Export
        exportSessionData,

        // Configuration
        setConfig: (key, value) => { CONFIG[key] = value; },
        getConfig: () => ({ ...CONFIG })
    };
})();

// Make available globally
if (typeof window !== 'undefined') {
    window.FormTracker = FormTracker;
}

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FormTracker;
}
