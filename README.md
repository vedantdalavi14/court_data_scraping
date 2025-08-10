# Karnataka High Court Case Scraper

This project contains a robust, containerized Python application to programmatically scrape case data from the official Karnataka High Court e-Courts website. It leverages the Playwright automation framework to navigate a highly dynamic, security-hardened website, uses Flask to provide a simple web-based UI, and employs BeautifulSoup for precise HTML parsing. All scraped data is archived in a local SQLite database.

## Features

- **Containerized Application**: A Dockerfile is included for easy, one-command setup and deployment.
- **Simple Web Interface**: Built with Flask to meet the project's UI/UX requirements.
- **Multiple Order Extraction**: Scrapes all available orders/judgments for a case, not just the most recent one.
- **Advanced Bot Detection Evasion**: Utilizes Playwright to navigate a site that blocks standard automation tools.
- **Intelligent CAPTCHA Handling**: Implements a multi-step process to bypass the website's "trap CAPTCHA" mechanism.
- **Human-like Behavior**: Simulates human typing speed to avoid behavioral detection.
- **Robust Multi-threaded Architecture**: Uses a thread-safe queue system to allow the Flask web server and the Playwright browser to communicate without conflicts.
- **Structured Data Storage**: Stores both cleanly parsed data and the raw source HTML in an SQLite database.

## Court Chosen

The scraper is specifically configured to work with the **High Court of Karnataka - Principal Bench at Bengaluru**. The target URL is:
`https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?court_code=1&dist_cd=1&stateNm=Karnataka&state_cd=3`

## Tech Stack

- **Language**: Python 3
- **Containerization**: Docker
- **Web Framework**: Flask
- **Browser Automation**: Playwright
- **HTML Parsing**: BeautifulSoup4
- **Database**: SQLite 3

## Setup and Usage

There are two methods to run this application. The Docker method is recommended for a quick and easy start.

### Method 1: Running with Docker (Recommended)

This method allows you to run the application without installing Python or any dependencies on your local machine.

#### Prerequisite

You must have Docker Desktop installed and running.

#### Build the Docker Image

Open your terminal in the main project folder (where the Dockerfile is located).

Run the following command to build the image. This will take a few minutes the first time.

```bash
docker build -t court-scraper .
```

#### Run the Docker Container

Once the image is built, run the application inside a container with this command:

```bash
docker run -p 5000:5000 --rm court-scraper
```

#### Access the Application

The application is now running. Open your web browser and navigate to:
`http://127.0.0.1:5000`

### Method 2: Running Manually (For Development)

#### Prerequisites

- Python 3.8 or newer.

#### Install Python Dependencies

All required Python libraries are listed in the `requirements.txt` file. Install them all with a single command:

```bash
pip install -r requirements.txt
```

#### Install Playwright Browsers

Playwright requires its own browser binaries. Run the following command in your terminal:

```bash
playwright install
```

#### Run the Scraper

Execute the main script from your terminal:

```bash
python main.py
```

Open your web browser and navigate to `http://127.0.0.1:5000`.

## CAPTCHA & Bot Detection Strategy

The e-Courts website is protected by a multi-layered, state-of-the-art anti-bot system. A sophisticated, phased strategy was engineered to ensure reliable automation.

- **Browser Fingerprinting Evasion**: Initial attempts using Selenium failed, as the website's security was able to identify the browser environment as automated. The solution was to migrate to Playwright, a more modern framework that successfully bypassed this initial check.
- **Behavioral Analysis Evasion**: The website was also found to detect impossibly fast form interactions. To counter this, the script was updated to simulate human-like typing, using `page.type()` with small, randomized delays.
- **Solving the "Trap CAPTCHA"**: We discovered the site uses a "trap" mechanism: the first CAPTCHA presented after filling the form is designed to be invalid. Our script automates a bypass by programmatically clicking the "Refresh Image" button after filling the case details, ensuring the CAPTCHA presented to the user is always the second, "real" one.
- **Handling Architectural Complexity**: The requirement for a Flask web UI introduced a critical threading conflict. This was solved by implementing a professional producer-consumer pattern using Python's thread-safe `queue` module to allow the Flask and Playwright threads to communicate safely.
- **Navigating Dynamic Content**: The search results are not on a new page but are loaded dynamically via AJAX. The script handles this by waiting for specific result elements to become visible, rather than relying on simple page navigation events.

This comprehensive, human-in-the-loop approach allows the script to function reliably against a very challenging target.

## Configuration

This script does not use `.env` files or environment variables. All inputs are collected interactively through the web user interface during runtime.

## Acknowledgements & Development Tools

- **Editor**: Visual Studio Code with Github Copilot
- **AI Assistance**: Development of this script was assisted by AI tools, including Google's Gemini and OpenAI's ChatGPT, for tasks such as code generation, debugging complex errors, architectural recommendations, and documentation refinement.

## License

This project is licensed under the MIT License.
