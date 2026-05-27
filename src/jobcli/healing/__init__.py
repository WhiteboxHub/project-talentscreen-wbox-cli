"""Self-healing automation system for JobCLI.

Complete self-healing capabilities:
- Selector healing with semantic matching and historical patterns
- Modern web handling (React SPAs, Shadow DOM, delayed hydration)
- Adaptive retry with confidence-based escalation
- Automatic fallback strategies

Usage:
    from jobcli.healing import SelfHealingEngine
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        page = p.chromium.launch().new_page()

        # Initialize self-healing engine
        engine = SelfHealingEngine(
            page=page,
            ats_type=ATSType.LEVER,
            enable_healing=True,
            enable_modern_web=True
        )

        # Execute actions with automatic healing
        result = engine.execute(action)

        # Print healing summary
        engine.print_summary()
"""

from .adaptive_retry import (
    AdaptiveRetry,
    EscalationLevel,
    RetryConfig,
    RetryResult,
    RetryStrategy,
    RetryWithHealing,
)
from .modern_web_handler import (
    HydrationStatus,
    ModernWebHandler,
    ModernWebInfo,
    WebFramework,
)
from .selector_healer import (
    HistoricalPattern,
    SelectorCandidate,
    SelectorHealer,
    SelectorHealingResult,
)
from .self_healing_engine import HealingMetrics, SelfHealingEngine

__all__ = [
    # Self-healing engine
    "SelfHealingEngine",
    "HealingMetrics",
    # Selector healing
    "SelectorHealer",
    "SelectorHealingResult",
    "SelectorCandidate",
    "HistoricalPattern",
    # Modern web
    "ModernWebHandler",
    "ModernWebInfo",
    "WebFramework",
    "HydrationStatus",
    # Adaptive retry
    "AdaptiveRetry",
    "RetryWithHealing",
    "RetryConfig",
    "RetryResult",
    "RetryStrategy",
    "EscalationLevel",
]
