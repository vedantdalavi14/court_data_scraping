## FINAL SCRIPT - With the Most Robust Waiting and Error Handling Logic ##

import time
import os
import io
import threading
import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, render_template, url_for
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page, expect
import queue
import platform
import subprocess

# --- Database and Parsing Functions ---
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

# --- Global Variables ---
page: Page = None
CAPTCHA_IMAGE_FILENAME = "captcha.png"
job_queue = queue.Queue()
result_queue = queue.Queue()

# --- Flask App Setup ---
app = Flask(__name__)

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('step1.html')

@app.route('/get_captcha', methods=['POST'])
def get_captcha():
    case_details = {
        'case_type': request.form['case_type'],
        'case_number': request.form['case_number'],
        'case_year': request.form['case_year']
    }
    job_queue.put({'action': 'fill_and_refresh', 'data': case_details})
    result = result_queue.get()
    if result['status'] == 'success':
        return render_template('step2.html', time=time)
    else:
        return render_template('error.html', error=result['error']), 500

@app.route('/captcha.png')
def captcha_image_route():
    with open(CAPTCHA_IMAGE_FILENAME, "rb") as f:
        return send_file(io.BytesIO(f.read()), mimetype='image/png')

@app.route('/submit', methods=['POST'])
def submit():
    solution = request.form['solution']
    job_queue.put({'action': 'submit', 'data': solution})
    result = result_queue.get()
    if result['status'] == 'success':
        return render_template('success.html', data=result['data'])
    else:
        return render_template('error.html', error=result['error'])

# --- Main Playwright Task Runner ---
def run_playwright_tasks():
    global page
    current_case_details = {}
    URL = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3"

    while True:
        try:
            job = job_queue.get()
            action = job.get('action')
            data = job.get('data')
            
            if action == 'fill_and_refresh':
                print("\nPlaywright: Starting a new search. Resetting to the main search page...")
                page.goto(URL, wait_until="domcontentloaded")
                print("Main search page reloaded.")
                
                current_case_details = data
                print(f"Playwright: Received job 'fill_and_refresh' for {data}")
                page.select_option('select#case_type', value=data['case_type'])
                page.locator('input#search_case_no').type(data['case_number'], delay=100)
                page.locator('input#rgyear').type(data['case_year'], delay=100)
                
                print("Bringing browser to front to ensure CAPTCHA is rendered...")
                page.bring_to_front()
                page.wait_for_timeout(500)
                
                page.click("a[title='Refresh Image']")
                page.wait_for_timeout(1500)
                captcha_element = page.locator("//img[@id='captcha_image' or @id='cap']")
                captcha_element.screenshot(path=CAPTCHA_IMAGE_FILENAME)
                result_queue.put({'status': 'success'})
            
            elif action == 'submit':
                print(f"Playwright: Received job 'submit' with solution '{data}'")
                page.locator('input#captcha').type(data, delay=100)
                page.click("input[name='submit1']")
                
                print("Waiting for response...")

                # --- START OF THE SIMPLIFIED ERROR HANDLING FIX ---
                try:
                    # We only try the "happy path" - wait for the 'View' link to appear.
                    view_link = page.locator("a[onclick*='viewHistory']")
                    view_link.wait_for(state="visible", timeout=10000)
                    
                    # If the line above does not time out, we have a success.
                    print("Success: 'View' link found.")
                    view_link.click(force=True)
                    page.wait_for_load_state('networkidle', timeout=10000)
                    
                    html_content = page.content()
                    scraped_data = parse_case_details(html_content)
                    scraped_data.update(current_case_details)
                    scraped_data['raw_html'] = html_content
                    save_case_data(scraped_data)
                    result_queue.put({'status': 'success', 'data': scraped_data})

                except Exception as e:
                    # If waiting for the 'View' link timed out, it's a failure.
                    # We will now send a single, clear error message back to the user.
                    print(f"Did not find 'View' link. Assuming submission failed. (Debug: {e})")
                    error_text = "Submission Failed. This is likely due to an incorrect CAPTCHA or invalid case details. Please try again."
                    result_queue.put({'status': 'failure', 'error': error_text})
                    # The page usually reloads on a failed submission, so a manual reload is often not needed here.

        except Exception as e:
            print(f"Error in Playwright task runner: {e}")
            result_queue.put({'status': 'failure', 'error': str(e)})

# --- Main Application Runner ---
def main_app():
    global page
    URL = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded")
        
        print("Starting Flask server in a separate thread...")
        flask_thread = threading.Thread(target=lambda: app.run(port=5000, debug=False, use_reloader=False))
        flask_thread.daemon = True
        flask_thread.start()

        print("Playwright task runner is waiting for jobs from Flask...")
        print(">>> Open http://127.0.0.1:5000 in your browser to begin. <<<")
        run_playwright_tasks()
        
        print("Closing Playwright browser.")
        browser.close()

if __name__ == "__main__":
    init_db()
    main_app()