/**
 * workdayStrategy.js
 * Strategy for Workday application forms.
 */
class WorkdayStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; // Keep standard threshold for workday
    }

    execute(normalizedData, aiEnabled) {
        console.log("Executing WorkdayStrategy...");

        // Workday uses dynamic shadow DOMs or heavily nested divs. Basic input selection
        const inputs = document.querySelectorAll('input, select, textarea');

        inputs.forEach(input => {
            if (input.type === 'hidden' || input.disabled || input.readOnly) return;

            let match = this.findWorkdaySpecificMatch(input, normalizedData);

            if (!match || !match.value) {
                match = this.findValueForInput(input, normalizedData);
            }

            if (match && match.value) {
                if (match.confidence >= this.CONFIDENCE_THRESHOLD) {
                    this.setInputValue(input, match.value);
                } else {
                    this.promptUserConfirmation(input, match.value, match.confidence);
                }
            } else if (aiEnabled) {
                console.log("AI Enabled: Would attempt to fill unmatched field", input.name || input.id);
            }
        });

        alert('Workday AutoFill complete! Please review the form.');
    }

    findWorkdaySpecificMatch(input, data) {
        const dataAutomationId = (input.getAttribute('data-automation-id') || "").toLowerCase();

        if (!dataAutomationId) return null;

        // Common Workday data-automation-ids
        if (dataAutomationId.includes('legalname-first')) return { value: data.identity.first_name, confidence: 95 };
        if (dataAutomationId.includes('legalname-last')) return { value: data.identity.last_name, confidence: 95 };
        if (dataAutomationId.includes('email')) return { value: data.contact.email, confidence: 95 };
        if (dataAutomationId.includes('phone-number')) return { value: data.contact.phone, confidence: 95 };
        if (dataAutomationId.includes('address-line1')) return { value: data.contact.address, confidence: 95 };
        if (dataAutomationId.includes('address-city')) return { value: data.contact.city, confidence: 95 };
        if (dataAutomationId.includes('address-postal-code')) return { value: data.contact.zip_code, confidence: 95 };

        return null;
    }
}

// Register with Strategy Registry if available
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('workday.com') || url.includes('myworkdayjobs.com'),
        WorkdayStrategy
    );
}
