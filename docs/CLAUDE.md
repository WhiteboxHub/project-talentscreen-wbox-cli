# CLAUDE.md

Behavioral guidelines for working on JobCLI — a production CLI that automates job applications across multiple ATS platforms.

## Project Context

- **What it does**: Automates job applications using Playwright + LLM reasoning (OpenAI/Anthropic/Gemini)
- **Core tech**: Python 3.10+, Playwright, SQLAlchemy, Typer, FastAPI
- **Architecture**: Agent-driven execution with human-in-the-loop checkpoints
- **Critical paths**: Browser automation, ATS detection, form filling, confidence-based memory

## Code Principles

### 1. Browser automation is fragile — defensive by default

- All Playwright operations must handle timeouts gracefully
- Never assume an element exists — check first or use `try/catch`
- Stealth/anti-bot measures are critical — don't break them
- Screenshots + structured logs on failure are non-negotiable

### 2. The LLM is a fallback, not the first tool

Execution order: Extension autofill → Rule-based locators → LLM reasoning → Human-in-the-loop

Don't reach for the LLM when a CSS selector will do.

### 3. Confidence-gated memory is load-bearing

Memory system rules (see `jobcli/core/memory.py` and `jobcli/sync/constants.py`):
- Only return learned answers when `confidence >= 0.6` AND `success_count >= 3`
- Human/user answers NEVER get overwritten by auto-learned data
- Personal fields (email, phone, SSN, etc.) are NEVER stored in reusable memory
- When merging server knowledge, only update if `server_confidence > local_confidence`

**Do not bypass these gates.** They prevent the agent from confidently using bad data.

### 4. Match existing patterns

- **Enums for state**: Use existing enums (`ATSType`, `ApplicationStatus`, `ExecutionPhase`, `InteractionMode`) — don't add strings
- **Pydantic schemas**: All data structures are in `jobcli/core/schemas.py` — extend there, not inline
- **Repository pattern**: Database access goes through `jobcli/storage/repositories.py` — no raw SQL in business logic
- **Structured logging**: Use `JobLogger` and `global_logger` with `.info()` / `.warning()` / `.error()` — not `print()`

### 5. ATS handlers are self-contained

Each ATS platform has its own handler in `jobcli/locators/ats/` (e.g., `greenhouse.py`, `lever.py`). When adding support for a new platform:
- Implement the handler interface (see `jobcli/locators/ats/base.py`)
- Register it in `jobcli/locators/ats/handler_factory.py`
- Update `ATSType` enum in `schemas.py`
- Add test URLs in `tests/`

Don't modify the core engine unless the change applies to ALL platforms.

### 6. Sync privacy rules are non-negotiable

Fields defined in `jobcli/sync/constants.py` as `PERSONAL_FIELDS` must NEVER be uploaded to the server. The extractor (`jobcli/sync/extractor.py`) filters them out. If you add a new personal field to the resume schema, add it to that list immediately.

### 7. Testing requirements

Before pushing changes that touch:
- **Browser automation**: Run `pytest tests/test_stealth.py -v`
- **ATS handlers**: Add a live test URL (non-login required) and verify with `jobcli apply --url <url> --mode manual`
- **Memory/sync logic**: Run full suite `pytest` — these tests catch confidence gate bypasses

## Anti-Patterns

- ❌ Bypassing confidence gates "just for this one field"
- ❌ Adding `time.sleep()` instead of proper `page.wait_for_selector()`
- ❌ Logging PII to stdout or structured logs
- ❌ Mixing business logic into CLI command handlers (keep in `core/` or `locators/`)
- ❌ Hardcoding selectors in the engine (put in ATS handlers or rule-based locators)
- ❌ Assuming headless mode works if headed mode does (test both)

## When Stuck

1. Check existing ATS handlers for similar patterns
2. Read the `README.md` — it documents the 5-phase strategy and memory rules
3. Run `jobcli doctor` to validate environment/config
4. Enable verbose logging: `export DEBUG=true` before running commands
5. Check `logs/` directory for per-job execution traces

## Success Criteria

Your change is production-ready when:
- ✅ Browser automation fails gracefully (no uncaught Playwright exceptions)
- ✅ Tests pass (`pytest`)
- ✅ No PII leaks (check logs + sync payload with `jobcli sync --dry-run` if it exists)
- ✅ Memory gates respected (no raw answers without confidence checks)
- ✅ Works in both headless and headed mode
- ✅ Error messages tell users what to do next (not just stack traces)
