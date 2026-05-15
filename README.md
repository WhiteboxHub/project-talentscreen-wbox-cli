# JobCLI

Production-grade CLI for automated job applications across multiple ATS platforms, powered by a self-learning local intelligence engine.

---

## Features

### Core Automation
- **No `.env` files** — credentials, LLM keys, resume paths, and the API base URL all live in `~/.jobcli/jobcli.db`, written by `jobcli login`, `jobcli resume-upload`, and `jobcli config`. The CLI never reads a `.env` file.
- **Guided interactive TUI** — running `wboxcli` walks you through onboarding in a fixed order (WBL login → visible browser + extension smoke test → LLM key → resume → discover), and at every step shows a `▶ Next step` panel telling you exactly which command to type next. Non-technical users never have to guess what to run.
- **Auto-download Extension** — `jobcli setup` downloads the TalentScreen extension into `~/.jobcli/extension_unpacked/` and `apply` loads it automatically — no manual paths required.
- **Always-visible browser** — `jobcli apply` forces `headless=False`; Chrome is always on screen so you can watch and intervene.
- **Don't-refill guard** — the extension autofills first; a three-layer guard (engine snapshot → LLM action filter → executor live-read) prevents the LLM or rules from overwriting any field the extension already populated. Placeholder values like `"Select..."` are correctly treated as empty, so real values still flow through.
- **Required-first human prompt** — when fields stay empty after extension + LLM + rules, the terminal asks for `[red]*required[/red]` fields first (must answer) and `[dim](optional, Enter to skip)[/dim]` fields second (press Enter to skip). The `required` flag is propagated from the page's Accessibility Tree.
- **Source-filtered discover** — `jobcli discover` only ingests links whose WBL `Source` value is one of `trueup.io`, `hiring.cafe`, `jobright`, `linkedin`. Other listings (Indeed, Workday, …) are dropped at ingest time and never touch the local DB, so `apply` simply iterates whatever is in the queue. To change the allow-list, edit `DEFAULT_SOURCES` in [`jobcli/core/source_filter.py`](jobcli/core/source_filter.py).
- **WBL job listings API** — `jobcli discover` calls `GET /api/positions/cli_window` (Bearer auth), pages with `offset` until every listing row is fetched (same filters as the dashboard Jobs grid by default: all time, `open` only). Tune with `JOBCLI_DISCOVER_DAYS`, `JOBCLI_DISCOVER_PAGE_SIZE`, `JOBCLI_DISCOVER_STATUS`. Legacy Playwright dashboard scrape: `WBOX_DISCOVER_MODE=browser` or `jobcli discover --legacy-ui`.
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

### Stable Release (Main)

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/install.ps1 | iex
```

### Development Release (Dev)

*For testing the latest features.*

**macOS / Linux:**
```bash
JOBCLI_BRANCH=dev curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.sh | bash
```

**Windows (PowerShell):**
```powershell
$env:JOBCLI_BRANCH="dev"; irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.ps1 | iex
```

This installs `wboxcli` globally — available from any terminal, just like `nvm` or `curl`. No virtual environment activation needed. After install, the interactive TUI launches automatically.

**Two ways to use it:**

| Command | What it does |
|---|---|
| `wboxcli` | Opens the interactive TUI (Claude Code style) |
| `wboxcli setup` | Runs a subcommand directly (any `jobcli` subcommand works under `wboxcli`) |
| `jobcli apply` | Direct CLI — apply to all pending jobs after `discover` |

**What the installer does:**
1. Clones the repo to `~/.jobcli/src`
2. Creates an isolated Python venv at `~/.jobcli/venv`
3. Installs all dependencies + Playwright Chromium
4. Drops `wboxcli` + `jobcli` shims at `~/.local/bin/` (Windows: `wboxcli.cmd` + `jobcli.cmd`)
5. Adds `~/.local/bin` to your PATH (if not already there)
6. Auto-launches the interactive TUI

**To update** (just re-run the installer — same one-liner as above):

```bash
# macOS / Linux (Main)
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/install.sh | bash

# macOS / Linux (Dev)
JOBCLI_BRANCH=dev curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.sh | bash
```
```powershell
# Windows PowerShell (Main)
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/install.ps1 | iex

# Windows PowerShell (Dev)
$env:JOBCLI_BRANCH="dev"; irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.ps1 | iex
```

**To uninstall** (see also [Cleanup, DB Reset, and Uninstall](#cleanup-db-reset-and-uninstall) for finer-grained options):

```bash
# macOS / Linux (Main)
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/uninstall.sh | bash

# macOS / Linux (Dev)
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.sh | bash
```
```powershell
# Windows PowerShell (Main)
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/uninstall.ps1 | iex

# Windows PowerShell (Dev)
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

> **Windows Note:** If a `pip install -e .` step fails with `[WinError 5] Access is denied` on `jobcli.exe`, close any open terminal that still has `jobcli` running and retry. The installer-managed venv at `~/.jobcli/venv` avoids this entirely.

---

## Quick Start — Interactive TUI (recommended for first-time users)

Just run:

```powershell
wboxcli
```

If `~/.jobcli/` does not exist yet, the CLI walks you through onboarding in this exact order:

| # | Step | What happens |
|---|---|---|
| 1 | **WBL Login + Browser test** | Enter your Whitebox email and password. Chrome opens visibly, the **TalentScreen** extension loads, the dashboard renders, and you see `✓ Open browser`, `✓ Plugin load`, `✓ Test successful`. Credentials are saved to `~/.jobcli/jobcli.db`. |
| 2 | **LLM provider + API key** | Pick `openai` / `anthropic` / `gemini`, paste your key. Validation is done in-process. |
| 3 | **Resume upload** | Enter the full path to your PDF (and JSON if you have one). |
| 4 | **Discover jobs** | The CLI calls the WBL listings API and tells you how many pending jobs are in the queue. |

After every step a `▶ Next step` panel appears at the bottom of the terminal showing the exact next command (`apply`, `discover`, etc.) — you never have to remember anything.

Returning users (where `~/.jobcli/jobcli.db` already exists) skip straight to the welcome banner and the `▶ Next step: apply` panel.

### Starting fresh (re-trigger onboarding)

`quit` only closes the session — it does not delete saved state. To go back to Step 1:

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.jobcli"   # Windows
# rm -rf ~/.jobcli                                       # macOS / Linux
wboxcli
```

Or use the built-in equivalents:

```powershell
jobcli reset --force     # wipe DB only (keeps extension + logs)
jobcli uninstall --force # wipe everything under ~/.jobcli/
```

---

## Quick Start — Direct CLI subcommands

JobCLI is fully **interactive** — there is no `.env` file. All configuration is stored in
`~/.jobcli/jobcli.db` by the commands below. The same four steps work on PowerShell, zsh, and bash.

### Step 1 — Save credentials and LLM keys

```bash
jobcli login
```

You'll be prompted for:
- Whitebox Learning username/password
- LLM API keys (at least one of OpenAI, Anthropic, Gemini)
- Default LLM provider (`openai` / `anthropic` / `gemini`)

You are **never asked for the WBL API base URL**. The CLI silently probes the hardcoded production endpoint — `https://api.whitebox-learning.com/api` — with the credentials you just entered, and saves it if authentication succeeds. If it's unreachable at login time, the next `jobcli discover` re-probes automatically. Developers running a local backend can override the saved URL with `jobcli config --key sync_server_url --set <url>`.

Re-running `jobcli login` updates the saved values. `jobcli login --auto` skips prompts entirely if credentials are already saved.

### Step 2 — Load your resume

```bash
# Windows (PowerShell)
jobcli resume-upload --pdf "C:\Users\you\resume.pdf" --json "C:\Users\you\resume.json"

# macOS / Linux
jobcli resume-upload --pdf "/Users/you/resume.pdf" --json "/Users/you/resume.json"
```

Both files are parsed and the absolute paths are saved into `~/.jobcli/jobcli.db`. The PDF is uploaded to the application engine at apply time; the JSON drives every form field.

### Step 3 — One-shot validation (downloads extension, runs browser test)

```bash
jobcli setup
```

This validates your saved config, downloads the **TalentScreen** Chrome extension into
`~/.jobcli/extension_unpacked/`, and runs a 15-second visible-browser smoke test.

### Step 4 — Discover, then apply

```bash
jobcli discover
jobcli apply
```

Apply to a single URL (optional):

```bash
jobcli apply --url "https://boards.greenhouse.io/company/jobs/123"
```

`jobcli apply` with no arguments applies to **all pending jobs** in your local DB. Chrome always opens visibly — `apply` is a human-in-the-loop flow by design.

---

## Cleanup, DB Reset, and Uninstall

> **Heads-up — `quit` does NOT wipe state.** Typing `quit` inside the TUI only closes the session; credentials, LLM keys, resume, and discovered jobs all stay in `~/.jobcli/jobcli.db`, so the next `wboxcli` run skips onboarding and shows the welcome banner. To force the onboarding flow again, use one of the cleanup commands below (or `Remove-Item -Recurse -Force "$env:USERPROFILE\.jobcli"` on Windows / `rm -rf ~/.jobcli` on macOS-Linux).

JobCLI gives you **three levels of cleanup**, smallest to largest. Pick the one that matches what you actually want to wipe.

| Command | Removes | Keeps |
|---|---|---|
| `jobcli db clear-jobs` | Discovered jobs + per-job application logs | Resume, credentials, LLM keys, field-answer memory, learned locators, sync state |
| `jobcli db reset` (alias: `jobcli reset`) | Entire local SQLite DB file (`jobcli.db` + `-wal` / `-shm` / `-journal` sidecars) | Log directory (`~/.jobcli/logs/`), downloaded extension, venv, shims |
| `jobcli uninstall` | Everything under `~/.jobcli/` **plus** the `wboxcli` / `jobcli` shims in `~/.local/bin/` | Nothing inside `~/.jobcli`; PATH entry is left alone (remove it manually if you like) |

### 1. Just forget the discovered jobs

```bash
jobcli db clear-jobs            # confirms first
jobcli db clear-jobs --force    # skip the prompt
```

Resets the `jobs` and `application_logs` tables only. Your resume, login, LLM keys, field answers, and learned locators stay put. Use this between dashboard refreshes.

### 2. Wipe the whole local database, keep the install

```bash
jobcli db reset                 # confirms first
jobcli db reset --force         # skip the prompt
jobcli reset --force            # short alias
```

Deletes `~/.jobcli/jobcli.db` (and any `.wal` / `.shm` / `.journal` sidecars) and recreates an empty schema. The TalentScreen extension, log files, venv, and global shims all remain — so the next `jobcli login` + `jobcli resume-upload` puts you straight back in business.

### 3. Full uninstall (works on Windows + macOS + Linux)

```bash
jobcli uninstall                # confirms first
jobcli uninstall --force        # skip the prompt
```

What it does:
- Releases all SQLite/log file handles so Windows doesn't block deletion.
- Deletes everything under `~/.jobcli/` (config, DB, extension, logs).
- Deletes the global shims: `wboxcli.cmd` / `jobcli.cmd` on Windows, `wboxcli` / `jobcli` elsewhere.
- **On Windows, if `jobcli` is the running process**, the venv subtree under `~/.jobcli/venv/` is *intentionally* skipped (Python can't delete its own executable). The command prints a one-liner to finish the job from a fresh terminal — usually the bundled `scripts/uninstall.ps1` one-liner from the [Installation](#installation) section.

If `jobcli uninstall` ever leaves files behind, the **bundled shell uninstaller** is the always-clean fallback because it doesn't run from inside the venv:

```bash
# macOS / Linux (Main)
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/uninstall.sh | bash

# macOS / Linux (Dev)
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.sh | bash
```
```powershell
# Windows PowerShell (Main)
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/uninstall.ps1 | iex

# Windows PowerShell (Dev)
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.ps1 | iex
```

> The PATH entry pointing to `~/.local/bin` is left alone by every cleanup command — remove it from your shell profile (`~/.zshrc` / `~/.bashrc`) or Windows System Environment Variables if you want it gone too.

---

## Interaction Modes

Control how much the agent pauses for your input:

```bash
# supervised (default) — AI drives, pauses for missing fields and submission
jobcli apply --mode supervised
# single URL
jobcli apply --url <url> --mode supervised
# auto — fully autonomous, only stops for CAPTCHA or fatal errors
jobcli apply --mode auto
# manual — pauses before every action batch for explicit approval
jobcli apply --mode manual
```

### Two-tier human prompt (Supervised / Manual)

When the extension + rules + LLM still leave fields empty, the terminal pauses with a yellow panel summarising the gap, then asks for the missing fields in two passes:

1. **Required fields** — labelled `[red]*required[/red]`. You must type a value; pressing Enter loops the question.
2. **Optional fields** — labelled `[dim](optional, Enter to skip)[/dim]`. Press Enter to skip; any text you type is filled.

The `required` flag is read directly from the page's Accessibility Tree (`aria-required`, the HTML `required` attribute, or a visible `*` next to the label), so it matches what the form itself considers mandatory.

In `--mode auto`, the optional pass is suppressed entirely and required-but-empty fields fail-fast instead of blocking the loop.

### Filtering by Source

Every job listing carries a `Source` value in the WBL dashboard (visible as the **Source** column — values like `Linkedin`, `Jobright`, `Hiring.Cafe`, `Trueup.Io`, `Indeed`, …). The filter is **unconditional and applied at discover time**: `jobcli discover` only ingests rows whose `Source` matches the allow-list — every other row is dropped before it touches the local SQLite database.

The default allow-list is the four CLI-friendly sources:

- `trueup.io`
- `hiring.cafe`
- `jobright`
- `linkedin`

```bash
# Pull only allow-listed listings into the local queue.
# No flag, no env var — the filter is always on.
jobcli discover

# Apply iterates whatever discover persisted; no source filter needed here.
jobcli apply
```

Notes:
- Comparison is **case- and punctuation-insensitive**: `LinkedIn`, `linkedin`, `LINKEDIN` and `Linked-In` all normalise to the same token.
- Rows with a missing/empty `source` value are rejected too, so legacy listings predating the column can't sneak through.
- To change the allow-list, edit the `DEFAULT_SOURCES` tuple in [`jobcli/core/source_filter.py`](jobcli/core/source_filter.py). There is intentionally **no** `--sources` flag or env var — the only change path is the source tuple.
- **Upgrading?** If you ran `jobcli discover` on a build that pre-dates this filter, your local DB may still contain rows from disallowed sources. Run `jobcli reset --force` then `jobcli discover` to start with a clean, filter-compliant queue.

---

## LinkedIn Jobs

LinkedIn does not allow bot automation. When the batch encounters a LinkedIn job:

1. The browser navigates to the LinkedIn job page
2. A **60-second countdown** is displayed in the terminal
3. You apply manually in the browser during that window
4. After 60 seconds, the engine automatically moves to the next job

---

## Commands Reference

### Setup & daily flow

| Command | Description |
|---|---|
| `jobcli login` | **Required first** — save Whitebox credentials, API base URL, and LLM keys to local config |
| `jobcli login --auto` | Skip prompts if credentials are already saved in local config |
| `jobcli resume-upload --pdf <file.pdf> --json <file.json>` | Load resume into local config |
| `jobcli setup` | One-shot validation: checks config, downloads extension, runs browser smoke test |
| `jobcli discover` | Pull job listings from WBL API (`/positions/cli_window`, fully paginated) |
| `jobcli apply` | Apply to all **pending** jobs (typical flow after `discover`) — Chrome opens visibly |
| `jobcli apply --url <url>` | Apply to a single specific job URL |
| `jobcli apply --mode auto / supervised / manual` | Set interaction level (see [Interaction Modes](#interaction-modes)) |
| `jobcli questions` | Pre-fill answers to common application questions |
| `jobcli open-dashboard` | Launch an interactive browser window logged into Wbox |
| `jobcli scan` | Scan configured ATS portals for open jobs |
| `jobcli sync` | Push learned patterns / activity to the server and pull global updates |

### Config inspection

| Command | Description |
|---|---|
| `jobcli config` | Show the full saved config table |
| `jobcli config --key <name>` | Show a single saved value |
| `jobcli config --key <name> --set <value>` | Update a single value (e.g. `sync_server_url`) |

### Cleanup commands (see [Cleanup, DB Reset, and Uninstall](#cleanup-db-reset-and-uninstall) for details)

| Command | Scope |
|---|---|
| `jobcli db clear-jobs [--force]` | Discovered jobs + per-job logs only |
| `jobcli db reset [--force]` (alias: `jobcli reset`) | Entire SQLite DB; keeps logs / extension / venv |
| `jobcli uninstall [--force]` | Everything under `~/.jobcli/` + global shims |

### Diagnostics & extras

| Command | Description |
|---|---|
| `jobcli doctor` | Validate Playwright, SQLite, config, and resume JSON |
| `jobcli server` | Start the FastAPI bridge server for Chrome Extension integration |

---

## Architecture

```
jobcli/
├── cli/              # Typer CLI commands
├── core/             # Core execution engine
│   ├── engine.py     # 4-phase application loop + LinkedIn 60s manual loop
│   ├── memory.py     # AgentMemory — confidence-gated 3-layer memory
│   ├── wbox_discoverer.py  # WBL API discovery (default); optional Playwright dashboard fallback
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
2. **Phase 2: Extension Autofill** — High-speed DOM-native filling of standard fields. The engine then waits 1.5 s for the extension to settle and snapshots every populated field.
3. **Phase 3: AI Reasoning (LLM)** — Accessibility Tree analysis for complex/custom fields and questionnaires. Any LLM action whose target is already in the snapshot is dropped before it reaches the executor (the **don't-refill guard**). A second live-value check at the executor layer guarantees no field is ever filled twice.
4. **Phase 4: Human-in-the-Loop** — Two-tier prompt: required fields first, optional fields second (press Enter to skip). See [Two-tier human prompt](#two-tier-human-prompt-supervised--manual).
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

All config lives in `~/.jobcli/` and is written by the interactive commands. **No `.env` file is used.** To wipe any of this, see [Cleanup, DB Reset, and Uninstall](#cleanup-db-reset-and-uninstall).

| Path | Purpose | Owned by |
|---|---|---|
| `~/.jobcli/jobcli.db` | SQLite — credentials, LLM keys, resume paths, API base URL, jobs, learned memory | `jobcli login`, `jobcli resume-upload`, `jobcli config`, `jobcli discover` |
| `~/.jobcli/extension_unpacked/` | TalentScreen Chrome extension (auto-loaded during `apply`) | `jobcli setup` |
| `~/.jobcli/logs/` | Per-job JSON logs, screenshots, DOM snapshots | `jobcli apply` |
| `~/.jobcli/venv/` | Managed Python venv (only present from the one-line installer) | `scripts/install.sh` / `scripts/install.ps1` |
| `~/.jobcli/src/` | Cloned repo (one-line installer only) | `scripts/install.sh` / `scripts/install.ps1` |
| `~/.local/bin/wboxcli` (+ `jobcli`) | Global command shims; `.cmd` on Windows | One-line installer |

### Saving / updating settings

Use the matching interactive command:

| Setting | Command |
|---|---|
| Whitebox username/password, API base URL, LLM keys, default LLM provider | `jobcli login` |
| Resume PDF + JSON | `jobcli resume-upload --pdf <pdf> --json <json>` |
| Anything else | `jobcli config --key <name> --set <value>` |

To inspect what is currently saved:

```bash
jobcli config                       # full table
jobcli config --key sync_server_url # single value
```

### Optional advanced overrides (shell environment only — no `.env`)

These knobs are read directly from the process environment if you want to tweak runtime behavior without touching saved config. They can be set in your shell session and are scoped to that session only.

| Env var | Effect |
|---|---|
| `DATABASE_PATH` | Override the SQLite DB location (useful for tests / isolation) |
| `JOBCLI_DISCOVER_DAYS` | Override discover time window (default `0` = all listings) |
| `JOBCLI_DISCOVER_PAGE_SIZE` | Override discover page size (default `10000`, max `10000`) |
| `JOBCLI_DISCOVER_STATUS` | Override discover status filter (default `open`; use `all` for everything) |
| `WBOX_DISCOVER_MODE=browser` | Force the legacy Playwright dashboard scrape instead of the API |
| `JOBCLI_SSL_CA_BUNDLE` | Path to a corporate root CA `.pem` if HTTPS verification fails (applies to **every** outbound call: WBL API, OpenAI, Anthropic, Gemini) |
| `JOBCLI_INSECURE_TLS=1` | Last-resort: disable HTTPS verification everywhere (insecure; prefer the trust-store fix below) |
| `JOBCLI_TLS_DEBUG=1` | Print which TLS strategy was selected at startup (truststore / ca-bundle / certifi / insecure) |

### Fixing `CERTIFICATE_VERIFY_FAILED` or `Connection error.` (TLS trust)

If you see `[SSL: CERTIFICATE_VERIFY_FAILED]` from `requests` **or** the
OpenAI SDK reporting `APIConnectionError: Connection error.` (which silently
wraps the same TLS failure), the cause is almost always a Windows machine
behind a corporate MITM proxy / AV that re-signs HTTPS with a private root
CA that Python's bundled `certifi` store doesn't know about.

JobCLI handles this transparently by injecting the **OS native trust store**
into Python's `ssl` module at startup (via the [`truststore`](https://pypi.org/project/truststore/)
package). On Python 3.10+ this Just Works for ~99% of users — no env var
required. If you still see TLS errors after upgrading, escalate in this order:

1. **Install the corporate root CA into your OS trust store** (Windows: Certificate Manager → *Trusted Root Certification Authorities*; macOS: Keychain Access → System → Always Trust). Restart your terminal.
2. **Point `JOBCLI_SSL_CA_BUNDLE`** at a PEM file containing the chain root:
   ```powershell
   $env:JOBCLI_SSL_CA_BUNDLE = "C:\path\to\corporate-ca.pem"
   ```
3. **Last resort — disable verification** (do not do this on shared/work machines):
   ```powershell
   # Windows (PowerShell, current session only)
   $env:JOBCLI_INSECURE_TLS = "1"
   ```
   ```bash
   # macOS / Linux
   export JOBCLI_INSECURE_TLS=1
   ```

When an LLM call hits a TLS error, JobCLI now **fails fast** (no 3-retry
delay) and hands you the browser with a remediation panel telling you
exactly which knob to flip — instead of the misleading "API quota exhausted"
message.

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

JobCLI ships with four test strata. Run them before any change that
touches browser automation or ATS handlers.

### 1. Full test suite

```bash
pytest
```

### 2. Don't-refill guard + required-first human prompt

Covers `BrowserAction.required`, the engine's `_snapshot_filled` / `_action_target_already_filled`, the executor's `_read_live_value` + skip-refill guard, `LLMClient._propagate_required_flag`, the two-tier `AgentInterface.show_failed_fields`, and the TUI next-step helpers — 58 tests across 7 groups.

```bash
pytest tests/test_refill_and_required.py -v
```

### 3. Stealth / anti-bot verification

```bash
pytest tests/test_stealth.py -v
```

### 4. Live fingerprint diagnostic

```bash
python scripts/stealth_check.py
python scripts/stealth_check.py --headless
python scripts/stealth_check.py --url 'https://bot.sannysoft.com/'
```

## License

MIT
