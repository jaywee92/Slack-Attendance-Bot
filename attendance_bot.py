from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import time
import os

# Slack workspace and channel identifiers
TEAM_ID = "TNS9HAY6M"
CHANNEL_ID = "C09BXD87H54"

# Where the Slack session is stored
SESSION_FILE = "slack_auth.json"

# Load credentials from .env file
load_dotenv()
EMAIL = os.getenv("SLACK_EMAIL")
PASSWORD = os.getenv("SLACK_PASSWORD")


def login_and_save_session():
    # Log into Slack and store session cookies locally
    print("🔐 No session found - logging into Slack")

    with sync_playwright() as p:
        # Launch a visible browser so login works reliably
        browser = p.chromium.launch(headless=False)

        # Create a fresh browser context (clean session)
        context = browser.new_context()
        page = context.new_page()

        # Open Slack login page
        page.goto("https://wbscodingschool.slack.com/sign_in_with_password")

        # Fill in email and password from .env
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)

        # Click the login button
        page.wait_for_selector('button[type="submit"]', state="visible")
        page.click('[data-qa="signin_button"]')

        # Force Slack Web Client after login
        page.wait_for_load_state("domcontentloaded")
        page.goto("https://app.slack.com/client")

        # Give Slack time to fully load and set auth cookies
        time.sleep(20)

        # Save session cookies and storage for later reuse
        context.storage_state(path=SESSION_FILE)
        print("✅ Slack session saved")

        browser.close()


def is_session_valid():
    # Check if session file exists and is not empty
    if not os.path.exists(SESSION_FILE):
        return False
    if os.path.getsize(SESSION_FILE) == 0:
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            # Load the stored session
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()

            # Open Slack client to verify login
            page.goto("https://app.slack.com/client")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)

            # If Slack redirects to login, session is invalid
            if "signin" in page.url or "sign_in" in page.url:
                return False

            # If login form appears, session is invalid
            login_fields = page.locator('input[type="email"], input[type="password"]')
            if login_fields.count() > 0:
                return False

            return True
        except Exception as exc:
            # Any error -> treat as invalid session
            print(f"WARN: Session validation failed, will re-login: {exc}")
            return False
        finally:
            browser.close()


def mark_present():
    # Open the channel and click the newest "present" radio button
    print("🟢 Marking attendance as PRESENT")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Use stored session so no login is needed
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        # Open the Slack channel where the attendance form exists
        page.goto(f"https://app.slack.com/client/{TEAM_ID}/{CHANNEL_ID}")

        # Slack can be slow to load
        time.sleep(20)

        # Find all "present" radio buttons
        present_radios = page.locator('input[type="radio"][id$="-present-0"]')

        # If none are found, stop
        count = present_radios.count()
        if count == 0:
            print("❌ No present buttons found")
            browser.close()
            return

        # Click the newest "present" option
        newest_present = present_radios.nth(count - 1)
        newest_present.scroll_into_view_if_needed()
        newest_present.check()

        print("✅ Attendance successfully marked")

        # Small delay to ensure the click is registered
        time.sleep(3)
        browser.close()


def ensure_session():
    # Reuse valid session if possible, otherwise login again
    if is_session_valid():
        print("🔑 Existing Slack session found")
        return False

    login_and_save_session()
    return True


def run_once():
    # Single run: ensure session exists, then mark attendance
    print("⏰ Attendance run started")
    ensure_session()
    mark_present()


if __name__ == "__main__":
    # Run once and exit (no scheduler / no infinite loop)
    run_once()
