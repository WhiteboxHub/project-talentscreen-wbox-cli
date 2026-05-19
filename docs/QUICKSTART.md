# JobCLI Quick Start

Get started with JobCLI in 5 minutes.

## Installation

```bash
cd project-avatar-wbox-cli
pip install -e .
```

## Basic Usage

### 1. Simple Application

```python
from jobcli.observability import create_trace_context, set_trace_context, get_logger
from jobcli.execution import ExecutionEngine, FillInputAction
from playwright.sync_api import sync_playwright

# Setup logging
logger = get_logger("my_application")

# Create trace context
context = create_trace_context(
    session_id="session_test",
    company_name="Google",
    position_title="Software Engineer"
)
set_trace_context(context)

# Launch browser
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://jobs.example.com/apply")
    
    # Create execution engine
    engine = ExecutionEngine(page=page, logger=logger)
    
    # Fill form fields
    action = FillInputAction(
        selector="#email",
        field_id="email",
        field_type="email",
        field_label="Email",
        value="user@example.com"
    )
    
    result = engine.execute(action)
    
    if result.success:
        logger.info("Application submitted!")
    
    browser.close()
```

### 2. With Self-Healing

```python
from jobcli.healing import SelfHealingEngine, SelectorHealer

# Create healing engine
healer = SelectorHealer()
healing_engine = SelfHealingEngine(
    page=page,
    execution_engine=engine,
    selector_healer=healer,
    enable_healing=True
)

# If selector fails, automatically tries 5 healing strategies
result = healing_engine.execute(action)
```

### 3. With Application Memory

```python
from jobcli.memory import ApplicationMemory

# Create memory
memory = ApplicationMemory()

# Create application
app = memory.create_application(
    company_name="Google",
    position_title="Software Engineer",
    ats_type="greenhouse"
)

# Record answer
memory.add_answer(
    application_id=app.application_id,
    question="Why do you want to work here?",
    answer="I'm passionate about...",
    confidence=0.9
)

# Get learned answers
answers = memory.get_similar_answers("Why Google?")
```

## Next Steps

1. **Read Core Docs**:
   - [Execution Layer](EXECUTION_LAYER.md) - Action execution
   - [Observability](OBSERVABILITY.md) - Tracing and logging
   - [Self-Healing](SELF_HEALING.md) - Automatic recovery

2. **Run Examples**:
   ```bash
   python examples/execution_layer_demo.py
   python examples/debug_system_demo.py
   ```

3. **Run Tests**:
   ```bash
   pytest tests/ -v
   ```

4. **Check Full Documentation**:
   - [docs/README.md](README.md) - Complete documentation index

## Common Patterns

### Pattern 1: Complete Application Flow

```python
# 1. Setup
context = create_trace_context(...)
set_trace_context(context)

memory = ApplicationMemory()
app = memory.create_application(...)

# 2. Fill fields
for field in fields:
    action = FillInputAction(...)
    result = healing_engine.execute(action)
    
    if result.success:
        memory.add_answer(app.application_id, ...)

# 3. Submit
submit_action = ClickAction(...)
result = healing_engine.execute(submit_action)

# 4. Update memory
memory.update_application(app.application_id, status="submitted")
```

### Pattern 2: Debug Failed Application

```python
from jobcli.debug import ActionReplayer, TraceAnalyzer

# Replay with inspection
replayer = ActionReplayer(page, snapshot_manager)
session = replayer.replay_sequence(
    actions=failed_actions,
    mode=ReplayMode.INSPECT
)

# Analyze failure
analyzer = TraceAnalyzer(log_file)
stats = analyzer.get_session_statistics(session_id)

# Export report
analyzer.export_session_report(session_id, Path("report.txt"))
```

### Pattern 3: Optimize with Memory

```python
from jobcli.memory import OptimizationIntelligence

intelligence = OptimizationIntelligence(memory)

# Score opportunity
score = intelligence.score_opportunity("Amazon", "Senior Engineer")
print(f"Opportunity score: {score.score}/100")

# Get recommendations
recommendations = intelligence.get_recommendations()
for rec in recommendations:
    print(f"{rec.priority}: {rec.title}")
```

## Configuration

Create `.env` file:

```bash
# Logging
LOG_LEVEL=info
LOG_DIR=logs/

# Self-Healing
HEALING_ENABLED=true
HEALING_CONFIDENCE_THRESHOLD=0.6

# Memory
MEMORY_PATH=application_memory.json
MEMORY_CONFIDENCE_THRESHOLD=0.6

# Debug
DEBUG_SNAPSHOTS=true
SNAPSHOT_PATH=snapshots/
```

## Troubleshooting

**Selector not found?**
- Enable self-healing
- Check debug snapshots
- Use field overlay debugger

**Low confidence?**
- Review AI reasoning inspection
- Check memory for similar patterns
- Enable step-by-step replay

**Memory not recalling?**
- Check confidence threshold
- Verify minimum success count
- Review application history

## Support

- Documentation: [docs/README.md](README.md)
- Tests: Run `pytest tests/ -v`
- Examples: Check `examples/` directory
