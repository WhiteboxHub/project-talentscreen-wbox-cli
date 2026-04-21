# JobCLI

Production-grade CLI for automated job applications across multiple ATS systems.

## Features

- **Wbox Dashboard Integration**: Automated job discovery from Whitebox Learning
- **Advanced AI Reasoning**: Uses AXTree (Accessibility Tree) for high-accuracy form field mapping
- **Universal Iframe Search**: Reach-through support for Greenhouse, Lever, Paylocity, and nested iframes
- **JS Force-Fill Fallback**: Bypasses stubborn React/Angular listeners for 100% input reliability
- **Three-Phase Strategy**: Autonomous AI → Heuristic Rules → Human-in-the-loop fallback
- **Smart Logic**: Suppresses redundant manual prompts for information already in your resume
- **Structured Logging**: JSON logs with screenshots and DOM snapshots
- **Multi-Provider**: Native support for OpenAI, Anthropic, and Google Gemini

## Installation

Requires **Python 3.10+**.

```bash
# Recommend using a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows

pip install -e .
playwright install chromium
```

## Quick Start

```bash
# Initial setup
jobcli setup

# Configure credentials
jobcli login

# Upload resume
jobcli resume-upload --pdf resume.pdf --json resume.json

# Answer common questions
jobcli questions

# Open Wbox Dashboard
jobcli open-dashboard

# Gather latest jobs
jobcli discover

# Apply to all pending jobs
jobcli apply --batch

# Apply to a single URL
jobcli apply --url https://example.com/jobs/123
```

## Commands

### `jobcli setup`
Initialize configuration and database.

### `jobcli login`
Store credentials for job boards and LLM API keys.

### `jobcli config`
View or modify configuration.

### `jobcli resume-upload`
Upload resume in PDF and JSON formats.

### `jobcli questions`
Pre-fill answers to common application questions.

### `jobcli discover`
Automatically fetch job links from your Whitebox Learning dashboard.

### `jobcli open-dashboard`
Launch an interactive browser window logged into your Wbox dashboard.

### `jobcli apply`
Apply to jobs from URLs or in batch mode (--batch).

## Architecture

```
jobcli/
├── cli/           # Typer CLI commands
├── core/          # Core execution engine
├── locators/      # Rule-based locator system
│   └── ats/       # ATS-specific handlers
├── llm/           # LLM reasoning layer
├── human/         # Human-in-the-loop interface
├── storage/       # SQLite persistence
└── logs/          # Application logs
```

## Configuration

Config stored in `~/.jobcli/`:
- `config.json` - Main configuration
- `jobcli.db` - SQLite database
- `logs/` - Per-job logs and screenshots

## Resume JSON Format

```json
{
  "personal": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "linkedin": "https://linkedin.com/in/johndoe"
  },
  "experience": [...],
  "education": [...]
}
```

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
