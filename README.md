# JobCLI

Production-grade CLI for automated job applications across multiple ATS systems.

## Features

- **Wbox Dashboard Integration**: Automated job discovery from Whitebox Learning
- **Interactive Dashboard**: Single-command login to your Wbox dashboard
- **Three-Phase Execution Strategy**: Rule-based locators → LLM reasoning → Human-in-the-loop
- **Multi-ATS Support**: Greenhouse, Lever, Workday, and 17 other ATS systems
- **Structured Logging**: JSON logs with screenshots and DOM snapshots
- **LLM Providers**: OpenAI, Anthropic, and Google Gemini support

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

## License

MIT
