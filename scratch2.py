from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://jobs.ashbyhq.com/mach9/00cdc4ed-eea2-4a95-bbd6-a885d5429e38/application")
    page.wait_for_selector("input[type='file']")
    
    inputs = page.locator("input[type='file']").all()
    for i, inp in enumerate(inputs):
        text = inp.evaluate("""el => {
            let node = el;
            for (let d = 0; d < 8 && node; d++) {
                if (node.textContent && node.textContent.toLowerCase().includes('autofill')) return 'FOUND';
                node = node.parentElement;
            }
            return 'NOT FOUND';
        }""")
        print(f"Input {i}: {text}")
    browser.close()
