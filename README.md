# Karnataka High Court Case Scraper

This project contains a robust Python script to programmatically scrape case data from the official Karnataka High Court e-Courts website. It leverages the Playwright automation framework to navigate a highly dynamic, security-hardened website, uses Flask to provide a simple web-based UI, and employs BeautifulSoup for precise HTML parsing. All scraped data is archived in a local SQLite database.

## Features

- **Simple Web Interface**: Built with Flask to meet the project's UI/UX requirements.
- **Advanced Bot Detection Evasion**: Utilizes Playwright to navigate a site that blocks standard automation tools.
- **Intelligent CAPTCHA Handling**: Implements a multi-step process to bypass the website's "trap CAPTCHA" mechanism.
- **Human-like Behavior**: Simulates human typing speed to avoid behavioral detection.
- **Robust Multi-threaded Architecture**: Uses a thread-safe queue system to allow the Flask web server and the Playwright browser to communicate without conflicts.
- **Dynamic Content Handling**: Successfully interacts with page content that is loaded dynamically via JavaScript (AJAX).
- **Structured Data Storage**: Stores both cleanly parsed data and the raw source HTML in an SQLite database.

## Court Chosen

The scraper is specifically configured to work with the **High Court of Karnataka - Principal Bench at Bengaluru**. The target URL is:
`https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3`

## Tech Stack

- **Language**: Python 3
- **Web Framework**: Flask
- **Browser Automation**: Playwright
- **HTML Parsing**: BeautifulSoup4
- **Database**: SQLite 3

## Setup and Installation

Follow these steps to set up your environment and run the scraper.

### Prerequisites

- Python 3.8 or newer.

### Clone the Repository

```bash
git clone <https://github.com/vedantdalavi14/court_data_scraping>
cd court_data_scraping
```

### Install Python Dependencies

The script requires several Python libraries. Install them using `pip`:

```bash
pip install playwright flask beautifulsoup4 lxml requests
```

### Install Playwright Browsers

Playwright requires its own browser binaries. Run the following command in your terminal to download them:

```bash
playwright install
```

### Database Initialization

The database (`cases.db`) and its table structure are created automatically by the `init_db()` function when the script is first run.

## How to Run the Scraper

The script runs a local web server that provides a simple user interface for entering data.

1.  Execute the main script from your terminal. This will start both the Playwright browser in the background and the local web server.

    ```bash
    python main.py
    ```

2.  You will see messages in your terminal indicating that the server is running on `http://127.0.0.1:5000`.

3.  Open your web browser (like Chrome, Firefox, etc.) and navigate to the following address:

    `http://127.0.0.1:5000`

4.  You will see **Step 1** of the web form. Enter the Case Type, Number, and Year, and click "Get CAPTCHA".

5.  The page will refresh to **Step 2**, showing you the fresh CAPTCHA image.

6.  Enter the characters from the CAPTCHA image into the solution box and click "Submit Case".

7.  The result (either a success page with the scraped data or an error page) will be displayed in your web browser.

## CAPTCHA & Bot Detection Strategy

The e-Courts website is protected by a multi-layered, state-of-the-art anti-bot system. A sophisticated, phased strategy was engineered to ensure reliable automation while meeting the project's web UI requirement.

- **Browser Fingerprinting Evasion**: Initial attempts using Selenium and `undetected-chromedriver` failed, as the website's security was able to identify the browser environment as automated. The solution was to migrate to Playwright, a more modern framework that successfully bypassed this initial check.

- **Behavioral Analysis Evasion**: The website was also found to detect impossibly fast form interactions. To counter this, the script was updated to simulate human-like typing, using `page.type()` with small, randomized delays between keystrokes.

- **Solving the "Trap CAPTCHA"**: We discovered the site uses a "trap" mechanism: the first CAPTCHA presented after filling the form is designed to be invalid. Our script automates a bypass by programmatically clicking the "Refresh Image" button after filling the case details, ensuring the CAPTCHA presented to the user is always the second, "real" one.

- **Handling Architectural Complexity**: The requirement for a Flask web UI introduced a critical threading conflict, as the web server and the synchronous Playwright API cannot safely interact directly. This was solved by implementing a professional producer-consumer pattern using Python's thread-safe `queue` module. The Flask thread acts as a producer, adding jobs to a queue, while the main Playwright thread acts as a consumer, safely executing the browser commands.

- **Navigating Dynamic Content**: The search results are not on a new page but are loaded dynamically via AJAX. The script handles this by waiting for specific result elements to become visible, rather than relying on simple page navigation events.

This comprehensive, human-in-the-loop approach allows the script to function reliably against a very challenging target.

## Configuration

This script does not use `.env` files or environment variables. All inputs are collected interactively through the web user interface during runtime.

## Acknowledgements & Development Tools

- **Editor**: Visual Studio Code with github copilot
- **AI Assistance**: Development of this script was assisted by AI tools, including Google's Gemini and OpenAI's ChatGPT, for tasks such as code generation, debugging complex errors, architectural recommendations, and documentation refinement.

## License

This project is licensed under the MIT License.
