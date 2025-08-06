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
import queue 

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
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap');
    
    body {
        font-family: 'Poppins', sans-serif;
        background-color: #f8f9fa;
        color: #343a40;
        margin: 0;
        padding: 2em;
        display: flex;
        justify-content: center;
        align-items: flex-start;
        min-height: 100vh;
    }
    .container {
        background-color: #ffffff;
        padding: 2.5em;
        border-radius: 12px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
        width: 100%;
        max-width: 550px;
    }
    h1 {
        color: #0d6efd;
        margin-top: 0;
        margin-bottom: 0.5em;
        font-weight: 600;
        text-align: center;
    }
    h2 {
        color: #343a40;
        margin-top: 1.5em;
        border-bottom: 1px solid #dee2e6;
        padding-bottom: 0.5em;
        font-size: 1.2em;
        text-align: left;
    }
    p.subtitle {
        color: #6c757d;
        margin-bottom: 2em;
        text-align: center;
        font-size: 1.1em;
    }
    ul.results-list {
        list-style-type: none;
        padding: 0;
        text-align: left;
    }
    ul.results-list li {
        padding: 0.8em 0;
        border-bottom: 1px solid #f1f3f5;
    }
    ul.results-list li:last-child {
        border-bottom: none;
    }
    ul.results-list b {
        color: #0d6efd;
        display: block;
        font-size: 0.9em;
        margin-bottom: 0.2em;
    }
    .error-box {
        color: #842029;
        background-color: #f8d7da;
        border: 1px solid #f5c2c7;
        padding: 1em 1.5em;
        border-radius: 8px;
        margin: 1em 0;
    }
    img {
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 0.5em;
        margin-top: 1em;
        margin-bottom: 1.5em;
        max-width: 200px;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    form div {
        margin-bottom: 1.2em;
    }
    label {
        display: block;
        margin-bottom: 0.5em;
        font-weight: 600;
        color: #495057;
    }
    input, select {
        width: 100%;
        padding: 0.8em;
        box-sizing: border-box;
        border: 1px solid #ced4da;
        border-radius: 6px;
        font-family: 'Poppins', sans-serif;
        font-size: 1em;
    }
    input:focus, select:focus {
        outline: none;
        border-color: #86b7fe;
        box-shadow: 0 0 0 0.25rem rgba(13, 110, 253, 0.25);
    }
    button {
        background-color: #0d6efd;
        color: white;
        padding: 0.9em 1.5em;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        width: 100%;
        font-size: 1.1em;
        font-weight: 600;
        transition: background-color 0.2s ease-in-out;
    }
    button:hover {
        background-color: #0b5ed7;
    }
    a.button-link {
        text-decoration: none;
        display: block;
        margin-top: 1em;
    }
    .pdf-link {
        color: #fff;
        background-color: #198754;
        padding: 0.4em 0.8em;
        border-radius: 5px;
        text-decoration: none;
        font-size: 0.9em;
        transition: background-color 0.2s ease;
    }
    .pdf-link:hover {
        background-color: #157347;
    }
</style>
"""

STEP_1_TEMPLATE = f"""
<!doctype html><html><head><title>Step 1: Enter Case Details</title>{HTML_STYLE}</head>
<body><div class="container">
    <h1>e-Courts Case Scraper</h1>
    <p class="subtitle">Step 1: Enter Case Details</p>
    <form action="/get_captcha" method="post">
        <div><label for="case_type">Case Type:</label><select id="case_type" name="case_type">
            <option value="0">Select Case Type</option>
            <option value="156">AC - Arbitration Case(156)</option>
            <option value="170">AP.EFA - Arbitration Petition(Enforcement of Foreign Arbitral Award)(170)</option>
            <option value="168">AP.IM - Arbitration Petition-Interim Measure(168)</option>
            <option value="101">CA - Company Application(101)</option>
            <option value="143">CCC - Civil Contempt Petition(143)</option>
            <option value="169">CC(CIA) - Criminal Complaint (Commissions of Inquiry Act)(169)</option>
            <option value="104">CEA - Central Excise Appeal(104)</option>
            <option value="105">CMP - CIVIL MISC. PETITION(105)</option>
            <option value="155">COA - U/s 10(f) of the Companies Act(155)</option>
            <option value="171">COMAP - Commercial Appeals(171)</option>
            <option value="176">COMAP.CR - Commercial Appeals Cross Objection(176)</option>
            <option value="173">COM.APLN - Commercial Application(173)</option>
            <option value="178">COM.OS(178)</option>
            <option value="103">COMPA - Company Appeal(103)</option>
            <option value="177">COM.S - Commercial Suit(177)</option>
            <option value="102">COP - Company Petition(102)</option>
            <option value="106">CP - Civil Petition(106)</option>
            <option value="159">CP.KLRA - CP On Karnataka Land Reforms Act(159)</option>
            <option value="160">CRA - CROSS APPEALS(160)</option>
            <option value="107">CRC - Civil Referred Case(107)</option>
            <option value="110">CRL.A - Criminal Appeal(110)</option>
            <option value="111">CRL.CCC - Criminal Contempt Petition(111)</option>
            <option value="112">CRL.P - Criminal Petition(112)</option>
            <option value="113">CRL.RC - Criminal Referred Case(113)</option>
            <option value="114">CRL.RP - Criminal Revision Petition(114)</option>
            <option value="161">CROB - Cross Objection(161)</option>
            <option value="108">CRP - Civil Revision Petition(108)</option>
            <option value="115">CSTA - Customs Appeal(115)</option>
            <option value="116">EP - Election Petition(116)</option>
            <option value="117">EX.FA - EXECUTION FIRST APPEAL(117)</option>
            <option value="118">EX.SA - EXECUTION SECOND APPEAL(118)</option>
            <option value="148">GTA - Gift Tax Appeal(148)</option>
            <option value="119">HRRP - House Rent Rev. Petition(119)</option>
            <option value="120">ITA - Income Tax Appeal(120)</option>
            <option value="162">ITA.CROB - I.T Appeal CROSS Objection(162)</option>
            <option value="121">ITRC - Income-tax referred case(121)</option>
            <option value="122">LRRP - Land Reforms Revision Petition(122)</option>
            <option value="123">LTRP - LUXURY TAX REVISION PETN.(123)</option>
            <option value="124">MFA - Miscellaneous First Appeal(124)</option>
            <option value="125">MFA.CROB - MFA Cross Objection(125)</option>
            <option value="164">MISC.CRL - Miscellaneous Case for Crml(164)</option>
            <option value="165">MISC.CVL - Miscellaneous Case for Civil(165)</option>
            <option value="166">MISC.P - Misc Petition(166)</option>
            <option value="167">MISC.W - Miscellaneous Case for Writ(167)</option>
            <option value="126">MSA - Miscellaneous Second Appeal(126)</option>
            <option value="127">MSA.CROB - MSA Cross Objection(127)</option>
            <option value="128">OLR - Official Liquidator Report(128)</option>
            <option value="154">OS - Original Suit(154)</option>
            <option value="129">OSA - Original Side Appeal(129)</option>
            <option value="130">OSA.CROB - OSA Cross Objection(130)</option>
            <option value="131">PROB.CP - Probate Civil Petition(131)</option>
            <option value="153">RA - Regular Appeal(153)</option>
            <option value="172">RERA.A - RERA APPEALS(172)</option>
            <option value="179">RERA.CRB - RERA Appeals cross-objection(179)</option>
            <option value="132">RFA - Regular First Appeal(132)</option>
            <option value="133">RFA.CROB - RFA Cross Objection(133)</option>
            <option value="134">RP - Review Petition(134)</option>
            <option value="135">RPFC - Rev.Pet Family Court(135)</option>
            <option value="136">RSA - Regular Second Appeal(136)</option>
            <option value="137">RSA.CROB - RSA Cross Objection(137)</option>
            <option value="152">SCLAP - SUPREME COURT LEAVE APPLICATION(152)</option>
            <option value="138">STA - Sales Tax Appeal(138)</option>
            <option value="139">STRP - Sales Tax Revision Petition(139)</option>
            <option value="151">TAET - Tax Appeal on Entry Tax(151)</option>
            <option value="141">TOS - Testamentory Original Suit(141)</option>
            <option value="142">TRC - Tax referred cases(142)</option>
            <option value="145">WA - Writ Appeal(145)</option>
            <option value="147">WA.CROB - WA Cross Objection(147)</option>
            <option value="144">WP - Writ Petition(144)</option>
            <option value="150">WPCP - Civil Pet in Writ Side(150)</option>
            <option value="146">WPHC - Habeas Corpus(146)</option>
            <option value="149">WTA - Wealth Tax Appeal(149)</option>
        </select></div>
        <div><label for="case_number">Case Number:</label><input type="text" id="case_number" name="case_number" required></div>
        <div><label for="case_year">Case Year:</label><input type="text" id="case_year" name="case_year" required></div>
        <button type="submit">Get CAPTCHA</button>
    </form>
</div></body></html>
"""

STEP_2_TEMPLATE = f"""
<!doctype html><html><head><title>Step 2: Solve CAPTCHA</title>{HTML_STYLE}</head>
<body><div class="container">
    <h1>e-Courts Case Scraper</h1>
    <p class="subtitle">Step 2: Solve the Fresh CAPTCHA</p>
    <img src="/captcha.png?t={{{{ time.time() }}}}" alt="CAPTCHA Image">
    <form action="/submit" method="post">
        <div><label for="solution">CAPTCHA Solution:</label><input type="text" id="solution" name="solution" required autocomplete="off" autofocus></div>
        <button type="submit">Submit Case</button>
    </form>
</div></body></html>
"""

SUCCESS_TEMPLATE = f"""
<!doctype html><html><head><title>Success!</title>{HTML_STYLE}</head>
<body><div class="container">
    <h1>Scraping Successful!</h1>
    <p class="subtitle">The following details were found and saved to the database.</p>
    <h2>Parsed Details</h2>
    <ul class="results-list">
        <li><b>Case Type/No/Year:</b> {{{{ data.get('case_type') }}}}/{'{{ data.get("case_number") }}'}/{'{{ data.get("case_year") }}'}</li>
        <li><b>Parties:</b> {{{{ data.get('petitioner_name') }}}} vs. {{{{ data.get('respondent_name') }}}}</li>
        <li><b>Filing Date:</b> {{{{ data.get('filing_date') }}}}</li>
        <li><b>Case Status:</b> {{{{ data.get('case_status') }}}}</li>
        <li><b>Next Hearing Date:</b> {{{{ data.get('next_hearing_date') }}}}</li>
        <li><b>Most Recent Order:</b> <a href="{{{{ data.get('most_recent_order_pdf_url') }}}}" class="pdf-link" target="_blank">Download PDF</a></li>
    </ul>
    <a href="/" class="button-link"><button style="background-color:#007BFF; margin-top: 1.5em;">Scrape Another Case</button></a>
</div></body></html>
"""

ERROR_TEMPLATE = f"""
<!doctype html><html><head><title>Error</title>{HTML_STYLE}</head>
<body><div class="container">
    <h1>An Error Occurred</h1>
    <div class="error-box">
        <strong>Error Message:</strong><br>
        {{{{ error }}}}
    </div>
    <a href="/" class="button-link"><button>Try Again</button></a>
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
    
    # Define the URL here so we can reuse it for resetting
    URL = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3"

    while True:
        try:
            job = job_queue.get()
            action = job.get('action')
            data = job.get('data')
            
            if action == 'fill_and_refresh':
                
                # --- START OF "SCRAPE ANOTHER CASE" FIX ---
                # At the beginning of every new search, navigate back to the main search page.
                print("\nPlaywright: Starting a new search. Resetting to the main search page...")
                page.goto(URL, wait_until="domcontentloaded")
                print("Main search page reloaded.")
                # --- END OF "SCRAPE ANOTHER CASE" FIX ---

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
                try:
                    # First, we try the "happy path" - wait only for the 'View' link.
                    view_link = page.locator("a[onclick*='viewHistory']")
                    view_link.wait_for(state="visible", timeout=20000)
                    
                    # If the line above does not fail, it means we have a success.
                    print("Success: 'View' link found.")
                    view_link.click(force=True)
                    page.wait_for_load_state('networkidle', timeout=20000)
                    
                    html_content = page.content()
                    scraped_data = parse_case_details(html_content)
                    scraped_data.update(current_case_details)
                    scraped_data['raw_html'] = html_content
                    save_case_data(scraped_data)
                    result_queue.put({'status': 'success', 'data': scraped_data})

                except Exception:
                    # If waiting for the 'View' link timed out, we know it's a failure.
                    # Now we can safely and patiently wait for the error message.
                    print("Did not find 'View' link. Checking for a specific error message...")
                    try:
                        error_input = page.locator("input#txtmsg")
                        
                        # This is the key: Wait for the input to have a value that is NOT an empty string.
                        expect(error_input).not_to_have_attribute("value", "", timeout=5000)
                        
                        error_text = error_input.get_attribute('value')
                        print(f"Failure: Error message found on page: '{error_text}'")
                        result_queue.put({'status': 'failure', 'error': error_text})
                        page.reload()
                    except Exception as inner_e:
                        # If we failed to find a populated error message, it's an unknown state.
                        print(f"Error: Neither 'View' link nor a populated error message was found. {inner_e}")
                        result_queue.put({'status': 'failure', 'error': 'The website returned an unknown response. Please try again.'})
                        page.reload()

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
    main_app()
    