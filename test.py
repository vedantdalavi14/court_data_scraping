# File: test_playwright.py

import time
from playwright.sync_api import sync_playwright

def run_playwright_test():
    URL = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3"
    
    with sync_playwright() as p:
        # We will try to emulate a real browser as closely as possible
        browser = p.chromium.launch(headless=False) # Use headed mode for the test
        
        # Create a persistent context, similar to a user profile
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        print("Navigating to e-Courts website with Playwright...")
        try:
            page.goto(URL, wait_until="networkidle", timeout=30000)
            print("Page loaded successfully.")
            
            # Locate the CAPTCHA image element
            captcha_element = page.locator("//img[@id='captcha_image' or @id='cap']")
            
            # Take a screenshot of just the CAPTCHA
            screenshot_path = "captcha_playwright.png"
            captcha_element.screenshot(path=screenshot_path)
            
            print(f"SUCCESS: Playwright was not blocked. CAPTCHA image saved to '{screenshot_path}'")
            print("You can now try manually solving the CAPTCHA in the Playwright browser window to see if it works.")
            
        except Exception as e:
            print(f"FAILURE: An error occurred. Playwright may also have been blocked. Error: {e}")
            
        print("\nTest will finish in 60 seconds...")
        time.sleep(60)
        browser.close()

if __name__ == "__main__":
    run_playwright_test()