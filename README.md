# JobCLI

Production-grade CLI for automated job applications across multiple ATS platforms, powered by a self-learning local intelligence engine.

---

## Features

### Core Automation
- **One-Shot Setup** — Single `jobcli setup` command loads credentials, uploads resume, and discovers all jobs
- **Auto-Discovery Extension** — Browser extension is automatically detected and loaded from the project root; no manual `.env` paths required.
- **Wbox Dashboard Integration** — Automated job discovery from Whitebox Learning (scrolls through all rows)
- **Advanced AI Reasoning** — AXTree (Accessibility Tree) analysis for high-accuracy form field mapping
- **Universal Iframe Support** — Reach-through for Greenhouse, Lever, Paylocity, and nested iframes
- **JS Force-Fill Fallback** — Bypasses stubborn React/Angular event listeners for 100% input reliability
- **Three-Phase Strategy** — Autonomous AI → Heuristic Rules → Human-in-the-loop
- **Interactive Terminal Help** — If the agent fails to find a field, it pauses and asks you in the terminal. You can pick options (Yes/No) or enter values directly without switching to the browser.
- **Robust Manual Skip** — Typer-friendly skip command handles common typos (`skipp`, `skp`, `s`) during high-speed application loops.
- **Resume Path Validation** — Automatically detects missing resume files and warns you instead of crashing, ensuring batch continuity.
- **Multi-Provider LLM** — Native support for OpenAI, Anthropic, and Google Gemini
- **LinkedIn Manual Loop** — LinkedIn jobs are opened in the browser with a 60-second window for manual application before auto-skipping
- **Job Activity Dashboard Sync** — Automatically pushes `SUBMITTED` and `FAILED` application statuses to your central dashboard for real-time tracking

### Phase 1 — Local Learning & Memory Engine
- **Confidence-Based Memory** — Answers are only trusted after ≥ 3 successful uses at ≥ 60% confidence
- **Merge Protection** — Human/user answers can never be silently overwritten by auto-learned data
- **Outcome Feedback Loop** — Every Playwright action (success or failure) updates confidence scores in real-time
- **Personal Data Isolation** — PII fields (email, phone, name, address, etc.) are never stored in reusable memory
- **Structured Logging** — JSON logs with screenshots and DOM snapshots

### Phase 2 — Knowledge & Activity Sync *(updated)*
- **Anonymous Crowd Intelligence** — Share only high-confidence, non-PII patterns with the central server
- **Aggregated Downloads** — Pull the best field answers and UI locators from all contributing users
- **Automated Activity Logging** — Pushes your application history (title, company, status) to the central dashboard
- **Intelligent Job Mapping** — Automatically maps local job titles to centralized job types for accurate metrics
- **Unified Sync Flow** — Single command to keep your local engine and central dashboard in perfect sync

---

## Installation

### One-Line Install (Recommended)

Requires **Python 3.10+** and **git**.

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.ps1 | iex
```

This installs `wboxcli` globally — available from any terminal, just like `nvm` or `curl`. No virtual environment activation needed. After install, the interactive TUI launches automatically.

**Two ways to use it:**

| Command | What it does |
|---|---|
| `wboxcli` | Opens the interactive TUI (Claude Code style) |
| `wboxcli setup` | Runs a command directly (any subcommand works) |
| `jobcli apply --batch` | Direct CLI mode (also installed, for scripting) |

**What the installer does:**
1. Clones the repo to `~/.jobcli/src`
2. Creates an isolated Python venv at `~/.jobcli/venv`
3. Installs all dependencies + Playwright Chromium
4. Drops `wboxcli` + `jobcli` wrappers at `~/.local/bin/`
5. Adds `~/.local/bin` to your PATH (if not already there)
6. Auto-launches the interactive TUI

**To update:**
```bash
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.sh | bash
```

**To uninstall:**

macOS / Linux:
```bash
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.sh | bash
```
Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.ps1 | iex
```

### Manual Install (For Development)

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
# source venv/bin/activate    # macOS / Linux

pip install --upgrade pip setuptools
pip install -e .
playwright install chromium
```

> **Windows Note:** After installing, if `jobcli` gives a `ModuleNotFoundError`, use the `.bat` wrapper which is created automatically in `venv/Scripts/jobcli.bat`. This is a known Windows path issue with locked `.exe` files. Simply run `jobcli` as normal after activating the venv — the `.bat` takes priority.

---

## Quick Start — Just 2 Commands

### Step 1 — Fill in your `.env` file

Copy `.env.example` to `.env` in the project root and fill in your values:

```env
# LLM API Key (at least one required)
OPENAI_API_KEY=sk-...
DEFAULT_LLM_PROVIDER=openai        # openai | anthropic | gemini

# Whitebox Learning credentials
JOBCLI_USERNAME=you@example.com
JOBCLI_PASSWORD=your_password

# Resume file paths
RESUME_PDF_PATH=C:/Users/you/resume.pdf
RESUME_JSON_PATH=C:/Users/you/resume.json

# Browser mode
HEADLESS=false                     # false = visible browser window
```

### Step 2 — Run setup (does everything in one shot)

```bash
jobcli setup
```

This single command will:
1. ✅ Load all credentials from `.env` — no prompts
2. ✅ Save config to `~/.jobcli/`
3. ✅ Upload your resume automatically from the paths in `.env`
4. ✅ Log into Whitebox Learning and discover **all** jobs from your dashboard
5. ✅ Print a summary and tell you when you're ready

### Step 3 — Start Applying

```bash
# Apply to all discovered jobs
jobcli apply --batch
# Apply to a single URL
jobcli apply --url "https://boards.greenhouse.io/company/jobs/123"
```

### Cleanup

```bash
# Wipe everything (config, database, job history)
jobcli uninstall
# Force wipe without confirmation
jobcli uninstall --force
```

---

## Interaction Modes

Control how much the agent pauses for your input:

```bash
# supervised (default) — AI drives, pauses for missing fields and submission
jobcli apply --url <url> --mode supervised
# auto — fully autonomous, only stops for CAPTCHA or fatal errors
jobcli apply --url <url> --mode auto
# manual — pauses before every action batch for explicit approval
jobcli apply --url <url> --mode manual
```

---

## LinkedIn Jobs

LinkedIn does not allow bot automation. When the batch encounters a LinkedIn job:

1. The browser navigates to the LinkedIn job page
2. A **60-second countdown** is displayed in the terminal
3. You apply manually in the browser during that window
4. After 60 seconds, the engine automatically moves to the next job

---

## Commands Reference

| Command | Description |
|---|---|
| `jobcli setup` | **One-shot setup** — loads .env, saves config, uploads resume, discovers all jobs |
| `jobcli uninstall` | **Wipe everything** — deletes `~/.jobcli/` (config, database, job history) |
| `jobcli apply --batch` | Apply to all pending jobs in the database |
| `jobcli apply --url <url>` | Apply to a single specific job URL |
| `jobcli server` | Start the FastAPI bridge server for Chrome Extension integration |
| `jobcli login` | Manually update credentials (use only if `.env` is not set) |
| `jobcli login --auto` | Skip prompts if credentials already exist in `.env` |
| `jobcli discover` | Re-run job discovery from Whitebox dashboard manually |
| `jobcli resume-upload` | Manually upload a resume PDF and JSON |
| `jobcli questions` | Pre-fill answers to common application questions |
| `jobcli open-dashboard` | Launch an interactive browser window logged into Wbox |
| `jobcli scan` | Scan configured ATS portals for open jobs |
| `jobcli sync` | **Sync all data** — push patterns/activity to server and pull global updates |
| `jobcli doctor` | Validate Playwright, SQLite, config, and resume JSON |

---

## Architecture

```
jobcli/
├── cli/              # Typer CLI commands
├── core/             # Core execution engine
│   ├── engine.py     # 4-phase application loop + LinkedIn 60s manual loop
│   ├── memory.py     # AgentMemory — confidence-gated 3-layer memory
│   ├── wbox_discoverer.py  # Dashboard scraper with AG Grid scroll pagination
│   └── tool_executor.py
├── locators/         # Rule-based locator system
│   └── ats/          # ATS-specific handlers (Greenhouse, Lever, Rippling…)
├── llm/              # LLM reasoning layer (OpenAI / Anthropic / Gemini)
├── human/            # Human-in-the-loop interface
├── storage/          # SQLite persistence (SQLAlchemy)
│   ├── models.py     # ORM models incl. SyncMetadataModel
│   └── repositories.py
├── sync/             # Phase 1 local learning + Phase 2 server sync
│   ├── constants.py  # CONFIDENCE_THRESHOLD, MIN_SUCCESS_COUNT, PERSONAL_FIELDS
│   ├── extractor.py  # Exports high-confidence non-PII data for sync
│   ├── client.py     # HTTP bridge to /api/sync_cli endpoints
│   └── sqlite_merger.py  # Merges server knowledge back into local SQLite
├── bridge/           # Phase 3 Chrome Extension Integration
│   └── server.py     # FastAPI bridge server exposing /api/v1/context
└── tests/            # pytest suite
```

---

### Dashboard UI (Advanced mode)
The JobCLI Dashboard provides a high-fidelity, interactive terminal experience for monitoring and controlling your job applications in real-time.

- **Real-time Streaming**: WebSocket integration for live status updates and AI thought process visibility.
- **Interactive Terminal**: Full keyboard control, supporting manual intervention pauses and resume-on-ENTER.
- **Premium Dark Aesthetics**: A modern, Claude-style interface designed for productivity.

To start the dashboard:
1. Ensure the engine bridge is running: `jobcli server`
2. Start the UI: `cd ui && npm install && npm run dev`
3. Open `http://localhost:3000`

---

## 5-Phase Interaction Strategy
JobCLI follows a 5-phase strategy to ensure application success:

1. **Phase 1: Discovery** — URL normalization and ATS platform detection.
2. **Phase 2: Extension Autofill** — High-speed DOM-native filling of standard fields.
3. **Phase 3: AI Reasoning (LLM)** — Accessibility Tree analysis for complex/custom fields and questionnaires.
4. **Phase 4: Human-in-the-Loop** — Dashboard-mode pause for validation or missing information.
5. **Phase 5: Submission & Verification** — Final checks and behavioral outcome detection.

---

## Supported ATS Platforms

| Platform | Status |
|---|---|
| Greenhouse | ✅ Full support |
| Lever | ✅ Full support |
| Workday | ⚠️ Filtered out (requires account login) |
| Ashby | ✅ Full support |
| Rippling | ✅ Full support |
| iCIMS | ✅ Supported |
| BambooHR | ✅ Supported |
| Breezy HR | ✅ Supported |
| Jobvite | ✅ Supported |
| SmartRecruiters | ✅ Supported |
| Workable | ✅ Supported |
| Recruitee | ✅ Supported |
| LinkedIn | ⏱️ 60-second manual loop |
| Generic / Unknown | ✅ Heuristic fallback |

> **Best for first-time testing**: Greenhouse (`boards.greenhouse.io`) and Lever (`jobs.lever.co`) — no account login required.

---

## Knowledge Sync (Phase 2)

JobCLI can contribute learned patterns to a central server and pull back aggregated improvements from all contributors. No personal data is ever shared.

### How it works

```
Local SQLite
    │
    ├─ extractor.py ──► strips PII, filters weak data (success < 3)
    │
    ▼
POST /api/sync_cli/knowledge_sync   ──► Server aggregates & scores
    │
POST /api/job_activity_logs/bulk     ──► Pushes application logs to dashboard
    │
GET  /api/sync_cli/knowledge_updates ◄── Top-ranked patterns per ATS
    │
    ▼
sqlite_merger.py ──► only overwrites local if server_confidence > local_confidence
```

### Running a sync

```bash
jobcli sync
```

### Privacy guarantees

| What is shared | What is NEVER shared |
|---|---|
| Field label → value mappings (e.g. `years_of_experience → 4`) | Email, phone, name, address |
| UI locators (CSS selectors ranked by success rate) | Resume content, salary, SSN |
| ATS type + confidence scores | Job URLs, company names, candidate identity |

---

## Local Learning & Memory System

JobCLI learns from every application it runs. Field answers and UI locators accumulate confidence scores based on real execution outcomes.

### How confidence works

```
confidence = success_count / (success_count + failure_count)
```

A record is only returned from memory (instead of calling the LLM) when **both** conditions are met:

| Gate | Default | Meaning |
|---|---|---|
| `confidence >= CONFIDENCE_THRESHOLD` | 0.6 | At least 60% success rate |
| `success_count >= MIN_SUCCESS_COUNT` | 3 | Confirmed correct at least 3 times |

### Merge protection rules

| Incoming source | Existing source | Value updated? |
|---|---|---|
| `human` / `user` | anything | ✅ Yes — higher trust wins |
| `auto` / `local` | `auto` / `local` | ✅ Yes |
| `auto` / `local` | `human` / `user` | ❌ No — human answer preserved |

---

## Configuration

All config lives in `~/.jobcli/`:

| File | Purpose |
|---|---|
| `config.json` | API keys, paths, preferences |
| `jobcli.db` | SQLite database (memory, answers, locators, sync state) |
| `logs/` | Per-job JSON logs, screenshots, DOM snapshots |

### `.env` file (project root — full reference)

```env
# Whitebox Learning
WBOX_LOGIN_URL=https://whitebox-learning.com/login
WBOX_DASHBOARD_URL=https://whitebox-learning.com/user_dashboard

# LLM API Keys (at least one required for AI form-filling)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AI...
DEFAULT_LLM_PROVIDER=openai       # openai | anthropic | gemini

# Job Board Credentials
JOBCLI_USERNAME=you@example.com
JOBCLI_PASSWORD=yourpassword

# LinkedIn Credentials (optional — for reference only, not used for automation)
LINKEDIN_USERNAME=you@example.com
LINKEDIN_PASSWORD=yourpassword

# Resume paths
RESUME_PDF_PATH=C:/Users/you/resume.pdf
RESUME_JSON_PATH=C:/Users/you/resume.json

# Browser settings
HEADLESS=false                    # false = visible browser
MAX_RETRIES=3

# Storage
DATABASE_PATH=C:/Users/you/.jobcli/jobcli.db
LOG_DIRECTORY=logs
```

---

## Resume JSON Format

```json
{
  "personal": {
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com",
    "phone": "+1-555-0100",
    "linkedin": "https://linkedin.com/in/janedoe"
  },
  "experience": [
    {
      "company": "Acme Corp",
      "title": "Senior Engineer",
      "start_date": "2021-01",
      "end_date": "present",
      "description": "Led platform migration..."
    }
  ],
  "education": [
    {
      "institution": "State University",
      "degree": "B.S. Computer Science",
      "graduation_year": "2019"
    }
  ]
}
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Testing

JobCLI ships with three test strata. Run them before any change that
touches browser automation or ATS handlers.

### 1. Full test suite

```bash
pytest
```

### 2. Stealth / anti-bot verification

```bash
pytest tests/test_stealth.py -v
```

### 3. Live fingerprint diagnostic

```bash
python scripts/stealth_check.py
python scripts/stealth_check.py --headless
python scripts/stealth_check.py --url 'https://bot.sannysoft.com/'
```

## License

MIT
