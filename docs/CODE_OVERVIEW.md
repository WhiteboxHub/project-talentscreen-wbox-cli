# JobCLI – Codebase Overview

A production-grade Python CLI that automates job applications across 20+ ATS
(Applicant Tracking System) platforms. It combines a **Typer-based CLI**, a
**Playwright-driven browser engine**, an **LLM reasoning layer**
(OpenAI / Anthropic / Gemini), and an **SQLite-backed memory** that learns
locators and field answers across runs.

---

## 1. High-Level Architecture

```
                      ┌────────────────────────┐
   user $ jobcli ---> │  jobcli/cli/main.py    │   Typer commands
                      │  (setup/login/apply..) │
                      └──────────┬─────────────┘
                                 │
                                 ▼
                      ┌────────────────────────┐
                      │  ApplicationEngine     │   unified agent loop
                      │  (jobcli/core/engine)  │
                      └────┬───────────┬───────┘
                           │           │
                ┌──────────┘           └────────────┐
                ▼                                   ▼
   ┌────────────────────────┐          ┌─────────────────────────┐
   │  Playwright + Stealth  │          │   LLM Client            │
   │  ToolExecutor          │          │   (AXTree-driven)       │
   │  ATS Handlers          │          │   OpenAI/Anthropic/Gem. │
   │  FormFiller / Locators │          └─────────────────────────┘
   └────────────────────────┘
                │
                ▼
   ┌────────────────────────┐          ┌─────────────────────────┐
   │  AgentInterface        │  <─────> │ AgentMemory (SQLite)    │
   │  (human in the loop)   │          │ field answers, locators │
   └────────────────────────┘          └─────────────────────────┘
```

Three-tier strategy used during application:
1. **Rule-based locators** (fast, deterministic).
2. **LLM autonomous reasoning** over the AXTree (high-accuracy fallback).
3. **Human-in-the-loop** (only when confidence is low or in `manual`/`supervised` mode).

---

## 2. Project Layout

```
wbox-cli/
├── jobcli/                  # Main package (~19.6k LOC)
│   ├── __main__.py          # `python -m jobcli` entry
│   ├── cli/                 # Typer commands
│   │   ├── main.py          # All user-facing subcommands
│   │   └── doctor.py        # Diagnostics command
│   ├── core/                # Execution engine + cross-cutting modules
│   ├── llm/                 # LLM client + AX/DOM extractors
│   ├── locators/            # Rule-based locators + per-ATS handlers
│   ├── human/               # Human-in-the-loop interfaces
│   └── storage/             # SQLAlchemy models + repositories
├── config/                  # Example portal & profile YAML
├── docs/                    # Architecture & data-contract docs
├── scripts/                 # Stealth diagnostic + helper scripts
├── tests/                   # Pytest suite (unit + stealth)
├── templates/               # Reserved for output templates
├── pyproject.toml           # Package + dependency manifest
├── requirements.txt         # Pinned runtime deps
├── pytest.ini               # Pytest config
└── README.md                # User-facing docs
```

---

## 3. CLI Layer (`jobcli/cli/`)

`main.py` exposes a `Typer` app with the following commands:

| Command           | Purpose                                                                |
|-------------------|------------------------------------------------------------------------|
| `setup`           | Create `~/.jobcli/`, init SQLite schema, seed default `Config`.        |
| `login`           | Prompt for Whitebox credentials and OpenAI/Anthropic/Gemini keys.      |
| `config`          | Print or set individual config keys (sensitive values masked).         |
| `resume-upload`   | Validate resume PDF + JSON, persist to `user_data` table.              |
| `questions`       | Pre-fill `CommonQuestions` (salary, notice, relocate, remote, etc.).   |
| `discover`        | Log into Wbox dashboard via Playwright and harvest job links.          |
| `open-dashboard`  | Open an interactive logged-in browser window.                          |
| `apply`           | Apply to one URL (`--url`) or all pending jobs (default, no flag needed). Has `--mode auto/supervised/manual`. |
| `scan`            | Zero-token API scan of Greenhouse/Lever/Ashby/BambooHR boards.         |
| `doctor`          | Validate Playwright, SQLite, config, resume; optional Wbox smoke test. |

`get_config()` reads only the local SQLite `config` table (no `.env` is loaded). Settings are populated by `login`, `resume-upload`, `setup`, or `config --key … --set …`.

---

## 4. Core Engine (`jobcli/core/`)

| Module                  | LOC   | Responsibility                                                                 |
|-------------------------|------:|--------------------------------------------------------------------------------|
| `engine.py`             | ~2.5k | Synchronous **unified agent loop**: detects ATS, dispatches handlers, integrates LLM + human checkpoints, manages retries, screenshots, and final status. |
| `engine_v2.py`          |       | Newer iteration of the engine (see `docs/ENGINE_V2_VS_LEGACY.md`).             |
| `async_engine.py`       |       | Asyncio variant of the engine for concurrent job processing.                   |
| `tool_executor.py`      | 1.7k  | Safe wrapper around Playwright actions (`click`, `fill`, `select`, `upload`, `wait`). Handles iframe reach-through (Greenhouse/Lever/Workday/etc.) and JS force-fill fallbacks. |
| `tool_executor_patch.py`|       | Monkey patches/extensions for the executor.                                    |
| `state_machine.py`      | 632   | Optional **LangGraph** state machine (3-phase: rules → LLM → human).            |
| `memory.py`             |       | `AgentMemory`: 3-layer persistent memory (Field, Interaction, Dropdown).        |
| `synonym_resolver.py`   | 715   | Maps free-text field labels to canonical resume paths (synonyms, normalisation).|
| `derived_profile.py`    |       | Derives values not in the resume (e.g. `country` from US city/state).           |
| `resume_normalize.py`   |       | Normalises LinkedIn URLs and other freeform inputs.                            |
| `url_normalize.py`      | 46    | Canonicalises job URLs for dedupe + storage.                                   |
| `wbox_discoverer.py`    | 151   | Whitebox Learning dashboard scraper (login → grid extraction).                 |
| `scanner.py`            |       | API-based **zero-token** ATS scanner (Greenhouse, Lever, Ashby, BambooHR).      |
| `anti_bot.py`           |       | Runtime detection / handling of anti-bot screens (Cloudflare, hCaptcha hints). |
| `stealth.py`            | 452   | Centralised launch flags + JS init-script for anti-fingerprinting.             |
| `secure_config.py`      |       | Encrypted-at-rest secrets via `cryptography` (Fernet).                         |
| `progress.py`           |       | Rich-based progress reporting helpers.                                         |
| `logger.py`             |       | Structured `JobLogger` (structlog, JSON, per-job log dir + screenshots).       |
| `schemas.py`            | 325   | All Pydantic models (`Job`, `ResumeData`, `Config`, `BrowserAction`, …).        |
| `locator_schemas.py`    |       | Pydantic model for `LearnedLocator` rows.                                      |

### `schemas.py` highlights

- **Enums**: `ATSType` (21 systems), `ApplicationStatus`, `ExecutionPhase`, `InteractionMode` (`auto`/`supervised`/`manual`), `SelectorType`, `ActionType`.
- **Resume model**: `ResumeData` → `PersonalInfo`, `Education`, `Experience`, `WorkAuthorization`, `Demographics`, plus `skills`/`certifications`.
- **Runtime models**: `BrowserAction`, `LLMActionResponse`, `ApplicationState`, `DOMSnapshot`.
- **`Config`**: credentials, API keys, browser preferences, paths, interaction mode.

---

## 5. LLM Layer (`jobcli/llm/`)

| Module               | Purpose                                                                                |
|----------------------|----------------------------------------------------------------------------------------|
| `client.py` (453)    | `LLMClient` — multi-provider (OpenAI gpt-4o, Anthropic claude-3.5-sonnet, Gemini 1.5-pro). Wraps prompt construction + JSON-schema enforced parsing into `LLMActionResponse`. Includes work-auth/legal guardrails baked into the system prompt. |
| `ax_tree_extractor.py` (535) | Pulls the **Accessibility Tree** from a Playwright `Page`. AXTree (vs raw DOM) yields more accurate field labels and dramatically improves LLM precision. |
| `dom_extractor.py` (193) | Backup raw-DOM extractor when AX info is missing.                                  |

The LLM produces structured `BrowserAction[]` (text/role selectors), enabling the engine to execute them through `ToolExecutor` with the same machinery used by rule-based locators.

---

## 6. Locators (`jobcli/locators/`)

Rule-based, deterministic counterparts to the LLM layer.

| Module                  | Purpose                                                                  |
|-------------------------|--------------------------------------------------------------------------|
| `apply_button.py` (505) | Heuristic locator for the *Apply* CTA + "adopt" logic when the click pops a new tab/window/iframe. |
| `ats_detector.py` (281) | Detects ATS from URL/host + DOM fingerprints.                            |
| `form_fields.py` (815)  | `FormFiller` + `FormFieldLocator` — confidence-scored search across HTML attributes, EEO/search skip lists, fuzzy dropdown fill. |
| `overlay_dismiss.py`    | Closes cookie banners, modals, and consent pop-ups.                      |
| `ats/` subpackage       | One handler per ATS (see below).                                         |

### ATS handlers (`jobcli/locators/ats/`)

`handler_factory.py` maps each `ATSType` to a dedicated handler that extends `BaseATSHandler`. Anything unknown falls back to `GenericATSHandler` (heuristic confidence engine).

Dedicated handlers ship for: **Greenhouse, Lever, Workday, iCIMS, Taleo, SAP SuccessFactors, SmartRecruiters, Jobvite, Ashby, Breezy HR, Recruitee, JazzHR, BambooHR, Workable, ADP Recruiting, Paylocity, UKG Pro, Cornerstone, Avature, Phenom People** (Workday is the largest at 768 LOC due to its multi-step flows).

---

## 7. Human-in-the-Loop (`jobcli/human/`)

| Module               | Purpose                                                                              |
|----------------------|--------------------------------------------------------------------------------------|
| `agent_interface.py` (868) | Primary integration: inline checkpoints during the agent loop, persisted via `AgentMemory` so the next run reuses answers. Honors `InteractionMode`. |
| `interface.py` (299) | Lower-level Rich-based TTY prompt helpers + handoff browser session helpers.         |

`HandoffResult` lets a human take manual control inside the running browser; the engine resumes from the human's current page rather than restarting the phase.

---

## 8. Storage (`jobcli/storage/`)

SQLite-backed via SQLAlchemy. Lightweight additive migrations live in `Database._migrate_sqlite_schema`.

### Tables (`models.py`)

| Model                     | Purpose                                                                  |
|---------------------------|--------------------------------------------------------------------------|
| `JobModel`                | Discovered/applied jobs (URL, ATS, status, score, evaluation report).    |
| `ApplicationLogModel`     | Per-step log entries (phase, action, success, screenshot, dom snapshot). |
| `LearnedLocatorModel`     | Selectors confirmed by humans/runs — confidence-weighted, ATS-scoped.    |
| `UserDataModel`           | Resume + common-question answers (JSON blob keyed by `data_type`).       |
| `ConfigModel`             | Persisted configuration (with `encrypted` flag).                         |
| `FieldAnswerModel`        | Memory of field-by-field answers (label + ATS).                          |
| `InteractionLogModel`     | Append-only log of every Playwright attempt + which strategy worked.     |
| `DropdownStrategyModel`   | Per-ATS dropdown interaction recipes that succeeded.                     |

### Repositories (`repositories.py`, 763 LOC)

Thin façades over SQLAlchemy: `JobRepository`, `ApplicationLogRepository`, `LearnedLocatorRepository`, `UserDataRepository`, `ConfigRepository`, `FieldAnswerRepository`, `InteractionLogRepository`, `DropdownStrategyRepository`.

`session.py` exposes a context-managed session helper.

---

## 9. Stealth & Anti-Bot Strategy

`jobcli/core/stealth.py` centralises:

- **Launch flags** that strip the obvious "automation" markers from Chromium.
- A **JS init-script** injected into every new document (main + iframes) **before** any page script. It hides `navigator.webdriver`, populates `plugins`/`languages`, spoofs WebGL vendor, patches `Function.prototype.toString` so spoofed getters still report `[native code]`, and patches `iframe.contentWindow` so child frames inherit the same defences.

`scripts/stealth_check.py` runs Chromium with the production flags + script and prints a pass/fail table for each fingerprint signal. `tests/test_stealth.py` enforces the same checks in CI (static + runtime strata).

---

## 10. Tests (`tests/`)

| File                          | Coverage                                                          |
|-------------------------------|-------------------------------------------------------------------|
| `test_async_engine.py`        | Async engine happy-path and concurrency.                          |
| `test_cli_guardrails.py`      | Typer command guardrails (config required, modes valid, etc.).    |
| `test_derived_profile.py`     | Derived values (e.g. country inference).                          |
| `test_llm_client.py`          | Multi-provider client wrapping + structured-output parsing.       |
| `test_repositories.py`        | SQLAlchemy repos: CRUD + dedupe + memory updates.                 |
| `test_secure_config.py`       | Fernet encryption round-trip for stored secrets.                  |
| `test_session_management.py`  | Session lifecycle for the storage layer.                          |
| `test_state_machine.py`       | LangGraph state machine transitions.                              |
| `test_stealth.py`             | Static + runtime stealth fingerprint assertions.                  |
| `test_url_normalize.py`       | URL canonicalisation for dedupe.                                  |

---

## 11. Configuration & Files

- `~/.jobcli/jobcli.db` — SQLite DB (credentials, LLM keys, resume paths, jobs, learned locators, memory, etc.). The single source of truth.
- `~/.jobcli/extension_unpacked/` — TalentScreen Chrome extension (downloaded by `jobcli setup`).
- `logs/<job-id>/…` — per-job log dir with screenshots and DOM snapshots.
- No `.env` file is read or written by the CLI. Optional runtime knobs (e.g. `DATABASE_PATH`, `JOBCLI_DISCOVER_*`, `JOBCLI_SSL_CA_BUNDLE`) are read directly from the shell environment.
- `config/portals.example.yml`, `config/profile.example.yml` — templates for `jobcli scan`.
- `example_resume.json`, `example_resume_standard.json` — reference resume schema fixtures.

---

## 12. Dependencies (`pyproject.toml`)

Runtime: `playwright`, `typer`, `pydantic`, `pydantic-settings`, `openai`,
`anthropic`, `google-generativeai`, `sqlalchemy`, `rich`, `python-dotenv`,
`requests`, `beautifulsoup4`, `lxml`, `python-dateutil`, `structlog`,
`langgraph`, `langchain-core`, `cryptography`.

Dev: `pytest`, `pytest-asyncio`, `pytest-playwright`, `black`, `ruff`, `mypy`.

Entry point: `jobcli = "jobcli.cli.main:app"` (defined in `[project.scripts]`).

---

## 13. End-to-End Flow (typical apply run)

1. **`jobcli discover`** — `WboxDiscoverer` logs into the Whitebox dashboard, scrapes new job rows, inserts into `jobs` table.
2. **`jobcli apply --mode supervised`** — for every pending job:
   1. Engine launches Chromium with **stealth** flags + init script.
   2. `ATSDetector` identifies the platform → `ATSHandlerFactory` returns a dedicated handler.
   3. Handler / `ApplyButtonLocator` clicks Apply (with iframe reach-through and "adopt" logic for new tabs).
   4. `FormFiller` fills known fields using rule-based locators backed by `AgentMemory` answers.
   5. Unknown / low-confidence fields → `LLMClient` parses the AXTree + resume and emits structured `BrowserAction[]`, executed by `ToolExecutor`.
   6. Anything still unresolved → `AgentInterface` prompts the user (mode-dependent), persists the answer for next time.
   7. Submission confirmation, screenshots, and final status are written via `ApplicationLogRepository`; `JobModel.status` is updated.
3. Subsequent runs reuse all answers / learned locators, so the same employer's next role typically requires zero manual input.

---

## 14. Where to Start Reading

- New to the project? → `README.md`, then `jobcli/cli/main.py`.
- Want to tweak the apply loop? → `jobcli/core/engine.py` + `jobcli/core/tool_executor.py`.
- Adding a new ATS? → copy a small handler (e.g. `paylocity_handler.py`), register it in `handler_factory.py`, add an `ATSType` enum value.
- Tuning the LLM? → `jobcli/llm/client.py` (`SYSTEM_PROMPT`) + `ax_tree_extractor.py`.
- Hardening stealth? → `jobcli/core/stealth.py` + `tests/test_stealth.py` + `scripts/stealth_check.py`.
- Memory / learning? → `jobcli/core/memory.py` + `jobcli/storage/repositories.py`.
