## Notes
- Website uses advanced bot detection (timing, typing, automation checks).
- Using undetected-chromedriver to bypass detection.
- Explicit waits and human-like delays added for robustness.
- CAPTCHA is typed character-by-character to mimic human input.
- Functional requirements received: UI form, backend automation, SQLite logging, HTML display, error handling.
- Current step: after clicking the "View" button, extract and store case details.

## Task List
- [x] Automate form filling (case type, number, year).
- [x] Handle CAPTCHA with simulated typing.
- [x] Submit the form and verify success.
- [x] Automate clicking the "View" button for the case result.
- [ ] Extract/download case details after clicking "View".
- [ ] Store query, raw response, and parsed data in SQLite.
- [ ] Display parsed details in UI and allow PDF download.
- [ ] Implement user-friendly error handling.

## Current Goal
Extract and store case details after clicking "View"