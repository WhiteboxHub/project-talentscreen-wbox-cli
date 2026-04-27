/**
 * leverStrategy.js
 * Strategy for Lever application forms.
 */
class LeverStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 65; // Slightly lower threshold for Lever
    }

    execute(normalizedData, aiEnabled) {
        console.log("Executing LeverStrategy...");

        const inputs = document.querySelectorAll('input, select, textarea');

        inputs.forEach(input => {
            if (input.type === 'hidden' || input.disabled || input.readOnly) return;

            let match = this.findLeverSpecificMatch(input, normalizedData);

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

        alert('Lever AutoFill complete! Please review the form.');
    }

    findLeverSpecificMatch(input, data) {
        const nameAttr = (input.name || "").toLowerCase();

        // Lever commonly uses name attributes like 'name', 'email', 'phone', 'org'
        if (nameAttr === 'name') return { value: data.identity.full_name, confidence: 95 };
        if (nameAttr === 'email') return { value: data.contact.email, confidence: 95 };
        if (nameAttr === 'phone') return { value: data.contact.phone, confidence: 95 };
        if (nameAttr === 'org') return { value: data.employment.current_company, confidence: 90 };

        // URLs in lever are often formatted like urls[LinkedIn]
        if (nameAttr.includes('url')) {
            if (nameAttr.includes('linkedin')) return { value: data.contact.linkedin, confidence: 95 };
            if (nameAttr.includes('github')) return { value: data.contact.github, confidence: 95 };
            if (nameAttr.includes('portfolio')) return { value: data.contact.portfolio, confidence: 95 };
        }

        return null;
    }
}

// Register with Strategy Registry if available
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url) => url.includes('lever.co'),
        LeverStrategy
    );
}
