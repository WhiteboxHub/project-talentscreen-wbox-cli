import re

with open('jobcli/core/tool_executor.py', 'r') as f:
    content = f.read()

# Add a small delay and highlight to make it visible to the user
fill_patch = """                if loc.is_visible(timeout=2000):
                    try:
                        loc.scroll_into_view_if_needed()
                        loc.highlight()
                        self.page.wait_for_timeout(300) # Give user a chance to see
                    except Exception:
                        pass
                    loc.fill(value, timeout=action.timeout)"""

click_patch = """                if loc.is_visible(timeout=2000):
                    try:
                        loc.scroll_into_view_if_needed()
                        loc.highlight()
                        self.page.wait_for_timeout(300)
                    except Exception:
                        pass
                    loc.click(timeout=action.timeout)"""

content = content.replace("                if loc.is_visible(timeout=2000):\n                    loc.fill(value, timeout=action.timeout)", fill_patch)
content = content.replace("                if loc.is_visible(timeout=2000):\n                    loc.click(timeout=action.timeout)", click_patch)

with open('jobcli/core/tool_executor.py', 'w') as f:
    f.write(content)
