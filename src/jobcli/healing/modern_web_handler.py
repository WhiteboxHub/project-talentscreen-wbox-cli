"""Handler for modern web technologies.

Supports:
- React SPAs with client-side rendering
- Shadow DOM
- Delayed hydration
- Dynamic rendering
- Framework-specific patterns (React, Vue, Angular)
"""

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page
from pydantic import BaseModel, Field


class WebFramework(str, Enum):
    """Detected web framework."""

    REACT = "react"
    VUE = "vue"
    ANGULAR = "angular"
    UNKNOWN = "unknown"


class HydrationStatus(str, Enum):
    """Client-side hydration status."""

    NOT_HYDRATED = "not_hydrated"
    HYDRATING = "hydrating"
    HYDRATED = "hydrated"
    UNKNOWN = "unknown"


class ModernWebInfo(BaseModel):
    """Information about modern web technologies on page."""

    framework: WebFramework
    hydration_status: HydrationStatus
    has_shadow_dom: bool = False
    is_spa: bool = False
    dynamic_content: bool = False
    detected_patterns: List[str] = Field(default_factory=list)


class ModernWebHandler:
    """Handler for modern web technologies."""

    # Wait times
    HYDRATION_WAIT_MS = 5000
    REACT_RENDER_WAIT_MS = 2000
    SHADOW_DOM_WAIT_MS = 1000

    def __init__(self, page: Page):
        """Initialize modern web handler.

        Args:
            page: Playwright Page instance
        """
        self.page = page
        self._framework: Optional[WebFramework] = None
        self._hydration_status: Optional[HydrationStatus] = None

    def detect_technologies(self) -> ModernWebInfo:
        """Detect modern web technologies on page.

        Returns:
            ModernWebInfo with detected technologies
        """
        framework = self._detect_framework()
        hydration_status = self._check_hydration_status()
        has_shadow_dom = self._check_shadow_dom()
        is_spa = self._check_if_spa()
        dynamic_content = self._check_dynamic_content()

        patterns = []
        if framework != WebFramework.UNKNOWN:
            patterns.append(f"framework:{framework.value}")
        if has_shadow_dom:
            patterns.append("shadow_dom")
        if is_spa:
            patterns.append("spa")
        if dynamic_content:
            patterns.append("dynamic_content")

        return ModernWebInfo(
            framework=framework,
            hydration_status=hydration_status,
            has_shadow_dom=has_shadow_dom,
            is_spa=is_spa,
            dynamic_content=dynamic_content,
            detected_patterns=patterns,
        )

    def wait_for_hydration(self, timeout_ms: int = HYDRATION_WAIT_MS) -> bool:
        """Wait for client-side hydration to complete.

        Args:
            timeout_ms: Maximum time to wait

        Returns:
            True if hydration completed
        """
        framework = self._detect_framework()

        if framework == WebFramework.REACT:
            return self._wait_for_react_hydration(timeout_ms)
        elif framework == WebFramework.VUE:
            return self._wait_for_vue_hydration(timeout_ms)
        elif framework == WebFramework.ANGULAR:
            return self._wait_for_angular_hydration(timeout_ms)
        else:
            # Generic wait
            return self._wait_for_generic_hydration(timeout_ms)

    def find_in_shadow_dom(
        self,
        selector: str,
        shadow_host_selector: Optional[str] = None,
    ) -> Optional[Any]:
        """Find element in Shadow DOM.

        Args:
            selector: Selector to find inside shadow root
            shadow_host_selector: Selector for shadow host (if known)

        Returns:
            Locator or None
        """
        if not self._check_shadow_dom():
            return None

        # If shadow host is known, use it
        if shadow_host_selector:
            try:
                # Pierce through shadow DOM
                full_selector = f"{shadow_host_selector} >>> {selector}"
                locator = self.page.locator(full_selector)
                if locator.count() > 0:
                    return locator.first
            except Exception:
                pass

        # Try common shadow host patterns
        shadow_hosts = ["[shadowroot]", "web-component", "*:has(shadowRoot)"]

        for host_pattern in shadow_hosts:
            try:
                full_selector = f"{host_pattern} >>> {selector}"
                locator = self.page.locator(full_selector)
                if locator.count() > 0:
                    return locator.first
            except Exception:
                pass

        return None

    def wait_for_dynamic_content(
        self,
        selector: str,
        timeout_ms: int = 5000,
    ) -> bool:
        """Wait for dynamically loaded content.

        Args:
            selector: Selector to wait for
            timeout_ms: Maximum time to wait

        Returns:
            True if content appeared
        """
        try:
            # Wait for network idle (common pattern for SPA)
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)

            # Wait for selector
            self.page.wait_for_selector(selector, timeout=timeout_ms, state="visible")

            return True

        except Exception:
            return False

    def handle_spa_navigation(self, action_callback: callable) -> bool:
        """Handle SPA navigation (client-side routing).

        Args:
            action_callback: Function that triggers navigation

        Returns:
            True if navigation handled successfully
        """
        if not self._check_if_spa():
            # Not an SPA, regular navigation
            action_callback()
            return True

        try:
            # For SPAs, wait for URL change instead of page load
            initial_url = self.page.url

            # Execute action
            action_callback()

            # Wait for URL change
            start_time = time.time()
            timeout_s = 5.0

            while time.time() - start_time < timeout_s:
                if self.page.url != initial_url:
                    # URL changed, wait for network idle
                    self.page.wait_for_load_state("networkidle", timeout=2000)
                    return True

                time.sleep(0.1)

            return False

        except Exception:
            return False

    def get_react_fiber_data(self, selector: str) -> Optional[Dict[str, Any]]:
        """Extract React Fiber data from element.

        Useful for understanding React component props.

        Args:
            selector: Element selector

        Returns:
            Fiber data or None
        """
        if self._detect_framework() != WebFramework.REACT:
            return None

        try:
            data = self.page.evaluate(
                f"""
                (selector) => {{
                    const element = document.querySelector(selector);
                    if (!element) return null;

                    // Try to get React Fiber
                    const fiberKey = Object.keys(element).find(key =>
                        key.startsWith('__reactFiber') ||
                        key.startsWith('__reactInternalInstance')
                    );

                    if (!fiberKey) return null;

                    const fiber = element[fiberKey];
                    if (!fiber) return null;

                    // Extract useful data
                    return {{
                        type: fiber.type?.name || fiber.elementType?.name || null,
                        props: fiber.memoizedProps || null,
                        state: fiber.memoizedState || null
                    }};
                }}
            """,
                selector,
            )

            return data

        except Exception:
            return None

    # ── Private Methods ───────────────────────────────────────────────────────

    def _detect_framework(self) -> WebFramework:
        """Detect JavaScript framework.

        Returns:
            WebFramework enum
        """
        if self._framework is not None:
            return self._framework

        try:
            result = self.page.evaluate(
                """
                () => {
                    // Check for React
                    if (window.React || document.querySelector('[data-reactroot]') ||
                        document.querySelector('[data-reactid]')) {
                        return 'react';
                    }

                    // Check for Vue
                    if (window.Vue || document.querySelector('[data-v-]') ||
                        document.querySelector('[v-cloak]')) {
                        return 'vue';
                    }

                    // Check for Angular
                    if (window.ng || document.querySelector('[ng-version]') ||
                        document.querySelector('[ng-app]')) {
                        return 'angular';
                    }

                    return 'unknown';
                }
            """
            )

            self._framework = WebFramework(result)
            return self._framework

        except Exception:
            self._framework = WebFramework.UNKNOWN
            return self._framework

    def _check_hydration_status(self) -> HydrationStatus:
        """Check if page hydration is complete.

        Returns:
            HydrationStatus enum
        """
        if self._hydration_status is not None:
            return self._hydration_status

        framework = self._detect_framework()

        if framework == WebFramework.REACT:
            status = self._check_react_hydration()
        elif framework == WebFramework.VUE:
            status = self._check_vue_hydration()
        elif framework == WebFramework.ANGULAR:
            status = self._check_angular_hydration()
        else:
            status = HydrationStatus.UNKNOWN

        self._hydration_status = status
        return status

    def _check_react_hydration(self) -> HydrationStatus:
        """Check React hydration status.

        Returns:
            HydrationStatus
        """
        try:
            is_hydrated = self.page.evaluate(
                """
                () => {
                    // Check if React root is hydrated
                    const root = document.querySelector('[data-reactroot]');
                    if (!root) return false;

                    // Check for React Fiber
                    const fiberKey = Object.keys(root).find(key =>
                        key.startsWith('__reactFiber')
                    );

                    return !!fiberKey;
                }
            """
            )

            return (
                HydrationStatus.HYDRATED
                if is_hydrated
                else HydrationStatus.NOT_HYDRATED
            )

        except Exception:
            return HydrationStatus.UNKNOWN

    def _check_vue_hydration(self) -> HydrationStatus:
        """Check Vue hydration status."""
        try:
            is_hydrated = self.page.evaluate(
                """
                () => {
                    // Check if Vue app is mounted
                    const vueEl = document.querySelector('[data-v-]');
                    if (!vueEl) return false;

                    // Check for Vue instance
                    return !!(vueEl.__vue__ || vueEl.__vueParentComponent);
                }
            """
            )

            return (
                HydrationStatus.HYDRATED
                if is_hydrated
                else HydrationStatus.NOT_HYDRATED
            )

        except Exception:
            return HydrationStatus.UNKNOWN

    def _check_angular_hydration(self) -> HydrationStatus:
        """Check Angular hydration status."""
        try:
            is_hydrated = self.page.evaluate(
                """
                () => {
                    // Check if Angular is bootstrapped
                    return !!(window.ng && window.ng.probe);
                }
            """
            )

            return (
                HydrationStatus.HYDRATED
                if is_hydrated
                else HydrationStatus.NOT_HYDRATED
            )

        except Exception:
            return HydrationStatus.UNKNOWN

    def _check_shadow_dom(self) -> bool:
        """Check if page uses Shadow DOM.

        Returns:
            True if Shadow DOM detected
        """
        try:
            has_shadow = self.page.evaluate(
                """
                () => {
                    // Check for shadow roots
                    const elements = document.querySelectorAll('*');
                    for (let el of elements) {
                        if (el.shadowRoot) return true;
                    }
                    return false;
                }
            """
            )

            return has_shadow

        except Exception:
            return False

    def _check_if_spa(self) -> bool:
        """Check if page is a Single Page Application.

        Returns:
            True if SPA detected
        """
        try:
            is_spa = self.page.evaluate(
                """
                () => {
                    // Check for common SPA indicators
                    // 1. History API usage
                    if (window.history.pushState.toString().includes('[native code]') === false) {
                        return true;
                    }

                    // 2. Client-side router
                    if (window.__REACT_ROUTER__ || window.$router || window.router) {
                        return true;
                    }

                    // 3. Framework detection
                    if (window.React || window.Vue || window.ng) {
                        return true;
                    }

                    return false;
                }
            """
            )

            return is_spa

        except Exception:
            return False

    def _check_dynamic_content(self) -> bool:
        """Check if page loads content dynamically.

        Returns:
            True if dynamic content detected
        """
        try:
            has_dynamic = self.page.evaluate(
                """
                () => {
                    // Check for loading indicators
                    const loadingSelectors = [
                        '[class*="loading"]',
                        '[class*="spinner"]',
                        '[class*="skeleton"]',
                        '[role="progressbar"]'
                    ];

                    for (let selector of loadingSelectors) {
                        if (document.querySelector(selector)) {
                            return true;
                        }
                    }

                    // Check for lazy loading
                    if (document.querySelector('[loading="lazy"]')) {
                        return true;
                    }

                    return false;
                }
            """
            )

            return has_dynamic

        except Exception:
            return False

    def _wait_for_react_hydration(self, timeout_ms: int) -> bool:
        """Wait for React hydration to complete."""
        try:
            self.page.wait_for_function(
                """
                () => {
                    const root = document.querySelector('[data-reactroot]');
                    if (!root) return false;

                    const fiberKey = Object.keys(root).find(key =>
                        key.startsWith('__reactFiber')
                    );

                    return !!fiberKey;
                }
            """,
                timeout=timeout_ms,
            )

            return True

        except Exception:
            return False

    def _wait_for_vue_hydration(self, timeout_ms: int) -> bool:
        """Wait for Vue hydration to complete."""
        try:
            self.page.wait_for_function(
                """
                () => {
                    const vueEl = document.querySelector('[data-v-]');
                    return !!(vueEl && (vueEl.__vue__ || vueEl.__vueParentComponent));
                }
            """,
                timeout=timeout_ms,
            )

            return True

        except Exception:
            return False

    def _wait_for_angular_hydration(self, timeout_ms: int) -> bool:
        """Wait for Angular hydration to complete."""
        try:
            self.page.wait_for_function(
                """
                () => {
                    return !!(window.ng && window.ng.probe);
                }
            """,
                timeout=timeout_ms,
            )

            return True

        except Exception:
            return False

    def _wait_for_generic_hydration(self, timeout_ms: int) -> bool:
        """Wait for generic hydration indicators."""
        try:
            # Wait for network idle
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)

            # Wait for no loading indicators
            self.page.wait_for_function(
                """
                () => {
                    const loadingSelectors = [
                        '[class*="loading"]',
                        '[class*="spinner"]',
                        '[role="progressbar"]'
                    ];

                    for (let selector of loadingSelectors) {
                        const el = document.querySelector(selector);
                        if (el && el.offsetParent !== null) {
                            return false;  // Still loading
                        }
                    }

                    return true;  // No loading indicators visible
                }
            """,
                timeout=timeout_ms,
            )

            return True

        except Exception:
            return False
