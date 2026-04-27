# AutoFill Job Applications Extension

A powerful Chrome Extension that fully automates the manual data entry process of job applications. By parsing your standard [JSON Resume](https://jsonresume.org/) schema, this extension intelligently maps and autofills fields on common Applicant Tracking Systems (ATS) like Greenhouse, Lever, and Workday.

## 🚀 Key Features

*   **100% Automatic Execution**: No need to click "Fill." As soon as you open a supported job application page, the extension intercepts DOM rendering, Single-Page App (SPA) routes, and Mutations to fill forms instantly.
*   **ATS Strategy Routing**: Implements dedicated matching algorithms for specific job boards:
    *   **Greenhouse** `(*.greenhouse.io)`
    *   **Lever** `(*.lever.co)`
    *   **Workday** `(*.workday.com)`
*   **Confidence Scoring & Visual Feedback**: Matches are assigned a confidence score based on keywords, nearby context, and HTML types.
    *   🟢 **Green**: High-confidence match (Auto-filled).
    *   🟡 **Yellow**: Low-confidence match (Prompts a manual UI confirmation box).
    *   🔴 **Red**: Required field that could not be matched.
*   **Chrome Side Panel UI**: Anchor the extension UI to the side of your browser. No more frustrating popups closing when you click away!
*   **Live Summary & Editing**: After a form is filled, the side panel displays a complete table reporting every answered field. Edit values directly in the panel and click **Apply Edits** to instantly push corrections back to the webpage.
*   **Custom ATS Overrides**: Encounter repeated questions your resume doesn't answer (e.g., "Will you now or in the future require sponsorship?")? Map custom JSON key-value pairs per ATS platform directly in the extension to automatically bypass them forever.
*   **Performance Caching**: Normalizes your resume file upon upload and stores the highly optimized object locally using Chrome Storage, ensuring lightning-fast execution on heavy dynamic pages.

## 🛠️ Installation

1.  Clone this repository or download the source code.
2.  Open Chrome and navigate to `chrome://extensions/`.
3.  Toggle **Developer mode** in the top right corner.
4.  Click **Load unpacked**.
5.  Select the directory containing this project.

## 📖 Usage

1.  **Format your Resume**: Create a `resume.json` file following the JSON Resume format. Use the `resume.json` included in this repo as a template.
2.  **Upload & Store**: Click the extension icon to open the Chrome Side Panel. Click **Upload resume.json** to parse and cache your data securely in local storage.
3.  *(Optional)* **Custom Answers**: Define static answers for repeating demographic/compliance questions under the "Custom Answers" section.
4.  **Apply**: Navigate to any Lever, Greenhouse, or Workday job application. Watch the form fill itself!
5.  **Review**: Expand the **Fill Summary** in the Side Panel, modify any incorrect values, click **Apply Edits**, and submit your application.

## 📂 Project Structure

*   `manifest.json`: Manifest V3 configuration supporting the Side Panel API.
*   `sidepanel.html` / `styles.css` / `sidepanel.js`: The persistent extension UI, table summary logic, and user configuration panel.
*   `content.js`: Injected script responsible for listening to DOM loaded, history API, and MutationObserver events, routing to the correct ATS strategy.
*   `resumeProcessor.js`: Handles flattening and normalizing complex schemas to a 1D internal index.
*   `atsStrategies/`: Directory containing modular strategy classes for handling different application architectures (`genericStrategy.js`, `greenhouseStrategy.js`, `leverStrategy.js`, `workdayStrategy.js`).

## ✅ To-Do / Roadmap

*   [ ] **AI Integration**: Add support for Ollama (local LLM) or OpenAI API (via the currently disabled AI toggle switch) to dynamically hallucinate answers for unstructured short-answer questions.
*   [ ] **Generate Cover Letter**: One-click feature to scrape the Job Description and trigger a generative model to paste a custom cover letter.
*   [ ] **Multiple Profiles**: Support saving multiple resume iterations (e.g., "Frontend Resume", "Backend Resume").
