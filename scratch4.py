from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://jobs.ashbyhq.com/mach9/00cdc4ed-eea2-4a95-bbd6-a885d5429e38/application")
    page.wait_for_selector("input[type='file']")
    
    inputs = page.locator("input[type='file']").all()
    print("Length of Autofill box text:")
    length = inputs[0].evaluate("""el => {
        let node = el;
        for (let d = 0; d < 4 && node; d++) {
            const t = node.textContent || '';
            if (t.toLowerCase().includes('autofill')) return t.length;
            node = node.parentElement;
        }
        return -1;
    }""")
    print("Length:", length)
    text_content = inputs[0].evaluate("""el => {
        let node = el;
        for (let d = 0; d < 4 && node; d++) {
            const t = node.textContent || '';
            if (t.toLowerCase().includes('autofill')) return t;
            node = node.parentElement;
        }
        return '';
    }""")
    print("Content:", text_content)

    browser.close()
