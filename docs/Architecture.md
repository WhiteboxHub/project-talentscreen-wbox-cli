# JobCLI Architecture

High-level architecture overview of JobCLI's core systems and how they interact.

## System Overview

All systems integrate through the Observability Layer which provides complete traceability.

### Component Hierarchy

```
Observability Layer (trace context + structured logging)
    ↓
Execution Engine (structured actions + validation + retry)
    ↓
    ├─ On Success → Memory System (learn patterns)
    └─ On Failure → Self-Healing Engine (5 strategies)
    
Debug System (snapshots + replay + timeline + diagnosis)
```

## Core Components

1. **Observability** - 5-level ID hierarchy (session → app → job → attempt → trace)
2. **Execution Engine** - Structured actions with pre/post validation
3. **Self-Healing** - Automatic selector recovery
4. **Debug System** - Complete execution visibility
5. **Application Memory** - Learning from past applications
6. **Semantic Engine** - AI field classification

## Documentation

See [docs/README.md](README.md) for complete system documentation.

### System Details

- [Execution Layer](EXECUTION_LAYER.md) - Action execution
- [Debug System](DEBUG_SYSTEM.md) - Replay and diagnosis
- [Self-Healing](SELF_HEALING.md) - Selector recovery
- [Application Memory](APPLICATION_MEMORY.md) - Learning system
- [Observability](OBSERVABILITY.md) - Tracing and logging
- [Testing](TESTING.md) - Test strategy

## File Structure

```
src/jobcli/
├── execution/           # Execution engine
├── healing/             # Self-healing
├── debug/               # Debug system
├── observability/       # Observability
├── memory/              # Application memory
└── semantic/            # Semantic engine
```
