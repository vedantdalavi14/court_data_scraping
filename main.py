## FINAL SCRIPT - COMMAND-LINE VERSION (NO FLASK) ##

import time
import os
import sqlite3
import random
from pathlib import Path
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page, expect
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
# --------------------------------------------------------------------
# Replace your entire old main() function with this FINAL version
# --------------------------------------------------------------------
# --------------------------------------------------------------------
# The main() function, edited to use the onclick attribute locator
# --------------------------------------------------------------------
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

            # Step 2: Fill details and refresh CAPTCHA
            print("\nFilling form details...")
            page.select_option('select#case_type', value=case_type)
            page.fill('input#search_case_no', case_number)
            page.fill('input#rgyear', case_year)
            print("Forcing CAPTCHA refresh to get real image...")
            page.click("a[title='Refresh Image']")
            page.wait_for_timeout(1500)

            # Step 3: Get CAPTCHA and ask for solution
            captcha_element = page.locator("//img[@id='captcha_image' or @id='cap']")
            captcha_element.screenshot(path=CAPTCHA_IMAGE_FILENAME)
            print(f"CAPTCHA image saved to '{CAPTCHA_IMAGE_FILENAME}' and is opening now...")
            open_image(CAPTCHA_IMAGE_FILENAME)
            
            solution = input("\nEnter the CAPTCHA solution you see in the image: ")

            # Step 4: Submit and get results
            page.fill('input#captcha', solution)
            print("Submitting form...")
            page.click("input[name='submit1']")
            print("Waiting for server response (results to appear)...")

            # --- START OF THE EDIT ---
            # Define the new CSS selector for the success link based on its 'onclick' attribute.
            # The '*' means the attribute "contains" the text 'viewHistory'.
            view_link_selector = "a[onclick*='viewHistory']"
            error_input_selector = "input#txtmsg"

            # Use the new selector in our wait condition.
            page.wait_for_selector(
                f"{view_link_selector}, {error_input_selector}",
                state='visible',
                timeout=20000
            )

            # Define the locators again for the final check.
            view_link = page.locator(view_link_selector)
            error_input = page.locator(error_input_selector)
            
            # The rest of the logic is the same.
            if view_link.is_visible():
                print("\nSUCCESS! Case found. Scraping data...")
                view_link.click()
                page.wait_for_load_state('networkidle')
                
                html_content = page.content()
                scraped_data = parse_case_details(html_content)
                scraped_data.update(case_details)
                scraped_data['raw_html'] = html_content
                save_case_data(scraped_data)
                print("Scraped data has been saved to 'cases.db'.")
            elif error_input.is_visible():
                error_text = error_input.get_attribute('value')
                print(f"\nFAILURE. Reason from page: '{error_text}'")
                print("Please run the script again.")
            else:
                print("\nFAILURE. Unknown page state after waiting.")
                print("Please run the script again.")
            # --- END OF THE EDIT ---

        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
        
        finally:
            print("\nScript finished. Browser will close in 10 seconds.")
            time.sleep(10)
            browser.close()

if __name__ == "__main__":
    init_db()
    main()