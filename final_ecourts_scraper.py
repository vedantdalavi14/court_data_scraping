## FINAL WORKING SCRIPT - COMMAND-LINE VERSION ##

import time
import os
import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page
import subprocess
import platform

# --- Configuration ---
CAPTCHA_IMAGE_FILENAME = "captcha.png"

# --- Database and Parsing Functions (Unchanged) ---
def init_db():
    conn = sqlite3.connect('cases.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_type TEXT NOT NULL, case_number TEXT NOT NULL,
            case_year TEXT NOT NULL, petitioner_name TEXT, respondent_name TEXT, filing_date TEXT,
            next_hearing_date TEXT, case_status TEXT, most_recent_order_pdf_url TEXT,
            raw_html TEXT, scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_case_data(scraped_data):
    conn = sqlite3.connect('cases.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cases (case_type, case_number, case_year, petitioner_name, respondent_name, filing_date, next_hearing_date, case_status, most_recent_order_pdf_url, raw_html)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        scraped_data.get('case_type'), scraped_data.get('case_number'), scraped_data.get('case_year'),
        scraped_data.get('petitioner_name'), scraped_data.get('respondent_name'),
        scraped_data.get('filing_date'), scraped_data.get('next_hearing_date'),
        scraped_data.get('case_status'), scraped_data.get('most_recent_order_pdf_url'),
        scraped_data.get('raw_html')
    ))
    conn.commit()
    conn.close()

def parse_case_details(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    base_url = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/"
    parsed_data = {
        'petitioner_name': 'Not Found', 'respondent_name': 'Not Found', 'filing_date': 'Not Found',
        'next_hearing_date': 'Not Found', 'case_status': 'Not Found', 'most_recent_order_pdf_url': 'Not Found'
    }
    try:
        petitioner_full_text = soup.find('span', class_='Petitioner_Advocate_table').get_text(strip=True, separator=' ')
        parsed_data['petitioner_name'] = petitioner_full_text.split('Advocate-')[0].strip()
    except: pass
    try:
        parsed_data['respondent_name'] = soup.find('span', class_='Respondent_Advocate_table').get_text(strip=True, separator=' ')
    except: pass
    try:
        filing_date_label = soup.find(lambda tag: tag.name == 'label' and 'Filing Date' in tag.text)
        if filing_date_label:
            parsed_data['filing_date'] = filing_date_label.next_sibling.strip(': ').strip()
    except: pass
    try:
        status_label = soup.find('strong', string='Case Status ')
        if status_label:
            status = status_label.find_next_sibling('strong').text.strip(': ').strip()
            parsed_data['case_status'] = status
            if "DISPOSED" in status.upper(): parsed_data['next_hearing_date'] = 'N/A (Case Disposed)'
    except: pass
    try:
        orders_table = soup.find('table', class_='order_table')
        if orders_table:
            pdf_link_tag = orders_table.find('a')
            if pdf_link_tag and pdf_link_tag.has_attr('href'):
                parsed_data['most_recent_order_pdf_url'] = urljoin(base_url, pdf_link_tag['href'])
    except: pass
    return parsed_data

def open_image(path):
    """Opens the CAPTCHA image for the user in a cross-platform way."""
    system = platform.system()
    if system == "Windows":
        os.startfile(path)
    elif system == "Darwin": # macOS
        subprocess.run(["open", path])
    else: # Linux
        subprocess.run(["xdg-open", path])

# --- Main Application Runner ---
# ----------------------------------------------------------------------------------
# FINAL SCRIPT - With a retry loop for CAPTCHA fetching to handle network issues
# Replace your entire main() function with this version.
# ----------------------------------------------------------------------------------
def main():
    URL = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("Navigating to e-Courts website...")
        page.goto(URL, wait_until="domcontentloaded")
        print("Page loaded.")

        try:
            # Step 1: Get input from the user in the terminal
            print("\n--- Please enter case details below ---\n")
            case_type = input("Enter Case Type Code (e.g., 144 for WP): ")
            case_number = input("Enter Case Number: ")
            case_year = input("Enter Case Year (YYYY): ")

            case_details = {
                'case_type': case_type, 'case_number': case_number, 'case_year': case_year
            }

            # Step 2: Fill details
            print("\nFilling form details with human-like delays...")
            page.select_option('select#case_type', value=case_type)
            page.wait_for_timeout(500)
            page.locator('input#search_case_no').type(case_number, delay=100)
            page.wait_for_timeout(500)
            page.locator('input#rgyear').type(case_year, delay=100)
            
            # --- START OF CAPTCHA RETRY LOOP ---
            got_captcha = False
            max_retries = 3
            for attempt in range(max_retries):
                print(f"\nAttempt {attempt + 1} of {max_retries} to get a stable CAPTCHA image...")
                try:
                    # Always click refresh to ensure we're getting a fresh image
                    page.click("a[title='Refresh Image']")
                    page.wait_for_timeout(2000) # Give it 2 seconds to load

                    captcha_element = page.locator("//img[@id='captcha_image' or @id='cap']")
                    captcha_element.wait_for(state="visible", timeout=10000)
                    
                    # Try to take the screenshot
                    captcha_element.screenshot(path=CAPTCHA_IMAGE_FILENAME)
                    
                    print("Stable CAPTCHA image received and saved.")
                    got_captcha = True
                    break # If successful, exit the loop
                except Exception as e:
                    print(f"Warning: Failed to get CAPTCHA on attempt {attempt + 1}. The website might be slow.")
                    if attempt >= max_retries - 1:
                        print("Could not retrieve a stable CAPTCHA after multiple attempts.")
                        raise e # Give up and show the final error
            # --- END OF CAPTCHA RETRY LOOP ---
            
            # Step 3: Get CAPTCHA solution from user
            print(f"CAPTCHA image saved to '{CAPTCHA_IMAGE_FILENAME}' and is opening now...")
            open_image(CAPTCHA_IMAGE_FILENAME)
            solution = input("\nEnter the CAPTCHA solution you see in the image: ")

            # Step 4: Submit and get results
            page.locator('input#captcha').type(solution, delay=100)
            print("Submitting form...")
            page.click("input[name='submit1']")
            
            print("Waiting for AJAX results to appear on the page...")
            try:
                view_link = page.locator("a[onclick*='viewHistory']")
                view_link.wait_for(state="visible", timeout=20000)
                
                print("\nSUCCESS! Case found. Clicking 'View' to get details...")
                view_link.click(force=True)
                
                page.wait_for_load_state('networkidle', timeout=20000)
                
                print("Details page loaded. Parsing data...")
                html_content = page.content()
                scraped_data = parse_case_details(html_content)
                scraped_data.update(case_details)
                scraped_data['raw_html'] = html_content
                save_case_data(scraped_data)
                
                print("\n--- SCRAPED DATA ---")
                for key, value in scraped_data.items():
                    if key != 'raw_html':
                        print(f"{key.replace('_', ' ').title()}: {value}")
                print("\nScraped data has been saved to 'cases.db'.")

            except Exception as e:
                print("Did not find 'View' link. Checking for an error message...")
                error_input = page.locator("input#txtmsg")
                if error_input.is_visible(timeout=5000):
                    error_text = error_input.get_attribute('value')
                    print(f"\nFAILURE. Reason from page: '{error_text}'")
                else:
                    print("\nFAILURE. An unexpected error occurred and no results or error message could be found.")
                    print(f"Debug details: {e}")
                print("Please run the script again.")

        except Exception as e:
            print(f"\nAn unexpected error occurred in the main process: {e}")
        
        finally:
            print("\nScript finished. Browser will close in 10 seconds.")
            time.sleep(10)
            browser.close()

if __name__ == "__main__":
    init_db()
    main()
