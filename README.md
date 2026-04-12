# JobCLI

Production-grade CLI for automated job applications across multiple ATS systems.

## Features

- **Three-Phase Execution Strategy**: Rule-based locators → LLM reasoning → Human-in-the-loop
- **Multi-ATS Support**: Greenhouse, Lever, Workday, and 17 other ATS systems
- **Structured Logging**: JSON logs with screenshots and DOM snapshots
- **Extensible Architecture**: Modular design for easy extension
- **LLM Providers**: OpenAI, Anthropic, and Google Gemini support
- **Safe Execution**: Validated tool execution prevents direct LLM browser control

## Installation

```bash
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
jobcli resume upload --pdf resume.pdf --json resume.json

# Answer common questions
jobcli questions

# Apply to jobs
jobcli apply --url https://example.com/jobs/123
```

## Commands

### `jobcli setup`
Initialize configuration and database.

### `jobcli login`
Store credentials for job boards and LLM API keys.

### `jobcli config`
View or modify configuration.

### `jobcli resume upload`
Upload resume in PDF and JSON formats.

### `jobcli questions`
Pre-fill answers to common application questions.

### `jobcli apply`
Apply to jobs from URLs or a job board.

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
