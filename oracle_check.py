from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://fa-ewmy-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/2920?utm_medium=jobboard&utm_source=linkedin")
    page.wait_for_load_state("networkidle", timeout=15000)
    
    # print all buttons
    locators = page.locator("button, a").all()
    out = []
    for loc in locators:
        try:
            text = loc.text_content(timeout=100)
            if "apply" in (text or "").lower():
                out.append(f"TAG: {loc.evaluate('el => el.tagName')}, TEXT: {text.strip()}, CLASS: {loc.get_attribute('class')}, ID: {loc.get_attribute('id')}")
        except Exception:
            pass
            
    print("--- BUTTONS ---")
    print("\n".join(out))
    browser.close()
