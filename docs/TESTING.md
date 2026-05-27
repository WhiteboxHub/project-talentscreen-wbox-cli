# Testing Strategy

Comprehensive test coverage for JobCLI across four testing layers: unit, integration, regression, and chaos.

## Test Organization

```
tests/
├── test_observability.py              # Unit: Trace context, logging, analysis
├── test_execution_engine.py           # Unit: Action execution, validation
├── test_semantic_engine.py            # Unit: Semantic classification
├── test_memory_system.py              # Unit: Application memory
├── test_security_validation.py        # Unit: Input validation, PII detection
├── test_integration_ats_flows.py      # Integration: End-to-end ATS flows
├── test_chaos_self_healing.py         # Chaos: Random failures, recovery
└── test_regression_dom_snapshots.py   # Regression: Snapshot stability
```

## Testing Layers

### 1. Unit Tests

Test individual components in isolation.

**Coverage:**
- ✅ Observability: Trace context creation, propagation, logging, analysis
- ✅ Execution: Action execution, validation, retry logic
- ✅ Semantic: Field classification, confidence scoring
- ✅ Memory: Application records, company history, intelligence
- ✅ Security: Input validation, PII detection, sanitization

**Running unit tests:**
```bash
# All unit tests
pytest tests/test_*.py -v -k "not integration and not chaos"

# Specific component
pytest tests/test_observability.py -v
pytest tests/test_execution_engine.py -v
pytest tests/test_memory_system.py -v
```

**Example: Observability unit test**
```python
def test_trace_context_propagation():
    """Test context propagates through execution."""
    context = create_trace_context(
        session_id="test_session",
        company_name="Google",
        position_title="SWE",
    )
    
    set_trace_context(context)
    
    # Context available
    retrieved = get_trace_context()
    assert retrieved.session_id == "test_session"
    
    clear_trace_context()
```

### 2. Integration Tests

Test complete flows across multiple components.

**Coverage:**
- ✅ ATS Flows: Complete application workflows (Greenhouse, Lever, Workday)
- ✅ Extension Communication: Browser extension interaction
- ✅ Replay Systems: Action replay, timeline, debugging
- ✅ Memory Integration: Application tracking with execution
- ✅ Healing Integration: Self-healing with execution engine

**Running integration tests:**
```bash
# All integration tests
pytest tests/test_integration_*.py -v

# Specific ATS
pytest tests/test_integration_ats_flows.py::TestGreenhouseFlow -v
```

**Example: Greenhouse complete flow**
```python
def test_greenhouse_complete_application():
    """Test complete Greenhouse application."""
    # Create execution context
    context = create_trace_context(...)
    set_trace_context(context)
    
    # Create engines
    engine = ExecutionEngine(page, logger)
    memory = ApplicationMemory()
    
    # Fill all fields
    for field in fields:
        action = FillInputAction(...)
        result = engine.execute(action)
        
        # Record in memory
        memory.add_answer(...)
    
    # Upload resume
    upload_action = UploadFileAction(...)
    engine.execute(upload_action)
    
    # Submit
    submit_action = ClickAction(...)
    result = engine.execute(submit_action)
    
    assert result.success
    assert memory.get_application(...) is not None
```

### 3. Regression Tests

Validate stability of core data structures and behaviors.

**Coverage:**
- ✅ DOM Snapshots: Structure, serialization, comparison
- ✅ Selector Stability: Selector patterns remain valid
- ✅ Field Mappings: Field type classification consistency
- ✅ Timeline Events: Event types and ordering
- ✅ Failure Diagnosis: Root cause detection
- ✅ AI Reasoning: Confidence calibration

**Running regression tests:**
```bash
# All regression tests
pytest tests/test_regression_*.py -v

# Specific area
pytest tests/test_regression_dom_snapshots.py -v
```

**Example: DOM snapshot stability**
```python
def test_snapshot_structure_stability():
    """Test snapshot structure hasn't changed."""
    snapshot = DOMSnapshot(...)
    
    # Serialize
    json_data = snapshot.model_dump()
    
    # Expected fields present
    assert "snapshot_id" in json_data
    assert "timestamp" in json_data
    assert "html" in json_data
    assert "elements" in json_data
    
    # Element structure
    element = json_data["elements"]["email"]
    assert "selector" in element
    assert "visible" in element
    assert "attributes" in element
```

### 4. Chaos Tests

Test recovery mechanisms under random failures.

**Coverage:**
- ✅ Selector Mutations: Random selector changes
- ✅ Timing Delays: Race conditions, delays
- ✅ Rendering Issues: Dynamic content, hydration
- ✅ DOM Mutations: Structure changes, element detachment
- ✅ Cascading Failures: Multiple failure modes combined

**Running chaos tests:**
```bash
# All chaos tests
pytest tests/test_chaos_*.py -v -s

# Specific chaos scenario
pytest tests/test_chaos_self_healing.py::TestChaosSelectors -v
```

**Example: Random selector mutations**
```python
def test_random_selector_mutations():
    """Test healing with randomly mutated selectors."""
    healer = SelectorHealer(...)
    chaos = ChaosInjector(...)
    
    success_count = 0
    total_attempts = 100
    
    for _ in range(total_attempts):
        selector = random.choice(selectors)
        
        # Randomly mutate selector
        mutated = chaos.maybe_fail_selector(selector)
        
        # Try to heal
        result = healer.heal_selector(mutated, field_type)
        
        if result.success:
            success_count += 1
    
    healing_rate = success_count / total_attempts
    
    # Should heal at least 40% of failures
    assert healing_rate >= 0.4
```

## Test Coverage Requirements

### Critical Components (>90% coverage)

- ✅ Execution Engine
- ✅ Selector Healing
- ✅ Trace Context
- ✅ Application Memory
- ✅ Security Validation

### Important Components (>80% coverage)

- ✅ DOM Snapshots
- ✅ Action Replay
- ✅ Timeline Events
- ✅ Telemetry
- ✅ Modern Web Handling

### Supporting Components (>70% coverage)

- ✅ Failure Diagnosis
- ✅ AI Reasoning
- ✅ Overlay Debugger
- ✅ Optimization Intelligence

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run by Layer
```bash
# Unit tests only
pytest tests/ -v -k "not integration and not chaos and not regression"

# Integration tests only
pytest tests/test_integration_*.py -v

# Chaos tests only
pytest tests/test_chaos_*.py -v

# Regression tests only
pytest tests/test_regression_*.py -v
```

### Run with Coverage
```bash
# Generate coverage report
pytest tests/ --cov=jobcli --cov-report=html

# View coverage
open htmlcov/index.html
```

### Run Specific Test
```bash
# By file
pytest tests/test_observability.py -v

# By class
pytest tests/test_observability.py::TestTraceContext -v

# By method
pytest tests/test_observability.py::TestTraceContext::test_context_propagation -v
```

### Run with Output
```bash
# Show print statements
pytest tests/ -v -s

# Show all output
pytest tests/ -v -s --tb=long
```

### Run Parallel
```bash
# Install pytest-xdist
pip install pytest-xdist

# Run on 4 CPUs
pytest tests/ -v -n 4
```

## Continuous Integration

### Pre-commit Hook
```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "Running tests before commit..."

# Run unit tests (fast)
pytest tests/ -k "not integration and not chaos" --tb=short

if [ $? -ne 0 ]; then
    echo "Unit tests failed. Commit aborted."
    exit 1
fi

echo "Tests passed!"
```

### CI Pipeline (GitHub Actions)
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Run unit tests
        run: pytest tests/ -v -k "not integration and not chaos"
      
      - name: Run integration tests
        run: pytest tests/test_integration_*.py -v
      
      - name: Run regression tests
        run: pytest tests/test_regression_*.py -v
      
      - name: Run chaos tests
        run: pytest tests/test_chaos_*.py -v
      
      - name: Generate coverage
        run: pytest tests/ --cov=jobcli --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Test Data

### Fixtures

Common test fixtures in `tests/conftest.py`:

```python
import pytest
from pathlib import Path
import tempfile

@pytest.fixture
def temp_dir():
    """Temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_page():
    """Mock Playwright page."""
    from unittest.mock import Mock
    page = Mock()
    # Setup common page mocks
    return page

@pytest.fixture
def trace_context():
    """Test trace context."""
    from jobcli.observability import create_trace_context
    return create_trace_context(
        session_id="test_session",
        company_name="Test Company",
        position_title="Test Position",
    )

@pytest.fixture
def application_memory(temp_dir):
    """Application memory with temp storage."""
    from jobcli.memory import ApplicationMemory
    return ApplicationMemory(storage_path=temp_dir / "memory.json")
```

### Test Data Files

Store test data in `tests/data/`:

```
tests/data/
├── sample_greenhouse_page.html
├── sample_lever_page.html
├── sample_workday_page.html
├── test_resume.pdf
└── test_cover_letter.txt
```

## Debugging Failed Tests

### Verbose Output
```bash
# Show full error traces
pytest tests/test_file.py -v --tb=long

# Show local variables
pytest tests/test_file.py -v --tb=long -l

# Stop on first failure
pytest tests/test_file.py -x
```

### Interactive Debugging
```bash
# Drop into debugger on failure
pytest tests/test_file.py --pdb

# Drop into debugger on error
pytest tests/test_file.py --pdbcls=IPython.terminal.debugger:TerminalPdb
```

### Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

def test_something():
    logger = logging.getLogger(__name__)
    logger.debug("Debug info")
    # Test code
```

## Performance Testing

### Benchmarking
```bash
# Install pytest-benchmark
pip install pytest-benchmark

# Run benchmarks
pytest tests/test_performance.py --benchmark-only
```

### Example benchmark:
```python
def test_selector_healing_performance(benchmark):
    """Benchmark selector healing speed."""
    healer = SelectorHealer(...)
    
    def heal():
        return healer.heal_selector("#email", "email")
    
    result = benchmark(heal)
    assert result.success
```

## Test Metrics

Track test metrics over time:

```bash
# Count tests
pytest tests/ --collect-only | grep "test session" 

# Test duration
pytest tests/ --durations=10

# Slowest tests
pytest tests/ --durations=0 | sort -k 2 -n
```

## Writing New Tests

### Test Template
```python
"""Test module for [component].

Tests:
- [What this tests]
"""

import pytest
from jobcli.[module] import [Component]


class Test[Component]:
    """Test [component] functionality."""
    
    def test_[behavior](self):
        """Test [specific behavior]."""
        # Setup
        component = [Component](...)
        
        # Execute
        result = component.method()
        
        # Assert
        assert result.success
        assert result.value == expected


def test_[edge_case]():
    """Test [edge case]."""
    # Test code
```

### Best Practices

1. **Descriptive names**: `test_context_propagates_through_async_operations`
2. **Single assertion focus**: Test one behavior per test
3. **Arrange-Act-Assert**: Clear test structure
4. **Isolated tests**: No dependencies between tests
5. **Fast execution**: Mock external dependencies
6. **Deterministic**: Same input → same output
7. **Documented**: Docstring explains what's tested

## Summary

JobCLI has comprehensive test coverage across four layers:

1. **Unit Tests**: Individual component testing (>90% coverage)
2. **Integration Tests**: End-to-end ATS flows
3. **Regression Tests**: Data structure stability
4. **Chaos Tests**: Recovery under random failures

**Total test count**: 150+ tests across all layers

**Run complete test suite:**
```bash
pytest tests/ -v --cov=jobcli --cov-report=html
```

**Expected results:**
- ✅ All unit tests pass (100%)
- ✅ All integration tests pass (100%)
- ✅ All regression tests pass (100%)
- ✅ Chaos tests pass (>80% recovery rate)

This ensures JobCLI remains reliable, maintainable, and resilient to failures.
