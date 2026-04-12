# JobCLI Usage Guide

## Installation

```bash
# Install dependencies
pip install -e .

# Install Playwright browsers
playwright install chromium
```

## Quick Start

### 1. Setup

Initialize the application:

```bash
jobcli setup
```

This creates:
- Database at `~/.jobcli/jobcli.db`
- Configuration directory at `~/.jobcli/`
- Log directory at `logs/`

### 2. Add Credentials

Configure your credentials:

```bash
jobcli login
```

You'll be prompted for:
- **Job board credentials** (whitebox-learning.com)
- **LLM API keys** (OpenAI, Anthropic, or Gemini - at least one recommended)

### 3. Upload Resume

Prepare your resume in two formats:

1. **PDF** - Your formatted resume
2. **JSON** - Structured data for form filling

See `example_resume.json` for the required JSON schema.

```bash
jobcli resume upload --pdf resume.pdf --json resume.json
```

### 4. Pre-fill Common Questions

Answer common application questions once:

```bash
jobcli questions
```

This stores your answers for:
- Salary expectations
- Notice period
- Relocation willingness
- Remote work preference
- Available start date
- Referrals

### 5. Apply to Jobs

Apply to a single job:

```bash
jobcli apply --url "https://example.com/jobs/123"
```

Apply to multiple jobs in batch:

```bash
jobcli apply --batch
```

## Resume JSON Schema

Your `resume.json` must follow this structure:

```json
{
  "personal": {
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "phone": "string",
    "address": "string (optional)",
    "city": "string (optional)",
    "state": "string (optional)",
    "country": "string (optional)",
    "zip_code": "string (optional)",
    "linkedin": "string (optional)",
    "github": "string (optional)",
    "portfolio": "string (optional)",
    "website": "string (optional)"
  },
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM or null",
      "current": boolean,
      "description": "string (optional)"
    }
  ],
  "education": [
    {
      "school": "string",
      "degree": "string",
      "field_of_study": "string",
      "graduation_year": integer,
      "gpa": float (optional)
    }
  ],
  "work_authorization": {
    "authorized_to_work": boolean,
    "require_sponsorship": boolean,
    "visa_status": "string (optional)"
  },
  "demographics": {
    "gender": "string (optional)",
    "race": "string (optional)",
    "veteran_status": "string (optional)",
    "disability_status": "string (optional)"
  },
  "skills": ["string"],
  "certifications": ["string"]
}
```

## Configuration

View all configuration:

```bash
jobcli config
```

View specific setting:

```bash
jobcli config --key headless
```

Set a configuration value:

```bash
jobcli config --key headless --set true
```

Available configuration options:

- `headless` - Run browser in headless mode (default: true)
- `max_retries` - Maximum retry attempts (default: 3)
- `screenshot_on_error` - Capture screenshots on errors (default: true)
- `screenshot_on_success` - Capture screenshots on success (default: false)
- `random_delay_min` - Minimum delay between actions in seconds (default: 1.0)
- `random_delay_max` - Maximum delay between actions in seconds (default: 3.0)
- `default_llm_provider` - LLM provider to use (openai, anthropic, or gemini)

## How It Works

### Three-Phase Execution Strategy

JobCLI uses a three-phase approach to maximize success:

#### Phase 1: Rule-Based Locators
- **Fastest and most reliable**
- 40+ pre-defined locator strategies
- ATS-specific handlers for Greenhouse, Lever, Workday
- Detects and uses appropriate selectors automatically

#### Phase 2: LLM Reasoning
- **Activated when rules fail**
- Extracts structured DOM snapshot
- Sends to LLM (OpenAI, Anthropic, or Gemini)
- Receives validated, structured JSON actions
- Safe execution layer prevents direct LLM browser control

#### Phase 3: Human-in-the-Loop
- **Fallback when automation fails**
- Interactive CLI shows detected elements
- Manual selector input
- Saves learned locators for future use
- Maintains human oversight

### Supported ATS Systems

JobCLI can detect and handle 20+ ATS systems:

**Fully Implemented:**
- Greenhouse
- Lever
- Workday

**Detected (generic handling):**
- iCIMS
- Taleo Oracle
- SAP SuccessFactors
- SmartRecruiters
- Jobvite
- Ashby
- Breezy HR
- Recruitee
- JazzHR
- BambooHR
- Workable
- ADP Recruiting
- Paylocity
- UKG Pro
- Cornerstone
- Avature
- Phenom People

### Anti-Bot Measures

- Random delays between actions
- Real browser mode (no detection)
- User agent rotation
- Human-like typing patterns
- CAPTCHA detection
- Retry logic with exponential backoff

### Observability

Every job application creates:

```
logs/
└── job_123/
    ├── application.jsonl      # Structured JSON logs
    ├── screenshots/           # Screenshots at each step
    │   ├── 001_initial.png
    │   ├── 002_after_apply_click.png
    │   └── 003_form_filled.png
    └── dom_snapshots/         # HTML snapshots
        ├── 001_snapshot.html
        └── 002_structured.json
```

## Advanced Usage

### Batch Processing

Create a list of jobs in the database:

```python
from jobcli.storage.models import Database
from jobcli.storage.repositories import JobRepository
from jobcli.core.schemas import Job

db = Database("sqlite:///~/.jobcli/jobcli.db")
session = db.get_session()
repo = JobRepository(session)

# Add jobs
urls = [
    "https://company1.com/jobs/123",
    "https://company2.com/jobs/456",
    "https://company3.com/jobs/789",
]

for url in urls:
    job = Job(url=url)
    repo.create(job)

session.close()
```

Then run batch apply:

```bash
jobcli apply --batch
```

### Custom LLM Prompts

The LLM prompts are in `jobcli/llm/client.py`. You can modify:

- `SYSTEM_PROMPT` - System instructions for the LLM
- Temperature settings
- Model versions

### Extending ATS Support

To add support for a new ATS:

1. Create handler in `jobcli/locators/ats/your_ats_handler.py`
2. Extend `BaseATSHandler`
3. Implement required methods
4. Register in `handler_factory.py`

Example:

```python
from jobcli.locators.ats.base_handler import BaseATSHandler

class MyATSHandler(BaseATSHandler):
    def find_apply_button(self) -> bool:
        # Your implementation
        pass

    def fill_form(self, resume_path=None) -> dict:
        # Your implementation
        pass

    # ... other methods
```

### Database Schema

Tables:
- `jobs` - Job listings and status
- `application_logs` - Detailed execution logs
- `learned_locators` - Human-taught selectors
- `user_data` - Resume and preferences
- `config` - Configuration key-value pairs

Query examples:

```python
from jobcli.storage.models import Database
from sqlalchemy import select

db = Database("sqlite:///~/.jobcli/jobcli.db")
session = db.get_session()

# Get all submitted applications
from jobcli.storage.models import JobModel
from jobcli.core.schemas import ApplicationStatus

jobs = session.query(JobModel).filter(
    JobModel.status == ApplicationStatus.SUBMITTED
).all()

for job in jobs:
    print(f"{job.company}: {job.title}")

session.close()
```

## Troubleshooting

### Browser not found

```bash
playwright install chromium
```

### LLM not working

Check API keys:

```bash
jobcli config --key openai_api_key
jobcli config --key anthropic_api_key
jobcli config --key gemini_api_key
```

### Application stuck

- Check logs in `logs/job_<id>/application.jsonl`
- View screenshots in `logs/job_<id>/screenshots/`
- Run with `headless=false` to see browser:

```bash
jobcli config --key headless --set false
```

### CAPTCHA detected

- JobCLI will detect CAPTCHAs and escalate to human
- Complete CAPTCHA manually when prompted
- Application will continue automatically

### Elements not found

- Human-in-the-loop will activate
- Select correct element from displayed list
- Or provide custom selector
- Save for future reuse

## Best Practices

1. **Test with one job first** before batch processing
2. **Run in non-headless mode** initially to observe behavior
3. **Keep resume.json updated** with accurate information
4. **Review logs regularly** to identify patterns
5. **Save learned locators** to improve future success
6. **Respect rate limits** - don't apply to too many jobs too quickly
7. **Use LLM fallback** for complex or unknown ATS systems

## Privacy & Security

- All data stored locally in `~/.jobcli/`
- No data sent to third parties except:
  - Job board sites (for applications)
  - LLM providers (only DOM structure, not personal data)
- API keys stored in local database
- Resume data never leaves your machine except during application

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review `application.jsonl` for detailed execution trace
- Examine screenshots to see what happened
- Enable debug mode: set log level to DEBUG in code

## License

MIT
