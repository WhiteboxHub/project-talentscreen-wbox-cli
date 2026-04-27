from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://jobs.ashbyhq.com/mach9/00cdc4ed-eea2-4a95-bbd6-a885d5429e38/application")
    page.wait_for_selector("input[type='file']")
    
    inputs = page.locator("input[type='file']").all()
    print(f"Found {len(inputs)} file inputs.")
    
    for i, inp in enumerate(inputs):
        html = inp.evaluate("el => el.outerHTML")
        parent_html = inp.evaluate("el => el.parentElement ? el.parentElement.outerHTML : ''")
        print(f"\n--- Input {i} ---")
        print("HTML:", html)
        print("Parent HTML:", parent_html[:500]) # Truncate parent to 500 chars

    browser.close()
