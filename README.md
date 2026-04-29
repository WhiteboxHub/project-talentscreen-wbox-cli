# JobCLI

Production-grade CLI for automated job applications across multiple ATS platforms, powered by a self-learning local intelligence engine.

---

## Features

### Core Automation
- **Wbox Dashboard Integration** — Automated job discovery from Whitebox Learning
- **Advanced AI Reasoning** — AXTree (Accessibility Tree) analysis for high-accuracy form field mapping
- **Universal Iframe Support** — Reach-through for Greenhouse, Lever, Paylocity, and nested iframes
- **JS Force-Fill Fallback** — Bypasses stubborn React/Angular event listeners for 100% input reliability
- **Three-Phase Strategy** — Autonomous AI → Heuristic Rules → Human-in-the-loop
- **Multi-Provider LLM** — Native support for OpenAI, Anthropic, and Google Gemini

### Phase 1 — Local Learning & Memory Engine
- **Confidence-Based Memory** — Answers are only trusted after ≥ 3 successful uses at ≥ 60% confidence
- **Merge Protection** — Human/user answers can never be silently overwritten by auto-learned data
- **Outcome Feedback Loop** — Every Playwright action (success or failure) updates confidence scores in real-time
- **Personal Data Isolation** — PII fields (email, phone, name, address, etc.) are never stored in reusable memory
- **Structured Logging** — JSON logs with screenshots and DOM snapshots

### Phase 2 — Knowledge Sync *(new)*
- **Anonymous Crowd Intelligence** — Share only high-confidence, non-PII patterns with the central server
- **Aggregated Downloads** — Pull the best field answers and UI locators from all contributing users
- **Strict Merge Protection** — Server data only updates local data when `server_confidence > local_confidence`
- **Weak Data Filtering** — Records with fewer than 3 successes are never uploaded or accepted
- **Locator Ranking** — Server ranks selectors per `(ats_type, purpose)` using `score = confidence + log(success_count)` and returns the top 3

---

## Installation

Requires **Python 3.10+**.

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
# source venv/bin/activate    # macOS / Linux

pip install -e .
playwright install chromium
```

---

## Quick Start

```bash
# 1. Initialize database and config
jobcli setup

# 2. Add credentials & LLM API keys
jobcli login

# 3. Upload your resume
jobcli resume-upload --pdf resume.pdf --json resume.json

# 4. Pre-fill common answers (optional but recommended)
jobcli questions

# 5. Discover jobs from your Wbox dashboard
jobcli discover

# 6. Start the FastAPI bridge server for the Chrome Extension
jobcli server

# 7. Apply — single job
jobcli apply --url https://boards.greenhouse.io/company/jobs/123

# 8. Apply — all pending jobs
jobcli apply --batch
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

## Commands

| Command | Description |
|---|---|
| `jobcli setup` | Initialize configuration and database |
| `jobcli login` | Store credentials for job boards and LLM API keys |
| `jobcli config` | View or modify configuration |
| `jobcli resume-upload` | Upload resume in PDF and JSON formats |
| `jobcli questions` | Pre-fill answers to common application questions |
| `jobcli discover` | Fetch job links from your Whitebox Learning dashboard |
| `jobcli open-dashboard` | Launch an interactive browser window logged into Wbox |
| `jobcli apply` | Apply to jobs (single `--url` or `--batch` mode) |
| `jobcli server` | Start the FastAPI bridge server for Chrome Extension integration |
| `jobcli sync` | Push local learned patterns to server and pull aggregated updates |
| `jobcli doctor` | Validate Playwright, SQLite, config, and resume JSON |

---

## Architecture

```
jobcli/
├── cli/              # Typer CLI commands
├── core/             # Core execution engine
│   ├── engine.py     # 4-phase application loop
│   ├── memory.py     # AgentMemory — confidence-gated 3-layer memory
│   └── tool_executor.py
├── locators/         # Rule-based locator system
│   └── ats/          # ATS-specific handlers (Greenhouse, Lever, Workday…)
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
JobCLI now follows a 5-phase strategy to ensure application success:

1. **Phase 1: Discovery** — URL normalization and ATS platform detection.
2. **Phase 2: Extension Autofill** — High-speed DOM-native filling of standard fields.
3. **Phase 3: AI Reasoning (LLM)** — Accessibility Tree analysis for complex/custom fields and questionnaires.
4. **Phase 4: Human-in-the-Loop** — Dashboard-mode pause for validation or missing information.
5. **Phase 5: Submission & Verification** — Final checks and behavioral outcome detection.

---

3. **Extension Execution**: The extension listens for the trigger, fetches the parsed resume + memory from the bridge server, and executes native DOM autofill strategies.
4. **Feedback Loop**: The extension posts a report back to the CLI with what it filled, allowing the Python engine to seamlessly fall back to LLM processing for any missed fields.

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
GET  /api/sync_cli/knowledge_updates ◄── Top-ranked patterns per ATS
    │
    ▼
sqlite_merger.py ──► only overwrites local if server_confidence > local_confidence
```

### Running a sync

```bash
jobcli sync
```

The command will interactively confirm before syncing. It shows how many applications worth of new data you have accumulated since the last sync.

### Privacy guarantees

| What is shared | What is NEVER shared |
|---|---|
| Field label → value mappings (e.g. `years_of_experience → 4`) | Email, phone, name, address |
| UI locators (CSS selectors ranked by success rate) | Resume content, salary, SSN |
| ATS type + confidence scores | Job URLs, company names, candidate identity |

### Merge protection rules (client side)

| Condition | Action |
|---|---|
| `server_confidence > local_confidence` | Local value **updated** |
| `server_confidence ≤ local_confidence` | Local value **kept** |
| `server total_success < 3` | Record **ignored** |

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

### Personal data isolation

The following fields are **never** exported from local memory to the extractor output:
`email`, `phone`, `name`, `address`, `linkedin`, `github`, `ssn`, `salary`, `date of birth`, and 40+ other PII categories.

### Inspecting the local memory

```bash
# Run the smoke test against the live DB
python -X utf8 smoke_test.py

# See what would be exported to a Phase 2 sync server
python -X utf8 -c "
import json
from jobcli.storage.models import Database
from jobcli.sync.extractor import extract_field_answers, extract_locators
db = Database()
db.create_tables()
s = db.get_session()
print(json.dumps(extract_field_answers(s), indent=2))
s.close()
"
```

---

## Configuration

All config lives in `~/.jobcli/`:

| File | Purpose |
|---|---|
| `config.json` | API keys, paths, preferences |
| `jobcli.db` | SQLite database (memory, answers, locators, sync state) |
| `logs/` | Per-job JSON logs, screenshots, DOM snapshots |

### `.env` file (project root)

```env
OPENAI_API_KEY=sk-...
DEFAULT_LLM_PROVIDER=openai      # openai | anthropic | gemini
HEADLESS=false                   # false = visible browser
RESUME_PDF_PATH=C:/path/to/resume.pdf
RESUME_JSON_PATH=C:/path/to/resume.json

# Phase 2 Sync (optional)
JOBCLI_SYNC_SERVER_URL=https://your-backend.com   # defaults to http://localhost:8000

# Phase 3 Extension Integration
EXTENSION_PATH=C:/path/to/project-autofill-resume-json-extension
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

## Supported ATS Platforms

| Platform | Status |
|---|---|
| Greenhouse | ✅ Full support |
| Lever | ✅ Full support |
| Workday | ✅ Supported (requires account login) |
| Ashby | ✅ Full support |
| iCIMS | ✅ Supported |
| BambooHR | ✅ Supported |
| Jobvite | ✅ Supported |
| SmartRecruiters | ✅ Supported |
| Taleo | ✅ Supported |
| Generic / Unknown | ✅ Heuristic fallback |

> **Best for first-time testing**: Greenhouse (`boards.greenhouse.io`) and Lever (`jobs.lever.co`) — no account login required.

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

Runs unit tests for CLI guardrails, LLM client wrappers, repositories,
session management, the state machine, URL normalisation, the async
engine, and the stealth fingerprint (see below).

### 2. Stealth / anti-bot verification

The single biggest reason an ATS flags an application as spam is a
bot-like browser fingerprint. `tests/test_stealth.py` locks down every
patch we apply via `jobcli/core/stealth.py` so regressions are caught
before they reach production.

```bash
# Just the stealth tests
pytest tests/test_stealth.py -v
```

Two strata of checks:

| Stratum | What it verifies | Runs when |
|---|---|---|
| **Static** (13 tests) | Every fingerprint patch is present in the stealth JS + launch config (webdriver hidden, plugins populated, WebGL vendor spoofed, `Function.prototype.toString` native, iframe contentWindow patched, etc.) | Always |
| **Runtime** (9 tests) | Launches headless Chromium with the production config, injects the stealth script, and asserts the patches actually took effect in a real document — `navigator.webdriver === undefined`, plugins length ≥ 3, WebGL vendor ≠ SwiftShader, spoofed getters report `[native code]`, permissions.query returns `prompt` not `denied`, etc. | Skipped automatically when Playwright browsers aren't installed |

To run the runtime tests you need the Chromium binary:

```bash
playwright install chromium
pytest tests/test_stealth.py -v
```

When you add a new patch to `jobcli/core/stealth.py`, add a matching
assertion in `tests/test_stealth.py` — both a static check (the source
contains the patch) and a runtime check (the page reflects it).

### 3. Live fingerprint diagnostic

Before a real application submission on a flaky ATS, run the
diagnostic script to confirm your current fingerprint still looks
human. It spins up Chromium with the exact flags / init-script the
production engine uses and prints a pass/fail table for each signal,
plus excerpts from public bot-detection pages.

```bash
# Headed (watch what the ATS would see)
python scripts/stealth_check.py

# Headless — same binary the engine uses at apply time
python scripts/stealth_check.py --headless

# Throw in a specific ATS URL or your own probe
python scripts/stealth_check.py --url 'https://bot.sannysoft.com/'
python scripts/stealth_check.py --skip-remote   # offline mode
```

Exit code is `0` when every local check passes, `1` otherwise — wire
it into CI (or a git pre-push hook) to prevent broken stealth patches
from shipping. A healthy output looks like:

```
[PASS] navigator.webdriver is undefined
[PASS] navigator.plugins is populated
[PASS] navigator.languages looks US-English
[PASS] window.chrome exists
[PASS] window.chrome.runtime has OnInstalledReason
[PASS] navigator.hardwareConcurrency is plausible
[PASS] navigator.deviceMemory is plausible
[PASS] WebGL vendor is not SwiftShader
[PASS] Function.prototype.toString on spoofed getter looks native
[PASS] navigator.permissions.query('notifications') returns 'default'
```

If any line reads `[FAIL]`, **do not run a live application** until
the patch is fixed — that exact signal is what Ashby / Greenhouse /
Workday spam classifiers will latch onto.

## License

MIT
