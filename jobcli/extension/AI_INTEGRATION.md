# AI Integration Guide

This extension can be enhanced with AI to provide "tailored responses" for short-answer questions (e.g., "Why do you want to work here?", "Cover Letter").

## 1. Integration Strategy

Since Chrome Extensions cannot directly hold large API keys securely on the client side without risk, or run heavy models locally (though WebLLM is changing this), here are the recommended approaches:

### Option A: Local LLM (Ollama)
- **Tool**: [Ollama](https://ollama.ai/)
- **Setup**: User runs `ollama serve` locally.
- **Extension**:
    - Add permission `http://localhost:11434` to `manifest.json`.
    - Fetch completion endpoint:
    ```javascript
    fetch('http://localhost:11434/api/generate', {
        method: 'POST',
        body: JSON.stringify({
            model: 'llama2',
            prompt: `Write a cover letter for ${jobDescription} based on this resume: ${resumeData}`
        })
    })
    ```

### Option B: Interface to Cloud APIs (Gemini/OpenAI)
- **Setup**: User inputs their API Key in the Extension Options page (saved to `chrome.storage.local`).
- **Extension**:
    - Call API (e.g. Google Gemini API) directly from `background.js` or `popup.js`.
    - **Prompt Engineering**: "You are a job applicant assistant. Use the following Resume JSON to answer the question: [Question Text]."

## 2. Recommended Features to Build

1.  **Context Menu "Generate Answer"**:
    - Add `chrome.contextMenus` API.
    - User right-clicks a text area -> "Generate Answer with AI".
    - Content script reads the label of the textarea (the question).
    - Sends prompt to LLM.
    - Streams response back to the textarea.

2.  **Cover Letter Generator**:
    - In the Popup, add a "Job Description" text area.
    - Button "Generate Cover Letter".
    - Use Resume JSON + Job Desc to generate text.
    - Copy to clipboard.

## 3. Recommended Libraries
- **LangChain.js**: For structuring prompts and chaining calls.
- **WebLLM**: For running models *inside* the browser (WebGPU required), ensuring complete privacy.
