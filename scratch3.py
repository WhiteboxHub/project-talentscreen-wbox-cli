from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://jobs.ashbyhq.com/mach9/00cdc4ed-eea2-4a95-bbd6-a885d5429e38/application")
    page.wait_for_selector("input[type='file']")
    
    # Check buttons matching upload
    buttons = page.locator("button:has-text('Upload'), [role='button']:has-text('Upload')").all()
    print(f"Found {len(buttons)} 'Upload' buttons.")
    for i, btn in enumerate(buttons):
        html = btn.evaluate("el => el.outerHTML")
        is_trap = btn.evaluate("""el => {
            let node = el;
            for (let depth = 0; depth < 3 && node; depth++) {
                const text = (node.textContent || '').toLowerCase();
                if (text.includes('autofill') || text.includes('parse') || text.includes('extract')) {
                    if (text.length < 500) {
                        return true;
                    }
                }
                const attrs = [...node.attributes].map(a => (a.value || '').toLowerCase());
                if (attrs.some(v => v.includes('autofill') || v.includes('parse'))) {
                    return true;
                }
                node = node.parentElement;
            }
            return false;
        }""")
        print(f"\n--- Button {i} ---")
        print("HTML:", html)
        print("is_trap:", is_trap)
        
    print("\n\nChecking input[type='file']...")
    inputs = page.locator("input[type='file']").all()
    print(f"Found {len(inputs)} file inputs.")
    for i, inp in enumerate(inputs):
        html = inp.evaluate("el => el.outerHTML")
        is_trap = inp.evaluate("""el => {
            let node = el;
            for (let depth = 0; depth < 4 && node; depth++) {
                const text = (node.textContent || '').toLowerCase();
                if (text.includes('autofill') || text.includes('parse') || text.includes('extract')) {
                    if (text.length < 500) return true;
                }
                const attrs = [...node.attributes].map(a => (a.value || '').toLowerCase());
                if (attrs.some(v => v.includes('autofill') || v.includes('parse'))) {
                    return true;
                }
                node = node.parentElement;
            }
            return false;
        }""")
        print(f"\n--- Input {i} ---")
        print("HTML:", html)
        print("is_trap:", is_trap)

    browser.close()
