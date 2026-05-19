# Project Avatar / JobCLI — Complete Project Documentation

> **Generated:** May 18, 2026  
> **Repository:** `project-avatar-wbox-cli`  
> **Package name:** `jobcli` v0.1.0  
> **License:** MIT

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What This Project Does](#2-what-this-project-does)
3. [Repository Layout](#3-repository-layout)
4. [Technology Stack](#4-technology-stack)
5. [Entry Points & Commands](#5-entry-points--commands)
6. [Architecture Overview](#6-architecture-overview)
7. [Application Flow (5 Phases)](#7-application-flow-5-phases)
8. [Module Reference](#8-module-reference)
9. [Database Schema](#9-database-schema)
10. [Configuration & Local Storage](#10-configuration--local-storage)
11. [External Integrations](#11-external-integrations)
12. [ATS Platform Support](#12-ats-platform-support)
13. [Learning, Memory & Sync](#13-learning-memory--sync)
14. [Chrome Extension (TalentScreen)](#14-chrome-extension-talentscreen)
15. [Web Dashboard UI](#15-web-dashboard-ui)
16. [Testing](#16-testing)
17. [Installation & Deployment](#17-installation--deployment)
18. [Environment Variables](#18-environment-variables)
19. [Security & Privacy](#19-security--privacy)
20. [Development Guide](#20-development-guide)

---

## 1. Executive Summary

**JobCLI** (marketed as **WboxCLI**) is a production-grade Python CLI that automates job applications across many Applicant Tracking System (ATS) platforms. It combines:

- **Playwright** browser automation (always visible during apply)
- **TalentScreen** Chrome extension for fast DOM autofill
- **LLM reasoning** (OpenAI, Anthropic, Gemini) via Accessibility Tree analysis
- **Rule-based ATS handlers** for 20+ platforms
- **Human-in-the-loop** terminal prompts for missing fields
- **Local SQLite learning** with optional crowd sync to Whitebox Learning (WBL)

The project lives under `wbox/` as `project-avatar-wbox-cli/` and is distributed via one-line install scripts from the WhiteboxHub GitHub org.

---

## 2. What This Project Does

| Capability | Description |
|---|---|
| **Job discovery** | Pulls listings from WBL API (`GET /positions/cli_window`), filters by source allow-list, stores in local SQLite |
| **Automated apply** | Opens Chrome with extension loaded, fills forms via extension → LLM → rules → human prompts |
| **Don't-refill guard** | Never overwrites fields the extension already populated |
| **LinkedIn handling** | 60-second manual window, then auto-skips |
| **Learning** | Field answers and UI locators gain confidence from success/failure; human answers are protected |
| **Crowd sync** | Anonymous high-confidence patterns pushed to WBL; aggregated knowledge pulled back |
| **Interactive TUI** | `wboxcli` with guided onboarding for non-technical users |
| **Dashboard UI** | Optional React + WebSocket control center on port 3000 |

**Primary users:** Job seekers using Whitebox Learning who want to batch-apply to curated job listings without manually filling every ATS form.

---

## 3. Repository Layout

```
project-avatar-wbox-cli/
├── src/jobcli/              # Main Python package (~91 files)
│   ├── cli/                 # Typer CLI + interactive TUI
│   ├── orchestration/       # Engine, discoverer, state machine, tool executor
│   ├── ats/                 # ATS detection, handlers, locators
│   ├── llm/                 # LLM client + AX tree extractor
│   ├── intelligence/        # Agent memory, synonym resolver, coder agent
│   ├── human/               # Human-in-the-loop interfaces
│   ├── storage/             # SQLAlchemy models + repositories
│   ├── sync/                # WBL API client, knowledge sync, merger
│   ├── profile/             # Pydantic schemas, resume normalization
│   ├── extension/           # TalentScreen path resolution helpers
│   ├── automation/          # Stealth + anti-bot utilities
│   ├── api/                 # FastAPI bridge for dashboard UI
│   └── utils/               # TLS, logging, URL normalize, secure config
├── ui/                      # React + Vite dashboard (port 3000)
├── tests/                   # pytest suite (~20 test modules)
├── scripts/                 # install.sh/ps1, uninstall, stealth_check
├── pyproject.toml           # Package metadata + dependencies
└── README.md                # User-facing guide (716 lines)
```

**Not in repo (local / installer):**
- TalentScreen extension — resolved at runtime (see §14); often `bin/project-talentscreen-autofill-extension/` or sibling repo
- Cloned JobCLI source (installer) → `~/.jobcli/src/`
- Python venv (installer) → `~/.jobcli/venv/`

---

## 4. Technology Stack

| Layer | Technologies |
|---|---|
| **Runtime** | Python ≥ 3.10 |
| **CLI** | Typer, Rich |
| **Browser** | Playwright (Chromium) |
| **ORM** | SQLAlchemy 2.x (SQLite) |
| **Validation** | Pydantic 2.x |
| **LLM** | openai, anthropic, google-genai |
| **Agent framework** | langgraph, langchain-core |
| **API server** | FastAPI, uvicorn, websockets |
| **UI** | React 19, Vite 8, Tailwind 4, xterm.js |
| **HTTP** | requests, truststore (OS CA injection) |
| **Crypto** | cryptography (secure config) |
| **Testing** | pytest, pytest-asyncio, pytest-playwright |
| **Lint/format** | black, ruff, mypy |

---

## 5. Entry Points & Commands

### Binaries (from `pyproject.toml`)

| Command | Entry | Behavior |
|---|---|---|
| `wboxcli` | `jobcli.cli.entry:main` | No args → interactive TUI; with args → forwards to Typer |
| `jobcli` | `jobcli.cli.main:app` | Direct Typer CLI |

### CLI Commands (`jobcli.cli.main`)

#### Setup & daily flow

| Command | Purpose |
|---|---|
| `jobcli login` | Save WBL credentials + LLM API keys to SQLite |
| `jobcli login --auto` | Skip prompts if credentials exist |
| `jobcli resume-upload --pdf <path> --json <path>` | Load resume files into DB |
| `jobcli setup` | Validate config, download extension, browser smoke test |
| `jobcli discover` | Pull WBL job listings (API, paginated) |
| `jobcli apply` | Apply to all pending jobs (visible Chrome) |
| `jobcli apply --url <url>` | Apply to single URL |
| `jobcli apply --mode auto\|supervised\|manual` | Interaction level |
| `jobcli questions` | Pre-fill common application questions |
| `jobcli open-dashboard` | Open WBL dashboard in browser |
| `jobcli scan` | Scan configured ATS portals |
| `jobcli sync` | Push/pull knowledge + activity to WBL |

#### Config & maintenance

| Command | Purpose |
|---|---|
| `jobcli config-cmd` | Show full config table |
| `jobcli config-cmd --key <name> --set <value>` | Update single value (e.g. `extension_path`) |
| `jobcli db clear-jobs [--force]` | Clear jobs + application logs only |
| `jobcli db reset [--force]` | Wipe entire SQLite DB |
| `jobcli reset` | Alias for `db reset` |
| `jobcli uninstall [--force]` | Remove `~/.jobcli/` + global shims |

#### Diagnostics

| Command | Purpose |
|---|---|
| `jobcli doctor` | Validate Playwright, SQLite, config, resume JSON |
| `jobcli server` | Start FastAPI bridge for dashboard UI |
| `jobcli agent` | Coder/intelligence agent subcommand |

### Interactive TUI commands (`wboxcli`)

`setup`, `apply`, `discover`, `jobs`, `status`, `doctor`, `login`, `resume`, `config`, `questions`, `scan`, `sync`, `server`, `dashboard`, `clear`, `help`, `exit`

---

## 6. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                                  │
│  wboxcli (TUI)  │  jobcli (Typer)  │  Dashboard UI (React :3000)       │
└────────┬────────────────┬───────────────────────┬──────────────────────┘
         │                │                       │ WebSocket
         ▼                ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  cli/main.py          cli/interactive.py         api/main.py (FastAPI)   │
└────────┬────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    orchestration/engine.py                               │
│  ApplicationEngine — unified agent loop + human checkpoints              │
│  ├── tool_executor.py    Playwright actions                             │
│  ├── state_machine.py    Application state transitions                  │
│  ├── human_interaction.py                                               │
│  └── wbox_discoverer.py  Job import from WBL                            │
└────────┬───────────────────┬──────────────────┬─────────────────────────┘
         │                   │                  │
         ▼                   ▼                  ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐
│ ats/handlers │  │ llm/client.py    │  │ intelligence/memory.py       │
│ ats/locators │  │ ax_tree_extractor│  │ synonym_resolver             │
│ ats/detector │  └──────────────────┘  └──────────────────────────────┘
└──────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  storage/ (SQLite)          sync/ (WBL API)         extension/helpers  │
│  models, repositories       client, extractor,      TalentScreen path  │
│                             sqlite_merger, manager                       │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Playwright Chromium + TalentScreen Extension + WBL API                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

1. **No `.env` files** — all config in `~/.jobcli/jobcli.db`
2. **Always visible browser** — `headless=False` forced during apply
3. **Source filter at discover** — only 4 sources ingested by default
4. **TLS at import** — `jobcli/__init__.py` configures OS trust store before any HTTP
5. **Don't-refill** — three-layer guard: engine snapshot → LLM filter → executor live-read

---

## 7. Application Flow (5 Phases)

| Phase | Name | What happens |
|---|---|---|
| **1** | Discovery | URL normalization, ATS detection, job stored in SQLite |
| **2** | Extension autofill | TalentScreen fills standard fields; 1.5s settle; snapshot populated fields |
| **3** | AI reasoning (LLM) | Accessibility Tree → field mapping; don't-refill guard drops targets already filled |
| **4** | Human-in-the-loop | Required fields first (must answer); optional second (Enter to skip) |
| **5** | Submission & verification | Final checks, outcome detection, status sync to WBL |

### Interaction modes

| Mode | Behavior |
|---|---|
| `supervised` (default) | AI drives; pauses for missing fields and submission |
| `auto` | Fully autonomous; only CAPTCHA/fatal errors stop |
| `manual` | Pauses before every action batch for approval |

---

## 8. Module Reference

### `jobcli/cli/`

| File | Role |
|---|---|
| `main.py` | Typer app (~1,470 lines); all `jobcli` subcommands |
| `entry.py` | `wboxcli` router: TUI vs Typer |
| `interactive.py` | Rich-based interactive shell with onboarding wizard |
| `doctor.py` | Health checks for dependencies and config |

### `jobcli/orchestration/`

| File | Role |
|---|---|
| `engine.py` | **Core** — `ApplicationEngine`, 4-phase loop, LinkedIn 60s, don't-refill |
| `async_engine.py` | Async variant of application engine |
| `tool_executor.py` | Executes Playwright actions from LLM/rules |
| `state_machine.py` | Application state transitions |
| `wbox_discoverer.py` | WBL API + legacy Playwright dashboard scrape |
| `source_filter.py` | `DEFAULT_SOURCES` allow-list + `normalize_source()` |
| `scanner.py` | ATS portal scanning |
| `human_interaction.py` | Human prompt orchestration |

### `jobcli/ats/`

| Path | Role |
|---|---|
| `detector/ats_detector.py` | Detect ATS type from URL/DOM |
| `handlers/handler_factory.py` | Maps 20 `ATSType` values → dedicated handlers |
| `handlers/*_handler.py` | Platform-specific logic (Greenhouse, Lever, …) |
| `handlers/generic_handler.py` | Fallback heuristic engine |
| `handlers/base_handler.py` | Abstract base for all handlers |
| `locators/form_fields.py` | Rule-based form filling |
| `locators/apply_button.py` | Apply button detection + page adoption |
| `locators/repeating_sections.py` | Dynamic sections (experience blocks) |
| `locators/overlay_dismiss.py` | Cookie banners, modals |

### `jobcli/llm/`

| File | Role |
|---|---|
| `client.py` | Multi-provider LLM (OpenAI, Anthropic, Gemini); action parsing |
| `ax_tree_extractor.py` | Playwright Accessibility Tree → structured field list |

### `jobcli/intelligence/`

| File | Role |
|---|---|
| `memory.py` | `AgentMemory` — 3-layer memory with confidence gates |
| `synonym_resolver.py` | Field label normalization ("Mobile" → "phone") |

### `jobcli/human/`

| File | Role |
|---|---|
| `agent_interface.py` | Mode-aware human checkpoints (auto/supervised/manual) |
| `interface.py` | Terminal prompts for failed fields (two-tier required/optional) |

### `jobcli/storage/`

| File | Role |
|---|---|
| `models.py` | SQLAlchemy ORM — 10 tables + `Database` manager |
| `repositories.py` | CRUD for jobs, config, field answers, locators, sync metadata |
| `session.py` | Session helpers |

### `jobcli/sync/`

| File | Role |
|---|---|
| `client.py` | WBL HTTP client — login, discover, activity logs, knowledge sync |
| `extractor.py` | Export high-confidence non-PII patterns for upload |
| `sqlite_merger.py` | Merge server knowledge into local DB (confidence-aware) |
| `manager.py` | Orchestrates full sync flow |
| `constants.py` | `CONFIDENCE_THRESHOLD`, `MIN_SUCCESS_COUNT`, `PERSONAL_FIELDS` |

### `jobcli/profile/`

| File | Role |
|---|---|
| `schemas.py` | Pydantic models: `Job`, `ResumeData`, `Config`, `ATSType`, enums |
| `derived_profile.py` | Computed profile fields from resume |
| `resume_normalize.py` | JSON Resume standard compatibility |
| `resume_export.py` | Export `ResumeData` → JSON Resume for TalentScreen v2 |

### `jobcli/extension/`

| File | Role |
|---|---|
| `helpers.py` | Resolve extension path, ATS URL detection, `chromium_extension_launch_args()`, verify in browser |
| `autofill_bridge.py` | Playwright bridge to `window.AutofillExtension` (v2 page-world bridge) |

### `jobcli/automation/`

| File | Role |
|---|---|
| `stealth.py` | Browser fingerprint hardening |
| `anti_bot.py` | `AntiBotManager` — delays, human-like behavior |

### `jobcli/api/`

| File | Role |
|---|---|
| `main.py` | FastAPI + WebSocket control center for dashboard UI |

### `jobcli/utils/`

| File | Role |
|---|---|
| `tls.py` | OS trust store injection, `JOBCLI_*` TLS env vars |
| `secure_config.py` | Encrypted config values in SQLite |
| `url_normalize.py` | Job URL canonicalization |
| `logger.py` | Structured JSON logging + screenshots |
| `constants.py` | Shared constants (domains, dashboard days) |

---

## 9. Database Schema

**Location:** `~/.jobcli/jobcli.db` (SQLite, no Alembic — additive migrations in `Database._migrate_sqlite_schema`)

| Table | Purpose |
|---|---|
| `jobs` | Discovered job listings (URL, title, company, ATS type, status, WBL metadata, `source`) |
| `application_logs` | Per-action logs with phase, screenshots, DOM snapshots |
| `learned_locators` | CSS/XPath selectors ranked by success rate per ATS |
| `user_data` | Resume JSON, common questions |
| `config` | Key-value settings (credentials encrypted) |
| `field_answers` | Learned form field answers with confidence + source |
| `interaction_log` | Playwright action attempt history |
| `dropdown_strategies` | Successful dropdown interaction strategies |
| `sync_metadata` | Last sync time, apps since sync, download count |

### Job status lifecycle (`ApplicationStatus`)

`pending` → `evaluating` → `in_progress` → `submitted` | `failed` | `skipped` | `requires_human` | `rejected` | `interview` | `offer`

---

## 10. Configuration & Local Storage

### Directory layout (`~/.jobcli/`)

| Path | Purpose |
|---|---|
| `jobcli.db` | SQLite — credentials, jobs, memory, config |
| `extension_path` (in DB) / resolved folder | TalentScreen v2 unpacked extension |
| `extension_unpacked/` | Legacy extension copy (fallback only) |
| `logs/` | Per-job JSON logs, screenshots, DOM snapshots |
| `venv/` | Managed Python venv (installer only) |
| `src/` | Cloned repo (installer only) |
| `history` | TUI readline history |

### Config keys (stored in `config` table)

Written by `jobcli login`, `resume-upload`, `setup`, `config`:

- WBL username/password
- `sync_server_url` (default: `https://api.whitebox-learning.com/api`)
- LLM API keys (OpenAI, Anthropic, Gemini)
- Default LLM provider
- Resume PDF/JSON paths
- Extension path

---

## 11. External Integrations

### Whitebox Learning API

| Endpoint | Usage |
|---|---|
| `POST /auth/login` | Authenticate with WBL credentials |
| `GET /positions/cli_window` | Paginated job listings for discover |
| `POST /api/sync_cli/knowledge_sync` | Upload anonymous learned patterns |
| `GET /api/sync_cli/knowledge_updates` | Download aggregated patterns |
| `POST /api/job_activity_logs/bulk` | Push application status to dashboard |

**Default API base:** `https://api.whitebox-learning.com/api`  
**Override:** `jobcli config-cmd --key sync_server_url --set <url>`

### LLM Providers

| Provider | Config key | Used for |
|---|---|---|
| OpenAI | `openai_api_key` | Form field reasoning, AX tree analysis |
| Anthropic | `anthropic_api_key` | Same |
| Google Gemini | `gemini_api_key` | Same |

### TalentScreen Extension

- Bundled in package (`src/jobcli/assets/talentscreen_extension/`); `jobcli setup` installs to `~/.jobcli/extension_unpacked/`. Override via `extension_path` / `JOBCLI_EXTENSION_PATH` or legacy `bin/` clone
- Loaded during `jobcli apply` via `--load-extension` (see `extension/helpers.py`)
- Phase 2 autofill: `extension/autofill_bridge.py` calls `window.AutofillExtension` (page-world bridge in extension v2.0.0+)

---

## 12. ATS Platform Support

### Dedicated handlers (20 platforms)

| ATSType | Handler |
|---|---|
| `greenhouse` | GreenhouseHandler |
| `lever` | LeverHandler |
| `workday` | WorkdayHandler |
| `icims` | IcimsHandler |
| `taleo` | TaleoHandler |
| `sap_successfactors` | SuccessFactorsHandler |
| `smartrecruiters` | SmartRecruitersHandler |
| `jobvite` | JobviteHandler |
| `ashby` | AshbyHandler |
| `breezy_hr` | BreezyHandler |
| `recruitee` | RecruiteeHandler |
| `jazz_hr` | JazzHRHandler |
| `bamboo_hr` | BambooHRHandler |
| `workable` | WorkableHandler |
| `adp_recruiting` | ADPHandler |
| `paylocity` | PaylocityHandler |
| `ukg_pro` | UKGHandler |
| `cornerstone` | CornerstoneHandler |
| `avature` | AvatureHandler |
| `phenom_people` | PhenomHandler |
| `unknown` | GenericATSHandler (heuristic fallback) |

### User-facing status (from README)

| Platform | Status |
|---|---|
| Greenhouse, Lever, Ashby, Rippling, iCIMS, BambooHR, Breezy, Jobvite, SmartRecruiters, Workable, Recruitee | Full support |
| Workday | Filtered out at discover (login required) |
| LinkedIn | 60-second manual loop |
| Generic/Unknown | Heuristic fallback |

### Discover source filter (default allow-list)

Only these WBL `Source` values are ingested:

- `trueup.io`
- `hiring.cafe`
- `jobright`
- `linkedin`

Edit `DEFAULT_SOURCES` in `orchestration/source_filter.py` to change.

---

## 13. Learning, Memory & Sync

### Confidence model

```
confidence = success_count / (success_count + failure_count)
```

Memory is used **instead of LLM** only when:
- `confidence >= 0.6` (`CONFIDENCE_THRESHOLD`)
- `success_count >= 3` (`MIN_SUCCESS_COUNT`)

### Answer priority chain

1. Resume JSON
2. Saved memory for this ATS (confidence-gated)
3. Universal saved memory (confidence-gated)
4. LLM fallback

### Merge protection

| Incoming | Existing | Updated? |
|---|---|---|
| `human` / `user` | anything | Yes |
| `auto` / `local` | `auto` / `local` | Yes |
| `auto` / `local` | `human` / `user` | **No** |

### Sync flow

```
Local SQLite
  → extractor.py (strip PII, filter weak data)
  → POST knowledge_sync + activity logs
  → GET knowledge_updates
  → sqlite_merger.py (only if server_confidence > local)
```

Run: `jobcli sync`

---

## 14. Chrome Extension (TalentScreen v2)

- **Bundled in package** — `src/jobcli/assets/talentscreen_extension/` (refresh: `python scripts/bundle_talentscreen_extension.py`)
- **`jobcli setup`** copies to `~/.jobcli/extension_unpacked/` and saves `extension_path`
- **Resolution order** (`extension/helpers.py`):
  1. `JOBCLI_EXTENSION_PATH` environment variable
  2. `config.extension_path` (SQLite)
  3. `~/.jobcli/extension_unpacked/` (installed copy)
  4. Auto-install bundled extension to `~/.jobcli/extension_unpacked/`
  5. `<project-root>/bin/project-talentscreen-autofill-extension/` (legacy installer clone)
  6. Sibling `../project-talentscreen-autofill-extension/` (local `wbox/` monorepo layout)
- **Chrome launch:** `chromium_extension_launch_args(ext_dir)` — shared by `engine.start_session()`, `jobcli setup`, and `verify_extension_in_browser()`
- **Page-world bridge:** extension `pageWorldBridge.js` exposes `window.AutofillExtension` with `__bridge: true` for Playwright; isolated `autofillAPI.js` handles RPC.
- **Autofill bridge** (`extension/autofill_bridge.py`): `injectProfile` → `configure` → `fill` → optional `exportReport()`. Profile from `profile/resume_export.py`.
- **Engine timing:** runs after the form is visible, then `EXTENSION_AUTOFILL_SETTLE_MS` (1500 ms), then `_snapshot_filled()` for don't-refill.
- **Dev shortcut:** `jobcli config-cmd --key extension_path --set <path-to-v2-extension>`
- **API reference:** extension repo `docs/api/CLI_API.md`
- **Bridge tests:** Python tests in `tests/test_extension_bridge.py`, `tests/test_resume_export.py`. Extension Jest tests live in `project-talentscreen-autofill-extension`.

---

## 15. Web Dashboard UI

**Location:** `ui/`  
**Stack:** React 19, Vite 8, Tailwind 4, xterm.js, lucide-react

### Start

```bash
jobcli server          # FastAPI bridge
cd ui && npm install && npm run dev   # http://localhost:3000
```

### Features

- WebSocket real-time streaming (`/ws`)
- Terminal emulation for agent output
- Stop/resume/cancel via WebSocket commands
- Dark Claude-style aesthetic

### API (`jobcli/api/main.py`)

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Health check |
| `WebSocket /ws` | Live events, terminal I/O, stop/resume |

---

## 16. Testing

### Python (pytest)

| Test file | Focus |
|---|---|
| `test_refill_and_required.py` | Don't-refill guard, required-first prompts (58 tests) |
| `test_stealth.py` | Anti-bot / fingerprint |
| `test_source_filter.py` | Source allow-list normalization |
| `test_memory_confidence.py` | Confidence gates |
| `test_repositories.py` | SQLite CRUD |
| `test_state_machine.py` | State transitions |
| `test_llm_client.py` | LLM action parsing |
| `test_async_engine.py` | Async engine |
| `test_extension_setup.py` | Extension path resolution (`JOBCLI_EXTENSION_PATH`, bundled fallback) |
| `test_extension_bridge.py` | TalentScreen v2 `injectProfile` / `configure` / `fill` bridge |
| `test_resume_export.py` | `ResumeData` → JSON Resume for extension |
| `test_cli_guardrails.py` | CLI safety checks |
| `test_auth_gate.py` | Authentication gates |
| + 10 more modules | URL normalize, secure config, extractor, coder agent, etc. |

```bash
pip install -e ".[dev]"
pytest
pytest tests/test_refill_and_required.py -v
python scripts/stealth_check.py
```

---

## 17. Installation & Deployment

### One-line install

**Windows:**
```powershell
irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/install.ps1 | iex
```

**macOS/Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/main/scripts/install.sh | bash
```

**Dev branch:** set `JOBCLI_BRANCH=dev`

### What installer does

1. Clone repo → `~/.jobcli/src`
2. Create venv → `~/.jobcli/venv`
3. `pip install` + `playwright install chromium`
4. Drop `wboxcli` / `jobcli` shims → `~/.local/bin/`
5. Add to PATH
6. Launch interactive TUI

### Manual dev install

```bash
python -m venv venv
pip install -e ".[dev]"
playwright install chromium
```

---

## 18. Environment Variables

| Variable | Effect |
|---|---|
| `DATABASE_PATH` | Override SQLite DB location |
| `JOBCLI_DISCOVER_DAYS` | Discover time window (default `0` = all) |
| `JOBCLI_DISCOVER_PAGE_SIZE` | Page size (default `10000`) |
| `JOBCLI_DISCOVER_STATUS` | Status filter (default `open`) |
| `WBOX_DISCOVER_MODE=browser` | Legacy Playwright scrape instead of API |
| `JOBCLI_SSL_CA_BUNDLE` | Corporate CA PEM path |
| `JOBCLI_INSECURE_TLS=1` | Disable HTTPS verification (insecure) |
| `JOBCLI_TLS_DEBUG=1` | Print TLS strategy at startup |
| `WBOX_LOGIN_URL` | Override WBL login URL |
| `WBOX_DASHBOARD_URL` | Override WBL dashboard URL |
| `JOBCLI_USERNAME` / `JOBCLI_PASSWORD` | Fallback credentials for discover |

**Note:** No `.env` file is read by the CLI. Env vars are optional runtime overrides only.

---

## 19. Security & Privacy

| Topic | Implementation |
|---|---|
| **Credentials** | Stored in SQLite; encrypted flag on `config` table |
| **No `.env`** | Reduces accidental secret commits |
| **PII in sync** | `PERSONAL_FIELDS` frozenset blocks export of email, phone, name, etc. |
| **TLS** | OS trust store via `truststore` at import time |
| **Human answer protection** | Auto-learned data cannot overwrite human answers |
| **Source filter** | Prevents ingesting unsupported job sources |

---

## 20. Development Guide

### Branch info

Current git branch in workspace: `mahi_test` (per `.git/HEAD`)

### Code style

- Black + Ruff, line length 100
- mypy with `disallow_untyped_defs = true`

### Adding a new ATS handler

1. Add enum value to `ATSType` in `profile/schemas.py`
2. Create `ats/handlers/<platform>_handler.py` extending `BaseATSHandler`
3. Register in `ATSHandlerFactory._HANDLERS`
4. Add detector rules in `ats/detector/ats_detector.py`
5. Add tests

### Changing discover sources

Edit `DEFAULT_SOURCES` in `orchestration/source_filter.py`, then:
```bash
jobcli db reset --force
jobcli discover
```

### Key files to read first

1. `cli/main.py` — command wiring
2. `orchestration/engine.py` — application loop
3. `profile/schemas.py` — data models
4. `storage/models.py` — database schema
5. `llm/client.py` — AI integration
6. `sync/client.py` — WBL API

---

## Quick Reference Card

```
# First-time setup
wboxcli                          # Interactive onboarding
jobcli login                     # Or: direct CLI
jobcli resume-upload --pdf ... --json ...
jobcli setup
jobcli discover
jobcli apply

# Maintenance
jobcli db clear-jobs --force     # Clear job queue only
jobcli db reset --force          # Full DB wipe
jobcli sync                      # Crowd knowledge sync
jobcli doctor                    # Health check

# Advanced
jobcli apply --mode auto
jobcli apply --url <url>
jobcli server                    # + ui npm run dev
```

---

*This document consolidates README.md, pyproject.toml, and source-code analysis. For user-facing install/troubleshooting, see [README.md](README.md).*
