/**
 * ripplingStrategy.js
 * Strategy for Rippling application forms.
 */
class RipplingStrategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70;
        this._hasUploadedRipplingResume = false;
    }

    async execute(normalizedData, resumeFile = null) {
        // console.log("Executing RipplingStrategy...");

        // 1. Specific Handle for Location Field
        const locationInput = document.querySelector('input[aria-label="textbox"]');
        if (locationInput && !locationInput.value) {
            const loc = normalizedData.contact || {};
            const locationStr = [loc.city, loc.state, loc.country].filter(Boolean).join(', ');
            if (locationStr) {
                this.setInputValue(locationInput, locationStr, 'green');
            }
        }

        // 2. Explicit Resume Upload (Fallback if Generic misses it)
        if (resumeFile && !this._hasUploadedRipplingResume) {
            const ripplingFileInputs = document.querySelectorAll('input[type="file"]');
            ripplingFileInputs.forEach(input => {
                const parent = input.closest('label') || input.parentElement;
                const containerTxt = parent?.innerText?.toLowerCase() || "";
                if ((containerTxt.includes("résumé") || containerTxt.includes("resume") || containerTxt.includes("upload")) && !containerTxt.includes("cover")) {
                    this.setFileUpload(input, resumeFile);
                }
            });
        }

        // Run generic execution for the rest
        await super.execute(normalizedData, resumeFile);
    }

    findValueForInput(input, data) {
        const features = this.extractFeatures(input);
        const labelTxt = features.label_text.toLowerCase();

        const identity = data?.identity || {};

        // 1. Veteran Status
        if (labelTxt.includes("veteran status")) {
            return { value: identity.veteran_status || "I am not a protected veteran", confidence: 95, fieldKey: "identity.veteran_status" };
        }

        // 2. Disability Status
        if (labelTxt.includes("disability status")) {
            return { value: identity.disability_status || "No, I don't have a disability", confidence: 95, fieldKey: "identity.disability_status" };
        }

        // 3. SMS Agreement
        if (labelTxt.includes("receive text message updates") || labelTxt.includes("sms agreement") || labelTxt.includes("text message agreement")) {
            return { value: "Yes", confidence: 95, fieldKey: "custom.sms_agreement" };
        }

        return super.findValueForInput(input, data);
    }

    // Override to handle radio buttons better in Rippling context
    handleRadioCheckbox(input, data) {
        const features = this.extractFeatures(input);
        const labelTxt = (this.getLabelText(input) || "").toLowerCase();
        const valueMatch = this.findValueForInput(input, data);

        if (valueMatch && valueMatch.value) {
            const targetVal = String(valueMatch.value).toLowerCase();

            // Veteran Status specific radio labels
            if (valueMatch.fieldKey === "identity.veteran_status") {
                if (targetVal.includes("not a protected veteran") && (labelTxt.includes("not a protected veteran") || labelTxt.includes("no, i am not"))) {
                    input.checked = true;
                    this.setInputValue(input, null, 'green');
                    return;
                }
            }

            // Disability Status specific radio labels
            if (valueMatch.fieldKey === "identity.disability_status") {
                if (targetVal === "no" && (labelTxt.includes("no, i don't have a disability") || labelTxt === "no")) {
                    input.checked = true;
                    this.setInputValue(input, null, 'green');
                    return;
                }
            }

            // SMS Agreement
            if (valueMatch.fieldKey === "custom.sms_agreement") {
                if (targetVal === "yes" && labelTxt === "yes") {
                    input.checked = true;
                    this.setInputValue(input, null, 'green');
                    return;
                }
            }
        }

        super.handleRadioCheckbox(input, data);
    }

    // Helper to reuse the logic from GenericStrategy but with a specific input
    setFileUpload(input, resumeFile) {
        try {
            const byteString = atob(resumeFile.data.split(',')[1]);
            const mimeString = resumeFile.data.split(',')[0].split(':')[1].split(';')[0];
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) {
                ia[i] = byteString.charCodeAt(i);
            }
            const blob = new Blob([ab], { type: mimeString });
            const file = new File([blob], resumeFile.name, { type: mimeString });

            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            input.files = dataTransfer.files;

            ['change', 'input', 'blur'].forEach(ev => {
                input.dispatchEvent(new Event(ev, { bubbles: true }));
            });

            this._hasUploadedRipplingResume = true;
        } catch (e) {
            console.error("AutoFill: Error attaching file", e);
        }
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => url.includes('rippling.com') || doc.body.innerText.includes('Rippling'),
        RipplingStrategy
    );
}
