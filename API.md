# JobCLI API Documentation

This document describes how to use JobCLI programmatically.

## Core Components

### 1. Application Engine

The main orchestrator for job applications.

```python
from jobcli.core.engine import ApplicationEngine
from jobcli.core.schemas import Config, Job, ResumeData
from jobcli.storage.models import Database

# Initialize
config = Config(
    headless=True,
    max_retries=3,
    openai_api_key="sk-...",
    resume_pdf_path="/path/to/resume.pdf",
)

# Load resume
with open("resume.json") as f:
    resume_data = json.load(f)
resume = ResumeData(**resume_data)

# Setup database
db = Database("sqlite:///jobcli.db")
db.create_tables()

# Create engine
engine = ApplicationEngine(config, resume, db)

# Apply to job
job = Job(url="https://example.com/jobs/123")
status = engine.apply_to_job(job)

print(f"Application status: {status}")
```

### 2. Storage Layer

#### Database Setup

```python
from jobcli.storage.models import Database

db = Database("sqlite:///jobcli.db")
db.create_tables()
session = db.get_session()
```

#### Job Repository

```python
from jobcli.storage.repositories import JobRepository
from jobcli.core.schemas import Job, ApplicationStatus

repo = JobRepository(session)

# Create job
job = Job(
    url="https://example.com/jobs/123",
    title="Software Engineer",
    company="Tech Corp",
)
job = repo.create(job)

# Get job
job = repo.get(job_id=1)

# Update status
repo.update_status(job_id=1, status=ApplicationStatus.SUBMITTED)

# List pending jobs
pending = repo.list_pending()
```

#### User Data Repository

```python
from jobcli.storage.repositories import UserDataRepository
from jobcli.core.schemas import ResumeData, CommonQuestions

repo = UserDataRepository(session)

# Save resume
resume = ResumeData(...)
repo.save_resume(resume)

# Get resume
resume = repo.get_resume()

# Save questions
questions = CommonQuestions(
    salary_expectations="$150k-$180k",
    notice_period="2 weeks",
)
repo.save_questions(questions)

# Get questions
questions = repo.get_questions()
```

### 3. Locators

#### Apply Button Locator

```python
from jobcli.locators.apply_button import ApplyButtonLocator
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com/jobs/123")

    locator = ApplyButtonLocator(page, logger=None)
    result = locator.find()

    if result.success:
        print(f"Found apply button: {result.selector}")
        locator.click_apply_button()

    browser.close()
```

#### Form Filler

```python
from jobcli.locators.form_fields import FormFiller
from jobcli.core.schemas import ResumeData

resume = ResumeData(...)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com/jobs/123/apply")

    filler = FormFiller(page, resume, logger=None)

    # Fill personal info
    results = filler.fill_personal_info()

    # Upload resume
    filler.upload_resume("/path/to/resume.pdf")

    # Fill all
    all_results = filler.fill_all("/path/to/resume.pdf")

    browser.close()
```

#### ATS Detection

```python
from jobcli.locators.ats_detector import ATSDetector

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.greenhouse.io/jobs/123")

    detector = ATSDetector(page, logger=None)
    ats_type = detector.detect(page.url)

    print(f"Detected ATS: {ats_type.value}")

    browser.close()
```

### 4. ATS Handlers

#### Using ATS Handlers

```python
from jobcli.locators.ats.handler_factory import ATSHandlerFactory
from jobcli.core.schemas import ATSType, ResumeData

resume = ResumeData(...)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://boards.greenhouse.io/company/jobs/123")

    handler = ATSHandlerFactory.create_handler(
        ATSType.GREENHOUSE,
        page,
        resume,
        logger=None,
    )

    if handler:
        # Find and click apply button
        handler.find_apply_button()

        # Fill form
        results = handler.fill_form("/path/to/resume.pdf")

        # Submit
        success = handler.submit_application()

    browser.close()
```

#### Creating Custom ATS Handler

```python
from jobcli.locators.ats.base_handler import BaseATSHandler
from jobcli.core.schemas import ApplicationState

class CustomATSHandler(BaseATSHandler):
    def find_apply_button(self) -> bool:
        selectors = ["#apply-btn", ".apply-button"]
        for selector in selectors:
            try:
                self.page.click(selector)
                return True
            except:
                continue
        return False

    def detect_form_fields(self) -> list[str]:
        fields = []
        if self.page.query_selector("input[name='email']"):
            fields.append("email")
        # ... detect more fields
        return fields

    def fill_form(self, resume_path=None) -> dict:
        results = {}
        # Fill form fields
        try:
            self.page.fill("input[name='email']", self.resume.personal.email)
            results["email"] = True
        except:
            results["email"] = False
        return results

    def submit_application(self) -> bool:
        try:
            self.page.click("button[type='submit']")
            return True
        except:
            return False

    def handle_multi_step(self, state: ApplicationState) -> bool:
        # Handle multi-step flow
        return False  # No more steps
```

### 5. LLM Integration

#### LLM Client

```python
from jobcli.llm.client import LLMClient
from jobcli.llm.dom_extractor import DOMExtractor
from jobcli.core.schemas import ResumeData

resume = ResumeData(...)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com/jobs/123/apply")

    # Extract DOM
    extractor = DOMExtractor(page)
    dom_snapshot = extractor.extract()

    # Analyze with LLM
    client = LLMClient("openai", "sk-...", logger=None)
    response = client.analyze_page(
        dom_snapshot,
        resume,
        task="find_apply_button",
    )

    if response and not response.requires_human:
        print(f"LLM suggested {len(response.actions)} actions")
        for action in response.actions:
            print(f"  - {action.action.value}: {action.selector}")

    browser.close()
```

#### Tool Executor

```python
from jobcli.core.tool_executor import ToolExecutor
from jobcli.core.schemas import BrowserAction, ActionType, SelectorType

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com/jobs/123/apply")

    executor = ToolExecutor(page, logger=None)

    # Execute single action
    action = BrowserAction(
        action=ActionType.TYPE,
        selector="input[name='email']",
        selector_type=SelectorType.CSS,
        value="john@example.com",
        confidence=0.95,
    )

    success = executor.execute_action(action)

    # Execute LLM response
    llm_response = ...  # From LLM client
    results = executor.execute_actions(llm_response)

    browser.close()
```

### 6. Human Interface

```python
from jobcli.human.interface import HumanInterface
from jobcli.storage.repositories import LearnedLocatorRepository
from jobcli.core.schemas import ATSType

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://example.com/jobs/123/apply")

    # Setup repository
    db = Database("sqlite:///jobcli.db")
    session = db.get_session()
    locator_repo = LearnedLocatorRepository(session)

    # Create interface
    human = HumanInterface(page, locator_repo, logger=None)

    # Request help
    success, selector, selector_type = human.request_help(
        task="find_apply_button",
        ats_type=ATSType.UNKNOWN,
    )

    if success and selector:
        page.click(selector)
        human.show_success("Button clicked!")

    # Confirm action
    if human.confirm_submission():
        # Submit application
        pass

    session.close()
    browser.close()
```

### 7. Logging

#### Job Logger

```python
from jobcli.core.logger import JobLogger
from jobcli.core.schemas import ExecutionPhase

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    # Create logger
    logger = JobLogger(
        job_id=123,
        log_directory="logs",
        enable_screenshots=True,
    )

    # Log messages
    logger.info("Starting application", phase=ExecutionPhase.RULES)
    logger.error("Failed to find button", phase=ExecutionPhase.RULES, error="timeout")

    # Capture screenshot
    page.goto("https://example.com")
    screenshot_path = logger.capture_screenshot(page, "initial", ExecutionPhase.RULES)

    # Save DOM snapshot
    dom_path = logger.save_dom_snapshot(page, "snapshot", ExecutionPhase.RULES)

    # Get summary
    summary = logger.get_log_summary()
    print(summary)

    browser.close()
```

#### Global Logger

```python
from jobcli.core.logger import global_logger

global_logger.info("Application started", version="0.1.0")
global_logger.error("Failed to connect", error="timeout")
```

### 8. Anti-Bot Measures

```python
from jobcli.core.anti_bot import AntiBotManager, RetryManager, ErrorHandler

# Anti-bot manager
anti_bot = AntiBotManager(logger=None)

# Random user agent
user_agent = anti_bot.get_random_user_agent()

# Random delays
anti_bot.random_delay(min_seconds=1.0, max_seconds=3.0)

# Human-like actions
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com")

    # Human-like typing
    anti_bot.human_like_typing(page, "input[name='email']", "john@example.com")

    # Human-like click
    anti_bot.human_like_click(page, "button#apply")

    # Detect CAPTCHA
    has_captcha = anti_bot.detect_captcha(page)

    browser.close()

# Retry manager
retry = RetryManager(max_retries=3, initial_delay=1.0)

for attempt in range(retry.max_retries):
    try:
        # Do something
        break
    except Exception as e:
        if retry.should_retry(attempt, e):
            delay = retry.get_delay(attempt)
            time.sleep(delay)
        else:
            raise

# Error handler
error_handler = ErrorHandler(logger=None)

try:
    # Do something
    pass
except Exception as e:
    category = error_handler.categorize_error(e)
    is_retryable = error_handler.is_retryable(e)
    info = error_handler.handle_error(e, "apply_button_click", page)
```

## Complete Example

Here's a complete example that puts it all together:

```python
import json
from pathlib import Path
from jobcli.core.engine import ApplicationEngine
from jobcli.core.schemas import Config, Job, ResumeData
from jobcli.storage.models import Database
from jobcli.storage.repositories import JobRepository, UserDataRepository

def main():
    # Setup configuration
    config = Config(
        headless=False,  # Show browser
        max_retries=3,
        openai_api_key="sk-...",
        resume_pdf_path="/path/to/resume.pdf",
        screenshot_on_error=True,
    )

    # Load resume
    with open("resume.json") as f:
        resume_data = json.load(f)
    resume = ResumeData(**resume_data)

    # Setup database
    db = Database("sqlite:///jobcli.db")
    db.create_tables()

    # Save resume to database
    session = db.get_session()
    user_repo = UserDataRepository(session)
    user_repo.save_resume(resume)

    # Create job
    job_repo = JobRepository(session)
    job = Job(
        url="https://boards.greenhouse.io/company/jobs/123",
        title="Senior Software Engineer",
        company="Tech Corp",
    )
    job = job_repo.create(job)

    session.close()

    # Apply
    engine = ApplicationEngine(config, resume, db)
    status = engine.apply_to_job(job)

    print(f"Application status: {status.value}")

    # Check logs
    log_dir = Path("logs") / f"job_{job.id}"
    print(f"Logs saved to: {log_dir}")

if __name__ == "__main__":
    main()
```

## Testing

### Unit Tests

```python
import pytest
from jobcli.core.schemas import ResumeData, PersonalInfo

def test_resume_validation():
    resume = ResumeData(
        personal=PersonalInfo(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="+1-555-0123",
        ),
        experience=[],
        education=[],
    )

    assert resume.personal.first_name == "John"
    assert resume.personal.email == "john@example.com"
```

### Integration Tests

```python
import pytest
from playwright.sync_api import sync_playwright
from jobcli.locators.apply_button import ApplyButtonLocator

def test_apply_button_locator():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Navigate to test page
        page.goto("https://test-site.com/job")

        locator = ApplyButtonLocator(page)
        result = locator.find()

        assert result.success
        assert result.selector is not None

        browser.close()
```

## Best Practices

1. **Always use Pydantic schemas** for data validation
2. **Use repositories** for database access, never raw SQLAlchemy
3. **Log extensively** using JobLogger for debugging
4. **Handle exceptions** gracefully and log errors
5. **Use retry logic** for network operations
6. **Validate LLM responses** before execution
7. **Save learned locators** from human interaction
8. **Capture screenshots** at key steps
9. **Use type hints** throughout your code
10. **Test with real browsers** before production use

## Extension Points

### Custom Locators

Create custom locators by extending base classes:

```python
from jobcli.locators.form_fields import FormFieldLocator

class CustomFormLocator(FormFieldLocator):
    def find_custom_field(self, label: str) -> Optional[str]:
        # Custom logic
        pass
```

### Custom LLM Providers

Add new LLM providers to the client:

```python
# In jobcli/llm/client.py

def _call_custom_llm(self, user_prompt: str) -> str:
    # Implement custom LLM API call
    pass
```

### Custom ATS Handlers

See "Creating Custom ATS Handler" above.

### Custom Hooks

Add hooks for custom behavior:

```python
class MyEngine(ApplicationEngine):
    def _before_apply(self, job: Job) -> None:
        # Custom logic before applying
        pass

    def _after_apply(self, job: Job, status: ApplicationStatus) -> None:
        # Custom logic after applying
        pass
```

## Error Handling

All major operations return status codes or raise typed exceptions:

```python
from jobcli.core.schemas import ApplicationStatus

status = engine.apply_to_job(job)

if status == ApplicationStatus.SUBMITTED:
    print("Success!")
elif status == ApplicationStatus.FAILED:
    print("Failed - check logs")
elif status == ApplicationStatus.REQUIRES_HUMAN:
    print("Needs human intervention")
```

## Performance Tips

1. **Use headless mode** for production: `config.headless = True`
2. **Batch processing**: Apply to multiple jobs in sequence
3. **Parallel execution**: Use multiprocessing for multiple jobs
4. **Cache DOM snapshots**: Reuse for multiple LLM queries
5. **Limit screenshots**: Only on errors to save space
6. **Database connection pooling**: For high-volume applications
7. **Retry with backoff**: Implement exponential backoff for rate limits

## Security

- API keys stored in local database (consider encryption)
- Never log sensitive data (passwords, SSN, etc.)
- Resume data stays local except during application
- LLM providers only receive sanitized DOM data
- Use HTTPS for all external connections
- Validate all user inputs with Pydantic

## License

MIT
