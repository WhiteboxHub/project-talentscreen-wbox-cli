"""DOM extraction for LLM analysis."""

from typing import Any

from playwright.sync_api import Page

from jobcli.core.schemas import DOMSnapshot


class DOMExtractor:
    """Extract structured DOM data for LLM processing."""

    def __init__(self, page: Page) -> None:
        """Initialize extractor."""
        self.page = page

    def extract(self) -> DOMSnapshot:
        """Extract structured DOM snapshot."""
        url = self.page.url
        title = self.page.title()

        # Extract interactive elements
        interactive = self._extract_interactive_elements()
        forms = self._extract_forms()
        buttons = self._extract_buttons()
        inputs = self._extract_inputs()
        links = self._extract_links()

        # Extract metadata
        metadata = self._extract_metadata()

        return DOMSnapshot(
            url=url,
            title=title,
            interactive_elements=interactive,
            forms=forms,
            buttons=buttons,
            inputs=inputs,
            links=links,
            metadata=metadata,
        )

    def _extract_interactive_elements(self) -> list[dict[str, Any]]:
        """Extract all interactive elements."""
        script = """
        () => {
            const elements = document.querySelectorAll('button, a, input, select, textarea, [role="button"]');
            return Array.from(elements).slice(0, 100).map((el, idx) => ({
                index: idx,
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                text: el.textContent?.trim().substring(0, 100) || '',
                visible: el.offsetParent !== null,
                role: el.getAttribute('role'),
                ariaLabel: el.getAttribute('aria-label'),
                className: el.className,
                id: el.id,
                name: el.name || null,
                href: el.href || null,
                value: el.value || null,
            }));
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _extract_forms(self) -> list[dict[str, Any]]:
        """Extract form information."""
        script = """
        () => {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map((form, idx) => ({
                index: idx,
                action: form.action,
                method: form.method,
                id: form.id,
                className: form.className,
                fieldCount: form.elements.length,
                fields: Array.from(form.elements).slice(0, 50).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || null,
                    name: el.name || null,
                    id: el.id || null,
                    required: el.required || false,
                    placeholder: el.placeholder || null,
                })),
            }));
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _extract_buttons(self) -> list[dict[str, Any]]:
        """Extract button elements."""
        script = """
        () => {
            const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]');
            return Array.from(buttons).slice(0, 50).map((btn, idx) => ({
                index: idx,
                tag: btn.tagName.toLowerCase(),
                type: btn.type || null,
                text: btn.textContent?.trim() || btn.value || '',
                visible: btn.offsetParent !== null,
                disabled: btn.disabled || false,
                className: btn.className,
                id: btn.id,
                ariaLabel: btn.getAttribute('aria-label'),
            }));
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _extract_inputs(self) -> list[dict[str, Any]]:
        """Extract input fields."""
        script = """
        () => {
            const inputs = document.querySelectorAll('input, textarea, select');
            return Array.from(inputs).slice(0, 50).map((input, idx) => {
                const label = input.labels?.[0]?.textContent?.trim() ||
                              document.querySelector(`label[for="${input.id}"]`)?.textContent?.trim() ||
                              input.closest('label')?.textContent?.trim() ||
                              input.getAttribute('aria-label') ||
                              input.placeholder ||
                              '';
                return {
                    index: idx,
                    tag: input.tagName.toLowerCase(),
                    type: input.type || 'text',
                    name: input.name || null,
                    id: input.id || null,
                    label: label.substring(0, 100),
                    placeholder: input.placeholder || null,
                    required: input.required || false,
                    visible: input.offsetParent !== null,
                    value: input.value || null,
                };
            });
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _extract_links(self) -> list[dict[str, Any]]:
        """Extract link elements."""
        script = """
        () => {
            const links = document.querySelectorAll('a');
            return Array.from(links).slice(0, 50).map((link, idx) => ({
                index: idx,
                text: link.textContent?.trim().substring(0, 100) || '',
                href: link.href || null,
                visible: link.offsetParent !== null,
                className: link.className,
                id: link.id,
            }));
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return []

    def _extract_metadata(self) -> dict[str, Any]:
        """Extract page metadata."""
        metadata: dict[str, Any] = {}

        try:
            # Get meta tags
            meta_tags = self.page.query_selector_all("meta")
            for meta in meta_tags:
                name = meta.get_attribute("name") or meta.get_attribute("property")
                content = meta.get_attribute("content")
                if name and content:
                    metadata[name] = content

            # Get body classes
            body = self.page.query_selector("body")
            if body:
                metadata["body_classes"] = body.get_attribute("class") or ""

        except Exception:
            pass

        return metadata
