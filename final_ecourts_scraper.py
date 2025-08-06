## FINAL ASSIGNMENT SCRIPT: Flask UI + Playwright Backend (Multi-Threaded Queue Architecture) ##

import time
import os
import io
import threading
import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, render_template_string, redirect, url_for
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page
import queue # Used for safe communication between threads

# --- Global Variables ---
page: Page = None
CAPTCHA_IMAGE_FILENAME = "captcha.png"

# Thread-safe queues for communication between Flask and Playwright threads
job_queue = queue.Queue()
result_queue = queue.Queue()

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

# --- Flask App Setup ---
app = Flask(__name__)

# --- HTML Templates ---
HTML_STYLE = """
<style>
    body { font-family: sans-serif; margin: 2em; background-color: #f4f4f4; text-align: center; }
    h1, h2 { color: #333; }
    ul { list-style-type: none; padding: 0; } li { margin-bottom: 0.5em; }
    .container { background-color: white; padding: 2em; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); max-width: 600px; margin: auto; text-align: left; }
    .error { color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 3px; margin: 1em 0; }
    img { border: 1px solid #ddd; margin-top: 1em; max-width: 200px; display: block; margin-left: auto; margin-right: auto; }
    form div { margin-bottom: 1em; } label { display: block; margin-bottom: 5px; font-weight: bold; }
    input, select { width: 100%; padding: 8px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 3px; }
    button { background-color: #4CAF50; color: white; padding: 12px 15px; border: none; border-radius: 3px; cursor: pointer; width: 100%; font-size: 16px; }
    button:hover { background-color: #45a049; }
</style>
"""

STEP_1_TEMPLATE = f"""
<!doctype html><html><head><title>Step 1: Enter Case Details</title>{HTML_STYLE}</head>
<body><div class="container"><h1>e-Courts Case Scraper</h1>
<form action="/get_captcha" method="post">
    <div><label for="case_type">Case Type:</label><select id="case_type" name="case_type">
        <option value="144">WP - Writ Petition(144)</option>
        </select></div>
    <div><label for="case_number">Case Number:</label><input type="text" id="case_number" name="case_number" required></div>
    <div><label for="case_year">Case Year:</label><input type="text" id="case_year" name="case_year" required></div>
    <button type="submit">Get CAPTCHA</button>
</form></div></body></html>
"""

STEP_2_TEMPLATE = f"""
<!doctype html><html><head><title>Step 2: Solve CAPTCHA</title>{HTML_STYLE}</head>
<body><div class="container"><h1>Step 2: Solve CAPTCHA</h1>
<p style="text-align:center;">Case details have been filled. Please solve the fresh CAPTCHA below.</p>
<img src="/captcha.png?t={{{{ time.time() }}}}" alt="CAPTCHA Image">
<form action="/submit" method="post">
    <div><label for="solution">CAPTCHA Solution:</label><input type="text" id="solution" name="solution" required autocomplete="off" autofocus></div>
    <button type="submit">Submit Case</button>
</form></div></body></html>
"""

SUCCESS_TEMPLATE = f"""
<!doctype html><html><head><title>Success!</title>{HTML_STYLE}</head>
<body><div class="container"><h1>Scraping Successful!</h1>
<h2>Parsed Details:</h2>
<ul>
    <li><b>Case Type/No/Year:</b> {{{{ data.get('case_type') }}}}/{'{{ data.get("case_number") }}'}/{'{{ data.get("case_year") }}'}</li>
    <li><b>Parties:</b> {{{{ data.get('petitioner_name') }}}} vs. {{{{ data.get('respondent_name') }}}}</li>
    <li><b>Filing Date:</b> {{{{ data.get('filing_date') }}}}</li>
    <li><b>Case Status:</b> {{{{ data.get('case_status') }}}}</li>
    <li><b>Next Hearing Date:</b> {{{{ data.get('next_hearing_date') }}}}</li>
    <li><b>Most Recent Order:</b> <a href="{{{{ data.get('most_recent_order_pdf_url') }}}}" target="_blank">Click to Download PDF</a></li>
</ul>
<p>Data has been saved to the database.</p>
<a href="/"><button style="background-color:#007BFF;">Scrape Another Case</button></a>
</div></body></html>
"""

ERROR_TEMPLATE = f"""
<!doctype html><html><head><title>Error</title>{HTML_STYLE}</head>
<body><div class="container"><h1>An Error Occurred</h1>
<p class="error">Error Message: {{{{ error }}}}</p>
<a href="/"><button>Try Again</button></a>
</div></body></html>
"""


# --- Flask Routes (Using Queues for Thread Safety) ---
@app.route('/')
def index():
    return render_template_string(STEP_1_TEMPLATE)

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
        return render_template_string(STEP_2_TEMPLATE, time=time)
    else:
        return render_template_string(ERROR_TEMPLATE, error=result['error']), 500

@app.route('/captcha.png')
def captcha_image_route():
    # Use an in-memory buffer to avoid file access conflicts
    with open(CAPTCHA_IMAGE_FILENAME, "rb") as f:
        return send_file(io.BytesIO(f.read()), mimetype='image/png')

@app.route('/submit', methods=['POST'])
def submit():
    solution = request.form['solution']
    job_queue.put({'action': 'submit', 'data': solution})
    result = result_queue.get()

    if result['status'] == 'success':
        return render_template_string(SUCCESS_TEMPLATE, data=result['data'])
    else:
        return render_template_string(ERROR_TEMPLATE, error=result['error'])

# --- Main Playwright Task Runner (Runs in the Main Thread) ---
def run_playwright_tasks():
    global page
    current_case_details = {}

    while True:
        try:
            job = job_queue.get()
            action = job.get('action')
            data = job.get('data')
            
            if action == 'fill_and_refresh':
                current_case_details = data
                print(f"Playwright: Received job 'fill_and_refresh' for {data}")
                page.select_option('select#case_type', value=data['case_type'])
                page.locator('input#search_case_no').type(data['case_number'], delay=100)
                page.locator('input#rgyear').type(data['case_year'], delay=100)
                page.click("a[title='Refresh Image']")
                page.wait_for_timeout(1500)
                captcha_element = page.locator("//img[@id='captcha_image' or @id='cap']")
                captcha_element.screenshot(path=CAPTCHA_IMAGE_FILENAME)
                result_queue.put({'status': 'success'})
            
            elif action == 'submit':
                print(f"Playwright: Received job 'submit' with solution '{data}'")
                page.locator('input#captcha').type(data, delay=100)
                page.click("input[name='submit1']")
                
                # --- START OF THE AJAX FIX ---
                print("Waiting for AJAX results to appear on the main page...")
                try:
                    # We wait directly for the View link on the main page.
                    view_link = page.locator("a[onclick*='viewHistory']")
                    view_link.wait_for(state="visible", timeout=20000)
                    
                    print("\nSUCCESS! Case found. Clicking 'View' to get details...")
                    view_link.click(force=True)
                    
                    page.wait_for_load_state('networkidle', timeout=20000)
                    
                    print("Details page loaded. Parsing data...")
                    html_content = page.content()
                    scraped_data = parse_case_details(html_content)
                    scraped_data.update(current_case_details)
                    scraped_data['raw_html'] = html_content
                    save_case_data(scraped_data)
                    result_queue.put({'status': 'success', 'data': scraped_data})

                except Exception as e:
                    print(f"Did not find 'View' link. Checking for an error message... Debug Error: {e}")
                    error_input = page.locator("input#txtmsg")
                    error_text = "CAPTCHA failed or case not found."
                    if error_input.is_visible(timeout=3000):
                        error_text = error_input.get_attribute('value')
                    result_queue.put({'status': 'failure', 'error': error_text})
                    page.reload()
                # --- END OF THE AJAX FIX ---

        except Exception as e:
            print(f"Error in Playwright task runner: {e}")
            result_queue.put({'status': 'failure', 'error': str(e)})

# --- Main Application Runner ---
def main_app():
    global page
    URL = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
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
    # You must copy your full function definitions for the ones marked pass
    # before running this script.
    main_app()